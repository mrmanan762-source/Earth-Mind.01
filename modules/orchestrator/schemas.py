from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from modules.orchestrator.enums import (
    CapabilityStatus,
    CompletionCondition,
    FailureHandlingPolicy,
    StepExecutionState,
    WorkflowState,
    WorkflowStrategyType,
)


class ScopeContext(BaseModel):
    """Scope isolation parameters for security, privacy, and domain boundaries."""
    farmer_id: Optional[str] = None
    farm_id: Optional[str] = None
    field_id: Optional[str] = None
    crop_cycle_id: Optional[str] = None
    session_id: Optional[str] = None


class CapabilityMetadata(BaseModel):
    """Metadata contract describing a registered system capability."""
    capability_id: str
    version: str = "1.0.0"
    interface_name: str
    supported_operations: List[str] = Field(default_factory=list)
    input_contract: Dict[str, Any] = Field(default_factory=dict)
    output_contract: Dict[str, Any] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)
    availability: CapabilityStatus = CapabilityStatus.AVAILABLE
    timeout_seconds: float = 30.0
    max_retries: int = 3
    health_status: str = "HEALTHY"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkflowStepSpec(BaseModel):
    """Specification of a capability step within a workflow composition."""
    step_id: str
    capability_id: str
    operation: str
    dependencies: List[str] = Field(default_factory=list)
    is_required: bool = True
    timeout_seconds: float = 30.0
    max_retries: int = 3
    failure_policy: FailureHandlingPolicy = FailureHandlingPolicy.RETRY_THEN_ALT
    alternative_capability_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkflowComposition(BaseModel):
    """Structured workflow definition detailing steps, execution order, and rules."""
    workflow_id: str
    strategy_type: WorkflowStrategyType
    steps: List[WorkflowStepSpec] = Field(default_factory=list)
    completion_requirements: List[CompletionCondition] = Field(default_factory=list)
    parallel_groups: List[List[str]] = Field(default_factory=list)
    conditional_branches: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OrchestrationPolicyConfig(BaseModel):
    """Configuration governing B5 execution, recovery, and completion policies."""
    max_retries: int = 3
    timeout_seconds: float = 60.0
    max_rechecks: int = 3
    allow_partial_results: bool = False
    require_inspector: bool = True
    failure_policy: FailureHandlingPolicy = FailureHandlingPolicy.RETRY_THEN_ALT
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OrchestrationRequest(BaseModel):
    """Standard request payload submitted to B5 AI Orchestrator."""
    request_id: str
    workflow_id: Optional[str] = None
    execution_id: Optional[str] = None
    strategy: WorkflowStrategyType = WorkflowStrategyType.STANDARD_DECISION
    payload: Dict[str, Any] = Field(default_factory=dict)
    scope: ScopeContext = Field(default_factory=ScopeContext)
    policy: OrchestrationPolicyConfig = Field(default_factory=OrchestrationPolicyConfig)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StepExecutionResult(BaseModel):
    """Execution result and metadata for an individual capability step."""
    step_id: str
    capability_id: str
    operation: str
    status: StepExecutionState = StepExecutionState.PENDING
    output: Any = None
    error: Optional[str] = None
    duration_seconds: float = 0.0
    retry_count: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TraceRecord(BaseModel):
    """Audit log entry for orchestrator execution traceability."""
    event_id: str
    request_id: str
    workflow_id: str
    execution_id: str
    capability_id: Optional[str] = None
    capability_version: Optional[str] = None
    operation: Optional[str] = None
    workflow_state: WorkflowState
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class OrchestrationTrace(BaseModel):
    """Comprehensive trace history for an orchestration request."""
    request_id: str
    workflow_id: str
    execution_id: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    state_history: List[Dict[str, Any]] = Field(default_factory=list)
    records: List[TraceRecord] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OrchestrationResponse(BaseModel):
    """Standardized response produced by B5 AI Orchestrator."""
    request_id: str
    workflow_id: str
    execution_id: str
    status: str
    workflow_state: WorkflowState
    final_output: Any = None
    capability_results: Dict[str, StepExecutionResult] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    trace: Optional[OrchestrationTrace] = None
    scope: ScopeContext = Field(default_factory=ScopeContext)
    metadata: Dict[str, Any] = Field(default_factory=dict)
