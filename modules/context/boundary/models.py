from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from modules.context.schemas import PrivacyLevel
from modules.context.boundary.enums import (
    KnowledgeClassification,
    ContextSourceType,
    ContextOwnership,
    ContextScope,
    PersistenceIntent,
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
