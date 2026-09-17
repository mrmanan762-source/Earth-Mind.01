"""Inference Executor Pathway for EarthMind AI Model Layer."""

import time
import re
from typing import Dict, Any, Optional, Set
from core.schemas.model import (
    ModelGenerationRequest,
    ModelGenerationResponse,
    InferenceExecutionState
)
from core.interfaces.initializer import IModelInitializer, InitializationState
from core.interfaces.runtime import IRuntime, RuntimeState
from core.config.settings import ModelConfig
from core.errors.exceptions import (
    InferenceValidationError,
    RuntimeUnavailableError,
    ModelNotLoadedError,
    InferenceTimeoutError,
    InferenceCancelledError,
    DuplicateRequestError,
    EarthMindException
)
from core.logging.logger import get_logger

logger = get_logger("modules.ai.inference_executor")

SECRET_PATTERNS = [
    re.compile(r"HF_TOKEN=['\"]?[a-zA-Z0-9_\-]+['\"]?", re.IGNORECASE),
    re.compile(r"api[_-]?key=['\"]?[a-zA-Z0-9_\-]+['\"]?", re.IGNORECASE),
    re.compile(r"secret=['\"]?[a-zA-Z0-9_\-]+['\"]?", re.IGNORECASE),
]


def sanitize_text(text: str) -> str:
    """Scrub tokens, keys, and secrets from string representations."""
    if not isinstance(text, str):
        return str(text)
    sanitized = text
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
    return sanitized


class InferenceExecutor:
    """Controls the inference execution pathway through ModelInitializer and ModelRuntime."""

    def __init__(
        self,
        initializer: IModelInitializer,
        runtime: IRuntime,
        config: ModelConfig
    ):
        self._initializer = initializer
        self._runtime = runtime
        self._config = config
        self._processed_request_ids: Set[str] = set()

    def validate_request(self, request: ModelGenerationRequest) -> None:
        """Validate request payload structure, required fields, and constraints."""
        if not isinstance(request, ModelGenerationRequest):
            raise InferenceValidationError("Payload must be an instance of ModelGenerationRequest.")

        if not request.request_id or not request.request_id.strip():
            raise InferenceValidationError("Field 'request_id' is required and cannot be empty.")

        if not request.task or not request.task.strip():
            raise InferenceValidationError("Field 'task' is required and cannot be empty.")

        if request.request_id in self._processed_request_ids:
            raise DuplicateRequestError(request.request_id)

    def execute_inference(
        self,
        request: ModelGenerationRequest,
        timeout: Optional[float] = None
    ) -> ModelGenerationResponse:
        """Executes full inference lifecycle pathway safely."""
        start_time = time.time()
        model_version_str = f"{self._config.repo_id}@{self._config.revision[:8]}"

        logger.info(sanitize_text(f"[REQUESTED] Inference request received. request_id={request.request_id}"))

        # State 1: VALIDATING
        try:
            self.validate_request(request)
            logger.info(sanitize_text(f"[VALIDATING] Request validated successfully. request_id={request.request_id}"))
        except EarthMindException as e:
            logger.warning(sanitize_text(f"[FAILED] Request validation failed for request_id={getattr(request, 'request_id', 'unknown')}: {e}"))
            return ModelGenerationResponse(
                request_id=getattr(request, "request_id", "invalid-req"),
                status=InferenceExecutionState.FAILED.value,
                response=None,
                warnings=[str(e)],
                model_version=model_version_str,
                metadata={
                    "execution_state": InferenceExecutionState.FAILED.value,
                    "error_code": e.error_contract.error_code,
                    "model_identifier": self._config.identifier
                }
            )

        # Record request_id for idempotency
        self._processed_request_ids.add(request.request_id)

        # Check Model Initializer Readiness
        if self._initializer.state != InitializationState.READY:
            logger.error(sanitize_text(f"[UNAVAILABLE] Model initializer not ready. Current state: {self._initializer.state.value}"))
            return ModelGenerationResponse(
                request_id=request.request_id,
                status=InferenceExecutionState.UNAVAILABLE.value,
                response=None,
                warnings=[f"Model '{self._config.identifier}' is not loaded/ready."],
                model_version=model_version_str,
                metadata={
                    "execution_state": InferenceExecutionState.UNAVAILABLE.value,
                    "model_identifier": self._config.identifier,
                    "error_code": "MODEL_NOT_READY"
                }
            )

        # Check Runtime Availability
        if self._runtime.state not in (RuntimeState.READY, RuntimeState.EXECUTING):
            logger.error(sanitize_text(f"[UNAVAILABLE] Runtime is unavailable. Current state: {self._runtime.state.value}"))
            return ModelGenerationResponse(
                request_id=request.request_id,
                status=InferenceExecutionState.UNAVAILABLE.value,
                response=None,
                warnings=[f"Runtime is unavailable (state: {self._runtime.state.value})."],
                model_version=model_version_str,
                metadata={
                    "execution_state": InferenceExecutionState.UNAVAILABLE.value,
                    "model_identifier": self._config.identifier,
                    "error_code": "RUNTIME_UNAVAILABLE"
                }
            )

        # Multimodal boundary check
        multimodal_meta = {}
        if request.multimodal_data is not None:
            multimodal_meta["multimodal_reference_passed"] = True
            if isinstance(request.multimodal_data, dict):
                multimodal_meta["multimodal_keys"] = list(request.multimodal_data.keys())

        # State 2: QUEUED / ACCEPTED -> State 3: EXECUTING
        logger.info(sanitize_text(f"[QUEUED] Request admitted to runtime queue. request_id={request.request_id}"))
        logger.info(sanitize_text(f"[EXECUTING] Inference execution started. request_id={request.request_id}"))

        try:
            raw_result = self._runtime.execute(
                request=request,
                model_version=model_version_str,
                timeout=timeout
            )
            duration = round(time.time() - start_time, 4)
            logger.info(sanitize_text(f"[COMPLETED] Inference execution finished successfully in {duration}s. request_id={request.request_id}"))

            # Normalize response
            response_metadata = {
                "execution_state": InferenceExecutionState.COMPLETED.value,
                "model_identifier": self._config.identifier,
                "repo_id": self._config.repo_id,
                "revision": self._config.revision,
                "duration_seconds": duration,
                "context_preserved": bool(request.context),
                "conversation_length": len(request.conversation) if request.conversation else 0,
                **multimodal_meta,
                **request.metadata
            }

            return ModelGenerationResponse(
                request_id=request.request_id,
                status="success",
                response=raw_result.get("response"),
                reasoning_data=raw_result.get("reasoning_data", {}),
                tool_information=request.tools_available or [],
                confidence_level=raw_result.get("confidence_level"),
                uncertainty=raw_result.get("uncertainty"),
                warnings=raw_result.get("warnings", []),
                model_version=model_version_str,
                metadata=response_metadata
            )

        except InferenceTimeoutError as e:
            duration = round(time.time() - start_time, 4)
            logger.error(sanitize_text(f"[TIMEOUT] Execution timed out for request_id={request.request_id} after {duration}s."))
            return ModelGenerationResponse(
                request_id=request.request_id,
                status=InferenceExecutionState.TIMEOUT.value,
                response=None,
                warnings=[str(e)],
                model_version=model_version_str,
                metadata={
                    "execution_state": InferenceExecutionState.TIMEOUT.value,
                    "duration_seconds": duration,
                    "model_identifier": self._config.identifier,
                    "error_code": "INFERENCE_TIMEOUT"
                }
            )

        except InferenceCancelledError as e:
            duration = round(time.time() - start_time, 4)
            logger.warning(sanitize_text(f"[CANCELLED] Execution cancelled for request_id={request.request_id}."))
            return ModelGenerationResponse(
                request_id=request.request_id,
                status=InferenceExecutionState.CANCELLED.value,
                response=None,
                warnings=[str(e)],
                model_version=model_version_str,
                metadata={
                    "execution_state": InferenceExecutionState.CANCELLED.value,
                    "duration_seconds": duration,
                    "model_identifier": self._config.identifier,
                    "error_code": "INFERENCE_CANCELLED"
                }
            )

        except Exception as e:
            duration = round(time.time() - start_time, 4)
            logger.error(sanitize_text(f"[FAILED] Execution failed for request_id={request.request_id}: {e}"))
            return ModelGenerationResponse(
                request_id=request.request_id,
                status=InferenceExecutionState.FAILED.value,
                response=None,
                warnings=[str(e)],
                model_version=model_version_str,
                metadata={
                    "execution_state": InferenceExecutionState.FAILED.value,
                    "duration_seconds": duration,
                    "model_identifier": self._config.identifier,
                    "error_code": getattr(e, "error_contract", None).error_code if hasattr(e, "error_contract") else "EXECUTION_FAILURE"
                }
            )
