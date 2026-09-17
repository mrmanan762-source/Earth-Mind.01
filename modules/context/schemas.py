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
