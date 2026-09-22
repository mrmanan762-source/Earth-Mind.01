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
