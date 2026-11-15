"""Tool Execution Manager for the EarthMind Phase 3 Backend Tool Infrastructure.

Responsibilities:
- Enforce execution timeouts.
- Controlled, bounded retries for transient failures (never for non-idempotent tools).
- Per-tool concurrency limits.
- Per-tool rate-limit handling.
- Cooperative cancellation where supported.
- Execution status tracking.
- Structured error reporting.

The manager does not orchestrate workflows: B5 retains orchestration
responsibility. It only executes a single, already-validated tool call.
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import random
import threading
import time
from typing import Callable, Dict, Optional, Tuple

from core.errors.exceptions import (
    EarthMindException,
    ToolCancelledError,
    ToolConcurrencyLimitError,
    ToolExecutionError,
    ToolRateLimitError,
    ToolTimeoutError,
    ToolUnavailableError,
)
from core.logging.logger import get_logger
from core.schemas.tools import (
    ToolCallRecord,
    ToolCallRequest,
    ToolCallStatus,
    ToolDefinition,
    ToolExecutionMetadata,
)
from modules.tools.security import sanitize_error_message

logger = get_logger("modules.tools.execution_manager")


class _SlidingWindowRateLimiter:
    """Thread-safe per-tool sliding-window rate limiter (requests per minute)."""

    def __init__(self, limit_per_minute: int) -> None:
        self._limit = limit_per_minute
        self._lock = threading.Lock()
        self._timestamps: list = []

    def acquire(self) -> bool:
        now = time.time()
        window_start = now - 60.0
        with self._lock:
            self._timestamps = [t for t in self._timestamps if t >= window_start]
            if len(self._timestamps) >= self._limit:
                return False
            self._timestamps.append(now)
            return True


class ToolExecutionManager:
    """Executes validated tool calls under a bounded, observable policy."""

    def __init__(self, max_workers: Optional[int] = None) -> None:
        self._lock = threading.Lock()
        self._semaphores: Dict[str, threading.BoundedSemaphore] = {}
        self._rate_limiters: Dict[str, _SlidingWindowRateLimiter] = {}
        self._records: Dict[str, ToolCallRecord] = {}
        # Cancellation requests may arrive before the execution record exists.
        self._cancelled_requests: set = set()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers or 16, thread_name_prefix="tool-exec"
        )

    # -- public API --------------------------------------------------------

    def execute(
        self,
        definition: ToolDefinition,
        request: ToolCallRequest,
        run_fn: Callable[[], object],
    ) -> Tuple[object, ToolExecutionMetadata]:
        """Execute a tool run function with the tool's execution policy applied.

        Returns a tuple of (raw_result, execution_metadata). Raises a
        ToolError subclass (or the original EarthMindException) on failure.
        """
        config = definition.execution
        timeout = self._resolve_timeout(config.timeout_seconds, request.timeout_override)
        record = self._begin_record(definition.tool_id, request.request_id)
        metadata = ToolExecutionMetadata(provider=definition.tool_id)

        # Rate limit check (pre-execution, non-blocking).
        if config.rate_limit_per_minute:
            limiter = self._get_rate_limiter(definition.tool_id, config.rate_limit_per_minute)
            if not limiter.acquire():
                record.mark_finished(ToolCallStatus.RATE_LIMITED, "TOOL_RATE_LIMITED")
                metadata.rate_limited = True
                raise ToolRateLimitError(
                    definition.tool_id,
                    f"Exceeded {config.rate_limit_per_minute} requests/minute.",
                )

        semaphore = self._get_semaphore(definition.tool_id, config.max_concurrency)
        acquired = semaphore.acquire(timeout=0.5)
        if not acquired:
            record.mark_finished(ToolCallStatus.CONCURRENCY_LIMIT, "TOOL_CONCURRENCY_LIMIT")
            raise ToolConcurrencyLimitError(definition.tool_id, config.max_concurrency)

        attempts = 0
        last_error: Optional[BaseException] = None
        max_attempts = 1 + (config.max_retries if config.idempotent else 0)
        start = time.perf_counter()

        try:
            while attempts < max_attempts:
                attempts += 1
                record.attempts = attempts
                metadata.attempts = attempts

                if record.cancel_requested:
                    record.mark_finished(ToolCallStatus.CANCELLED, "TOOL_CANCELLED")
                    metadata.cancelled = True
                    raise ToolCancelledError(definition.tool_id, request.request_id)

                try:
                    result = self._run_with_timeout(run_fn, timeout, definition.tool_id)
                    metadata.duration_ms = (time.perf_counter() - start) * 1000.0
                    record.mark_finished(ToolCallStatus.SUCCESS)
                    return result, metadata
                except ToolTimeoutError as exc:
                    last_error = exc
                    metadata.timed_out = True
                    metadata.duration_ms = (time.perf_counter() - start) * 1000.0
                    # Timeouts are not retried: the operation may still be running.
                    record.mark_finished(ToolCallStatus.TIMEOUT, "TOOL_TIMEOUT")
                    raise
                except EarthMindException as exc:
                    last_error = exc
                    retryable = bool(getattr(exc.error_contract, "retryable", False))
                    if attempts < max_attempts and retryable:
                        metadata.retries = attempts
                        self._sleep_backoff(config.retry_backoff_seconds, attempts)
                        continue
                    record.mark_finished(
                        ToolCallStatus.EXECUTION_ERROR,
                        exc.error_contract.error_code,
                    )
                    raise
                except Exception as exc:  # unexpected tool error
                    last_error = exc
                    if attempts < max_attempts:
                        metadata.retries = attempts
                        self._sleep_backoff(config.retry_backoff_seconds, attempts)
                        continue
                    record.mark_finished(ToolCallStatus.EXECUTION_ERROR, "TOOL_EXECUTION_ERROR")
                    raise ToolExecutionError(
                        definition.tool_id, sanitize_error_message(str(exc))
                    ) from exc

            # Exhausted retries without returning or raising explicitly.
            record.mark_finished(ToolCallStatus.EXECUTION_ERROR, "TOOL_EXECUTION_ERROR")
            if isinstance(last_error, EarthMindException):
                raise last_error
            raise ToolExecutionError(
                definition.tool_id,
                sanitize_error_message(str(last_error) if last_error else "unknown error"),
            )
        finally:
            metadata.duration_ms = metadata.duration_ms or (time.perf_counter() - start) * 1000.0
            semaphore.release()

    def request_cancel(self, request_id: str) -> bool:
        """Request cooperative cancellation of an in-flight (or not-yet-started) call."""
        with self._lock:
            record = self._records.get(request_id)
            if record is not None and record.finished_at is not None:
                return False
            self._cancelled_requests.add(request_id)
            if record is not None:
                record.cancel_requested = True
        return True

    def get_record(self, request_id: str) -> Optional[ToolCallRecord]:
        with self._lock:
            return self._records.get(request_id)

    def status_snapshot(self) -> Dict[str, int]:
        """Return a low-cardinality count of in-flight records per status."""
        with self._lock:
            snapshot: Dict[str, int] = {}
            for record in self._records.values():
                snapshot[record.status.value] = snapshot.get(record.status.value, 0) + 1
        return snapshot

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _resolve_timeout(default: float, override: Optional[float]) -> float:
        if override is None:
            return default
        # Bound override so callers cannot extend beyond 2x the configured default.
        return min(override, default * 2.0)

    def _run_with_timeout(
        self, run_fn: Callable[[], object], timeout: float, tool_id: str
    ) -> object:
        future = self._executor.submit(run_fn)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            future.cancel()
            raise ToolTimeoutError(tool_id, timeout)

    @staticmethod
    def _sleep_backoff(base: float, attempt: int) -> None:
        if base <= 0:
            return
        delay = min(base * (2 ** (attempt - 1)), 5.0)
        # Full jitter to avoid thundering herds.
        time.sleep(random.uniform(0.0, delay))

    def _get_semaphore(self, tool_id: str, limit: int) -> threading.BoundedSemaphore:
        with self._lock:
            sem = self._semaphores.get(tool_id)
            if sem is None:
                sem = threading.BoundedSemaphore(limit)
                self._semaphores[tool_id] = sem
            return sem

    def _get_rate_limiter(self, tool_id: str, limit: int) -> _SlidingWindowRateLimiter:
        with self._lock:
            limiter = self._rate_limiters.get(tool_id)
            if limiter is None:
                limiter = _SlidingWindowRateLimiter(limit)
                self._rate_limiters[tool_id] = limiter
            return limiter

    def _begin_record(self, tool_id: str, request_id: str) -> ToolCallRecord:
        record = ToolCallRecord(request_id=request_id, tool_id=tool_id)
        with self._lock:
            if request_id in self._cancelled_requests:
                record.cancel_requested = True
                self._cancelled_requests.discard(request_id)
            self._records[request_id] = record
        return record
