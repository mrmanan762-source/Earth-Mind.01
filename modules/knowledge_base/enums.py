"""Enumerations for C.2 Canonical Knowledge Data Model."""

from enum import Enum


class KnowledgeContentType(str, Enum):
    """Supported content types for Knowledge Units and Chunks."""
    TEXT = "TEXT"
    TABLE = "TABLE"
    IMAGE = "IMAGE"
    FIGURE = "FIGURE"
    STRUCTURED_DATA = "STRUCTURED_DATA"
    MULTIMODAL = "MULTIMODAL"


class SourceStatus(str, Enum):
    """Status representing origin/provider source state."""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DEPRECATED = "DEPRECATED"
    PENDING_REVIEW = "PENDING_REVIEW"


class ArtifactStatus(str, Enum):
    """Status representing raw source artifact ingestion/processing state."""
    RAW = "RAW"
    INGESTED = "INGESTED"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class DocumentStatus(str, Enum):
    """Status representing logical domain document state."""
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DRAFT = "DRAFT"
    SUPERSEDED = "SUPERSEDED"


class DocumentVersionStatus(str, Enum):
    """Status representing specific document version lifecycle state."""
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    RETIRED = "RETIRED"
    INVALID = "INVALID"
    PENDING_REVIEW = "PENDING_REVIEW"


class KnowledgeUnitStatus(str, Enum):
    """Status representing atomic knowledge unit lifecycle state."""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUPERSEDED = "SUPERSEDED"
    DEPRECATED = "DEPRECATED"


class ChunkStatus(str, Enum):
    """Status representing chunk lifecycle state."""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUPERSEDED = "SUPERSEDED"
    DEPRECATED = "DEPRECATED"


class ChangeType(str, Enum):
    """Categorization of changes introduced in a document version."""
    INITIAL_CREATION = "INITIAL_CREATION"
    MINOR_REVISION = "MINOR_REVISION"
    MAJOR_REVISION = "MAJOR_REVISION"
    CORRECTION = "CORRECTION"
    RESTRUCTURED = "RESTRUCTURED"
    SUPERSEDED = "SUPERSEDED"


class QualityStatus(str, Enum):
    """Status indicating knowledge quality assessment state."""
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    LOW_QUALITY = "LOW_QUALITY"
    HIGH_QUALITY = "HIGH_QUALITY"
    DEPRECATED = "DEPRECATED"


class ProcessingStatus(str, Enum):
    """Status representing processing pipeline operational state."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class KnowledgeLifecycleState(str, Enum):
    """Lifecycle states for C.2 Knowledge Base documents and processing pipeline."""
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    EMBEDDED = "EMBEDDED"
    INDEXED = "INDEXED"
    PENDING_REVIEW = "PENDING_REVIEW"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    INVALID = "INVALID"
    RETIRED = "RETIRED"
    SUPERSEDED = "SUPERSEDED"


class ReviewStatus(str, Enum):
    """Status representing expert or system review state."""
    UNREVIEWED = "UNREVIEWED"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AccessPolicy(str, Enum):
    """Access policy levels for knowledge artifacts."""
    PUBLIC = "PUBLIC"
    RESTRICTED = "RESTRICTED"
    CONFIDENTIAL = "CONFIDENTIAL"
    INTERNAL = "INTERNAL"


class Visibility(str, Enum):
    """Visibility scope for retrieval and organization."""
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    ORGANIZATIONAL = "ORGANIZATIONAL"


class EvidenceType(str, Enum):
    """Classification of knowledge evidence source type."""
    EXPERIMENTAL_DATA = "EXPERIMENTAL_DATA"
    EXTENSION_GUIDE = "EXTENSION_GUIDE"
    ACADEMIC_PAPER = "ACADEMIC_PAPER"
    OBSERVATIONAL = "OBSERVATIONAL"
    SATELLITE_OBSERVATION = "SATELLITE_OBSERVATION"
    EXPERT_OPINION = "EXPERT_OPINION"


class IndexStatus(str, Enum):
    """Status representing index record or indexing pipeline operational state."""
    PENDING = "PENDING"
    INDEXING = "INDEXING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
