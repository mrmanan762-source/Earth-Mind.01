"""Reliability, Circuit Breaker, Rate Limiter & Quota Management for EarthMind Stage R10 Web Search.

Architectural Guarantees:
- Circuit Breaker Pattern:
  - 3 States: CLOSED (normal operations), OPEN (tripped after repeated failures, fast-fails requests),
    HALF_OPEN (controlled probe trials to test provider recovery).
  - Isolated per provider: Tavily circuit failure never affects Gemini Grounding or public APIs.
  - Permanent configuration / auth errors fast-fail without endless retry loops.
- Provider Rate Limiting & Concurrency Control:
  - Sliding-window or token bucket rate limiter per provider (e.g. 60 RPM).
  - Concurrency semaphores preventing resource exhaustion.
  - Respects HTTP 429 and Retry-After response headers.
- Local Estimated Quota Management:
  - Tracks local estimated request counters per day/month against configured application usage budgets.
  - Clearly identifies tracking as locally estimated (API providers do not reveal remaining credits).
  - Quota exhaustion halts requests safely to prevent unintended billing triggers or paid tier overages.
  - Never triggers billing or auto-pay via code.
- Bounded Retries with Exponential Backoff:
  - Retries only transient failures (HTTP 429, timeouts, 5xx).
  - Full jitter to prevent thundering herds.
"""

from enum import Enum
import logging
import random
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from core.config.settings import WebSearchConfig
from core.errors.exceptions import (
    WebSearchAuthenticationError,
    WebSearchConfigurationError,
    WebSearchError,
    WebSearchExecutionError,
    WebSearchProviderUnavailableError,
    WebSearchRateLimitError,
    WebSearchTimeoutError,
)

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Operational states for provider circuit breaker."""
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(WebSearchProviderUnavailableError):
    """Raised when a request is attempted while the provider circuit breaker is OPEN."""

    def __init__(self, provider_name: str, cooldown_remaining: float):
        super().__init__(
            provider_name,
            f"Circuit breaker for provider '{provider_name}' is OPEN. "
            f"Fast-failing request (cooldown remaining: {cooldown_remaining:.1f}s)."
        )
        self.cooldown_remaining = cooldown_remaining


class QuotaExceededError(WebSearchRateLimitError):
    """Raised when local estimated daily or monthly usage budget is exhausted."""

    def __init__(self, provider_name: str, period: str, limit: int, current: int):
        super().__init__(
            provider_name,
            f"Local estimated {period} usage budget exhausted for provider '{provider_name}' "
            f"({current}/{limit} estimated calls). Halting requests to prevent unintended billing."
        )
        self.period = period
        self.limit = limit
        self.current = current


class CircuitBreaker:
    """Thread-safe circuit breaker with CLOSED, OPEN, and HALF_OPEN states."""

    def __init__(
        self,
        provider_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_success_threshold: int = 2,
    ):
        self.provider_name = provider_name
        self.failure_threshold = max(1, failure_threshold)
        self.recovery_timeout = max(0.1, recovery_timeout)
        self.half_open_success_threshold = max(1, half_open_success_threshold)

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._last_state_change = time.time()
        self._last_failure_time = 0.0
        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._evaluate_state_transition()
            return self._state

    def _evaluate_state_transition(self) -> None:
        """Internal state transition evaluation based on recovery cooldown."""
        if self._state == CircuitState.OPEN:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                logger.info(
                    f"Circuit breaker for '{self.provider_name}' transitioned from OPEN to HALF_OPEN "
                    f"after {elapsed:.1f}s recovery cooldown."
                )
                self._state = CircuitState.HALF_OPEN
                self._consecutive_successes = 0

    def before_execution(self) -> None:
        """Check if request is permitted through the circuit breaker.

        Raises:
            CircuitBreakerOpenError if circuit is OPEN.
        """
        with self._lock:
            self._evaluate_state_transition()

            if self._state == CircuitState.OPEN:
                remaining = max(0.0, self.recovery_timeout - (time.time() - self._last_failure_time))
                raise CircuitBreakerOpenError(self.provider_name, remaining)

    def record_success(self) -> None:
        """Record successful execution, potentially closing a HALF_OPEN circuit."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._consecutive_successes += 1
                if self._consecutive_successes >= self.half_open_success_threshold:
                    logger.info(
                        f"Circuit breaker for '{self.provider_name}' transitioned from HALF_OPEN to CLOSED "
                        f"after {self._consecutive_successes} consecutive successful probes."
                    )
                    self._state = CircuitState.CLOSED
                    self._consecutive_failures = 0
                    self._consecutive_successes = 0
                    self._last_state_change = time.time()
            elif self._state == CircuitState.CLOSED:
                self._consecutive_failures = 0

    def record_failure(self, exception: Optional[Exception] = None) -> None:
        """Record execution failure, potentially opening the circuit."""
        # Permanent config/auth errors do not trip the circuit (they fast-fail separately)
        if isinstance(exception, (WebSearchAuthenticationError, WebSearchConfigurationError)):
            return

        with self._lock:
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                logger.warning(
                    f"Circuit breaker for '{self.provider_name}' probe failed in HALF_OPEN state. "
                    f"Re-opening circuit for {self.recovery_timeout}s."
                )
                self._state = CircuitState.OPEN
                self._consecutive_failures = self.failure_threshold
                self._consecutive_successes = 0
                self._last_state_change = time.time()
            elif self._state == CircuitState.CLOSED:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self.failure_threshold:
                    logger.warning(
                        f"Circuit breaker for '{self.provider_name}' reached failure threshold "
                        f"({self._consecutive_failures}/{self.failure_threshold}). Transitioning to OPEN."
                    )
                    self._state = CircuitState.OPEN
                    self._last_state_change = time.time()

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic state of the circuit breaker."""
        with self._lock:
            self._evaluate_state_transition()
            return {
                "provider": self.provider_name,
                "state": self._state.value,
                "consecutive_failures": self._consecutive_failures,
                "consecutive_successes": self._consecutive_successes,
                "last_failure_time": self._last_failure_time,
                "recovery_timeout": self.recovery_timeout,
            }


class ProviderRateLimiter:
    """Sliding-window rate limiter and concurrency gate per provider."""

    def __init__(self, provider_name: str, rate_limit_per_minute: int = 60, max_concurrency: int = 5):
        self.provider_name = provider_name
        self.rate_limit_per_minute = max(1, rate_limit_per_minute)
        self.max_concurrency = max(1, max_concurrency)

        self._timestamps: list[float] = []
        self._semaphore = threading.Semaphore(self.max_concurrency)
        self._lock = threading.RLock()
        self._cooldown_until = 0.0

    def acquire(self, timeout: float = 5.0) -> bool:
        """Attempt to acquire permission to make a request within timeout.

        Enforces concurrency limit and sliding-window RPM limit.
        """
        now = time.time()
        with self._lock:
            # Check explicit cooldown (from 429 Retry-After)
            if now < self._cooldown_until:
                wait_time = self._cooldown_until - now
                if wait_time > timeout:
                    raise WebSearchRateLimitError(
                        self.provider_name,
                        f"Provider '{self.provider_name}' is in rate-limit cooldown for {wait_time:.1f}s."
                    )
                time.sleep(wait_time)
                now = time.time()

            # Clean timestamps older than 60 seconds
            window_start = now - 60.0
            self._timestamps = [ts for ts in self._timestamps if ts > window_start]

            if len(self._timestamps) >= self.rate_limit_per_minute:
                oldest = self._timestamps[0]
                wait_needed = 60.0 - (now - oldest)
                if wait_needed > timeout:
                    raise WebSearchRateLimitError(
                        self.provider_name,
                        f"Rate limit exceeded for provider '{self.provider_name}' "
                        f"({len(self._timestamps)}/{self.rate_limit_per_minute} RPM). "
                        f"Wait needed: {wait_needed:.1f}s."
                    )
                time.sleep(max(0.01, wait_needed))
                now = time.time()

            self._timestamps.append(now)

        # Acquire concurrency slot
        acquired = self._semaphore.acquire(blocking=True, timeout=timeout)
        if not acquired:
            raise WebSearchRateLimitError(
                self.provider_name,
                f"Concurrency limit ({self.max_concurrency}) exceeded for provider '{self.provider_name}'."
            )
        return True

    def release(self) -> None:
        """Release concurrency slot."""
        try:
            self._semaphore.release()
        except ValueError:
            pass

    def apply_retry_after(self, retry_after_seconds: float) -> None:
        """Applies explicit cooldown period from HTTP 429 response."""
        with self._lock:
            cooldown = max(1.0, min(retry_after_seconds, 300.0))
            self._cooldown_until = time.time() + cooldown
            logger.warning(
                f"Applied Retry-After cooldown of {cooldown:.1f}s for provider '{self.provider_name}'."
            )


class QuotaManager:
    """Local estimated usage budget tracking across managed search providers.

    Guarantees that EarthMind will not silently trigger unexpected paid usage
    or billable charges by stopping requests when application limits are hit.
    """

    def __init__(self, daily_budget: int = 1000, monthly_budget: int = 25000):
        self.daily_budget = max(1, daily_budget)
        self.monthly_budget = max(1, monthly_budget)

        self._lock = threading.RLock()
        self._provider_usage: Dict[str, Dict[str, int]] = {}
        self._current_day = self._get_day_key()
        self._current_month = self._get_month_key()

    def _get_day_key(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    def _get_month_key(self) -> str:
        return time.strftime("%Y-%m", time.gmtime())

    def check_and_increment(self, provider_name: str) -> None:
        """Validates estimated budget and records an estimated request call."""
        day_key = self._get_day_key()
        month_key = self._get_month_key()

        with self._lock:
            # Day reset
            if day_key != self._current_day:
                self._current_day = day_key
                for p in self._provider_usage:
                    self._provider_usage[p]["daily"] = 0

            # Month reset
            if month_key != self._current_month:
                self._current_month = month_key
                for p in self._provider_usage:
                    self._provider_usage[p]["monthly"] = 0

            if provider_name not in self._provider_usage:
                self._provider_usage[provider_name] = {"daily": 0, "monthly": 0}

            curr = self._provider_usage[provider_name]
            if curr["daily"] >= self.daily_budget:
                raise QuotaExceededError(provider_name, "daily", self.daily_budget, curr["daily"])

            if curr["monthly"] >= self.monthly_budget:
                raise QuotaExceededError(provider_name, "monthly", self.monthly_budget, curr["monthly"])

            curr["daily"] += 1
            curr["monthly"] += 1

    def get_usage(self, provider_name: str) -> Dict[str, Any]:
        """Returns local estimated usage tracking snapshot."""
        with self._lock:
            usage = self._provider_usage.get(provider_name, {"daily": 0, "monthly": 0})
            return {
                "provider": provider_name,
                "is_locally_estimated": True,
                "daily_estimated_count": usage["daily"],
                "daily_budget": self.daily_budget,
                "monthly_estimated_count": usage["monthly"],
                "monthly_budget": self.monthly_budget,
                "day_key": self._current_day,
                "month_key": self._current_month,
            }


class ResilienceManager:
    """Consolidated resilience coordinator managing circuit breakers, rate limits, and budgets."""

    def __init__(self, config: Optional[WebSearchConfig] = None):
        self._config = config or WebSearchConfig()
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._rate_limiters: Dict[str, ProviderRateLimiter] = {}
        self._quota_manager = QuotaManager(
            daily_budget=self._config.daily_usage_budget,
            monthly_budget=self._config.monthly_usage_budget,
        )
        self._lock = threading.RLock()

    def get_circuit_breaker(self, provider_name: str) -> CircuitBreaker:
        """Returns or creates circuit breaker for specified provider."""
        with self._lock:
            if provider_name not in self._circuit_breakers:
                self._circuit_breakers[provider_name] = CircuitBreaker(
                    provider_name=provider_name,
                    failure_threshold=self._config.circuit_breaker_failure_threshold,
                    recovery_timeout=self._config.circuit_breaker_recovery_timeout,
                    half_open_success_threshold=self._config.circuit_breaker_half_open_success_threshold,
                )
            return self._circuit_breakers[provider_name]

    def get_rate_limiter(self, provider_name: str) -> ProviderRateLimiter:
        """Returns or creates rate limiter for specified provider."""
        with self._lock:
            if provider_name not in self._rate_limiters:
                rpm = self._config.rate_limits_per_minute.get(provider_name, 60)
                self._rate_limiters[provider_name] = ProviderRateLimiter(
                    provider_name=provider_name,
                    rate_limit_per_minute=rpm,
                    max_concurrency=self._config.max_concurrent_requests,
                )
            return self._rate_limiters[provider_name]

    @property
    def quota_manager(self) -> QuotaManager:
        return self._quota_manager

    def execute_with_resilience(
        self,
        provider_name: str,
        operation: Callable[[], Any],
        is_managed_provider: bool = False,
    ) -> Any:
        """Executes a provider operation wrapped with circuit breaker, rate limiter, and bounded retries.

        Args:
            provider_name: Unique provider identifier string.
            operation: Callable executing search query.
            is_managed_provider: If True, tracks and enforces local usage quota.
        """
        cb = self.get_circuit_breaker(provider_name)
        rl = self.get_rate_limiter(provider_name)

        # 1. Circuit breaker pre-check
        cb.before_execution()

        # 2. Quota check for managed providers (Tavily, Gemini)
        if is_managed_provider:
            self._quota_manager.check_and_increment(provider_name)

        # 3. Rate limiter slot acquisition
        rl.acquire()

        max_attempts = max(1, self._config.max_retries + 1)
        attempt = 0
        last_exception: Optional[Exception] = None

        try:
            while attempt < max_attempts:
                attempt += 1
                try:
                    result = operation()
                    cb.record_success()
                    return result
                except Exception as ex:
                    last_exception = ex
                    cb.record_failure(ex)

                    # Check if error is non-retryable
                    if isinstance(ex, (WebSearchAuthenticationError, WebSearchConfigurationError, CircuitBreakerOpenError, QuotaExceededError)):
                        logger.warning(f"Non-retryable error from provider '{provider_name}': {ex}")
                        raise ex

                    # Rate limit with Retry-After header extraction
                    if isinstance(ex, WebSearchRateLimitError):
                        retry_after = getattr(ex, "retry_after", None)
                        if retry_after:
                            rl.apply_retry_after(float(retry_after))

                    # If final attempt reached, exit loop and re-raise
                    if attempt >= max_attempts:
                        break

                    # Compute exponential backoff with jitter
                    backoff = min(
                        self._config.max_retry_backoff,
                        self._config.initial_retry_backoff * (2 ** (attempt - 1))
                    )
                    if self._config.backoff_jitter:
                        backoff = random.uniform(backoff * 0.5, backoff * 1.5)

                    logger.info(
                        f"Transient error from provider '{provider_name}' (attempt {attempt}/{max_attempts}): {ex}. "
                        f"Retrying in {backoff:.2f}s..."
                    )
                    time.sleep(backoff)

            if last_exception:
                raise last_exception
        finally:
            rl.release()
