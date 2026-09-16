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

class ArtifactNotFoundError(EarthMindException):
    def __init__(self, identifier: str, details: str):
        super().__init__(
            message=f"Model artifact '{identifier}' not found: {details}",
            error_code="ARTIFACT_NOT_FOUND",
            module="ai_initializer",
            operation="resolve_artifact"
        )

class EnvironmentIncompatibleError(EarthMindException):
    def __init__(self, reason: str):
        super().__init__(
            message=f"Environment incompatible for model loading: {reason}",
            error_code="ENVIRONMENT_INCOMPATIBLE",
            module="ai_initializer",
            operation="detect_environment"
        )

class InitializationError(EarthMindException):
    def __init__(self, identifier: str, details: str):
        super().__init__(
            message=f"Failed to initialize model '{identifier}': {details}",
            error_code="INITIALIZATION_FAILED",
            module="ai_initializer",
            operation="initialize"
        )

class ReadinessError(EarthMindException):
    def __init__(self, identifier: str, reason: str):
        super().__init__(
            message=f"Model '{identifier}' failed readiness check: {reason}",
            error_code="READINESS_FAILED",
            module="ai_initializer",
            operation="check_readiness"
        )

class InvalidRuntimeStateError(EarthMindException):
    def __init__(self, current_state: str, action: str):
        super().__init__(
            message=f"Cannot perform action '{action}' in runtime state '{current_state}'.",
            error_code="INVALID_RUNTIME_STATE",
            module="ai_runtime",
            operation=action
        )

class RuntimeUnavailableError(EarthMindException):
    def __init__(self, reason: str):
        super().__init__(
            message=f"Model runtime unavailable: {reason}",
            error_code="RUNTIME_UNAVAILABLE",
            module="ai_runtime",
            operation="execute"
        )

class ResourceUnavailableError(EarthMindException):
    def __init__(self, resource_name: str, details: str):
        super().__init__(
            message=f"Required resource '{resource_name}' unavailable: {details}",
            error_code="RESOURCE_UNAVAILABLE",
            module="ai_runtime",
            operation="resource_allocation"
        )

class ModelTimeoutError(EarthMindException):
    def __init__(self, request_id: str, timeout: float):
        super().__init__(
            message=f"Execution of request '{request_id}' timed out after {timeout} seconds.",
            error_code="MODEL_TIMEOUT",
            module="ai_runtime",
            operation="execute",
            retryable=True
        )

class ModelCancelledError(EarthMindException):
    def __init__(self, request_id: str):
        super().__init__(
            message=f"Execution of request '{request_id}' was cancelled.",
            error_code="MODEL_CANCELLED",
            module="ai_runtime",
            operation="execute"
        )

class ModelExecutionError(EarthMindException):
    def __init__(self, model_identifier: str, details: str):
        super().__init__(
            message=f"Error executing model '{model_identifier}': {details}",
            error_code="MODEL_EXECUTION_ERROR",
            module="ai",
            operation="generate"
        )
