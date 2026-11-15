"""Tool Result Normalizer for the EarthMind Phase 3 Backend Tool Infrastructure.

Converts raw tool outputs and failures into the single consistent
`ToolCallResult` contract, preserving tool id, request id, execution status,
result payload, source references, execution metadata and error information.
"""

from typing import Any, Dict, Iterable, List, Optional

from core.errors.exceptions import EarthMindException, ToolError
from core.schemas.tools import (
    ToolCallResult,
    ToolCallStatus,
    ToolExecutionMetadata,
    ToolSourceReference,
)
from modules.tools.security import redact_mapping, sanitize_error_message

# Maps tool exception error codes to normalized statuses.
_ERROR_CODE_STATUS = {
    "TOOL_NOT_FOUND": ToolCallStatus.NOT_FOUND,
    "TOOL_ALREADY_REGISTERED": ToolCallStatus.INVALID_REQUEST,
    "INVALID_TOOL_SCHEMA": ToolCallStatus.INTERNAL_ERROR,
    "INVALID_TOOL_REQUEST": ToolCallStatus.INVALID_REQUEST,
    "TOOL_VALIDATION_ERROR": ToolCallStatus.VALIDATION_ERROR,
    "TOOL_PERMISSION_DENIED": ToolCallStatus.PERMISSION_DENIED,
    "TOOL_TIMEOUT": ToolCallStatus.TIMEOUT,
    "TOOL_CANCELLED": ToolCallStatus.CANCELLED,
    "TOOL_RATE_LIMITED": ToolCallStatus.RATE_LIMITED,
    "TOOL_CONCURRENCY_LIMIT": ToolCallStatus.CONCURRENCY_LIMIT,
    "TOOL_UNAVAILABLE": ToolCallStatus.UNAVAILABLE,
    "TOOL_PAYLOAD_LIMIT_EXCEEDED": ToolCallStatus.PAYLOAD_LIMIT_EXCEEDED,
    "UNSAFE_TOOL_EXPRESSION": ToolCallStatus.VALIDATION_ERROR,
    "TOOL_CONFIGURATION_ERROR": ToolCallStatus.INTERNAL_ERROR,
    "TOOL_EXECUTION_ERROR": ToolCallStatus.EXECUTION_ERROR,
}

# Provider-level error codes that indicate a transient (retryable) condition.
_RETRYABLE_ERROR_CODES = {
    "TOOL_TIMEOUT",
    "TOOL_RATE_LIMITED",
    "TOOL_CONCURRENCY_LIMIT",
    "PROVIDER_UNAVAILABLE",
    "WEATHER_PROVIDER_ERROR",
}


def status_for_error_code(error_code: str) -> ToolCallStatus:
    return _ERROR_CODE_STATUS.get(error_code, ToolCallStatus.EXECUTION_ERROR)


class ToolResultNormalizer:
    """Builds normalized `ToolCallResult` objects from raw outputs and errors."""

    def success(
        self,
        tool_id: str,
        request_id: str,
        payload: Any,
        *,
        sources: Optional[Iterable[ToolSourceReference]] = None,
        execution: Optional[ToolExecutionMetadata] = None,
        warnings: Optional[Iterable[str]] = None,
        status: ToolCallStatus = ToolCallStatus.SUCCESS,
    ) -> ToolCallResult:
        return ToolCallResult(
            tool_id=tool_id,
            request_id=request_id,
            status=status,
            payload=payload,
            sources=list(sources or []),
            execution=execution or ToolExecutionMetadata(),
            warnings=[sanitize_error_message(w) for w in (warnings or [])],
        )

    def failure(
        self,
        tool_id: str,
        request_id: str,
        *,
        status: ToolCallStatus,
        error_code: str,
        message: str,
        retryable: bool = False,
        execution: Optional[ToolExecutionMetadata] = None,
        warnings: Optional[Iterable[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ToolCallResult:
        return ToolCallResult(
            tool_id=tool_id,
            request_id=request_id,
            status=status,
            payload=None,
            execution=execution or ToolExecutionMetadata(),
            warnings=[sanitize_error_message(w) for w in (warnings or [])],
            error={
                "error_code": error_code,
                "message": sanitize_error_message(message),
                "retryable": retryable,
                "metadata": redact_mapping(metadata or {}),
            },
        )

    def from_exception(
        self,
        tool_id: str,
        request_id: str,
        exc: BaseException,
        *,
        execution: Optional[ToolExecutionMetadata] = None,
    ) -> ToolCallResult:
        if isinstance(exc, EarthMindException):
            contract = exc.error_contract
            return self.failure(
                tool_id,
                request_id,
                status=status_for_error_code(contract.error_code),
                error_code=contract.error_code,
                message=contract.message,
                retryable=bool(contract.retryable),
                execution=execution,
                metadata=contract.metadata,
            )
        return self.failure(
            tool_id,
            request_id,
            status=ToolCallStatus.INTERNAL_ERROR,
            error_code="INTERNAL_ERROR",
            message=str(exc),
            retryable=False,
            execution=execution,
        )
