from typing import Any, Dict, List, Optional, Protocol
from modules.orchestrator.enums import WorkflowState, WorkflowStrategyType
from modules.orchestrator.schemas import (
    CapabilityMetadata,
    OrchestrationPolicyConfig,
    OrchestrationRequest,
    OrchestrationResponse,
    ScopeContext,
    StepExecutionResult,
    WorkflowComposition,
)


class ICapability(Protocol):
    """Generic interface contract for any replaceable capability invoked by B5."""
    capability_id: str
    version: str
    interface_name: str

    def get_metadata(self) -> CapabilityMetadata:
        ...

    def execute(
        self,
        operation: str,
        payload: Any,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        ...


class ICapabilityManager(Protocol):
    """Manager for capability registration, metadata, health, and contract verification."""

    def register_capability(self, capability: ICapability) -> None:
        ...

    def unregister_capability(self, capability_id: str) -> None:
        ...

    def get_capability(self, capability_id: str) -> ICapability:
        ...

    def get_metadata(self, capability_id: str) -> CapabilityMetadata:
        ...

    def is_available(self, capability_id: str) -> bool:
        ...

    def check_contract_compatibility(
        self, source_capability_id: str, target_capability_id: str
    ) -> bool:
        ...


class IWorkflowComposer(Protocol):
    """Selector / Composer for generating capability execution workflows."""

    def compose_workflow(
        self,
        strategy_type: WorkflowStrategyType,
        request_payload: Dict[str, Any],
        available_capabilities: List[str]
    ) -> WorkflowComposition:
        ...


class IExecutionController(Protocol):
    """Controls step execution lifecycle, dependency ordering, concurrency, and routing."""

    def execute_workflow(
        self,
        workflow: WorkflowComposition,
        request: OrchestrationRequest,
        capability_manager: ICapabilityManager
    ) -> Dict[str, StepExecutionResult]:
        ...


class IStateTracker(Protocol):
    """Tracks state transitions, step outputs, errors, and traces."""

    def transition_state(
        self, request_id: str, new_state: WorkflowState, reason: str = ""
    ) -> None:
        ...

    def get_state(self, request_id: str) -> WorkflowState:
        ...

    def record_step_result(
        self, request_id: str, step_result: StepExecutionResult
    ) -> None:
        ...


class IRecoveryManager(Protocol):
    """Handles recoverable failures, missing information, and orchestration-level replanning."""

    def handle_step_failure(
        self,
        step_result: StepExecutionResult,
        workflow: WorkflowComposition,
        capability_manager: ICapabilityManager,
        policy: OrchestrationPolicyConfig
    ) -> Optional[StepExecutionResult]:
        ...


class ICompletionManager(Protocol):
    """Evaluates whether an orchestration workflow meets all completion criteria."""

    def is_complete(
        self,
        workflow: WorkflowComposition,
        step_results: Dict[str, StepExecutionResult],
        policy: OrchestrationPolicyConfig,
        inspector_status: str
    ) -> bool:
        ...
