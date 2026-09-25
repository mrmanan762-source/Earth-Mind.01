from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from modules.context.schemas import PrivacyLevel
import uuid
from datetime import datetime, timezone
from modules.context.boundary.enums import (
    KnowledgeClassification,
    ContextSourceType,
    ContextOwnership,
    ContextScope,
    PersistenceIntent,
    TransitionType,
    GovernanceOutcome,
    GovernanceState,
    GovernanceFailureReason,
)


class ContextSourceRecord(BaseModel):
    """Canonical provider-independent context source record for C.3 boundary contracts."""
    source_type: ContextSourceType = Field(..., description="Origin source system/subsystem type")
    ownership: ContextOwnership = Field(..., description="Subsystem owning information lifecycle and meaning")
    classification: KnowledgeClassification = Field(..., description="Classification category of context")
    scope: ContextScope = Field(..., description="Scope boundary of information")
    persistence_intent: PersistenceIntent = Field(..., description="Persistence classification signal")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Traceable origin provenance chain")
    timestamp: Optional[str] = Field(None, description="ISO timestamp of record")

    # Scope entity references
    farmer_id: Optional[str] = Field(None, description="Farmer entity identifier")
    farm_id: Optional[str] = Field(None, description="Farm entity identifier")
    field_id: Optional[str] = Field(None, description="Field entity identifier")
    crop_cycle_id: Optional[str] = Field(None, description="Crop cycle entity identifier")
    session_id: Optional[str] = Field(None, description="Session entity identifier")

    # Privacy & Lifecycle
    privacy_level: Optional[PrivacyLevel] = Field(None, description="Privacy classification level")
    is_pii: bool = Field(False, description="Whether record contains PII")
    lifecycle_status: Optional[str] = Field(None, description="Lifecycle status string")
    trace_id: Optional[str] = Field(None, description="System traceability identifier")
    source_id: Optional[str] = Field(None, description="Specific identifier in source system")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class RAGContextContract(BaseModel):
    """Executable contract for RAG context provided to B2 and downstream components."""
    source_type: ContextSourceType = Field(ContextSourceType.RAG, description="Source origin type")
    ownership: ContextOwnership = Field(ContextOwnership.RAG_OWNED, description="Subsystem ownership")
    classification: KnowledgeClassification = Field(
        KnowledgeClassification.GENERAL_KNOWLEDGE, description="Classification category"
    )
    scope: ContextScope = Field(ContextScope.GLOBAL, description="Scope boundary")
    persistence_intent: PersistenceIntent = Field(
        PersistenceIntent.PERSISTENT, description="Persistence intent signal"
    )
    content: Any = Field(..., description="General or curated knowledge content")

    # C.2 Lineage and retrieval metadata
    collection_id: Optional[str] = Field(None, description="Knowledge collection ID")
    document_id: Optional[str] = Field(None, description="Document ID")
    document_version_id: Optional[str] = Field(None, description="Document version ID")
    knowledge_unit_id: Optional[str] = Field(None, description="Knowledge unit ID")
    chunk_id: Optional[str] = Field(None, description="Chunk ID")
    publication_state: str = Field("PUBLISHED", description="Publication state of RAG knowledge")

    evidence_metadata: Dict[str, Any] = Field(default_factory=dict, description="Evidence metadata")
    retrieval_metadata: Dict[str, Any] = Field(default_factory=dict, description="Retrieval score and strategy details")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Source provenance chain")
    timestamp: Optional[str] = Field(None, description="ISO timestamp")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    source_id: Optional[str] = Field(None, description="Origin source ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")

    def to_source_record(self) -> ContextSourceRecord:
        """Convert contract to canonical ContextSourceRecord."""
        return ContextSourceRecord(
            source_type=self.source_type,
            ownership=self.ownership,
            classification=self.classification,
            scope=self.scope,
            persistence_intent=self.persistence_intent,
            provenance=self.provenance,
            timestamp=self.timestamp,
            privacy_level=PrivacyLevel.PUBLIC,
            is_pii=False,
            lifecycle_status=self.publication_state,
            trace_id=self.trace_id,
            source_id=self.source_id or self.chunk_id or self.knowledge_unit_id,
            metadata=self.metadata,
        )


class MemoryContextContract(BaseModel):
    """Executable contract for Memory context provided to B2 and downstream components."""
    memory_id: str = Field(..., description="Memory record identifier")
    source_type: ContextSourceType = Field(ContextSourceType.MEMORY, description="Source origin type")
    ownership: ContextOwnership = Field(ContextOwnership.MEMORY_OWNED, description="Subsystem ownership")
    classification: KnowledgeClassification = Field(
        KnowledgeClassification.FARMER_KNOWLEDGE, description="Classification category"
    )
    scope: ContextScope = Field(ContextScope.FARMER, description="Scope boundary")
    persistence_intent: PersistenceIntent = Field(
        PersistenceIntent.PERSISTENT, description="Persistence intent signal"
    )
    content: Any = Field(..., description="Farmer/farm/field specific content")

    # Scope entity references
    farmer_id: Optional[str] = Field(None, description="Farmer entity identifier")
    farm_id: Optional[str] = Field(None, description="Farm entity identifier")
    field_id: Optional[str] = Field(None, description="Field entity identifier")
    crop_cycle_id: Optional[str] = Field(None, description="Crop cycle entity identifier")
    session_id: Optional[str] = Field(None, description="Session entity identifier")

    provenance: Dict[str, Any] = Field(default_factory=dict, description="Memory origin provenance chain")
    lifecycle_status: str = Field("ACTIVE", description="Memory lifecycle status")
    timestamp: Optional[str] = Field(None, description="ISO timestamp")
    privacy_level: PrivacyLevel = Field(PrivacyLevel.FARM_PRIVATE, description="Privacy level")
    is_pii: bool = Field(False, description="Whether memory contains PII")
    relevance_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Memory relevance score")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")

    def to_source_record(self) -> ContextSourceRecord:
        """Convert contract to canonical ContextSourceRecord."""
        return ContextSourceRecord(
            source_type=self.source_type,
            ownership=self.ownership,
            classification=self.classification,
            scope=self.scope,
            persistence_intent=self.persistence_intent,
            provenance=self.provenance,
            timestamp=self.timestamp,
            farmer_id=self.farmer_id,
            farm_id=self.farm_id,
            field_id=self.field_id,
            crop_cycle_id=self.crop_cycle_id,
            session_id=self.session_id,
            privacy_level=self.privacy_level,
            is_pii=self.is_pii,
            lifecycle_status=self.lifecycle_status,
            trace_id=self.trace_id,
            source_id=self.memory_id,
            metadata=self.metadata,
        )


class RAGContextRequest(BaseModel):
    """Provider-independent executable request contract for RAG knowledge retrieval."""
    request_id: str = Field(..., description="Unique context request identifier")
    request_origin: Optional[str] = Field("B2_CONTEXT_MANAGER", description="Origin of request")
    session_id: Optional[str] = Field(None, description="Session identifier")
    query_text: Optional[str] = Field(None, description="Agronomic or general knowledge query prompt/task")
    classification: KnowledgeClassification = Field(
        KnowledgeClassification.GENERAL_KNOWLEDGE, description="Target knowledge classification"
    )
    scope: ContextScope = Field(ContextScope.GLOBAL, description="Knowledge scope (GLOBAL or REGIONAL)")
    collection_ids: List[str] = Field(default_factory=list, description="Target knowledge collection IDs")
    content_types: List[str] = Field(default_factory=list, description="Target content types (e.g., crop, soil, disease)")
    language: Optional[str] = Field("en", description="Target language code")
    region: Optional[str] = Field(None, description="Target regional constraint")
    time_range: Optional[Dict[str, Any]] = Field(None, description="Temporal constraints")
    relevance_threshold: float = Field(0.5, ge=0.0, le=1.0, description="Minimum relevance threshold")
    maximum_result_count: int = Field(10, ge=1, description="Maximum number of items to return")
    publication_required: bool = Field(True, description="Enforce publication requirement (state == PUBLISHED)")
    trace_id: Optional[str] = Field(None, description="System traceability identifier")
    timestamp: Optional[str] = Field(None, description="ISO timestamp of request creation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class PromotionCandidate(BaseModel):
    """Provider-independent candidate object for cross-domain context promotion (C.3.3)."""
    candidate_id: str = Field(
        default_factory=lambda: f"cand_{uuid.uuid4().hex[:12]}",
        description="Unique candidate identifier"
    )
    source_id: Optional[str] = Field(None, description="Source item identifier")
    source_type: ContextSourceType = Field(..., description="Source origin subsystem type")
    ownership: ContextOwnership = Field(..., description="Source subsystem ownership")
    classification: KnowledgeClassification = Field(..., description="Source knowledge classification")
    scope: ContextScope = Field(..., description="Source scope boundary")
    persistence_intent: PersistenceIntent = Field(..., description="Source persistence intent")
    content: Any = Field(..., description="Context payload or item content")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Originating source provenance chain")
    timestamp: Optional[str] = Field(None, description="ISO timestamp of candidate or source record creation")
    originating_request: Optional[str] = Field(None, description="Originating context request identifier")
    privacy_level: Optional[PrivacyLevel] = Field(None, description="Source privacy classification level")
    is_pii: bool = Field(False, description="Whether candidate contains PII")
    lifecycle_status: Optional[str] = Field(None, description="Source lifecycle status")
    trace_id: Optional[str] = Field(None, description="System traceability correlation ID")

    # Target requested transition parameters
    requested_transition: TransitionType = Field(..., description="Requested cross-domain transition type")
    target_domain: str = Field(..., description="Target system/domain name")
    target_ownership: Optional[ContextOwnership] = Field(None, description="Requested target ownership")
    target_scope: Optional[ContextScope] = Field(None, description="Requested target scope")
    target_persistence_intent: Optional[PersistenceIntent] = Field(None, description="Requested target persistence intent")

    # Scope entity references
    farmer_id: Optional[str] = Field(None, description="Target/source farmer ID")
    farm_id: Optional[str] = Field(None, description="Target/source farm ID")
    field_id: Optional[str] = Field(None, description="Target/source field ID")
    crop_cycle_id: Optional[str] = Field(None, description="Target/source crop cycle ID")
    session_id: Optional[str] = Field(None, description="Target/source session ID")

    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")

    @classmethod
    def from_rag_contract(
        cls,
        rag_contract: RAGContextContract,
        requested_transition: TransitionType = TransitionType.RAG_TO_MEMORY,
        target_scope: Optional[ContextScope] = ContextScope.FARMER,
        target_ownership: Optional[ContextOwnership] = ContextOwnership.MEMORY_OWNED,
        target_persistence_intent: Optional[PersistenceIntent] = PersistenceIntent.PERSISTENT,
        farmer_id: Optional[str] = None,
        farm_id: Optional[str] = None,
        field_id: Optional[str] = None,
        crop_cycle_id: Optional[str] = None,
        session_id: Optional[str] = None,
        candidate_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "PromotionCandidate":
        """Construct a PromotionCandidate from a RAGContextContract for RAG->Memory promotion."""
        cid = candidate_id or f"cand_rag_{uuid.uuid4().hex[:12]}"
        return cls(
            candidate_id=cid,
            source_id=rag_contract.source_id or rag_contract.chunk_id or rag_contract.knowledge_unit_id,
            source_type=rag_contract.source_type,
            ownership=rag_contract.ownership,
            classification=rag_contract.classification,
            scope=rag_contract.scope,
            persistence_intent=rag_contract.persistence_intent,
            content=rag_contract.content,
            provenance=dict(rag_contract.provenance),
            timestamp=rag_contract.timestamp or datetime.now(timezone.utc).isoformat(),
            privacy_level=PrivacyLevel.PUBLIC,
            is_pii=False,
            lifecycle_status=rag_contract.publication_state,
            trace_id=rag_contract.trace_id,
            requested_transition=requested_transition,
            target_domain="MEMORY",
            target_ownership=target_ownership or ContextOwnership.MEMORY_OWNED,
            target_scope=target_scope or ContextScope.FARMER,
            target_persistence_intent=target_persistence_intent or PersistenceIntent.PERSISTENT,
            farmer_id=farmer_id,
            farm_id=farm_id,
            field_id=field_id,
            crop_cycle_id=crop_cycle_id,
            session_id=session_id,
            metadata=metadata or {},
        )

    @classmethod
    def from_memory_contract(
        cls,
        memory_contract: MemoryContextContract,
        requested_transition: TransitionType = TransitionType.MEMORY_TO_RAG,
        target_scope: Optional[ContextScope] = ContextScope.GLOBAL,
        target_ownership: Optional[ContextOwnership] = ContextOwnership.RAG_OWNED,
        target_persistence_intent: Optional[PersistenceIntent] = PersistenceIntent.PERSISTENT,
        candidate_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "PromotionCandidate":
        """Construct a PromotionCandidate from a MemoryContextContract for Memory->RAG promotion."""
        cid = candidate_id or f"cand_mem_{uuid.uuid4().hex[:12]}"
        return cls(
            candidate_id=cid,
            source_id=memory_contract.memory_id,
            source_type=memory_contract.source_type,
            ownership=memory_contract.ownership,
            classification=memory_contract.classification,
            scope=memory_contract.scope,
            persistence_intent=memory_contract.persistence_intent,
            content=memory_contract.content,
            provenance=dict(memory_contract.provenance),
            timestamp=memory_contract.timestamp or datetime.now(timezone.utc).isoformat(),
            privacy_level=memory_contract.privacy_level,
            is_pii=memory_contract.is_pii,
            lifecycle_status=memory_contract.lifecycle_status,
            trace_id=memory_contract.trace_id,
            requested_transition=requested_transition,
            target_domain="RAG",
            target_ownership=target_ownership or ContextOwnership.RAG_OWNED,
            target_scope=target_scope or ContextScope.GLOBAL,
            target_persistence_intent=target_persistence_intent or PersistenceIntent.PERSISTENT,
            farmer_id=memory_contract.farmer_id,
            farm_id=memory_contract.farm_id,
            field_id=memory_contract.field_id,
            crop_cycle_id=memory_contract.crop_cycle_id,
            session_id=memory_contract.session_id,
            metadata=metadata or {},
        )


class GovernanceDecision(BaseModel):
    """Provider-independent governance evaluation result contract (C.3.3)."""
    decision_id: str = Field(
        default_factory=lambda: f"dec_{uuid.uuid4().hex[:12]}",
        description="Unique decision identifier"
    )
    candidate_id: str = Field(..., description="Target candidate identifier")
    transition_type: TransitionType = Field(..., description="Evaluated transition type")
    outcome: GovernanceOutcome = Field(..., description="Governance decision outcome")
    state: GovernanceState = Field(..., description="Lifecycle state of governance evaluation")
    reason: str = Field(..., description="Detailed explanation for decision")
    violations: List[str] = Field(default_factory=list, description="List of boundary or policy violations")
    failure_reason: Optional[GovernanceFailureReason] = Field(
        None, description="Explicit failure classification if blocked/invalid/rejected"
    )
    applicable_policy: str = Field("DEFAULT_DENY_POLICY", description="Policy name or reference applied")

    source_ownership: ContextOwnership = Field(..., description="Evaluated source ownership")
    target_ownership: ContextOwnership = Field(..., description="Evaluated target ownership")
    source_scope: ContextScope = Field(..., description="Evaluated source scope")
    target_scope: ContextScope = Field(..., description="Evaluated target scope")
    source_persistence_intent: PersistenceIntent = Field(..., description="Evaluated source persistence intent")
    target_persistence_intent: PersistenceIntent = Field(..., description="Evaluated target persistence intent")

    source_lifecycle: Optional[str] = Field(None, description="Source lifecycle state string")
    target_lifecycle_requirements: Optional[str] = Field(None, description="Target domain required lifecycle process")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Preserved provenance chain")
    trace_id: Optional[str] = Field(None, description="System traceability correlation ID")
    reviewed_at: Optional[str] = Field(None, description="ISO timestamp of review execution")
    reviewer_id: Optional[str] = Field(None, description="Reviewer identifier or mechanism reference")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp of decision creation"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class PromotionRecord(BaseModel):
    """Provider-independent governance and promotion record for traceability (C.3.3)."""
    promotion_id: str = Field(
        default_factory=lambda: f"prom_{uuid.uuid4().hex[:12]}",
        description="Unique promotion record identifier"
    )
    candidate_id: str = Field(..., description="Promoted candidate identifier")
    transition_type: TransitionType = Field(..., description="Transition type")
    source_domain: str = Field(..., description="Source domain name")
    target_domain: str = Field(..., description="Target domain name")
    source_ownership: ContextOwnership = Field(..., description="Source ownership")
    target_ownership: ContextOwnership = Field(..., description="Target ownership")
    source_scope: ContextScope = Field(..., description="Source scope")
    target_scope: ContextScope = Field(..., description="Target scope")
    outcome: GovernanceOutcome = Field(..., description="Governance outcome")
    decision: GovernanceDecision = Field(..., description="Full governance decision object")
    reason: str = Field(..., description="Governance decision reason")
    policy_reference: str = Field(..., description="Policy reference identifier")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO creation timestamp"
    )
    reviewed_at: Optional[str] = Field(None, description="ISO review timestamp")
    reviewer: Optional[str] = Field(None, description="Reviewer identifier")
    source_provenance: Dict[str, Any] = Field(default_factory=dict, description="Original source provenance chain")
    target_lifecycle_reference: Optional[str] = Field(
        None, description="Target domain lifecycle reference or target execution ticket"
    )
    trace_id: Optional[str] = Field(None, description="System traceability correlation ID")
    status: GovernanceState = Field(..., description="Current governance state of promotion")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class MemoryContextRequest(BaseModel):
    """Provider-independent executable request contract for Memory context retrieval."""
    request_id: str = Field(..., description="Unique context request identifier")
    request_origin: Optional[str] = Field("B2_CONTEXT_MANAGER", description="Origin of request")
    farmer_id: Optional[str] = Field(None, description="Farmer entity identifier")
    farm_id: Optional[str] = Field(None, description="Farm entity identifier")
    field_id: Optional[str] = Field(None, description="Field entity identifier")
    crop_cycle_id: Optional[str] = Field(None, description="Crop cycle entity identifier")
    session_id: Optional[str] = Field(None, description="Session identifier")
    query_text: Optional[str] = Field(None, description="Query prompt/task description")
    classification: KnowledgeClassification = Field(
        KnowledgeClassification.FARMER_KNOWLEDGE, description="Target memory classification"
    )
    scope: ContextScope = Field(ContextScope.FARMER, description="Memory scope (FARMER, FARM, FIELD, CROP_CYCLE, SESSION)")
    requested_memory_types: List[str] = Field(
        default_factory=list, description="Memory types (history, preferences, observations, constraints)"
    )
    time_range: Optional[Dict[str, Any]] = Field(None, description="Temporal constraints")
    relevance_threshold: float = Field(0.5, ge=0.0, le=1.0, description="Minimum relevance threshold")
    maximum_result_count: int = Field(10, ge=1, description="Maximum number of items to return")
    allow_pii: bool = Field(False, description="Whether PII memory records are permitted")
    trace_id: Optional[str] = Field(None, description="System traceability identifier")
    timestamp: Optional[str] = Field(None, description="ISO timestamp of request creation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")
