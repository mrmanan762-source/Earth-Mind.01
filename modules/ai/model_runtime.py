"""Model Runtime and Mock Inference Backend for EarthMind AI Layer."""

import time
import threading
from typing import Dict, Any, Optional, Set
from core.interfaces.runtime import IRuntime, RuntimeState
from core.schemas.model import ModelGenerationRequest
from core.errors.exceptions import (
    RuntimeUnavailableError,
    InferenceTimeoutError,
    InferenceCancelledError,
    ModelExecutionError
)
from core.logging.logger import get_logger

logger = get_logger("modules.ai.runtime")


class MockInferenceBackend:
    """Deterministic mock inference backend for testing without downloading model weights."""

    def __init__(
        self,
        should_fail: bool = False,
        simulate_delay: float = 0.0,
        is_available: bool = True,
        fail_message: str = "Mock backend failure"
    ):
        self.should_fail = should_fail
        self.simulate_delay = simulate_delay
        self.is_available = is_available
        self.fail_message = fail_message

    def generate(
        self,
        request: ModelGenerationRequest,
        model_version: str,
        cancelled_requests: Optional[Set[str]] = None
    ) -> Dict[str, Any]:
        if not self.is_available:
            raise RuntimeUnavailableError("Mock backend is unavailable.")

        start_time = time.time()
        if self.simulate_delay > 0:
            elapsed = 0.0
            step = 0.02
            while elapsed < self.simulate_delay:
                if cancelled_requests and request.request_id in cancelled_requests:
                    raise InferenceCancelledError(request.request_id)
                time.sleep(step)
                elapsed += step

        if cancelled_requests and request.request_id in cancelled_requests:
            raise InferenceCancelledError(request.request_id)

        if self.should_fail:
            raise ModelExecutionError("mock-backend", self.fail_message)

        generated_text = f"Processed task: {request.task}"
        if request.instructions:
            generated_text += f" | Instructions: {request.instructions}"

        return {
            "response": generated_text,
            "reasoning_data": {"step": "Mock inference reasoning pass"},
            "confidence_level": 0.95,
            "uncertainty": 0.05,
            "warnings": [],
            "execution_duration": round(time.time() - start_time, 4)
        }


class ModelRuntime(IRuntime):
    """Model Runtime implementing IRuntime for concurrency, execution, timeouts, and cancellations."""

    def __init__(
        self,
        backend: Optional[MockInferenceBackend] = None,
        max_concurrency: int = 4,
        default_timeout: float = 30.0
    ):
        self._backend = backend or MockInferenceBackend()
        self._max_concurrency = max_concurrency
        self._default_timeout = default_timeout
        self._state = RuntimeState.UNINITIALIZED
        self._semaphore = threading.Semaphore(max_concurrency)
        self._cancelled_requests: Set[str] = set()
        self._active_requests: Set[str] = set()
        self._lock = threading.Lock()

    @property
    def state(self) -> RuntimeState:
        return self._state

    def initialize(self) -> None:
        with self._lock:
            self._state = RuntimeState.READY
            logger.info(f"ModelRuntime initialized. Max concurrency: {self._max_concurrency}")

    def shutdown(self) -> None:
        with self._lock:
            self._state = RuntimeState.STOPPED
            self._active_requests.clear()
            self._cancelled_requests.clear()
            logger.info("ModelRuntime shut down.")

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            self._cancelled_requests.add(request_id)
            is_active = request_id in self._active_requests
        logger.info(f"Cancellation requested for request_id '{request_id}' (Active: {is_active})")
        return True

    def execute(
        self,
        request: ModelGenerationRequest,
        model_version: str = "sarvam-105b@pinned",
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        if self._state not in (RuntimeState.READY, RuntimeState.EXECUTING):
            raise RuntimeUnavailableError(f"Runtime is not ready. Current state: {self._state.value}")

        req_timeout = timeout if timeout is not None else self._default_timeout
        acquired = self._semaphore.acquire(blocking=True, timeout=req_timeout)
        if not acquired:
            raise InferenceTimeoutError(request.request_id, req_timeout)

        with self._lock:
            if request.request_id in self._cancelled_requests:
                self._semaphore.release()
                raise InferenceCancelledError(request.request_id)
            self._active_requests.add(request.request_id)
            self._state = RuntimeState.EXECUTING

        result_container: Dict[str, Any] = {}
        exception_container: Dict[str, Exception] = {}

        def _worker():
            try:
                res = self._backend.generate(request, model_version, self._cancelled_requests)
                result_container["result"] = res
            except Exception as e:
                exception_container["error"] = e

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        thread.join(timeout=req_timeout)

        with self._lock:
            self._active_requests.discard(request.request_id)
            if not self._active_requests and self._state == RuntimeState.EXECUTING:
                self._state = RuntimeState.READY

        self._semaphore.release()

        if thread.is_alive():
            with self._lock:
                self._cancelled_requests.add(request.request_id)
            raise InferenceTimeoutError(request.request_id, req_timeout)

        if "error" in exception_container:
            raise exception_container["error"]

        if request.request_id in self._cancelled_requests:
            raise InferenceCancelledError(request.request_id)

        return result_container["result"]

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self._state.value,
                "max_concurrency": self._max_concurrency,
                "active_requests_count": len(self._active_requests),
                "cancelled_requests_count": len(self._cancelled_requests),
                "backend_available": self._backend.is_available
            }
