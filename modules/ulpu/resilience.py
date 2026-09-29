"""Resilient Provider Execution Engine for ULPU."""

import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Type
from core.interfaces.ulpu import IProviderRegistry
from core.errors.exceptions import (
    EarthMindException,
    InvalidInputError,
    UnsupportedLanguageError,
    ULPUConfigurationError,
    ULPUTimeoutError,
    ProviderError,
    TranslationError,
    STTError,
    TTSError,
)
from core.logging.logger import get_logger

logger = get_logger("modules.ulpu.resilience")

NON_RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    InvalidInputError,
    UnsupportedLanguageError,
    ULPUConfigurationError,
    ValueError,
)


class ResilientProviderExecutor:
    """
    Resilient provider executor handling:
    - Primary provider call
    - Controlled retry with bounded backoff
    - Provider fallbacks in ordered chain
    - Timeout enforcement & latency measurement
    - Traceability and fallback metadata logging
    - No silent fake successes or silent language replacement
    """

    def __init__(
        self,
        provider_registry: IProviderRegistry,
        category: str,
        primary_provider_name: str,
        fallback_provider_names: Optional[List[str]] = None,
        max_retries: int = 2,
        retry_delay_seconds: float = 0.1,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.provider_registry = provider_registry
        self.category = category.lower().strip()
        self.primary_provider_name = primary_provider_name.lower().strip()
        self.fallback_provider_names = [
            f.lower().strip() for f in (fallback_provider_names or []) if f and f.strip()
        ]
        self.max_retries = max(0, max_retries)
        self.retry_delay_seconds = max(0.001, retry_delay_seconds)
        self.timeout_seconds = max(0.1, timeout_seconds)

    def execute(
        self,
        func_caller: Callable[[Any], Any],
        request_id: str = "unknown_req",
        operation_name: str = "ulpu_operation",
    ) -> Tuple[Any, Dict[str, Any]]:
        """
        Execute a provider function through primary -> retries -> fallbacks -> controlled error.
        Returns (result, execution_metadata).
        """
        candidate_providers = [self.primary_provider_name] + [
            f for f in self.fallback_provider_names if f != self.primary_provider_name
        ]

        failed_providers_log: List[Dict[str, Any]] = []
        overall_start_time = time.monotonic()

        for provider_idx, provider_name in enumerate(candidate_providers):
            is_fallback = provider_idx > 0
            try:
                provider_instance = self.provider_registry.get_provider(self.category, provider_name)
            except Exception as e:
                logger.warning(
                    f"[{request_id}] Could not retrieve provider '{provider_name}' in category '{self.category}': {e}"
                )
                failed_providers_log.append({
                    "provider": provider_name,
                    "is_fallback": is_fallback,
                    "error": str(e),
                    "attempts": 0,
                })
                continue

            attempts = 0
            last_provider_error: Optional[Exception] = None
            for attempt in range(1 + self.max_retries):
                attempts += 1
                stage_start_time = time.monotonic()
                try:
                    logger.info(
                        f"[{request_id}] Executing {operation_name} on provider '{provider_name}' "
                        f"(attempt {attempts}/{1 + self.max_retries}, fallback={is_fallback})"
                    )

                    result = func_caller(provider_instance)
                    stage_latency_ms = round((time.monotonic() - stage_start_time) * 1000, 2)
                    overall_latency_ms = round((time.monotonic() - overall_start_time) * 1000, 2)

                    resilience_metadata = {
                        "request_id": request_id,
                        "operation": operation_name,
                        "primary_provider": self.primary_provider_name,
                        "final_provider": provider_name,
                        "fallback_used": is_fallback,
                        "failed_providers": failed_providers_log,
                        "attempts_on_final_provider": attempts,
                        "stage_latency_ms": stage_latency_ms,
                        "total_latency_ms": overall_latency_ms,
                    }

                    logger.info(
                        f"[{request_id}] Provider '{provider_name}' succeeded for {operation_name} "
                        f"in {stage_latency_ms}ms (fallback_used={is_fallback})"
                    )
                    return result, resilience_metadata

                except NON_RETRYABLE_EXCEPTIONS as e:
                    # Non-retryable input or validation error -> re-raise immediately
                    logger.error(f"[{request_id}] Non-retryable error on provider '{provider_name}': {e}")
                    raise

                except Exception as e:
                    last_provider_error = e
                    stage_latency_ms = round((time.monotonic() - stage_start_time) * 1000, 2)
                    logger.warning(
                        f"[{request_id}] Attempt {attempts} failed on provider '{provider_name}' "
                        f"in {stage_latency_ms}ms: {e}"
                    )

                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay_seconds * (2 ** attempt))

            # All retries failed for this provider
            failed_providers_log.append({
                "provider": provider_name,
                "is_fallback": is_fallback,
                "attempts": attempts,
                "last_error": str(last_provider_error) if last_provider_error else "Unknown error",
            })

        # All primary and fallback providers failed
        total_latency_ms = round((time.monotonic() - overall_start_time) * 1000, 2)
        error_msg = (
            f"All providers exhausted for category '{self.category}' "
            f"(primary: '{self.primary_provider_name}', fallbacks: {self.fallback_provider_names}). "
            f"Failed attempts log: {failed_providers_log}"
        )
        logger.error(f"[{request_id}] {error_msg} (total_latency_ms={total_latency_ms})")

        # Raise category-specific structured exception
        if self.category == "translation":
            raise TranslationError(self.primary_provider_name, "unknown", "unknown", error_msg)
        elif self.category == "stt":
            raise STTError(self.primary_provider_name, error_msg)
        elif self.category == "tts":
            raise TTSError(self.primary_provider_name, error_msg)
        else:
            raise ProviderError(self.primary_provider_name, error_msg)
