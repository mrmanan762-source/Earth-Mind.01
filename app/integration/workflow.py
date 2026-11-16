"""Phase 4 integrated application workflow.

This is the single place that composes the end-to-end flow:

    farmer request -> normalise -> tool selection -> B5 orchestration
    (B2 context [memory + RAG + satellite + tool evidence] -> B3 reasoning ->
    B4 planning/decision -> Inspector validation) -> ULPU language handling ->
    structured ApplicationResponse.

B5 remains the sole workflow coordinator: this module only builds the request
and the workflow step graph (via B5's own CUSTOM composition) and assembles the
final response. It contains no agricultural reasoning, planning, retrieval or
language logic, and it never calls tools directly — the Tool Dispatcher does,
through the B5 tools step.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from core.errors.exceptions import EarthMindException
from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest, ApplicationResponse
from modules.orchestrator.enums import (
    FailureHandlingPolicy,
    StepExecutionState,
    WorkflowStrategyType,
)
from modules.orchestrator.schemas import (
    OrchestrationPolicyConfig,
    OrchestrationRequest,
    OrchestrationResponse,
    ScopeContext,
)

from app.integration.capabilities import ToolEvidenceBuffer, build_default_permissions
from app.integration.tool_selection import resolve_trusted_tool_metadata, select_tool_calls

logger = get_logger("app.integration.workflow")

_SUPPORTED_OPERATIONS = (
    "process_request",
    "farmer_request",
    "process_farmer_request",
    "run",
    "process_text",
)

_PLANNING_HINTS = (
    "plan",
    "planning",
    "schedule",
    "advice",
    "advise",
    "recommend",
    "should i",
    "what should",
    "how to",
    "how do i",
    "management",
    "treatment",
    "control",
    "dose",
    "dosage",
    "fertilizer",
    "fertiliser",
    "irrigation",
    "sow",
    "plant",
    "spray",
    "strategy",
    "improve",
    "increase yield",
)


def _has_non_latin(text: str) -> bool:
    return any(ord(ch) > 127 for ch in (text or ""))


class IntegratedWorkflow:
    """Coordinates the completed EarthMind modules through B5."""

    def __init__(
        self,
        orchestrator: Any,
        tool_buffer: ToolEvidenceBuffer,
        *,
        ulpu_service: Optional[Any] = None,
        default_language: str = "en",
        max_seen_requests: int = 2048,
    ) -> None:
        self._orchestrator = orchestrator
        self._buffer = tool_buffer
        self._ulpu = ulpu_service
        self._default_language = default_language
        self._seen_requests: Dict[str, bool] = {}
        self._max_seen = max_seen_requests

    # -- public API --------------------------------------------------------

    def run(self, request: ApplicationRequest) -> ApplicationResponse:
        """Execute the integrated workflow for a farmer request."""
        request_id = request.request_id or f"req_{uuid.uuid4().hex[:12]}"

        # 1. Duplicate request protection (bounded, in-memory).
        if request_id in self._seen_requests:
            return ApplicationResponse(
                request_id=request_id,
                status="FAILED",
                response=None,
                warnings=[f"Request '{request_id}' was already processed (duplicate request)."],
                metadata={"duplicate_request": True},
            )
        self._remember(request_id)

        try:
            return self._run_internal(request, request_id)
        except EarthMindException as exc:
            logger.error("Integrated workflow controlled failure for %s: %s", request_id, exc)
            return ApplicationResponse(
                request_id=request_id,
                status="FAILED",
                response=None,
                warnings=[exc.error_contract.message],
                metadata={"error_contract": exc.error_contract.model_dump()},
            )
        except Exception as exc:  # defensive: never leak a stack trace to the caller
            logger.error("Integrated workflow unexpected failure for %s: %s", request_id, exc)
            return ApplicationResponse(
                request_id=request_id,
                status="FAILED",
                response=None,
                warnings=["The request could not be completed."],
            )
        finally:
            self._buffer.clear(request_id)

    # -- internals ---------------------------------------------------------

    def _remember(self, request_id: str) -> None:
        if len(self._seen_requests) >= self._max_seen:
            for key in list(self._seen_requests.keys())[: self._max_seen // 4]:
                self._seen_requests.pop(key, None)
        self._seen_requests[request_id] = True

    def _run_internal(self, request: ApplicationRequest, request_id: str) -> ApplicationResponse:
        payload = request.payload if isinstance(request.payload, dict) else {"prompt": request.payload}
        metadata = request.metadata or {}

        # 1. Validate and normalise the request.
        task = self._extract_task(payload)
        if not task:
            return ApplicationResponse(
                request_id=request_id,
                status="INVALID_REQUEST",
                response=None,
                warnings=["A non-empty 'prompt', 'task' or 'query' is required."],
            )

        # 2. Preserve original language / relevant user context.
        scope = self._extract_scope(payload, metadata)
        language = payload.get("language") or metadata.get("language") or self._default_language

        # 3. Determine which tools (if any) this request requires.
        selected_tools = select_tool_calls(task, payload, scope)

        # 4. Record trusted tool metadata (permissions never come from the payload).
        trusted = resolve_trusted_tool_metadata(metadata, build_default_permissions())
        self._buffer.set_trusted(request_id, trusted)

        # 5. Build the B5 workflow composition for this request.
        steps = self._compose_steps(task, payload, language, selected_tools)

        # 6. Build the orchestration request (B5 owns coordination).
        policy = OrchestrationPolicyConfig(
            timeout_seconds=float(metadata.get("timeout_seconds", 60.0)),
            max_rechecks=int(metadata.get("max_rechecks", 2)),
            allow_partial_results=True,
            require_inspector=True,
        )
        orch_request = OrchestrationRequest(
            request_id=request_id,
            strategy=WorkflowStrategyType.CUSTOM,
            payload={
                **payload,
                "task": task,
                "prompt": task,
                "selected_tool_calls": selected_tools,
                "custom_steps": steps,
            },
            scope=ScopeContext(**scope),
            policy=policy,
            metadata={**metadata, **{k: v for k, v in scope.items() if v}},
        )

        orch_response: OrchestrationResponse = self._orchestrator.orchestrate(orch_request)
        return self._build_response(request_id, task, language, orch_response, selected_tools)

    def _compose_steps(
        self,
        task: str,
        payload: Dict[str, Any],
        language: str,
        selected_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        steps: List[Dict[str, Any]] = []
        context_deps: List[str] = []

        # Optional ULPU language step for multilingual input.
        wants_ulpu = (
            language not in ("en", "eng", "")
            or bool(payload.get("process_language"))
            or _has_non_latin(task)
        )
        if wants_ulpu and self._ulpu is not None:
            steps.append(
                {
                    "step_id": "step_ulpu",
                    "capability_id": "ulpu",
                    "operation": "process_language",
                    "dependencies": [],
                    "is_required": False,
                    "failure_policy": FailureHandlingPolicy.CONTINUE_ON_PARTIAL,
                }
            )
            context_deps.append("step_ulpu")

        # Optional tools step — only when the request actually requires tools.
        if selected_tools:
            steps.append(
                {
                    "step_id": "step_tools",
                    "capability_id": "tools",
                    "operation": "execute_tool",
                    "dependencies": [],
                    "is_required": False,
                    "failure_policy": FailureHandlingPolicy.CONTINUE_ON_PARTIAL,
                }
            )
            context_deps.append("step_tools")

        # Required context preparation (B2) — consumes memory/RAG/satellite/tool evidence.
        steps.append(
            {
                "step_id": "step_context",
                "capability_id": "context",
                "operation": "prepare_context",
                "dependencies": list(context_deps),
                "is_required": True,
            }
        )

        # Required reasoning (B3).
        steps.append(
            {
                "step_id": "step_reasoning",
                "capability_id": "reasoning",
                "operation": "reason",
                "dependencies": ["step_context"],
                "is_required": True,
            }
        )

        # Planning / decision support (B4) — included when the request needs advice.
        if self._requires_planning(task, payload):
            steps.append(
                {
                    "step_id": "step_planning",
                    "capability_id": "planning",
                    "operation": "execute_planning",
                    "dependencies": ["step_reasoning"],
                    "is_required": True,
                }
            )
            steps.append(
                {
                    "step_id": "step_inspector",
                    "capability_id": "inspector",
                    "operation": "validate_action",
                    "dependencies": ["step_planning"],
                    "is_required": True,
                }
            )

        return steps

    @staticmethod
    def _requires_planning(task: str, payload: Dict[str, Any]) -> bool:
        if isinstance(payload.get("planning"), bool):
            return bool(payload["planning"])
        lowered = (task or "").lower()
        return any(hint in lowered for hint in _PLANNING_HINTS)

    @staticmethod
    def _extract_task(payload: Dict[str, Any]) -> str:
        for key in ("prompt", "task", "query", "question", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _extract_scope(payload: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        meta_scope = metadata.get("scope") if isinstance(metadata.get("scope"), dict) else {}
        payload_scope = payload.get("scope") if isinstance(payload.get("scope"), dict) else {}
        merged: Dict[str, Any] = {}
        for key in ("farmer_id", "farm_id", "field_id", "crop_cycle_id", "session_id"):
            merged[key] = (
                payload.get(key)
                or payload_scope.get(key)
                or metadata.get(key)
                or meta_scope.get(key)
            )
        return merged

    def _build_response(
        self,
        request_id: str,
        task: str,
        language: str,
        orch_response: OrchestrationResponse,
        selected_tools: List[Dict[str, Any]],
    ) -> ApplicationResponse:
        capability_results = orch_response.capability_results or {}

        context = self._step_output(capability_results, "step_context")
        reasoning = self._step_output(capability_results, "step_reasoning")
        planning = self._step_output(capability_results, "step_planning")
        tools_step = self._step_output(capability_results, "step_tools")
        ulpu_step = self._step_output(capability_results, "step_ulpu")

        tool_failures = tools_step.get("failed_tools", []) if isinstance(tools_step, dict) else []
        warnings = list(orch_response.warnings or [])
        for failed_tool in tool_failures:
            warnings.append(
                f"Optional tool '{failed_tool}' did not complete; continuing with partial results."
            )

        summary_text = self._summarise(task, reasoning, planning)

        # Apply ULPU language handling for non-English responses.
        localized_text, language_meta = self._localize(summary_text, language, ulpu_step)

        response_body = {
            "summary": localized_text,
            "language": language_meta,
            "task": task,
            "evidence": self._summarise_context(context),
            "reasoning": reasoning,
            "planning": planning,
            "tools": {
                "requested": [t.get("tool_id") for t in selected_tools],
                "results": tools_step.get("tool_results", []) if isinstance(tools_step, dict) else [],
                "failed": tool_failures,
            },
            "workflow": {
                "workflow_id": orch_response.workflow_id,
                "execution_id": orch_response.execution_id,
                "workflow_state": orch_response.workflow_state.value,
                "step_statuses": {
                    step_id: res.status.value for step_id, res in capability_results.items()
                },
            },
        }

        status = self._map_status(orch_response.status)

        return ApplicationResponse(
            request_id=request_id,
            status=status,
            response=response_body,
            warnings=warnings,
            metadata={
                "workflow_id": orch_response.workflow_id,
                "execution_id": orch_response.execution_id,
                "workflow_state": orch_response.workflow_state.value,
                "partial": orch_response.status == "PARTIAL",
            },
        )

    @staticmethod
    def _step_output(capability_results: Dict[str, Any], step_id: str) -> Any:
        res = capability_results.get(step_id)
        if res is None or res.status != StepExecutionState.COMPLETED:
            return None
        return res.output

    @staticmethod
    def _summarise(task: str, reasoning: Any, planning: Any) -> str:
        parts: List[str] = []
        if isinstance(reasoning, dict):
            result = reasoning.get("result") or {}
            findings = result.get("findings") or []
            if findings:
                statement = str(findings[0].get("statement", "")).strip()
                if statement:
                    parts.append(statement)
        if isinstance(planning, dict):
            decision = planning.get("decision") or {}
            selected = decision.get("selected_plan") or {}
            if selected:
                parts.append(
                    f"Recommended plan: {selected.get('name', 'plan')} "
                    f"(feasibility: {selected.get('feasibility_state', 'UNKNOWN')})."
                )
        if not parts:
            return f"Processed request: {task}"
        return " ".join(parts)

    @staticmethod
    def _summarise_context(context: Any) -> Dict[str, Any]:
        if not isinstance(context, dict):
            return {"item_count": 0, "sources": []}
        items = context.get("items") or []
        sources = sorted(
            {item.get("source") for item in items if isinstance(item, dict) and item.get("source")}
        )
        return {
            "item_count": len(items),
            "sources": sources,
            "state": context.get("state"),
        }

    def _localize(
        self, text: str, language: str, ulpu_step: Any
    ) -> Tuple[str, Dict[str, Any]]:
        detected = language
        if isinstance(ulpu_step, dict) and ulpu_step.get("detected_language"):
            detected = ulpu_step["detected_language"]

        meta: Dict[str, Any] = {"detected": detected, "localized": False}
        if self._ulpu is None or detected in ("en", "eng", ""):
            return text, meta
        try:
            from core.schemas.ulpu import TranslationRequest

            translator = self._ulpu.provider_registry.get_provider("translation")
            if translator is None or not getattr(translator, "is_available", lambda: False)():
                return text, meta
            result = translator.translate(
                TranslationRequest(text=text, source_language="en", target_language=detected)
            )
            meta["localized"] = True
            meta["target_language"] = detected
            return result.translated_text, meta
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("ULPU response localization failed: %s", exc)
            return text, meta

    @staticmethod
    def _map_status(orch_status: str) -> str:
        mapping = {
            "SUCCESS": "SUCCESS",
            "PARTIAL": "PARTIAL",
            "FAILED": "FAILED",
            "ERROR": "FAILED",
            "CANCELLED": "FAILED",
        }
        return mapping.get(orch_status, "FAILED")


class IntegratedApplicationModule:
    """ModuleInterface entry point exposing the integrated workflow to the app."""

    module_name = "application"

    def __init__(self, workflow: IntegratedWorkflow) -> None:
        self._workflow = workflow
        self._is_initialized = False

    def initialize(self) -> None:
        self._is_initialized = True
        logger.info("Integrated Application module initialized.")

    def shutdown(self) -> None:
        self._is_initialized = False
        logger.info("Integrated Application module shut down.")

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        operation = (request.operation or "").lower().strip()
        if operation not in _SUPPORTED_OPERATIONS:
            return ApplicationResponse(
                request_id=request.request_id,
                status="UNSUPPORTED_OPERATION",
                response=None,
                warnings=[f"Unsupported application operation '{request.operation}'."],
            )
        return self._workflow.run(request)
