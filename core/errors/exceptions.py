from typing import Any, Dict, Optional
from core.schemas.contracts import ErrorContract

class EarthMindException(Exception):
    """Base exception for all EarthMind framework errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "EARTHMIND_ERROR",
        module: str = "core",
        operation: str = "unknown",
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.error_contract = ErrorContract(
            error_code=error_code,
            message=message,
            module=module,
            operation=operation,
            retryable=retryable,
            metadata=metadata or {}
        )

class ModuleNotFoundError(EarthMindException):
    def __init__(self, module_name: str):
        super().__init__(
            message=f"Module '{module_name}' is not registered.",
            error_code="MODULE_NOT_FOUND",
            module="core",
            operation="registry_lookup"
        )

class ModuleExecutionError(EarthMindException):
    def __init__(self, module_name: str, details: str):
        super().__init__(
            message=f"Execution error in module '{module_name}': {details}",
            error_code="MODULE_EXECUTION_ERROR",
            module=module_name,
            operation="handle"
        )

class ModelNotLoadedError(EarthMindException):
    def __init__(self, model_identifier: str):
        super().__init__(
            message=f"Model '{model_identifier}' is not loaded.",
            error_code="MODEL_NOT_LOADED",
            module="ai",
            operation="generate"
        )

class ModelExecutionError(EarthMindException):
    def __init__(self, model_identifier: str, details: str):
        super().__init__(
            message=f"Error executing model '{model_identifier}': {details}",
            error_code="MODEL_EXECUTION_ERROR",
            module="ai",
            operation="generate"
        )

class InferenceValidationError(EarthMindException):
    def __init__(self, details: str):
        super().__init__(
            message=f"Inference request validation failed: {details}",
            error_code="INFERENCE_VALIDATION_ERROR",
            module="ai",
            operation="validate_request"
        )

class RuntimeUnavailableError(EarthMindException):
    def __init__(self, details: str = "Runtime or model backend is unavailable."):
        super().__init__(
            message=details,
            error_code="RUNTIME_UNAVAILABLE",
            module="ai",
            operation="execute"
        )

class InferenceTimeoutError(EarthMindException):
    def __init__(self, request_id: str, timeout: float):
        super().__init__(
            message=f"Inference request '{request_id}' timed out after {timeout} seconds.",
            error_code="INFERENCE_TIMEOUT",
            module="ai",
            operation="execute",
            retryable=True,
            metadata={"request_id": request_id, "timeout": timeout}
        )

class InferenceCancelledError(EarthMindException):
    def __init__(self, request_id: str):
        super().__init__(
            message=f"Inference request '{request_id}' was cancelled.",
            error_code="INFERENCE_CANCELLED",
            module="ai",
            operation="execute",
            metadata={"request_id": request_id}
        )


class ContextError(EarthMindException):
    """Base exception for B2 Context Manager errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "CONTEXT_ERROR",
        operation: str = "context_processing",
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            module="context",
            operation=operation,
            retryable=retryable,
            metadata=metadata or {}
        )


class InvalidContextRequestError(ContextError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Invalid context request: {details}",
            error_code="INVALID_CONTEXT_REQUEST",
            operation="validate_request"
        )


class InvalidContextItemError(ContextError):
    def __init__(self, item_id: str, details: str):
        super().__init__(
            message=f"Invalid context item '{item_id}': {details}",
            error_code="INVALID_CONTEXT_ITEM",
            operation="validate_item",
            metadata={"item_id": item_id}
        )


class ContextScopeViolationError(ContextError):
    def __init__(self, item_id: str, details: str):
        super().__init__(
            message=f"Scope violation in context item '{item_id}': {details}",
            error_code="CONTEXT_SCOPE_VIOLATION",
            operation="filter_scope",
            metadata={"item_id": item_id}
        )


class ContextPrivacyViolationError(ContextError):
    def __init__(self, item_id: str, details: str):
        super().__init__(
            message=f"Privacy violation in context item '{item_id}': {details}",
            error_code="CONTEXT_PRIVACY_VIOLATION",
            operation="filter_privacy",
            metadata={"item_id": item_id}
        )


class InsufficientContextError(ContextError):
    def __init__(self, request_id: str, details: str):
        super().__init__(
            message=f"Insufficient context for request '{request_id}': {details}",
            error_code="INSUFFICIENT_CONTEXT",
            operation="prepare_context",
            metadata={"request_id": request_id}
        )


class ContextOutputValidationError(ContextError):
    def __init__(self, request_id: str, details: str):
        super().__init__(
            message=f"Output validation failed for context request '{request_id}': {details}",
            error_code="CONTEXT_OUTPUT_VALIDATION_ERROR",
            operation="validate_output",
            metadata={"request_id": request_id}
        )


class ContextProviderError(ContextError):
    def __init__(self, provider_name: str, details: str):
        super().__init__(
            message=f"Context provider '{provider_name}' error: {details}",
            error_code="CONTEXT_PROVIDER_ERROR",
            operation="collect_context",
            metadata={"provider_name": provider_name}
        )


class UnknownModelVersionError(EarthMindException):
    def __init__(self, identifier: str, version: str):
        super().__init__(
            message=f"Model '{identifier}' version '{version}' is not registered.",
            error_code="UNKNOWN_MODEL_VERSION",
            module="ai",
            operation="version_lookup"
        )


class InvalidLifecycleTransitionError(EarthMindException):
    def __init__(self, identifier: str, version: str, current_state: str, target_state: str, reason: str = ""):
        msg = f"Invalid lifecycle transition for model '{identifier}' (v{version}): {current_state} -> {target_state}."
        if reason:
            msg += f" Reason: {reason}"
        super().__init__(
            message=msg,
            error_code="INVALID_LIFECYCLE_TRANSITION",
            module="ai",
            operation="transition_lifecycle"
        )


class ModelCompatibilityError(EarthMindException):
    def __init__(self, identifier: str, version: str, details: str):
        super().__init__(
            message=f"Model '{identifier}' (v{version}) failed compatibility check: {details}",
            error_code="MODEL_COMPATIBILITY_ERROR",
            module="ai",
            operation="check_compatibility"
        )


class ValidationGateError(EarthMindException):
    def __init__(self, identifier: str, version: str, details: str):
        super().__init__(
            message=f"Validation gate failed for model '{identifier}' (v{version}): {details}",
            error_code="VALIDATION_GATE_ERROR",
            module="ai",
            operation="validate_gate"
        )


class ModelActivationError(EarthMindException):
    def __init__(self, identifier: str, version: str, details: str):
        super().__init__(
            message=f"Failed to activate model '{identifier}' (v{version}): {details}",
            error_code="MODEL_ACTIVATION_ERROR",
            module="ai",
            operation="activate_version"
        )


class ModelRollbackError(EarthMindException):
    def __init__(self, identifier: str, details: str):
        super().__init__(
            message=f"Rollback failed for model '{identifier}': {details}",
            error_code="MODEL_ROLLBACK_ERROR",
            module="ai",
            operation="rollback_version"
        )


class RetiredModelSelectedError(EarthMindException):
    def __init__(self, identifier: str, version: str):
        super().__init__(
            message=f"Cannot select or activate retired model '{identifier}' (v{version}).",
            error_code="RETIRED_MODEL_SELECTED",
            module="ai",
            operation="select_version"
        )


class ConflictingActiveVersionError(EarthMindException):
    def __init__(self, identifier: str, existing_version: str, new_version: str):
        super().__init__(
            message=f"Cannot set active version to '{new_version}' because '{existing_version}' is already active for model '{identifier}'.",
            error_code="CONFLICTING_ACTIVE_VERSION",
            module="ai",
            operation="activate_version"
        )


class InvalidRevisionError(EarthMindException):
    def __init__(self, identifier: str, revision: str, details: str):
        super().__init__(
            message=f"Invalid revision '{revision}' for model '{identifier}': {details}",
            error_code="INVALID_REVISION",
            module="ai",
            operation="validate_revision"
        )

class DuplicateRequestError(EarthMindException):
    def __init__(self, request_id: str):
        super().__init__(
            message=f"Duplicate inference request with ID '{request_id}'.",
            error_code="DUPLICATE_REQUEST",
            module="ai",
            operation="execute",
            metadata={"request_id": request_id}
        )
