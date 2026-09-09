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
