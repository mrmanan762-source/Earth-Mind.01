"""Domain models for Knowledge Collections in C.2 Knowledge Base."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator

from modules.knowledge_base.enums import AccessPolicy, Visibility


def _validate_non_empty_str(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{field_name}' must be a non-empty string.")
    return value.strip()


class CollectionType(str, Enum):
    """Supported logical collection classification types."""
    AGRICULTURE_GENERAL = "AGRICULTURE_GENERAL"
    CROPS = "CROPS"
    SOIL = "SOIL"
    DISEASES = "DISEASES"
    GOVERNMENT_GUIDELINES = "GOVERNMENT_GUIDELINES"
    RESEARCH = "RESEARCH"
    REGIONAL_KNOWLEDGE = "REGIONAL_KNOWLEDGE"
    MULTIMODAL_KNOWLEDGE = "MULTIMODAL_KNOWLEDGE"
    CUSTOM = "CUSTOM"


class CollectionStatus(str, Enum):
    """Lifecycle/operational state of a logical Knowledge Collection."""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"
    DEPRECATED = "DEPRECATED"


class MembershipStatus(str, Enum):
    """Status representing membership state of a knowledge object within a collection."""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class KnowledgeObjectType(str, Enum):
    """Types of canonical knowledge objects assignable to collections."""
    DOCUMENT = "DOCUMENT"
    DOCUMENT_VERSION = "DOCUMENT_VERSION"
    KNOWLEDGE_UNIT = "KNOWLEDGE_UNIT"
    CHUNK = "CHUNK"


class KnowledgeCollection(BaseModel):
    """Provider-independent model representing a logical Knowledge Collection."""
    collection_id: str = Field(..., description="Unique opaque collection identifier")
    collection_name: str = Field(..., description="Human-readable collection name")
    description: Optional[str] = Field(None, description="Detailed description of collection purpose")
    collection_type: Union[CollectionType, str] = Field(CollectionType.AGRICULTURE_GENERAL, description="Collection category type")
    domain: Optional[str] = Field("AGRICULTURE", description="Domain identifier (e.g. CROPS, SOIL, GENERAL)")
    language_scope: List[str] = Field(default_factory=lambda: ["en"], description="Languages covered by collection")
    region_scope: List[str] = Field(default_factory=list, description="Geographic regions covered by collection")
    status: CollectionStatus = Field(CollectionStatus.ACTIVE, description="Collection lifecycle status")
    visibility: Visibility = Field(Visibility.PUBLIC, description="Collection visibility level")
    access_policy: AccessPolicy = Field(AccessPolicy.PUBLIC, description="Collection access policy")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extensible collection metadata")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Last update timestamp")
    version: str = Field("1.0.0", description="Collection version tracking string")
    traceability: Dict[str, Any] = Field(default_factory=dict, description="Traceability information")

    @field_validator("collection_id", "collection_name")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        return _validate_non_empty_str(info.field_name, v)


class CollectionMembership(BaseModel):
    """Provider-independent representation of knowledge object membership in a collection."""
    membership_id: str = Field(..., description="Unique membership record identifier")
    collection_id: str = Field(..., description="Target logical collection identifier")
    knowledge_object_type: KnowledgeObjectType = Field(..., description="Type of canonical object")
    knowledge_object_id: str = Field(..., description="Canonical object identifier")
    document_id: Optional[str] = Field(None, description="Parent document identifier if applicable")
    version_id: Optional[str] = Field(None, description="Parent version identifier if applicable")
    status: MembershipStatus = Field(MembershipStatus.ACTIVE, description="Membership status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Assignment timestamp")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Last status update timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extensible membership metadata")
    traceability: Dict[str, Any] = Field(default_factory=dict, description="Traceability metadata")

    @field_validator("membership_id", "collection_id", "knowledge_object_id")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        return _validate_non_empty_str(info.field_name, v)
