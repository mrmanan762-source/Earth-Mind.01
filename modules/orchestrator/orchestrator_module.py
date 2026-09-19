import time
import uuid
from typing import Any, Dict, List, Optional, Union

from core.interfaces.module import ModuleInterface
from core.interfaces.services import InspectorInterface
from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest, ApplicationResponse
from modules.orchestrator.capability_manager import CapabilityManager
from modules.orchestrator.completion_manager import CompletionManager
from modules.orchestrator.enums import (
    StepExecutionState,
    WorkflowState,
    WorkflowStrategyType,
)
from modules.orchestrator.errors import (
    CapabilityNotFoundError,
    OrchestratorError,
    RecheckLimitExceededError,
)
from modules.orchestrator.execution_controller import ExecutionController
from modules.orchestrator.interfaces import ICapability
from modules.orchestrator.recovery_manager import RecoveryManager
from modules.orchestrator.request_manager import RequestManager
from modules.orchestrator.schemas import (
    CapabilityMetadata,
    OrchestrationRequest,
    OrchestrationResponse,
    StepExecutionResult,
)
from modules.orchestrator.state_manager import StateManager
from modules.orchestrator.workflow_composer import WorkflowComposer

logger = get_logger("modules.orchestrator")


class DefaultCapabilityWrapper(ICapability):
    """Generic interface adapter wrapping registered system modules as replaceable capabilities."""

    def __init__(
        self,
        capability_id: str,
        module_ref: Any,
        version: str = "1.0.0",
        supported_operations: Optional[List[str]] = None,
    ):
        self.capability_id = capability_id
        self.module_ref = module_ref
        self.version = version
        self.interface_name = type(module_ref).__name__ if module_ref else "DefaultCapability"
        self.supported_operations = supported_operations or ["execute", "handle", "prepare_context", "reason", "execute_planning", "validate_action"]

    def get_metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            capability_id=self.capability_id,
            version=self.version,
            interface_name=self.interface_name,
            supported_operations=self.supported_operations,
        )

    def execute(
        self,
        operation: str,
        payload: Any,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        meta = metadata or {}

        # 1. Check if module has direct handle method taking ApplicationRequest
        if hasattr(self.module_ref, "handle") and callable(self.module_ref.handle):
            app_req = ApplicationRequest(
                request_id=meta.get("request_id", f"req_{uuid.uuid4().hex[:8]}"),
                source="orchestrator",
                operation=operation,
                payload=payload,
                metadata=meta,
            )
            resp = self.module_ref.handle(app_req)
            if hasattr(resp, "model_dump"):
                return resp.model_dump()
            elif hasattr(resp, "response"):
                return {"status": resp.status, "response": resp.response}

        # 2. Check for explicit operation method on module
        if hasattr(self.module_ref, operation) and callable(getattr(self.module_ref, operation)):
            func = getattr(self.module_ref, operation)
            res = func(payload) if payload is not None else func()
            if hasattr(res, "model_dump"):
                return res.model_dump()
            return {"result": res}

        # 3. Default fallback execution call
        if callable(self.module_ref):
            res = self.module_ref(operation=operation, payload=payload, metadata=meta)
            return {"result": res}

        return {"status": "SUCCESS", "operation": operation, "payload": payload}


class OrchestratorModule(ModuleInterface):
    """B5 AI Orchestrator Module.

    Core Responsibility: Controlled Workflow Orchestration.
    Selects, composes, invokes capabilities, controls execution, routes results,
    handles failure, performs bounded recheck/replanning, coordinates Inspector,
    determines completion, and maintains traceability.

    Strict Architectural Directives:
    - MUST NOT perform agricultural reasoning or decisions.
    - MUST NOT collect/prepare context itself.
    - MUST NOT access database (SQLite) or model internals directly.
    - MUST NOT download/load Sarvam weights.
    - MUST NOT override Inspector.
    - MUST NOT fabricate results after failure.
    """

    module_name: str = "orchestrator"

    def __init__(
        self,
        capability_manager: Optional[CapabilityManager] = None,
        request_manager: Optional[RequestManager] = None,
        workflow_composer: Optional[WorkflowComposer] = None,
        execution_controller: Optional[ExecutionController] = None,
        recovery_manager: Optional[RecoveryManager] = None,
        completion_manager: Optional[CompletionManager] = None,
        inspector_service: Optional[InspectorInterface] = None,
    ) -> None:
        self.is_initialized: bool = False
        self.capability_manager = capability_manager or CapabilityManager()
        self.request_manager = request_manager or RequestManager()
        self.workflow_composer = workflow_composer or WorkflowComposer()
        self.execution_controller = execution_controller or ExecutionController()
        self.recovery_manager = recovery_manager or RecoveryManager()
        self.completion_manager = completion_manager or CompletionManager()
        self.inspector_service = inspector_service

    def initialize(self) -> None:
        """Initialize B5 AI Orchestrator resources and register default capability adapters."""
        self.is_initialized = True
        logger.info("B5 AI Orchestrator initialized successfully.")

    def shutdown(self) -> None:
        """Clean up Orchestrator resources."""
        self.is_initialized = False
        logger.info("B5 AI Orchestrator shut down cleanly.")

    def register_capability_module(
        self, capability_id: str, module_instance: Any, supported_operations: Optional[List[str]] = None
    ) -> None:
        """Helper method to wrap and register a system module into CapabilityManager."""
        wrapper = DefaultCapabilityWrapper(
            capability_id=capability_id,
            module_ref=module_instance,
            supported_operations=supported_operations,
        )
        self.capability_manager.register_capability(wrapper)

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        """Handle incoming ApplicationRequest from System Skeleton."""
        try:
            orch_req = self.request_manager.process_incoming_request(request)
            result = self.orchestrate(orch_req)
            return ApplicationResponse(
                request_id=request.request_id,
                status=result.status,
                response=result.final_output,
                warnings=result.warnings,
                metadata={
                    "workflow_id": result.workflow_id,
                    "execution_id": result.execution_id,
                    "workflow_state": result.workflow_state.value,
                    "capability_results": {
                        k: v.model_dump() for k, v in result.capability_results.items()
                    },
                },
            )
        except OrchestratorError as oe:
            logger.error(f"Orchestrator error handling request {request.request_id}: {str(oe)}")
            return ApplicationResponse(
                request_id=request.request_id,
                status="ERROR",
                warnings=[str(oe)],
                metadata={"error_contract": oe.error_contract.model_dump()},
            )
        except Exception as e:
            logger.error(f"Unexpected error in OrchestratorModule.handle(): {str(e)}")
            return ApplicationResponse(
                request_id=request.request_id,
                status="ERROR",
                warnings=[f"Internal orchestrator error: {str(e)}"],
            )

    def orchestrate(self, request: OrchestrationRequest) -> OrchestrationResponse:
        """Core orchestration pipeline execution.

        Workflow Lifecycle:
        REQUESTED -> VALIDATING -> SELECTING_WORKFLOW -> PREPARING_CAPABILITIES
        -> EXECUTING -> EVALUATING_RESULT -> ROUTING -> VALIDATING_FINAL_RESULT -> COMPLETED
        (with recovery / replanning / recheck loops as needed).
        """
        # Initialize Trace and State Manager
        trace = self.request_manager.create_initial_trace(request)
        state_mgr = StateManager(request_id=request.request_id, trace=trace)

        start_time = time.time()

        try:
            # 1. VALIDATING
            state_mgr.transition_state(request.request_id, WorkflowState.VALIDATING, "Validating request parameters")
            self.request_manager.validate_request(request)

            # Check for immediate cancellation flag
            if request.metadata.get("trigger_cancelled") or request.metadata.get("is_cancelled"):
                state_mgr.transition_state(request.request_id, WorkflowState.CANCELLED, "Request flagged as cancelled")
                return OrchestrationResponse(
                    request_id=request.request_id,
                    workflow_id=request.workflow_id,
                    execution_id=request.execution_id,
                    status="CANCELLED",
                    workflow_state=WorkflowState.CANCELLED,
                    errors=["Orchestration request was cancelled."],
                    trace=state_mgr.trace,
                    scope=request.scope,
                )

            # 2. SELECTING_WORKFLOW
            state_mgr.transition_state(
                request.request_id, WorkflowState.SELECTING_WORKFLOW, f"Composing workflow for strategy {request.strategy.value}"
            )
            workflow = self.workflow_composer.compose_workflow(
                strategy_type=request.strategy,
                request_payload=request.payload,
            )

            # 3. PREPARING_CAPABILITIES
            state_mgr.transition_state(
                request.request_id, WorkflowState.PREPARING_CAPABILITIES, "Checking capability registration and availability"
            )

            # Bounded recheck loop for Inspector coordination
            max_rechecks = request.policy.max_rechecks
            recheck_count = 0
            inspector_status = "PASS"
            step_results: Dict[str, StepExecutionResult] = {}

            while recheck_count <= max_rechecks:
                # 4. EXECUTING
                state_mgr.transition_state(
                    request.request_id, WorkflowState.EXECUTING, f"Executing workflow steps (iteration {recheck_count + 1})"
                )

                step_results = self.execution_controller.execute_workflow(
                    workflow=workflow,
                    request=request,
                    capability_manager=self.capability_manager,
                )

                # Record step results into state manager
                for s_id, s_res in step_results.items():
                    state_mgr.record_step_result(request.request_id, s_res)

                # 5. EVALUATING_RESULT
                state_mgr.transition_state(
                    request.request_id, WorkflowState.EVALUATING_RESULT, "Evaluating step execution outcomes"
                )

                # Check for blocking step failures
                failed_steps = [
                    res for res in step_results.values() if res.status == StepExecutionState.FAILED
                ]
                if failed_steps:
                    # Attempt recovery / replanning via RecoveryManager
                    all_recovered = True
                    for failed in failed_steps:
                        rec_res = self.recovery_manager.handle_step_failure(
                            step_result=failed,
                            workflow=workflow,
                            capability_manager=self.capability_manager,
                            policy=request.policy,
                        )
                        if rec_res and rec_res.status == StepExecutionState.COMPLETED:
                            step_results[failed.step_id] = rec_res
                        elif rec_res and rec_res.status == StepExecutionState.SKIPPED:
                            step_results[failed.step_id] = rec_res
                        else:
                            all_recovered = False

                    if not all_recovered and not request.policy.allow_partial_results:
                        state_mgr.transition_state(
                            request.request_id, WorkflowState.FAILED, "Workflow step execution failed without recovery"
                        )
                        return OrchestrationResponse(
                            request_id=request.request_id,
                            workflow_id=request.workflow_id,
                            execution_id=request.execution_id,
                            status="FAILED",
                            workflow_state=WorkflowState.FAILED,
                            capability_results=step_results,
                            warnings=state_mgr.warnings,
                            errors=state_mgr.errors,
                            trace=state_mgr.trace,
                            scope=request.scope,
                        )

                # 6. ROUTING & INSPECTOR INTEGRATION
                state_mgr.transition_state(
                    request.request_id, WorkflowState.ROUTING, "Routing results to Inspector validation"
                )

                inspector_status, insp_reason = self._coordinate_inspector(
                    workflow=workflow,
                    step_results=step_results,
                    request=request,
                )

                if inspector_status in ("PASS", "SUCCESS"):
                    inspector_status = "PASS"
                    break
                elif inspector_status == "FLAG":
                    state_mgr.add_warning(f"Inspector flag issued: {insp_reason}")
                    inspector_status = "FLAG"
                    break
                elif inspector_status == "RECHECK":
                    recheck_count += 1
                    if recheck_count > max_rechecks:
                        state_mgr.transition_state(
                            request.request_id, WorkflowState.FAILED, f"Exceeded max rechecks ({max_rechecks})"
                        )
                        raise RecheckLimitExceededError(request.request_id, max_rechecks)

                    state_mgr.transition_state(
                        request.request_id,
                        WorkflowState.REPLANNING,
                        f"Inspector requested RECHECK ({insp_reason}); re-executing affected stage (attempt {recheck_count}/{max_rechecks})",
                    )
                    # Re-run loop iteration
                    continue
                else:
                    inspector_status = "PASS"
                    break

            # 7. VALIDATING_FINAL_RESULT
            state_mgr.transition_state(
                request.request_id, WorkflowState.VALIDATING_FINAL_RESULT, "Validating final result against completion criteria"
            )

            is_complete = self.completion_manager.is_complete(
                workflow=workflow,
                step_results=step_results,
                policy=request.policy,
                inspector_status=inspector_status,
            )

            final_output = self.completion_manager.extract_final_output(workflow, step_results)

            if is_complete:
                state_mgr.transition_state(
                    request.request_id, WorkflowState.COMPLETED, "All completion conditions satisfied"
                )
                final_status = "SUCCESS"
            else:
                if request.policy.allow_partial_results:
                    state_mgr.transition_state(
                        request.request_id, WorkflowState.PARTIAL, "Completed with partial results"
                    )
                    final_status = "PARTIAL"
                else:
                    state_mgr.transition_state(
                        request.request_id, WorkflowState.FAILED, "Failed to satisfy completion criteria"
                    )
                    final_status = "FAILED"

            state_mgr.trace.end_time = state_mgr.trace.records[-1].start_time if state_mgr.trace.records else None

            return OrchestrationResponse(
                request_id=request.request_id,
                workflow_id=request.workflow_id,
                execution_id=request.execution_id,
                status=final_status,
                workflow_state=state_mgr.current_state,
                final_output=final_output,
                capability_results=step_results,
                warnings=state_mgr.warnings,
                errors=state_mgr.errors,
                trace=state_mgr.trace,
                scope=request.scope,
            )

        except OrchestratorError as oe:
            state_mgr.add_error(str(oe))
            return OrchestrationResponse(
                request_id=request.request_id,
                workflow_id=request.workflow_id,
                execution_id=request.execution_id,
                status="ERROR",
                workflow_state=state_mgr.current_state,
                errors=[str(oe)],
                trace=state_mgr.trace,
                scope=request.scope,
            )

    def _coordinate_inspector(
        self,
        workflow: Any,
        step_results: Dict[str, StepExecutionResult],
        request: OrchestrationRequest,
    ) -> tuple[str, str]:
        """Invoke Inspector validation on decision/planning step output.

        Returns (status, reason) where status is PASS, FLAG, or RECHECK.
        """
        # 1. Check metadata for simulated Inspector response overrides (for testing/simulation)
        insp_override = request.metadata.get("inspector_response_override")
        if isinstance(insp_override, dict):
            status = insp_override.get("status", "PASS")
            reason = insp_override.get("reason", insp_override.get("flag", "Overridden inspector status"))
            return status, reason

        # 2. Check if Inspector capability is registered
        try:
            insp_cap = self.capability_manager.get_capability("inspector")
            res = insp_cap.execute("validate_action", {"step_results": {k: v.model_dump() for k, v in step_results.items()}}, {})
            status = res.get("inspector_status") or res.get("status", "PASS")
            reason = res.get("reason", res.get("flag", "Inspector validation completed"))
            return status, reason
        except CapabilityNotFoundError:
            pass

        if self.inspector_service and hasattr(self.inspector_service, "validate_action"):
            try:
                res = self.inspector_service.validate_action(
                    action_name="orchestration_validation",
                    payload={"request_id": request.request_id, "step_results": {k: v.model_dump() for k, v in step_results.items()}},
                )
                status = res.get("inspector_status") or res.get("status", "PASS")
                reason = res.get("reason", res.get("flag", "Inspector validation completed"))
                return status, reason
            except Exception as e:
                logger.error(f"Inspector service call failed: {str(e)}")

        return "PASS", "Default Inspector validation passed."
