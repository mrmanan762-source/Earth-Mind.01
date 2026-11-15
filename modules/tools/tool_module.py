"""ToolModule: EarthMind ModuleInterface entry point for the tool infrastructure.

Exposes the backend tool system to the existing application lifecycle and B5
workflow dispatch without introducing a second workflow orchestrator. The module
accepts a single tool call per request and returns the normalized result inside
the standard `ApplicationResponse` contract.

Permission handling:
- Permission grants are read ONLY from trusted `request.metadata`
  (e.g. `granted_permissions`), never from the (potentially model-generated)
  `request.payload`. This prevents a model from self-granting permissions.
- When no grants are supplied, a conservative default policy is applied.
"""

from typing import Any, Dict, List, Optional

from core.errors.exceptions import InvalidToolRequestError
from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest, ApplicationResponse
from core.schemas.tools import ToolCallRequest, ToolPermission
from modules.tools.tool_service import ToolService

logger = get_logger("modules.tools.module")

# Default permissions granted to trusted internal (non-model) callers.
_DEFAULT_INTERNAL_PERMISSIONS = (
    ToolPermission.COMPUTE,
    ToolPermission.WEB_SEARCH,
    ToolPermission.EXTERNAL_NETWORK,
    ToolPermission.WEATHER_DATA,
    ToolPermission.SATELLITE_DATA,
    ToolPermission.READ_ONLY,
)


class ToolModule:
    """Module entry point exposing the tool infrastructure to EarthMind."""

    module_name = "tools"

    def __init__(self, service: Optional[ToolService] = None):
        self._service = service or ToolService()
        self._is_initialized = False

    @property
    def service(self) -> ToolService:
        return self._service

    def initialize(self) -> None:
        logger.info("Initializing Tool Infrastructure Module (Phase 3)...")
        self._service.refresh_availability()
        self._is_initialized = True
        report = self._service.health_report()
        logger.info(
            "Tool module initialized: %s/%s tools available.",
            report["available_tools"],
            report["registered_tools"],
        )

    def shutdown(self) -> None:
        logger.info("Shutting down Tool Infrastructure Module...")
        self._service.shutdown()
        self._is_initialized = False

    def health_check(self) -> Dict[str, Any]:
        report = self._service.health_report()
        report["initialized"] = self._is_initialized
        return report

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        operation = (request.operation or "").lower().strip()
        payload = request.payload or {}
        metadata = request.metadata or {}

        try:
            if operation in ("health_check", "health"):
                return ApplicationResponse(
                    request_id=request.request_id, status="SUCCESS", response=self.health_check()
                )

            if operation in ("list_tools", "tools"):
                only_available = bool(metadata.get("only_available", False))
                descriptors = self._service.list_tools(only_available=only_available)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=[d.model_dump(mode="json") for d in descriptors],
                )

            if operation in ("execute_tool", "call_tool", "invoke_tool"):
                return self._handle_execute(request, payload, metadata)

            return ApplicationResponse(
                request_id=request.request_id,
                status="UNKNOWN_OPERATION",
                warnings=[f"Unsupported tool operation '{request.operation}'."],
            )
        except InvalidToolRequestError as exc:
            return ApplicationResponse(
                request_id=request.request_id,
                status="INVALID_REQUEST",
                warnings=[exc.error_contract.message],
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Tool module error for request %s: %s", request.request_id, exc)
            return ApplicationResponse(
                request_id=request.request_id,
                status="ERROR",
                warnings=["Tool execution failed."],
            )

    def _handle_execute(
        self, request: ApplicationRequest, payload: Dict[str, Any], metadata: Dict[str, Any]
    ) -> ApplicationResponse:
        if not isinstance(payload, dict):
            raise InvalidToolRequestError("Tool execute payload must be an object.")

        tool_id = payload.get("tool_id")
        if not isinstance(tool_id, str) or not tool_id.strip():
            raise InvalidToolRequestError("'tool_id' is required to execute a tool.")

        # Permissions are trusted metadata ONLY (never payload / model output).
        permissions = self._resolve_permissions(metadata)

        tool_request = ToolCallRequest(
            tool_id=tool_id.strip(),
            request_id=request.request_id,
            arguments=payload.get("arguments", {}) or {},
            caller=metadata.get("caller"),
            permissions=permissions,
            source=metadata.get("tool_source", request.source or "internal"),
            timeout_override=payload.get("timeout_override"),
            dry_run=bool(payload.get("dry_run", False)),
            metadata=metadata,
        )

        result = self._service.execute(tool_request)
        status = "SUCCESS" if result.ok else _map_status(result.status.value)
        return ApplicationResponse(
            request_id=request.request_id,
            status=status,
            response=result.to_public_dict(),
            warnings=list(result.warnings),
            metadata={"tool_id": result.tool_id, "tool_status": result.status.value},
        )

    @staticmethod
    def _resolve_permissions(metadata: Dict[str, Any]) -> List[ToolPermission]:
        raw = metadata.get("granted_permissions")
        if raw is None:
            return list(_DEFAULT_INTERNAL_PERMISSIONS)
        permissions: List[ToolPermission] = []
        for item in raw:
            try:
                permissions.append(item if isinstance(item, ToolPermission) else ToolPermission(str(item)))
            except ValueError:
                continue
        return permissions


def _map_status(tool_status: str) -> str:
    if tool_status in ("NOT_FOUND", "UNAVAILABLE"):
        return "NOT_FOUND" if tool_status == "NOT_FOUND" else "UNAVAILABLE"
    if tool_status == "PERMISSION_DENIED":
        return "FORBIDDEN"
    if tool_status in ("INVALID_REQUEST", "VALIDATION_ERROR"):
        return "INVALID_REQUEST"
    if tool_status == "TIMEOUT":
        return "TIMEOUT"
    return "ERROR"
