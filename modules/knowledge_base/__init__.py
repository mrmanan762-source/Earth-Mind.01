"""C.2 Knowledge Base Module for EarthMind."""

from modules.knowledge_base.enums import (
    AccessPolicy,
    ArtifactStatus,
    ChangeType,
    ChunkStatus,
    DocumentStatus,
    DocumentVersionStatus,
    EvidenceType,
    KnowledgeContentType,
    KnowledgeLifecycleState,
    KnowledgeUnitStatus,
    ProcessingStatus,
    QualityStatus,
    ReviewStatus,
    SourceStatus,
    Visibility,
)
from modules.knowledge_base.metadata import CanonicalMetadata
from modules.knowledge_base.provenance import ProcessingStep, Provenance
from modules.knowledge_base.assessment import SourceAssessment
from modules.knowledge_base.lifecycle import (
    InvalidLifecycleTransitionError,
    KnowledgeLifecycleEngine,
    LifecycleTransitionRecord,
)
from modules.knowledge_base.canonical_models import (
    Artifact,
    Chunk,
    Document,
    DocumentVersion,
    KnowledgeUnit,
    LineageValidationError,
    Section,
    Source,
    Step6ValidationError,
    validate_canonical_lineage,
    validate_metadata_structure,
    validate_provenance_chain,
    validate_source_assessment,
)

__all__ = [
    # Enums
    "SourceStatus",
    "ArtifactStatus",
    "DocumentStatus",
    "DocumentVersionStatus",
    "KnowledgeUnitStatus",
    "ChunkStatus",
    "KnowledgeContentType",
    "ChangeType",
    "QualityStatus",
    "ProcessingStatus",
    "ReviewStatus",
    "AccessPolicy",
    "Visibility",
    "EvidenceType",
    "KnowledgeLifecycleState",
    # Step 5 Canonical Models
    "Source",
    "Artifact",
    "Document",
    "DocumentVersion",
    "Section",
    "KnowledgeUnit",
    "Chunk",
    "LineageValidationError",
    "validate_canonical_lineage",
    # Step 6 Models
    "CanonicalMetadata",
    "Provenance",
    "ProcessingStep",
    "SourceAssessment",
    "Step6ValidationError",
    "validate_metadata_structure",
    "validate_provenance_chain",
    "validate_source_assessment",
    # Step 7 Models & Lifecycle Engine
    "InvalidLifecycleTransitionError",
    "KnowledgeLifecycleEngine",
    "LifecycleTransitionRecord",
]
