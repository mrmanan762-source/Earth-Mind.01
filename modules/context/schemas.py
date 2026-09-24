from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ContextState(str, Enum):
    REQUESTED = "REQUESTED"
    VALIDATING = "VALIDATING"
    CACHE_CHECK = "CACHE_CHECK"
    COLLECTING = "COLLECTING"
    VALIDATING_CONTEXT = "VALIDATING_CONTEXT"
    DEDUPLICATING = "DEDUPLICATING"
    FILTERING = "FILTERING"
    EVALUATING_RELEVANCE = "EVALUATING_RELEVANCE"
    DETECTING_CONFLICTS = "DETECTING_CONFLICTS"
    ORGANIZING = "ORGANIZING"
    PRIORITIZING = "PRIORITIZING"
    LIMITING = "LIMITING"
    BUILDING = "BUILDING"
    VALIDATING_OUTPUT = "VALIDATING_OUTPUT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    TIMEOUT = "TIMEOUT"


class PrivacyLevel(str, Enum):
    PUBLIC = "PUBLIC"
    FARM_PRIVATE = "FARM_PRIVATE"
    FARMER_PII = "FARMER_PII"


class ConflictStatus(str, Enum):
    NORMAL = "NORMAL"
    CONFLICTED = "CONFLICTED"


class PriorityLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TransformationRecord(BaseModel):
    transform_name: str = Field(..., description="Name of transformation applied")
    timestamp: str = Field(..., description="ISO string timestamp of transformation")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional transformation details")


from modules.context.boundary.enums import (
    KnowledgeClassification,
    ContextSourceType,
    ContextOwnership,
    ContextScope,
    PersistenceIntent,
)


class ContextItem(BaseModel):
    context_id: str = Field(..., description="Unique context item identifier")
    entity_type: str = Field(..., description="Entity type (e.g. 'field', 'crop', 'soil', 'weather')")
    entity_id: str = Field(..., description="Identifier for entity being described")
    data_type: str = Field(..., description="Type of context data (e.g. 'sensor_reading', 'observation')")
    content: Any = Field(..., description="Content or value of the context item")

    # Scope fields
    farmer_id: Optional[str] = Field(None, description="Farmer identifier")
    farm_id: Optional[str] = Field(None, description="Farm identifier")
    field_id: Optional[str] = Field(None, description="Field identifier")
    crop_cycle_id: Optional[str] = Field(None, description="Crop cycle identifier")
    session_id: Optional[str] = Field(None, description="Session identifier")

    # Temporal fields
    event_time: Optional[str] = Field(None, description="ISO timestamp of when event occurred")
    recorded_at: Optional[str] = Field(None, description="ISO timestamp of when observation was recorded")
    valid_from: Optional[str] = Field(None, description="ISO timestamp from when item is valid")
    valid_until: Optional[str] = Field(None, description="ISO timestamp until when item is valid")

    # Provenance
    source: str = Field(..., description="Origin context provider or system")
    source_id: Optional[str] = Field(None, description="Source item identifier")
    transformation_history: List[TransformationRecord] = Field(
        default_factory=list, description="History of transformations"
    )

    # Quality & Privacy
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence score")
    conflict_status: ConflictStatus = Field(ConflictStatus.NORMAL, description="Conflict status")
    privacy_level: PrivacyLevel = Field(PrivacyLevel.FARM_PRIVATE, description="Privacy level")
    is_pii: bool = Field(False, description="Whether item contains PII")

    # Processing & Priority
    relevance_score: float = Field(1.0, ge=0.0, le=1.0, description="Evaluated relevance score")
    token_count: int = Field(0, ge=0, description="Estimated token count")
    is_compressed: bool = Field(False, description="Compression status flag")
    priority: PriorityLevel = Field(PriorityLevel.MEDIUM, description="Priority level")
    version: str = Field("1.0", description="Item version string")
    trace_id: Optional[str] = Field(None, description="Traceability identifier")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary item metadata")

    # C.3 Boundary & Data Classification Fields
    source_type: Optional[ContextSourceType] = Field(None, description="C.3 Source type")
    ownership: Optional[ContextOwnership] = Field(None, description="C.3 Subsystem ownership")
    classification: Optional[KnowledgeClassification] = Field(None, description="C.3 Data classification")
    scope: Optional[ContextScope] = Field(None, description="C.3 Context scope")
    persistence_intent: Optional[PersistenceIntent] = Field(None, description="C.3 Persistence intent")
    boundary_metadata: Optional[Dict[str, Any]] = Field(None, description="C.3 ContextSourceRecord metadata")

    @classmethod
    def from_rag_contract(cls, rag_contract: Any, context_id: Optional[str] = None) -> "ContextItem":
        from modules.context.boundary.models import RAGContextContract
        if not isinstance(rag_contract, RAGContextContract):
            raise ValueError("rag_contract must be a RAGContextContract")

        record = rag_contract.to_source_record()
        cid = context_id or f"rag_{rag_contract.chunk_id or rag_contract.knowledge_unit_id or rag_contract.source_id or id(rag_contract)}"

        return cls(
            context_id=cid,
            entity_type="general_knowledge",
            entity_id=rag_contract.document_id or rag_contract.collection_id or "global",
            data_type="rag_evidence",
            content=rag_contract.content,
            source=rag_contract.source_type.value,
            source_id=rag_contract.source_id or rag_contract.chunk_id,
            privacy_level=PrivacyLevel.PUBLIC,
            is_pii=False,
            source_type=rag_contract.source_type,
            ownership=rag_contract.ownership,
            classification=rag_contract.classification,
            scope=rag_contract.scope,
            persistence_intent=rag_contract.persistence_intent,
            boundary_metadata=record.model_dump(),
            trace_id=rag_contract.trace_id,
            metadata=rag_contract.metadata,
        )

    @classmethod
    def from_memory_contract(cls, memory_contract: Any, context_id: Optional[str] = None) -> "ContextItem":
        from modules.context.boundary.models import MemoryContextContract
        if not isinstance(memory_contract, MemoryContextContract):
            raise ValueError("memory_contract must be a MemoryContextContract")

        record = memory_contract.to_source_record()
        cid = context_id or f"mem_{memory_contract.memory_id}"

        return cls(
            context_id=cid,
            entity_type="farmer_context",
            entity_id=memory_contract.farmer_id or memory_contract.farm_id or memory_contract.field_id or "farmer",
            data_type="memory_record",
            content=memory_contract.content,
            farmer_id=memory_contract.farmer_id,
            farm_id=memory_contract.farm_id,
            field_id=memory_contract.field_id,
            crop_cycle_id=memory_contract.crop_cycle_id,
            session_id=memory_contract.session_id,
            source=memory_contract.source_type.value,
            source_id=memory_contract.memory_id,
            privacy_level=memory_contract.privacy_level,
            is_pii=memory_contract.is_pii,
            relevance_score=memory_contract.relevance_score if memory_contract.relevance_score is not None else 1.0,
            source_type=memory_contract.source_type,
            ownership=memory_contract.ownership,
            classification=memory_contract.classification,
            scope=memory_contract.scope,
            persistence_intent=memory_contract.persistence_intent,
            boundary_metadata=record.model_dump(),
            trace_id=memory_contract.trace_id,
            metadata=memory_contract.metadata,
        )

    def to_boundary_record(self) -> Any:
        from modules.context.boundary.models import ContextSourceRecord
        if self.boundary_metadata:
            return ContextSourceRecord(**self.boundary_metadata)

        st = self.source_type or (ContextSourceType.RAG if self.source.upper() == "RAG" else ContextSourceType.MEMORY)
        ow = self.ownership or (ContextOwnership.RAG_OWNED if st == ContextSourceType.RAG else ContextOwnership.MEMORY_OWNED)
        cl = self.classification or (KnowledgeClassification.GENERAL_KNOWLEDGE if ow == ContextOwnership.RAG_OWNED else KnowledgeClassification.FARMER_KNOWLEDGE)
        sc = self.scope or (ContextScope.GLOBAL if cl == KnowledgeClassification.GENERAL_KNOWLEDGE else ContextScope.FARMER)
        pi = self.persistence_intent or PersistenceIntent.PERSISTENT

        prov = {
            "source": self.source,
            "source_id": self.source_id,
            "transformations": [t.model_dump() for t in self.transformation_history],
        }

        return ContextSourceRecord(
            source_type=st,
            ownership=ow,
            classification=cl,
            scope=sc,
            persistence_intent=pi,
            provenance=prov,
            timestamp=self.event_time or self.recorded_at,
            farmer_id=self.farmer_id,
            farm_id=self.farm_id,
            field_id=self.field_id,
            crop_cycle_id=self.crop_cycle_id,
            session_id=self.session_id,
            privacy_level=self.privacy_level,
            is_pii=self.is_pii,
            trace_id=self.trace_id,
            source_id=self.source_id,
            metadata=self.metadata,
        )


class PolicyConfig(BaseModel):
    mandatory_context_types: List[str] = Field(default_factory=list, description="Mandatory context types")
    mandatory_item_ids: List[str] = Field(default_factory=list, description="Mandatory item IDs")
    required_providers: List[str] = Field(default_factory=list, description="Provider names required for complete context")
    allow_partial: bool = Field(True, description="Whether partial context results are permitted on failures")
    allow_pii: bool = Field(False, description="Whether FARMER_PII items are permitted")
    timeout_seconds: float = Field(5.0, ge=0.1, description="Timeout for provider context collection")
    max_tokens: Optional[int] = Field(None, description="Optional override for token limit")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Policy metadata")


class ContextRequest(BaseModel):
    request_id: str = Field(..., description="Unique context request identifier")
    farmer_id: Optional[str] = Field(None, description="Farmer scope ID")
    farm_id: Optional[str] = Field(None, description="Farm scope ID")
    field_id: Optional[str] = Field(None, description="Field scope ID")
    crop_cycle_id: Optional[str] = Field(None, description="Crop cycle scope ID")
    session_id: Optional[str] = Field(None, description="Session scope ID")
    task: Optional[str] = Field(None, description="Task or prompt objective description")
    requested_context_types: List[str] = Field(default_factory=list, description="Context types to retrieve")
    time_range: Optional[Dict[str, Any]] = Field(None, description="Temporal filter constraints")
    token_limit: int = Field(4096, ge=1, description="Maximum token budget for returned context")
    relevance_threshold: float = Field(0.5, ge=0.0, le=1.0, description="Minimum relevance score threshold")
    policy: PolicyConfig = Field(default_factory=PolicyConfig, description="Execution policy configuration")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class ContextResult(BaseModel):
    request_id: str = Field(..., description="Identifier matching ContextRequest")
    state: ContextState = Field(..., description="Final or current context lifecycle state")
    items: List[ContextItem] = Field(default_factory=list, description="Model-ready context items")
    structured_context: Dict[str, Any] = Field(default_factory=dict, description="Structured payload for model consumption")
    total_tokens: int = Field(0, ge=0, description="Total token count of context")
    is_compressed: bool = Field(False, description="Whether payload contains compressed content")
    trace_id: Optional[str] = Field(None, description="Traceability ID")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warning messages")
    errors: List[str] = Field(default_factory=list, description="Error messages if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Execution metadata")
