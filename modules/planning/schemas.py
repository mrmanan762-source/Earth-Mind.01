from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from modules.planning.enums import (
    ConstraintSeverity,
    ConstraintType,
    DecisionState,
    DecisionStatus,
    FeasibilityState,
    HardSoftType,
    PlanningState,
    RiskLevel,
)
from modules.reasoning.enums import ValidationStatus
from modules.reasoning.schemas import ReasoningResult


class Goal(BaseModel):
    """Structured goal representation preserving user/system objective."""
    goal_id: str = Field(..., description="Unique goal identifier")
    objective: str = Field(..., description="Statement of intended planning goal/target")
    priority: str = Field("MEDIUM", description="Goal priority level ('HIGH', 'MEDIUM', 'LOW')")
    target_state: Dict[str, Any] = Field(default_factory=dict, description="Desired target state parameters")
    deadlines: Dict[str, Any] = Field(default_factory=dict, description="Associated temporal boundaries or deadlines")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary goal metadata")


class Constraint(BaseModel):
    """Generic constraint model supporting hard/soft distinction, scope, and traceability."""
    constraint_id: str = Field(..., description="Unique constraint identifier")
    type: ConstraintType = Field(ConstraintType.OPERATIONAL, description="Constraint classification")
    severity: ConstraintSeverity = Field(ConstraintSeverity.MEDIUM, description="Constraint severity")
    source: str = Field("policy", description="Origin of constraint (e.g. 'user_input', 'policy', 'safety_rule')")
    description: str = Field(..., description="Detailed description or reference statement of constraint")
    scope: str = Field("GLOBAL", description="Scope of applicability (e.g. 'GLOBAL', 'FIELD', 'EQUIPMENT')")
    value_reference: Any = Field(None, description="Quantitative or qualitative threshold/boundary value")
    hard_or_soft: HardSoftType = Field(HardSoftType.HARD, description="HARD (cannot be violated) or SOFT (preferential)")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary constraint metadata")


class ResourceRequirement(BaseModel):
    """Resource requirement representation for candidate actions and plans."""
    resource_id: str = Field(..., description="Unique resource requirement identifier")
    resource_type: str = Field(..., description="Type of resource (e.g. 'water', 'fertilizer', 'drone', 'time')")
    quantity_required: float = Field(..., ge=0.0, description="Required quantity")
    quantity_available: Optional[float] = Field(None, ge=0.0, description="Known available quantity if known")
    unit: Optional[str] = Field(None, description="Measurement unit (e.g. 'liters', 'kg', 'hours')")
    is_available: bool = Field(True, description="Flag indicating resource availability status")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class PlanningPolicyConfig(BaseModel):
    """Configurable policy controlling planning iterations, bounds, and rules."""
    max_planning_iterations: int = Field(5, ge=1, le=20, description="Maximum planning iterations allowed")
    max_alternatives: int = Field(5, ge=1, le=50, description="Maximum alternative plans to retain")
    required_constraints: List[str] = Field(default_factory=list, description="Mandatory constraint IDs")
    feasibility_policy: Dict[str, Any] = Field(default_factory=dict, description="Feasibility policy parameters")
    risk_policy: Dict[str, Any] = Field(default_factory=dict, description="Risk evaluation policy parameters")
    confirmation_policy: Dict[str, Any] = Field(default_factory=dict, description="Confirmation policy settings")
    missing_information_policy: Dict[str, Any] = Field(default_factory=dict, description="Policy for handling missing info")
    temporal_policy: Dict[str, Any] = Field(default_factory=dict, description="Temporal & sequencing policy settings")
    timeout_seconds: float = Field(30.0, ge=0.1, description="Timeout limit for planning execution")
    enforce_inspector: bool = Field(True, description="Strict requirement for Inspector validation handoff")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary policy metadata")


class DecisionPolicyConfig(BaseModel):
    """Configurable policy controlling option comparison criteria and decision formation."""
    comparison_criteria: List[str] = Field(
        default_factory=lambda: [
            "goal_alignment",
            "feasibility",
            "resource_requirements",
            "timing",
            "risk",
            "expected_benefit",
            "uncertainty",
            "user_preferences",
        ],
        description="Explicit criteria used for option comparison",
    )
    criteria_weights: Dict[str, float] = Field(default_factory=dict, description="Configurable weights for criteria")
    min_feasibility_threshold: float = Field(0.5, ge=0.0, le=1.0, description="Minimum acceptable feasibility score")
    max_acceptable_risk: RiskLevel = Field(RiskLevel.HIGH, description="Maximum tolerable risk level")
    require_explicit_confirmation: bool = Field(False, description="Whether confirmation is explicitly required")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary decision policy metadata")


class CandidateAction(BaseModel):
    """Candidate action generated during planning before decision formation."""
    action_id: str = Field(..., description="Unique action identifier")
    name: str = Field(..., description="Action name or label")
    description: str = Field(..., description="Detailed description of action")
    action_type: str = Field("GENERIC", description="Action classification")
    prerequisites: List[str] = Field(default_factory=list, description="Action IDs or condition IDs required prior to execution")
    postconditions: List[str] = Field(default_factory=list, description="Expected state changes resulting from action")
    resource_requirements: List[ResourceRequirement] = Field(default_factory=list, description="Resources required")
    estimated_duration_seconds: Optional[float] = Field(None, ge=0.0, description="Estimated duration in seconds")
    feasibility_state: FeasibilityState = Field(FeasibilityState.UNKNOWN, description="Explicit feasibility outcome")
    reasoning_finding_refs: List[str] = Field(default_factory=list, description="References to B3 findings supporting this action")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class RiskItem(BaseModel):
    """Structured risk model associated with candidate actions or plans."""
    risk_id: str = Field(..., description="Unique risk identifier")
    description: str = Field(..., description="Detailed description of potential risk")
    level: RiskLevel = Field(RiskLevel.MEDIUM, description="Categorized risk severity level")
    likelihood: float = Field(0.5, ge=0.0, le=1.0, description="Probability score of risk occurring")
    impact: float = Field(0.5, ge=0.0, le=1.0, description="Impact score if risk occurs")
    mitigation_strategy: Optional[str] = Field(None, description="Suggested risk mitigation strategy")
    affected_action_ids: List[str] = Field(default_factory=list, description="Action IDs impacted by risk")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary risk metadata")


class FeasibilityAnalysisResult(BaseModel):
    """Structured result of feasibility evaluation for actions or plans."""
    feasibility_id: str = Field(..., description="Unique feasibility result identifier")
    target_id: str = Field(..., description="ID of action or plan evaluated")
    overall_state: FeasibilityState = Field(FeasibilityState.UNKNOWN, description="Explicit feasibility outcome")
    evaluated_constraints: List[Constraint] = Field(default_factory=list, description="Constraints evaluated")
    hard_violations: List[str] = Field(default_factory=list, description="Constraint IDs of violated HARD constraints")
    soft_violations: List[str] = Field(default_factory=list, description="Constraint IDs of violated SOFT constraints")
    missing_resources: List[str] = Field(default_factory=list, description="IDs or descriptions of missing resources")
    rationale: str = Field(..., description="Structured explanation of feasibility assessment")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class PlanReference(BaseModel):
    """Structured representation of a generated plan option."""
    plan_id: str = Field(..., description="Unique plan identifier")
    name: str = Field(..., description="Plan name/title")
    description: str = Field(..., description="Summary description of plan strategy")
    actions: List[CandidateAction] = Field(default_factory=list, description="Ordered sequence or set of candidate actions")
    feasibility_state: FeasibilityState = Field(FeasibilityState.UNKNOWN, description="Explicit overall plan feasibility state")
    risk_assessment: List[RiskItem] = Field(default_factory=list, description="Risks associated with this plan")
    constraint_satisfaction: Dict[str, Any] = Field(default_factory=dict, description="Summary of constraint evaluations")
    total_estimated_duration_seconds: Optional[float] = Field(None, ge=0.0, description="Total plan duration")
    score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Comparative evaluation score")
    reasoning_basis_ids: List[str] = Field(default_factory=list, description="References to B3 reasoning findings supporting plan")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary plan metadata")


class PlanningContextReference(BaseModel):
    """Structured reference to relevant context provided to B4."""
    context_id: str = Field(..., description="Unique context reference identifier")
    reference_type: str = Field("context_result", description="Context provider type or contract type")
    context_summary: Dict[str, Any] = Field(default_factory=dict, description="Summary of relevant context items")
    prepared_context: Optional[Any] = Field(None, description="Prepared context payload")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class PlanningInput(BaseModel):
    """Structured input contract for B4 Planning & Decision Engine."""
    request_id: str = Field(..., description="Unique request identifier")
    objective: Optional[Goal] = Field(None, description="Goal / objective contract")
    reasoning_result: Optional[ReasoningResult] = Field(None, description="B3 Reasoning Engine output contract")
    relevant_context: Optional[Dict[str, Any]] = Field(None, description="Relevant context data or reference")
    constraints: List[Constraint] = Field(default_factory=list, description="Explicit constraints to consider")
    available_resources: List[ResourceRequirement] = Field(default_factory=list, description="Available resources")
    time_requirements: Dict[str, Any] = Field(default_factory=dict, description="Time requirements and window constraints")
    planning_policy: PlanningPolicyConfig = Field(default_factory=PlanningPolicyConfig, description="Planning policy config")
    decision_policy: DecisionPolicyConfig = Field(default_factory=DecisionPolicyConfig, description="Decision policy config")
    confirmation_policy: Dict[str, Any] = Field(default_factory=dict, description="Confirmation policy settings")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary input metadata")


class RequiredConfirmation(BaseModel):
    """Structured details for decisions that require explicit confirmation."""
    what: str = Field(..., description="Description of action or decision requiring confirmation")
    why: str = Field(..., description="Reason confirmation is required")
    plan_reference: Optional[str] = Field(None, description="Associated plan or decision ID reference")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional confirmation details")


class PlanningDecision(BaseModel):
    """Structured decision output contract produced by B4 Planning & Decision Engine."""
    request_id: str = Field(..., description="Unique request identifier matching PlanningInput")
    objective: Optional[Goal] = Field(None, description="Preserved goal / objective contract")
    decision_status: DecisionStatus = Field(..., description="Explicit decision status outcome")
    selected_plan: Optional[PlanReference] = Field(None, description="Selected plan or option")
    alternatives: List[PlanReference] = Field(default_factory=list, description="Alternative candidate plans")
    reasoning_references: List[str] = Field(default_factory=list, description="References to B3 reasoning findings/results")
    context_references: List[str] = Field(default_factory=list, description="References to relevant context items")
    constraints: List[Constraint] = Field(default_factory=list, description="Applied constraints")
    feasibility: List[FeasibilityAnalysisResult] = Field(default_factory=list, description="Feasibility evaluations")
    risks: List[RiskItem] = Field(default_factory=list, description="Identified risks")
    uncertainty: Dict[str, Any] = Field(default_factory=dict, description="Preserved visible uncertainty parameters")
    missing_information: List[str] = Field(default_factory=list, description="Explicit missing information gaps")
    required_confirmation: Optional[RequiredConfirmation] = Field(None, description="Details if confirmation is required")
    action_sequence: List[CandidateAction] = Field(default_factory=list, description="Ordered candidate action sequence")
    decision_basis: List[str] = Field(default_factory=list, description="Structured rationale/findings supporting decision")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Estimated confidence score [0.0, 1.0]")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings or Inspector flags")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary decision metadata")


class PlanningResult(BaseModel):
    """Structured output contract for B4 Planning & Decision Engine."""
    request_id: str = Field(..., description="Identifier matching PlanningInput request_id")
    status: PlanningState = Field(..., description="Final planning lifecycle state")
    goal: Optional[Goal] = Field(None, description="Preserved target goal")
    decision: Optional[PlanningDecision] = Field(None, description="Structured PlanningDecision result")
    recommended_plan: Optional[PlanReference] = Field(None, description="Selected recommended plan option")
    alternative_plans: List[PlanReference] = Field(default_factory=list, description="Explicit alternative candidate plans")
    candidate_actions: List[CandidateAction] = Field(default_factory=list, description="Generated candidate actions")
    feasibility_analysis: List[FeasibilityAnalysisResult] = Field(default_factory=list, description="Feasibility results")
    risk_analysis: List[RiskItem] = Field(default_factory=list, description="Identified risks")
    decision_state: DecisionState = Field(DecisionState.PROPOSED, description="State of decision formation")
    decision_basis: List[str] = Field(default_factory=list, description="Structured references to decision rationale/findings")
    requires_confirmation: bool = Field(False, description="Flag indicating if confirmation is required before handoff")
    confirmation_reason: Optional[str] = Field(None, description="Explanation for confirmation requirement")
    operation_trace: List[Dict[str, Any]] = Field(default_factory=list, description="Audit trace of planning operations executed")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warning messages")
    errors: List[str] = Field(default_factory=list, description="Error messages if planning failed")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary result metadata")


class PlanningValidationHandoff(BaseModel):
    """Validation handoff contract submitted to Inspector service."""
    handoff_id: str = Field(..., description="Unique handoff identifier")
    request_id: str = Field(..., description="Identifier matching PlanningInput request_id")
    plan_id: str = Field(..., description="ID of plan submitted for Inspector validation")
    recommended_plan: Optional[PlanReference] = Field(None, description="Recommended plan data")
    constraints_applied: List[Constraint] = Field(default_factory=list, description="Constraints applied during planning")
    feasibility_summary: Dict[str, Any] = Field(default_factory=dict, description="Summary of feasibility findings")
    risk_summary: Dict[str, Any] = Field(default_factory=dict, description="Summary of risk findings")
    validation_status: ValidationStatus = Field(ValidationStatus.PENDING, description="Inspector validation status")
    inspector_response: Optional[Dict[str, Any]] = Field(None, description="Response returned by Inspector service")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary handoff metadata")
