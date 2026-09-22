"""Canonical Metadata Data Model for EarthMind Knowledge Base.

Defines extensible metadata structure attached to canonical knowledge objects.
Metadata provides identity, content, temporal, retrieval/filtering, quality,
and access properties without performing agricultural reasoning or retrieval decisions.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from modules.knowledge_base.enums import (
    AccessPolicy,
    ProcessingStatus,
    QualityStatus,
    ReviewStatus,
    Visibility,
)


def _clean_str_list(items: List[str]) -> List[str]:
    """Trims whitespace and excludes empty string elements from a list of strings."""
    cleaned = []
    for item in items:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip())
    return cleaned


class CanonicalMetadata(BaseModel):
    """Canonical extensible metadata structure for Knowledge Base objects.

    Metadata describes canonical objects across Identity, Content, Temporal,
    Retrieval/Filtering, Quality, and Access dimensions.
    """

    # Identity
    object_id: Optional[str] = Field(None, description="Identity reference of attached entity")
    object_type: Optional[str] = Field(None, description="Type designation of attached entity (e.g., 'Source', 'Document', 'Chunk')")
    source_id: Optional[str] = Field(None, description="Originating source reference ID")
    document_id: Optional[str] = Field(None, description="Parent document logical reference ID")
    version_id: Optional[str] = Field(None, description="Document version reference ID")

    # Content
    content_type: Optional[str] = Field(None, description="Content classification type")
    language: str = Field("en", description="Language code (ISO 639-1)")
    domain: Optional[str] = Field(None, description="Knowledge domain (e.g., 'AGRICULTURE', 'SOIL_SCIENCE')")
    topic: Optional[str] = Field(None, description="Specific topic or subject area")
    crop: Optional[str] = Field(None, description="Target crop (e.g., 'Maize', 'Wheat', 'Cassava')")
    region: Optional[str] = Field(None, description="Geographic applicability region")
    season: Optional[str] = Field(None, description="Agricultural season (e.g., 'Main Rain', 'Dry Season')")
    subject_category: Optional[str] = Field(None, description="Subject category classification")

    # Temporal
    relevant_timestamp: Optional[datetime] = Field(None, description="Primary timestamp associated with knowledge content")
    effective_from: Optional[datetime] = Field(None, description="Timestamp from which knowledge is effective/valid")
    effective_until: Optional[datetime] = Field(None, description="Timestamp until which knowledge is effective/valid")

    # Retrieval / Filtering
    retrieval_tags: List[str] = Field(default_factory=list, description="Categorical tags for filtering and indexing")
    search_terms: List[str] = Field(default_factory=list, description="Associated search keywords")
    filterable_attributes: Dict[str, Any] = Field(default_factory=dict, description="Custom filterable key-value pairs")

    # Quality
    quality_status: QualityStatus = Field(QualityStatus.UNVERIFIED, description="Knowledge quality status")
    completeness: Optional[float] = Field(None, ge=0.0, le=1.0, description="Completeness score between 0.0 and 1.0")
    processing_status: ProcessingStatus = Field(ProcessingStatus.PENDING, description="Processing stage status")
    review_status: ReviewStatus = Field(ReviewStatus.UNREVIEWED, description="Expert or automated review status")

    # Access
    access_policy: AccessPolicy = Field(AccessPolicy.PUBLIC, description="Access control classification policy")
    visibility: Visibility = Field(Visibility.PUBLIC, description="Visibility scope")

    # Extensibility
    extra_metadata: Dict[str, Any] = Field(default_factory=dict, description="Extensible key-value store for future field additions")

    @field_validator("retrieval_tags", "search_terms", mode="after")
    @classmethod
    def clean_string_lists(cls, v: List[str]) -> List[str]:
        return _clean_str_list(v)

    @field_validator("object_id", "object_type", "source_id", "document_id", "version_id", "content_type", "domain", "topic", "crop", "region", "season", "subject_category")
    @classmethod
    def trim_optional_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_trimmed = v.strip()
            return v_trimmed if v_trimmed else None
        return None

    @model_validator(mode="after")
    def validate_temporal_ordering(self) -> "CanonicalMetadata":
        if self.effective_from is not None and self.effective_until is not None:
            if self.effective_until < self.effective_from:
                raise ValueError("effective_until timestamp cannot be earlier than effective_from timestamp.")
        return self
