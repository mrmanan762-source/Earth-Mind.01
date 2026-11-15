"""Tool Dispatcher for the EarthMind Phase 3 Backend Tool Infrastructure.

The dispatcher receives a validated `ToolCallRequest`, resolves the target tool
via the registry, enforces the security boundary (permissions, payload limits,
availability), executes the tool through the Execution Manager, and returns a
normalized `ToolCallResult`.

The dispatcher deliberately does NOT orchestrate multi-step workflows; B5
retains workflow coordination. A tool call is a single atomic operation.
"""

from typing import Optional

from core.errors.exceptions import (
    InvalidToolRequestError,
    ToolPayloadLimitExceededError,
    ToolPermissionError,
    ToolUnavailableError,
    ToolValidationError,
)
from core.logging.logger import get_logger
from core.schemas.tools import (
    ToolCallRequest,
    ToolCallResult,
    ToolCallStatus,
    ToolExecutionMetadata,
)
from modules.tools.execution_manager import ToolExecutionManager
from modules.tools.normalizer import ToolResultNormalizer
from modules.tools.registry import ToolRegistry
from modules.tools.security import enforce_payload_limit, payload_size_bytes, sanitize_error_message

logger = get_logger("modules.tools.dispatcher")

# A caller holding ADMIN implicitly satisfies every tool permission requirement.
_ADMIN_PERMISSION = "ADMIN"


class ToolDispatcher:
    """Validates and routes tool requests to the correct tool implementation."""

    def __init__(
        self,
        registry: ToolRegistry,
        execution_manager: Optional[ToolExecutionManager] = None,
        normalizer: Optional[ToolResultNormalizer] = None,
    ) -> None:
        self._registry = registry
        self._execution = execution_manager or ToolExecutionManager()
        self._normalizer = normalizer or ToolResultNormalizer()

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    def dispatch(self, request: ToolCallRequest) -> ToolCallResult:
        """Validate, authorize, execute and normalize a single tool call."""
        request_id = request.request_id
        tool_id = (request.tool_id or "").strip()

        # 1. Structural request validation.
        if not tool_id:
            return self._normalizer.failure(
                tool_id="unknown",
                request_id=request_id,
                status=ToolCallStatus.INVALID_REQUEST,
                error_code="INVALID_TOOL_REQUEST",
                message="tool_id is required.",
            )

        # 2. Resolve tool via registry.
        if not self._registry.has(tool_id):
            return self._normalizer.from_exception(
                tool_id, request_id, _not_found(tool_id)
            )

        definition = self._registry.get_definition(tool_id)

        # 3. Availability check.
        if not definition.available:
            exc = ToolUnavailableError(tool_id, definition.unavailable_reason or "")
            return self._normalizer.from_exception(tool_id, request_id, exc)

        # 4. Permission enforcement.
        permission_error = self._check_permissions(definition, request)
        if permission_error is not None:
            return self._normalizer.from_exception(tool_id, request_id, permission_error)

        # 5. Request size limit.
        try:
            enforce_payload_limit(
                request.arguments,
                definition.execution.max_request_bytes,
                label="tool request",
            )
        except ValueError as exc:
            return self._normalizer.from_exception(
                tool_id,
                request_id,
                ToolPayloadLimitExceededError(str(exc), tool_id=tool_id),
            )

        tool = self._registry.get(tool_id)

        # 6. Argument validation via the tool's own validator.
        try:
            cleaned_arguments = tool.validate_arguments(dict(request.arguments or {}))
        except Exception as exc:
            if hasattr(exc, "error_contract"):
                return self._normalizer.from_exception(tool_id, request_id, exc)
            return self._normalizer.from_exception(
                tool_id,
                request_id,
                ToolValidationError(sanitize_error_message(str(exc)), tool_id=tool_id),
            )

        # 7. Dry-run short circuit (validate + route without executing).
        if request.dry_run:
            return self._normalizer.success(
                tool_id,
                request_id,
                payload={"dry_run": True, "validated_arguments": cleaned_arguments},
                execution=ToolExecutionMetadata(provider=tool_id),
                status=ToolCallStatus.SUCCESS,
            )

        # 8. Execute via the execution manager.
        try:
            raw_result, execution_meta = self._execution.execute(
                definition,
                request,
                lambda: tool.execute(cleaned_arguments, request),
            )
        except Exception as exc:
            return self._normalizer.from_exception(tool_id, request_id, exc)

        # 9. Normalize the raw result. Tools may return either a bare payload or
        #    a (payload, sources, warnings) triple.
        payload, sources, warnings, partial = self._unpack_result(raw_result)

        # 10. Result size limit.
        result_bytes = payload_size_bytes(payload)
        if result_bytes > definition.execution.max_result_bytes:
            return self._normalizer.failure(
                tool_id,
                request_id,
                status=ToolCallStatus.PAYLOAD_LIMIT_EXCEEDED,
                error_code="TOOL_PAYLOAD_LIMIT_EXCEEDED",
                message=(
                    f"tool result size {result_bytes} bytes exceeds limit of "
                    f"{definition.execution.max_result_bytes} bytes"
                ),
                execution=execution_meta,
            )

        return self._normalizer.success(
            tool_id,
            request_id,
            payload=payload,
            sources=sources,
            execution=execution_meta,
            warnings=warnings,
            status=ToolCallStatus.PARTIAL if partial else ToolCallStatus.SUCCESS,
        )

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _check_permissions(definition, request: ToolCallRequest) -> Optional[ToolPermissionError]:
        required = {p.value for p in definition.required_permissions}
        if not required:
            return None
        granted = {p.value for p in request.permissions}
        if _ADMIN_PERMISSION in granted:
            return None
        missing = required - granted
        if missing:
            return ToolPermissionError(
                definition.tool_id,
                required_permissions=sorted(required),
                details=f"Missing required permissions: {sorted(missing)}.",
            )
        return None

    @staticmethod
    def _unpack_result(raw_result):
        """Return (payload, sources, warnings, partial)."""
        from core.schemas.tools import ToolSourceReference

        payload = raw_result
        sources = []
        warnings = []
        partial = False

        if isinstance(raw_result, dict) and raw_result.get("__tool_result__") is True:
            payload = raw_result.get("payload")
            partial = bool(raw_result.get("partial", False))
            for item in raw_result.get("sources", []) or []:
                sources.append(
                    item if isinstance(item, ToolSourceReference) else ToolSourceReference(**item)
                )
            warnings = list(raw_result.get("warnings", []) or [])
        return payload, sources, warnings, partial


def _not_found(tool_id: str):
    from core.errors.exceptions import ToolNotFoundError

    return ToolNotFoundError(tool_id)
