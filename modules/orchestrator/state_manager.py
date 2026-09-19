from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from core.logging.logger import get_logger
from modules.orchestrator.enums import StepExecutionState, WorkflowState
from modules.orchestrator.errors import InvalidWorkflowStateTransitionError
from modules.orchestrator.interfaces import IStateTracker
from modules.orchestrator.schemas import (
    OrchestrationTrace,
    StepExecutionResult,
    TraceRecord,
)

logger = get_logger("orchestrator.state_manager")


class StateManager(IStateTracker):
    """B5.6 Result / State Manager.

    Responsibilities:
    - Track state across request lifecycle and 20 explicit workflow states.
    - Validate state machine transitions and prevent illegal state jumps.
    - Track step results, dependency states, warnings, errors, and traces.
    - Ensure recorded state accurately reflects execution reality.
    """

    # Allowed state transitions graph
    ALLOWED_TRANSITIONS: Dict[WorkflowState, Set[WorkflowState]] = {
        WorkflowState.REQUESTED: {WorkflowState.VALIDATING, WorkflowState.CANCELLED, WorkflowState.FAILED},
        WorkflowState.VALIDATING: {WorkflowState.SELECTING_WORKFLOW, WorkflowState.REJECTED, WorkflowState.FAILED, WorkflowState.CANCELLED},
        WorkflowState.SELECTING_WORKFLOW: {WorkflowState.PREPARING_CAPABILITIES, WorkflowState.FAILED, WorkflowState.CANCELLED},
        WorkflowState.PREPARING_CAPABILITIES: {WorkflowState.EXECUTING, WorkflowState.FAILED, WorkflowState.CANCELLED},
        WorkflowState.EXECUTING: {
            WorkflowState.WAITING_FOR_RESULT,
            WorkflowState.EVALUATING_RESULT,
            WorkflowState.ROUTING,
            WorkflowState.RETRYING,
            WorkflowState.REPLANNING,
            WorkflowState.PARTIAL,
            WorkflowState.FAILED,
            WorkflowState.TIMEOUT,
            WorkflowState.CANCELLED,
            WorkflowState.WAITING_FOR_INPUT,
            WorkflowState.REQUIRES_CONFIRMATION,
        },
        WorkflowState.WAITING_FOR_RESULT: {WorkflowState.EVALUATING_RESULT, WorkflowState.TIMEOUT, WorkflowState.CANCELLED, WorkflowState.FAILED},
        WorkflowState.EVALUATING_RESULT: {
            WorkflowState.ROUTING,
            WorkflowState.NEXT_CAPABILITY,
            WorkflowState.VALIDATING_FINAL_RESULT,
            WorkflowState.RETRYING,
            WorkflowState.REPLANNING,
            WorkflowState.PARTIAL,
            WorkflowState.FAILED,
        },
        WorkflowState.ROUTING: {WorkflowState.NEXT_CAPABILITY, WorkflowState.EXECUTING, WorkflowState.VALIDATING_FINAL_RESULT, WorkflowState.REPLANNING, WorkflowState.FAILED},
        WorkflowState.NEXT_CAPABILITY: {WorkflowState.EXECUTING, WorkflowState.VALIDATING_FINAL_RESULT, WorkflowState.REPLANNING, WorkflowState.FAILED},
        WorkflowState.VALIDATING_FINAL_RESULT: {
            WorkflowState.COMPLETED,
            WorkflowState.PARTIAL,
            WorkflowState.REPLANNING,
            WorkflowState.REQUIRES_CONFIRMATION,
            WorkflowState.REJECTED,
            WorkflowState.FAILED,
        },
        WorkflowState.RETRYING: {WorkflowState.EXECUTING, WorkflowState.FAILED, WorkflowState.TIMEOUT, WorkflowState.CANCELLED},
        WorkflowState.REPLANNING: {WorkflowState.SELECTING_WORKFLOW, WorkflowState.EXECUTING, WorkflowState.FAILED, WorkflowState.CANCELLED},
        WorkflowState.WAITING_FOR_INPUT: {WorkflowState.EXECUTING, WorkflowState.CANCELLED, WorkflowState.TIMEOUT, WorkflowState.FAILED},
        WorkflowState.PARTIAL: {WorkflowState.COMPLETED, WorkflowState.FAILED},
        WorkflowState.REQUIRES_CONFIRMATION: {WorkflowState.COMPLETED, WorkflowState.REJECTED, WorkflowState.CANCELLED, WorkflowState.FAILED},
        # Terminal states can transition to themselves or stay fixed
        WorkflowState.COMPLETED: set(),
        WorkflowState.FAILED: set(),
        WorkflowState.TIMEOUT: set(),
        WorkflowState.CANCELLED: set(),
        WorkflowState.REJECTED: set(),
    }

    def __init__(self, request_id: str, trace: Optional[OrchestrationTrace] = None) -> None:
        self.request_id = request_id
        self._current_state: WorkflowState = WorkflowState.REQUESTED
        self.step_results: Dict[str, StepExecutionResult] = {}
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.trace: OrchestrationTrace = trace or OrchestrationTrace(
            request_id=request_id,
            workflow_id="wf_default",
            execution_id="exec_default",
        )

    @property
    def current_state(self) -> WorkflowState:
        return self._current_state

    def get_state(self, request_id: str) -> WorkflowState:
        return self._current_state

    def transition_state(
        self, request_id: str, new_state: WorkflowState, reason: str = ""
    ) -> None:
        """Transition request state with strict state machine validation."""
        if new_state == self._current_state:
            return

        allowed = self.ALLOWED_TRANSITIONS.get(self._current_state, set())
        if new_state not in allowed:
            raise InvalidWorkflowStateTransitionError(
                current_state=self._current_state.value,
                target_state=new_state.value,
                reason=f"Transition from {self._current_state.value} to {new_state.value} is not permitted.",
            )

        old_state = self._current_state
        self._current_state = new_state
        now = datetime.now(timezone.utc)

        # Record transition in trace
        self.trace.state_history.append(
            {
                "from_state": old_state.value,
                "to_state": new_state.value,
                "timestamp": now.isoformat(),
                "reason": reason,
            }
        )

        trace_rec = TraceRecord(
            event_id=f"evt_{now.timestamp()}",
            request_id=request_id,
            workflow_id=self.trace.workflow_id,
            execution_id=self.trace.execution_id,
            workflow_state=new_state,
            start_time=now,
            details={"old_state": old_state.value, "reason": reason},
        )
        self.trace.records.append(trace_rec)

        logger.info(
            f"Transitioned state for request '{request_id}': {old_state.value} -> {new_state.value} ({reason})",
            extra={"request_id": request_id, "from_state": old_state.value, "to_state": new_state.value},
        )

    def record_step_result(
        self, request_id: str, step_result: StepExecutionResult
    ) -> None:
        """Record a capability step result into state and audit trace."""
        self.step_results[step_result.step_id] = step_result

        now = datetime.now(timezone.utc)
        rec = TraceRecord(
            event_id=f"evt_step_{step_result.step_id}_{now.timestamp()}",
            request_id=request_id,
            workflow_id=self.trace.workflow_id,
            execution_id=self.trace.execution_id,
            capability_id=step_result.capability_id,
            operation=step_result.operation,
            workflow_state=self._current_state,
            start_time=now,
            details={
                "step_id": step_result.step_id,
                "status": step_result.status.value,
                "error": step_result.error,
                "duration_seconds": step_result.duration_seconds,
            },
        )
        self.trace.records.append(rec)

        if step_result.status == StepExecutionState.FAILED and step_result.error:
            self.errors.append(f"Step '{step_result.step_id}' failed: {step_result.error}")

    def add_warning(self, warning_message: str) -> None:
        """Record execution warning."""
        self.warnings.append(warning_message)
        logger.warning(f"Workflow warning for {self.request_id}: {warning_message}")

    def add_error(self, error_message: str) -> None:
        """Record execution error."""
        self.errors.append(error_message)
        logger.error(f"Workflow error for {self.request_id}: {error_message}")
