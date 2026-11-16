"""Typed B5 ``ICapability`` adapters for the EarthMind Phase 4 integration.

Each adapter translates a B5 workflow step invocation (operation + merged step
payload + trusted metadata) into the *established* contract of the module it
fronts. The adapters contain no agricultural reasoning, planning, retrieval or
language logic of their own: they only marshal data between B5 and the modules.

Boundaries preserved:
- B2 prepares context only (``B2ContextCapability``).
- B3 analyses evidence only (``B3ReasoningCapability``).
- B4 owns planning/decision support only (``B4PlanningCapability``).
- Inspector validates only (``InspectorCapability``).
- Memory stores/retrieves authorised user context only (``MemoryCapability``).
- ULPU performs language handling only (``ULPUCapability``).
- Satellite supplies geospatial evidence only (``SatelliteCapability``).
- Tools execute single atomic operations only (``ToolExecutionCapability``);
  B5 keeps workflow coordination and the Tool Dispatcher keeps routing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.errors.exceptions import EarthMindException
from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest
from core.schemas.tools import ToolCallRequest, ToolCallResult, ToolPermission
from modules.context.boundary.models import MemoryContextRequest
from modules.context.schemas import ContextRequest, ContextResult, PolicyConfig
from modules.orchestrator.interfaces import ICapability
from modules.orchestrator.schemas import CapabilityMetadata
from modules.planning.schemas import Goal, PlanningInput, PlanningResult
from modules.reasoning.schemas import ReasoningInput, ReasoningResult

logger = get_logger("app.integration.capabilities")


def _as_dict(value: Any) -> Any:
    """Best-effort conversion of pydantic models / dataclasses to plain dicts."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    if isinstance(value, (list, tuple)):
        return [_as_dict(v) for v in value]
    return value


def _reconstruct(model_cls: Any, payload: Any) -> Any:
    """Rebuild a pydantic model from a dict produced by ``_as_dict``."""
    if payload is None:
        return None
    if isinstance(payload, model_cls):
        return payload
    if isinstance(payload, dict):
        return model_cls.model_validate(payload)
    return None


class ToolEvidenceBuffer:
    """Request-scoped buffer carrying tool results and trusted caller metadata.

    The tools capability writes normalised tool results here and the B2 tool
    evidence provider reads them, so tool output reaches B2 through the
    established provider interface without B5 duplicating the Dispatcher.
    Trusted metadata (permissions) is stored separately and never taken from the
    (potentially model-generated) step payload.
    """

    def __init__(self) -> None:
        self._results: Dict[str, List[ToolCallResult]] = {}
        self._trusted: Dict[str, Dict[str, Any]] = {}

    def set_trusted(self, request_id: str, trusted: Dict[str, Any]) -> None:
        self._trusted[request_id] = dict(trusted or {})

    def get_trusted(self, request_id: str) -> Dict[str, Any]:
        return self._trusted.get(request_id, {})

    def record_results(self, request_id: str, results: List[ToolCallResult]) -> None:
        self._results[request_id] = list(results)

    def get_results(self, request_id: str) -> List[ToolCallResult]:
        return list(self._results.get(request_id, []))

    def clear(self, request_id: str) -> None:
        self._results.pop(request_id, None)
        self._trusted.pop(request_id, None)


class _BaseCapability(ICapability):
    """Shared metadata plumbing for typed B5 capabilities."""

    def __init__(self, capability_id: str, supported_operations: List[str]) -> None:
        self.capability_id = capability_id
        self.version = "1.0.0"
        self.interface_name = type(self).__name__
        self.supported_operations = supported_operations

    def get_metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            capability_id=self.capability_id,
            version=self.version,
            interface_name=self.interface_name,
            supported_operations=list(self.supported_operations),
        )

    def execute(
        self,
        operation: str,
        payload: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:  # pragma: no cover - overridden
        raise NotImplementedError


class B2ContextCapability(_BaseCapability):
    """Fronts the B2 Context Manager (``prepare_context`` only)."""

    def __init__(self, context_manager: Any) -> None:
        super().__init__("context", ["prepare_context"])
        self._manager = context_manager

    def execute(self, operation: str, payload: Any, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if operation != "prepare_context":
            return {"status": "UNSUPPORTED_OPERATION", "operation": operation}

        data = payload if isinstance(payload, dict) else {}
        meta = metadata or {}
        scope = meta.get("scope", {}) if isinstance(meta.get("scope"), dict) else {}

        policy_dict = data.get("policy") if isinstance(data.get("policy"), dict) else {}
        policy = PolicyConfig(**policy_dict) if policy_dict else PolicyConfig()

        request = ContextRequest(
            request_id=meta.get("request_id") or data.get("request_id") or "ctx_req",
            farmer_id=data.get("farmer_id") or scope.get("farmer_id"),
            farm_id=data.get("farm_id") or scope.get("farm_id"),
            field_id=data.get("field_id") or scope.get("field_id"),
            crop_cycle_id=data.get("crop_cycle_id") or scope.get("crop_cycle_id"),
            session_id=data.get("session_id") or scope.get("session_id"),
            task=data.get("task") or data.get("prompt") or data.get("query"),
            requested_context_types=data.get("requested_context_types", []) or [],
            token_limit=int(data.get("token_limit", 4096)),
            relevance_threshold=float(data.get("relevance_threshold", 0.5)),
            policy=policy,
            trace_id=meta.get("trace_id") or data.get("trace_id"),
        )

        result: ContextResult = self._manager.prepare_context(request)
        return _as_dict(result)


class B3ReasoningCapability(_BaseCapability):
    """Fronts the B3 Reasoning Engine (``reason`` only)."""

    def __init__(self, reasoning_module: Any) -> None:
        super().__init__("reasoning", ["reason"])
        self._module = reasoning_module

    def execute(self, operation: str, payload: Any, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if operation not in ("reason", "analyze"):
            return {"status": "UNSUPPORTED_OPERATION", "operation": operation}

        data = payload if isinstance(payload, dict) else {}
        meta = metadata or {}

        prepared_context = _reconstruct(ContextResult, data.get("dep_step_context") or data.get("prepared_context"))

        task = data.get("task") or data.get("prompt") or data.get("query") or "Analyse available evidence"

        reasoning_input = ReasoningInput(
            request_id=meta.get("request_id") or data.get("request_id") or "reason_req",
            task=task,
            prepared_context=prepared_context,
            trace_id=meta.get("trace_id") or data.get("trace_id"),
        )

        result, handoff = self._module.reason(reasoning_input)
        return {
            "result": _as_dict(result),
            "handoff": _as_dict(handoff),
            "status": "SUCCESS",
        }


class B4PlanningCapability(_BaseCapability):
    """Fronts the B4 Planning & Decision Engine (``execute_planning`` only)."""

    def __init__(self, planning_module: Any) -> None:
        super().__init__("planning", ["execute_planning"])
        self._module = planning_module

    def execute(self, operation: str, payload: Any, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if operation not in ("execute_planning", "plan"):
            return {"status": "UNSUPPORTED_OPERATION", "operation": operation}

        data = payload if isinstance(payload, dict) else {}
        meta = metadata or {}

        reasoning_result: Optional[ReasoningResult] = None
        reasoning_dep = data.get("dep_step_reasoning")
        if isinstance(reasoning_dep, dict):
            reasoning_result = _reconstruct(ReasoningResult, reasoning_dep.get("result"))
        if reasoning_result is None:
            reasoning_result = _reconstruct(ReasoningResult, data.get("reasoning_result"))

        goal_text = (
            data.get("goal")
            or data.get("objective")
            or data.get("task")
            or data.get("prompt")
            or "Support decision for the farmer request"
        )

        planning_input = PlanningInput(
            request_id=meta.get("request_id") or data.get("request_id") or "plan_req",
            objective=Goal(goal_id=f"goal_{meta.get('request_id', 'req')}", objective=str(goal_text)),
            reasoning_result=reasoning_result,
            relevant_context=data.get("relevant_context"),
            trace_id=meta.get("trace_id") or data.get("trace_id"),
            metadata=meta,
        )

        result: PlanningResult = self._module.execute_planning(planning_input)
        return _as_dict(result)


class InspectorCapability(_BaseCapability):
    """Fronts the Inspector validation service (``validate_action`` only)."""

    def __init__(self, inspector_module: Any) -> None:
        super().__init__("inspector", ["validate_action"])
        self._module = inspector_module

    def execute(self, operation: str, payload: Any, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if operation != "validate_action":
            return {"status": "UNSUPPORTED_OPERATION", "operation": operation}
        data = payload if isinstance(payload, dict) else {}
        response = self._module.validate_action("orchestration_validation", data)
        if isinstance(response, dict):
            response.setdefault("status", "PASS")
            return response
        return {"status": "PASS"}


class MemoryCapability(_BaseCapability):
    """Fronts the Memory context provider for B5 (``retrieve_memory`` only)."""

    def __init__(self, memory_provider: Any) -> None:
        super().__init__("memory", ["retrieve_memory"])
        self._provider = memory_provider

    def execute(self, operation: str, payload: Any, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if operation != "retrieve_memory":
            return {"status": "UNSUPPORTED_OPERATION", "operation": operation}

        data = payload if isinstance(payload, dict) else {}
        meta = metadata or {}
        scope = meta.get("scope", {}) if isinstance(meta.get("scope"), dict) else {}

        farmer_id = data.get("farmer_id") or scope.get("farmer_id")
        try:
            contracts = self._provider.get_memory_context(
                MemoryContextRequest(
                    request_id=meta.get("request_id") or data.get("request_id") or "mem_req",
                    farmer_id=farmer_id,
                    farm_id=data.get("farm_id") or scope.get("farm_id"),
                    field_id=data.get("field_id") or scope.get("field_id"),
                    crop_cycle_id=data.get("crop_cycle_id") or scope.get("crop_cycle_id"),
                    session_id=data.get("session_id") or scope.get("session_id"),
                    query_text=data.get("task") or data.get("prompt"),
                    allow_pii=bool((data.get("policy") or {}).get("allow_pii", False))
                    if isinstance(data.get("policy"), dict)
                    else False,
                    trace_id=meta.get("trace_id") or data.get("trace_id"),
                )
            )
        except EarthMindException as exc:
            # Memory is an optional input; a failure must not break the workflow.
            logger.warning("Memory capability retrieval failed: %s", exc)
            return {"status": "UNAVAILABLE", "contracts": [], "warning": str(exc)}

        return {"status": "SUCCESS", "contracts": [_as_dict(c) for c in contracts]}


class ULPUCapability(_BaseCapability):
    """Fronts ULPU language handling (``process_language`` only)."""

    def __init__(self, ulpu_service: Any) -> None:
        super().__init__("ulpu", ["process_language"])
        self._service = ulpu_service

    def execute(self, operation: str, payload: Any, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if operation != "process_language":
            return {"status": "UNSUPPORTED_OPERATION", "operation": operation}
        data = payload if isinstance(payload, dict) else {}
        meta = metadata or {}
        text = data.get("task") or data.get("prompt") or data.get("query") or ""
        try:
            from core.schemas.ulpu import LanguageDetectionRequest

            detection = self._service.provider_registry.get_provider("language_detection").detect_language(
                LanguageDetectionRequest(text=text)
            )
            return {
                "status": "SUCCESS",
                "detected_language": detection.detected_language,
                "script": detection.script.value if hasattr(detection.script, "value") else str(detection.script),
                "confidence": detection.confidence,
                "request_id": meta.get("request_id"),
            }
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("ULPU capability failed: %s", exc)
            return {"status": "UNAVAILABLE", "warning": str(exc)}


class SatelliteCapability(_BaseCapability):
    """Fronts the Satellite Intelligence module adapter (catalog/health only)."""

    def __init__(self, satellite_module: Any) -> None:
        super().__init__("satellite", ["search_catalog", "health_check"])
        self._module = satellite_module

    def execute(self, operation: str, payload: Any, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if operation not in ("search_catalog", "health_check"):
            return {"status": "UNSUPPORTED_OPERATION", "operation": operation}
        data = payload if isinstance(payload, dict) else {}
        meta = metadata or {}
        try:
            response = self._module.handle(
                ApplicationRequest(
                    request_id=meta.get("request_id") or "sat_req",
                    source="orchestrator",
                    operation=operation,
                    payload=data,
                    metadata=meta,
                )
            )
            return {"status": response.status, "response": response.response}
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Satellite capability failed: %s", exc)
            return {"status": "UNAVAILABLE", "warning": str(exc)}


class ToolExecutionCapability(_BaseCapability):
    """Fronts the Tool Dispatcher (single atomic tool calls only).

    Executes the tool calls selected for the request through the existing
    ``ToolService`` dispatcher, records the normalised results into the shared
    ``ToolEvidenceBuffer`` (for B2), and returns a structured summary. The step
    never raises: individual tool failures are isolated and reported.
    """

    def __init__(self, tool_service: Any, buffer: ToolEvidenceBuffer) -> None:
        super().__init__("tools", ["execute_tool"])
        self._service = tool_service
        self._buffer = buffer

    def execute(self, operation: str, payload: Any, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if operation not in ("execute_tool", "call_tool"):
            return {"status": "UNSUPPORTED_OPERATION", "operation": operation}

        data = payload if isinstance(payload, dict) else {}
        meta = metadata or {}
        request_id = meta.get("request_id") or data.get("request_id") or "tool_req"

        trusted = self._buffer.get_trusted(request_id)
        permissions = trusted.get("granted_permissions") or []
        source = trusted.get("tool_source") or "integrated_workflow"

        selected = data.get("selected_tool_calls") or []
        results: List[ToolCallResult] = []
        for spec in selected:
            if not isinstance(spec, dict):
                continue
            tool_id = spec.get("tool_id")
            if not tool_id:
                continue
            tool_request = ToolCallRequest(
                tool_id=str(tool_id),
                request_id=f"{request_id}:{tool_id}",
                arguments=spec.get("arguments", {}) or {},
                permissions=list(permissions),
                source=source,
                metadata={"request_id": request_id, "trusted_metadata": trusted},
            )
            try:
                results.append(self._service.execute(tool_request))
            except Exception as exc:  # defensive: keep the workflow alive
                logger.warning("Tool '%s' raised during dispatch: %s", tool_id, exc)

        self._buffer.record_results(request_id, results)

        return {
            "status": "SUCCESS",
            "request_id": request_id,
            "tool_results": [r.to_public_dict() for r in results],
            "tool_count": len(results),
            "failed_tools": [r.tool_id for r in results if not r.ok],
        }


def build_default_permissions() -> List[ToolPermission]:
    """Conservative internal default permission set (trusted callers only)."""
    return [
        ToolPermission.COMPUTE,
        ToolPermission.WEB_SEARCH,
        ToolPermission.EXTERNAL_NETWORK,
        ToolPermission.WEATHER_DATA,
        ToolPermission.SATELLITE_DATA,
        ToolPermission.READ_ONLY,
    ]
