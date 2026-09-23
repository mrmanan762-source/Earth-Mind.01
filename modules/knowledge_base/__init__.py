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
from modules.knowledge_base.processor import (
    DocumentProcessingError,
    IDocumentProcessor,
    MalformedDocumentError,
    NormalizedBlock,
    NormalizedDocument,
    NormalizedSection,
    PlainTextProcessor,
    ProcessorConfig,
    StructuredDocumentProcessor,
    UnsupportedFormatError,
)
from modules.knowledge_base.chunker import (
    ChunkingConfig,
    IChunker,
    SemanticStructuralChunker,
)
from modules.knowledge_base.pipeline import (
    DocumentProcessingPipeline,
    DocumentProcessingResult,
)
from modules.knowledge_base.embedding import (
    EmbeddingRecord,
    EmbeddingAdapter,
    FakeEmbeddingProvider,
    KnowledgeEmbeddingEngine,
    EmbeddingBatchResult,
)
from modules.knowledge_base.sparse import (
    SparseRepresentationRecord,
    FakeSparseProvider,
    SparseRepresentationAdapter,
    KnowledgeSparseEngine,
    SparseBatchResult,
)
from modules.knowledge_base.index import (
    IndexRecord,
    IndexBatchResult,
    KnowledgeCollectionMapper,
    KnowledgeIndexEngine,
    FakeIndexAdapter,
    QdrantIndexAdapter,
)
from modules.knowledge_base.collections import (
    CollectionMembership,
    CollectionStatus,
    CollectionType,
    KnowledgeCollection,
    KnowledgeCollectionEngine,
    KnowledgeObjectType,
    MembershipStatus,
)
from modules.knowledge_base.publication import (
    KnowledgePublicationEngine,
    PublicationEligibilityResult,
    PublicationEligibilityValidator,
    PublicationRecord,
    PublicationStatus,
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
    "KnowledgeLifecycleState",
    "ChangeType",
    "QualityStatus",
    "ProcessingStatus",
    "ReviewStatus",
    "SourceStatus",
    "Visibility",
    "EvidenceType",
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
    # Step 8 Processing & Chunking
    "ProcessorConfig",
    "NormalizedBlock",
    "NormalizedSection",
    "NormalizedDocument",
    "DocumentProcessingError",
    "UnsupportedFormatError",
    "MalformedDocumentError",
    "IDocumentProcessor",
    "PlainTextProcessor",
    "StructuredDocumentProcessor",
    "ChunkingConfig",
    "IChunker",
    "SemanticStructuralChunker",
    "DocumentProcessingPipeline",
    "DocumentProcessingResult",
    # Step 9 Embedding Layer
    "EmbeddingRecord",
    "EmbeddingAdapter",
    "FakeEmbeddingProvider",
    "KnowledgeEmbeddingEngine",
    "EmbeddingBatchResult",
    # Step 10 Sparse Representation
    "SparseRepresentationRecord",
    "FakeSparseProvider",
    "SparseRepresentationAdapter",
    "KnowledgeSparseEngine",
    "SparseBatchResult",
    # Step 11 Index Layer
    "IndexRecord",
    "IndexBatchResult",
    "KnowledgeCollectionMapper",
    "KnowledgeIndexEngine",
    "FakeIndexAdapter",
    "QdrantIndexAdapter",
    # Step 12 Collections & Publication
    "CollectionType",
    "CollectionStatus",
    "MembershipStatus",
    "KnowledgeObjectType",
    "KnowledgeCollection",
    "CollectionMembership",
    "KnowledgeCollectionEngine",
    "PublicationStatus",
    "PublicationEligibilityResult",
    "PublicationRecord",
    "PublicationEligibilityValidator",
    "KnowledgePublicationEngine",
]
