"""Domain models for Knowledge Publication in C.2 Knowledge Base."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

from modules.knowledge_base.enums import KnowledgeLifecycleState
from modules.knowledge_base.collections.models import KnowledgeObjectType


def _validate_non_empty_str(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{field_name}' must be a non-empty string.")
    return value.strip()


class PublicationStatus(str, Enum):
    """Operational state of a publication record."""
    PUBLISHED = "PUBLISHED"
    PUBLISHED_INDEX_UNAVAILABLE = "PUBLISHED_INDEX_UNAVAILABLE"
    PENDING_INDEX = "PENDING_INDEX"
    PENDING_REVIEW = "PENDING_REVIEW"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    REVOKED = "REVOKED"
    SUPERSEDED = "SUPERSEDED"


class PublicationEligibilityResult(BaseModel):
    """Structured evaluation result for knowledge publication eligibility."""
    eligible: bool = Field(..., description="Whether the knowledge object meets all publication prerequisites")
    knowledge_object_id: str = Field(..., description="Canonical object identifier evaluated")
    knowledge_object_type: KnowledgeObjectType = Field(KnowledgeObjectType.DOCUMENT_VERSION, description="Target object type")
    reasons: List[str] = Field(default_factory=list, description="Descriptive validation results and eligibility notes")
    missing_prerequisites: List[str] = Field(default_factory=list, description="List of unfulfilled prerequisites if ineligible")
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Evaluation timestamp")

    @field_validator("knowledge_object_id")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        return _validate_non_empty_str(info.field_name, v)


class PublicationRecord(BaseModel):
    """Auditable record documenting a publication decision and state transition."""
    publication_id: str = Field(..., description="Unique publication audit record identifier")
    knowledge_object_type: KnowledgeObjectType = Field(..., description="Type of canonical knowledge object")
    knowledge_object_id: str = Field(..., description="Canonical object identifier")
    document_id: Optional[str] = Field(None, description="Parent document identifier")
    version_id: Optional[str] = Field(None, description="Parent version identifier")
    collection_id: Optional[str] = Field(None, description="Associated logical collection identifier")
    previous_lifecycle_state: KnowledgeLifecycleState = Field(..., description="Lifecycle state before publication action")
    new_lifecycle_state: KnowledgeLifecycleState = Field(..., description="Lifecycle state after publication action")
    publication_status: PublicationStatus = Field(..., description="Resulting publication operational status")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Publication timestamp")
    actor_id: str = Field("system", description="Identifier of actor or system initiating publication")
    reason: Optional[str] = Field(None, description="Rationale or trigger for publication action")
    validation_details: Dict[str, Any] = Field(default_factory=dict, description="Audit validation information")
    traceability: Dict[str, Any] = Field(default_factory=dict, description="Traceability metadata")

    @field_validator("publication_id", "knowledge_object_id")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        return _validate_non_empty_str(info.field_name, v)
