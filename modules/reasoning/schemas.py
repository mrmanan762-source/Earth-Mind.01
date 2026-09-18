from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from modules.context.schemas import ContextResult
from modules.reasoning.enums import (
    AssumptionType,
    ConflictType,
    EvidenceScope,
    ReasoningState,
    RelationshipType,
    UncertaintyLevel,
    ValidationStatus,
)


class EvidenceItem(BaseModel):
    """Structured evidence item preserving provenance, confidence, scope, and conflict status."""
    evidence_id: str = Field(..., description="Unique evidence item identifier")
    source: str = Field(..., description="Origin system or provider (e.g. 'context_manager', 'sensor', 'weather')")
    source_id: Optional[str] = Field(None, description="Original item ID at source")
    data_reference: Optional[str] = Field(None, description="Reference URI or dataset pointer")
    content: Any = Field(..., description="Evidence payload content")

    # Scope & Temporal
    scope: EvidenceScope = Field(EvidenceScope.FIELD, description="Granularity scope")
    event_time: Optional[str] = Field(None, description="ISO timestamp when event occurred")
    recorded_at: Optional[str] = Field(None, description="ISO timestamp when observation was recorded")
    valid_from: Optional[str] = Field(None, description="ISO timestamp valid start")
    valid_until: Optional[str] = Field(None, description="ISO timestamp valid end")

    # Quality & Provenance
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Evidence confidence score")
    reliability: float = Field(1.0, ge=0.0, le=1.0, description="Source reliability score")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Provenance and transformation audit metadata")
    conflict_status: str = Field("NORMAL", description="Conflict status tag ('NORMAL', 'CONFLICTED')")

    # Assumptions & Traceability
    is_assumption: bool = Field(False, description="Flag indicating whether item is an assumption rather than direct evidence")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary evidence metadata")


class AssumptionItem(BaseModel):
    """Explicitly declared reasoning assumption model."""
    assumption_id: str = Field(..., description="Unique assumption identifier")
    description: str = Field(..., description="Text description of the assumption")
    assumption_type: AssumptionType = Field(AssumptionType.DEFAULT_BASELINE, description="Categorization of assumption")
    rationale: str = Field(..., description="Rationale justifying why the assumption was declared")
    affected_claims: List[str] = Field(default_factory=list, description="IDs of claims or findings affected")
    confidence_penalty: float = Field(0.1, ge=0.0, le=1.0, description="Confidence score penalty applied when using this assumption")
    source_reference: Optional[str] = Field(None, description="Optional reference to missing or incomplete evidence ID")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class EvidenceRelationship(BaseModel):
    """Structured representation of relationships between evidence items."""
    relationship_id: str = Field(..., description="Unique relationship identifier")
    source_evidence_ids: List[str] = Field(..., description="IDs of source evidence items")
    target_evidence_ids: List[str] = Field(..., description="IDs of target evidence items")
    relationship_type: RelationshipType = Field(..., description="Detected relationship type")
    strength: float = Field(1.0, ge=0.0, le=1.0, description="Strength or correlation factor of relationship")
    description: str = Field(..., description="Descriptive rationale for relationship")
    temporal_delta_seconds: Optional[float] = Field(None, description="Time difference in seconds if temporal relationship")
    causal_hypothesis_id: Optional[str] = Field(None, description="Hypothesis ID if causal relationship")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class EvidenceConflict(BaseModel):
    """Structured representation of evidence conflicts preserving source, timestamp, and details."""
    conflict_id: str = Field(..., description="Unique conflict identifier")
    evidence_ids: List[str] = Field(..., description="IDs of conflicting evidence items")
    sources: List[str] = Field(default_factory=list, description="List of involved evidence sources")
    timestamps: List[str] = Field(default_factory=list, description="List of timestamps for conflicting items")
    conflict_type: ConflictType = Field(..., description="Classification of conflict")
    description: str = Field(..., description="Detailed description of conflicting values/claims")
    confidence_delta: float = Field(0.0, ge=0.0, le=1.0, description="Impact of conflict on overall confidence")
    resolution_hint: Optional[str] = Field(None, description="Non-binding hint for potential future resolution")
    is_resolved: bool = Field(False, description="Flag indicating if conflict was explicitly resolved (must not auto-resolve without cause)")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class UncertaintyItem(BaseModel):
    """Structured uncertainty representation."""
    uncertainty_id: str = Field(..., description="Unique uncertainty identifier")
    level: UncertaintyLevel = Field(..., description="Categorized uncertainty level")
    reason: str = Field(..., description="Detailed reason for uncertainty")
    affected_finding_ids: List[str] = Field(default_factory=list, description="IDs of findings affected by uncertainty")
    supporting_evidence_ids: List[str] = Field(default_factory=list, description="IDs of evidence related to uncertainty")
    missing_information_refs: List[str] = Field(default_factory=list, description="References to missing information items")
    insufficient_evidence_flag: bool = Field(False, description="True if uncertainty is due to insufficient evidence")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class MissingInformationItem(BaseModel):
    """Structured model for identified missing required evidence."""
    missing_info_id: str = Field(..., description="Unique missing info identifier")
    required_data_type: str = Field(..., description="Type or category of missing data (e.g. 'soil_moisture', 'rainfall')")
    entity_id: Optional[str] = Field(None, description="Target entity ID associated with missing data")
    scope: EvidenceScope = Field(EvidenceScope.FIELD, description="Scope of missing information")
    importance: str = Field("MEDIUM", description="Importance level ('HIGH', 'MEDIUM', 'LOW')")
    impact_on_reasoning: str = Field(..., description="Explanation of how missing info impacts analysis completeness")
    suggested_resolution: Optional[str] = Field(None, description="Suggested action to obtain missing data")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class ReasoningHypothesis(BaseModel):
    """Bounded hypothesis or explanation generated during reasoning."""
    hypothesis_id: str = Field(..., description="Unique hypothesis identifier")
    description: str = Field(..., description="Statement of hypothesis")
    supporting_evidence_ids: List[str] = Field(default_factory=list, description="Evidence IDs supporting hypothesis")
    contradicting_evidence_ids: List[str] = Field(default_factory=list, description="Evidence IDs contradicting hypothesis")
    confidence_score: float = Field(0.5, ge=0.0, le=1.0, description="Evaluated hypothesis confidence")
    status: str = Field("PROPOSED", description="Status ('PROPOSED', 'VALIDATED', 'REJECTED')")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class ReasoningFinding(BaseModel):
    """Structured finding produced by B3 reasoning engine."""
    finding_id: str = Field(..., description="Unique finding identifier")
    statement: str = Field(..., description="Reasoning statement or claim")
    confidence_score: float = Field(1.0, ge=0.0, le=1.0, description="Overall confidence score for finding")
    evidence_ids: List[str] = Field(default_factory=list, description="IDs of evidence items directly supporting finding")
    assumption_ids: List[str] = Field(default_factory=list, description="IDs of assumptions used to reach finding")
    relationship_ids: List[str] = Field(default_factory=list, description="IDs of relevant relationships")
    conflict_ids: List[str] = Field(default_factory=list, description="IDs of relevant conflicts")
    uncertainty_ids: List[str] = Field(default_factory=list, description="IDs of relevant uncertainties")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class ReasoningPolicyConfig(BaseModel):
    """Policy configuration controlling B3 reasoning strategy and execution bounds."""
    max_iterations: int = Field(3, ge=1, le=10, description="Maximum allowed reasoning iterations")
    min_confidence_threshold: float = Field(0.5, ge=0.0, le=1.0, description="Minimum confidence threshold for findings")
    min_evidence_threshold: float = Field(0.3, ge=0.0, le=1.0, description="Minimum required evidence score")
    allow_assumptions: bool = Field(True, description="Whether explicit assumptions are permitted when evidence is missing")
    enforce_inspector: bool = Field(True, description="Whether Inspector validation handoff is strictly enforced")
    strategy_timeout_seconds: float = Field(10.0, ge=0.1, description="Timeout limit for reasoning execution")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary policy metadata")


class ReasoningInput(BaseModel):
    """Structured input contract for B3 Reasoning Engine."""
    request_id: str = Field(..., description="Unique request identifier")
    task: str = Field(..., description="Task or reasoning problem description")
    prepared_context: Optional[ContextResult] = Field(None, description="Model-ready context received from Context Manager")
    evidence_items: List[EvidenceItem] = Field(default_factory=list, description="Explicit or parsed evidence items")
    constraints: Dict[str, Any] = Field(default_factory=dict, description="Execution or domain constraints")
    policy: ReasoningPolicyConfig = Field(default_factory=ReasoningPolicyConfig, description="Reasoning policy configuration")
    iteration_limits: Dict[str, Any] = Field(default_factory=dict, description="Iteration limits and termination rules")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary input metadata")


class ReasoningResult(BaseModel):
    """Structured output contract for B3 Reasoning Engine findings."""
    request_id: str = Field(..., description="Identifier matching ReasoningInput request_id")
    status: ReasoningState = Field(..., description="Final reasoning state")
    findings: List[ReasoningFinding] = Field(default_factory=list, description="Structured reasoning findings")
    evidence_references: List[str] = Field(default_factory=list, description="All evidence IDs referenced in reasoning")
    assumptions: List[AssumptionItem] = Field(default_factory=list, description="All explicit assumptions declared")
    relationships: List[EvidenceRelationship] = Field(default_factory=list, description="Identified relationships between evidence")
    conflicts: List[EvidenceConflict] = Field(default_factory=list, description="Identified conflicts between evidence")
    uncertainty: List[UncertaintyItem] = Field(default_factory=list, description="Identified uncertainties")
    missing_information: List[MissingInformationItem] = Field(default_factory=list, description="Identified missing required information")
    reasoning_operation_trace: List[Dict[str, Any]] = Field(default_factory=list, description="Structured trace of operations executed")
    iteration_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata regarding iteration count and strategy shifts")
    model_capability_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata regarding model/capability invoked")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings")
    errors: List[str] = Field(default_factory=list, description="Error messages if reasoning failed")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class ReasoningValidationHandoff(BaseModel):
    """Validation handoff contract submitted to Inspector."""
    handoff_id: str = Field(..., description="Unique handoff identifier")
    request_id: str = Field(..., description="Identifier matching ReasoningInput request_id")
    reasoning_result_id: str = Field(..., description="Reasoning result identifier")
    findings: List[ReasoningFinding] = Field(default_factory=list, description="Reasoning findings for validation")
    evidence_summary: Dict[str, Any] = Field(default_factory=dict, description="Summary of evidence utilized")
    conflicts_summary: Dict[str, Any] = Field(default_factory=dict, description="Summary of conflicts identified")
    uncertainty_summary: Dict[str, Any] = Field(default_factory=dict, description="Summary of uncertainty identified")
    validation_status: ValidationStatus = Field(ValidationStatus.PENDING, description="Inspector validation status")
    inspector_response: Optional[Dict[str, Any]] = Field(None, description="Response returned by Inspector service")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary handoff metadata")
