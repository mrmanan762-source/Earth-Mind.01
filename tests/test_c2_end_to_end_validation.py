"""Comprehensive End-to-End C.2 Knowledge Base Pipeline Validation Test Suite."""

from datetime import datetime, timezone
import pytest

from core.errors.exceptions import PublicationEligibilityError
from modules.knowledge_base.canonical_models import LineageValidationError
from modules.knowledge_base.enums import (
    AccessPolicy,
    ArtifactStatus,
    DocumentStatus,
    DocumentVersionStatus,
    KnowledgeContentType,
    KnowledgeLifecycleState,
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
    Section,
    Source,
    validate_canonical_lineage,
)
from modules.knowledge_base.processor import PlainTextProcessor, ProcessorConfig
from modules.knowledge_base.chunker import ChunkingConfig, SemanticStructuralChunker
from modules.knowledge_base.pipeline import DocumentProcessingPipeline
from modules.knowledge_base.embedding import (
    FakeEmbeddingProvider,
    KnowledgeEmbeddingEngine,
)
from modules.knowledge_base.sparse import (
    FakeSparseProvider,
    KnowledgeSparseEngine,
)
from modules.knowledge_base.index import (
    FakeIndexAdapter,
    KnowledgeIndexEngine,
)
from modules.knowledge_base.collections import (
    CollectionStatus,
    CollectionType,
    KnowledgeCollectionEngine,
    KnowledgeObjectType,
)
from modules.knowledge_base.publication import (
    KnowledgePublicationEngine,
    PublicationStatus,
)


@pytest.fixture
def e2e_source():
    return Source(
        source_id="src_agri_ext_001",
        source_name="East Africa Agricultural Extension Guidelines",
        source_type="EXTENSION_SERVICE",
        organization="Ministry of Agriculture",
        language="en",
        region="East Africa",
        status=SourceStatus.ACTIVE,
    )


@pytest.fixture
def e2e_artifact(e2e_source):
    return Artifact(
        artifact_id="art_maize_guide_2026",
        source_id=e2e_source.source_id,
        location_reference="data/sources/maize_guide_2026.txt",
        content_type="text/plain",
        status=ArtifactStatus.INGESTED,
    )


@pytest.fixture
def e2e_document(e2e_source):
    return Document(
        document_id="doc_maize_protection_2026",
        source_id=e2e_source.source_id,
        title="Maize Integrated Pest Management and Fall Armyworm Control",
        document_type="EXTENSION_GUIDELINE",
        language="en",
        region="East Africa",
        status=DocumentStatus.ACTIVE,
    )


@pytest.fixture
def e2e_version(e2e_document):
    return DocumentVersion(
        version_id="ver_maize_v1_0",
        document_id=e2e_document.document_id,
        version_number="1.0.0",
        status=DocumentVersionStatus.ACTIVE,
    )


@pytest.fixture
def e2e_provenance(e2e_source, e2e_artifact, e2e_document, e2e_version):
    return Provenance(
        provenance_id="prov_e2e_001",
        source_id=e2e_source.source_id,
        artifact_id=e2e_artifact.artifact_id,
        document_id=e2e_document.document_id,
        version_id=e2e_version.version_id,
        processing_stage="INGESTION",
        is_complete=True,
    )


@pytest.fixture
def e2e_metadata():
    return CanonicalMetadata(
        domain="CROPS",
        topic="Fall Armyworm Control",
        crop="Maize",
        region="East Africa",
        language="en",
        access_policy=AccessPolicy.PUBLIC,
        visibility=Visibility.PUBLIC,
    )


@pytest.fixture
def e2e_assessment():
    return SourceAssessment(
        assessment_id="assess_001",
        authority_score=0.95,
        reliability_score=0.92,
        recency_score=0.98,
        domain_relevance_score=0.99,
        geographic_relevance_score=0.95,
    )


# =====================================================================
# 1. E2E HAPPY PATH PIPELINE VALIDATION
# =====================================================================

def test_e2e_happy_path_pipeline(
    e2e_source, e2e_artifact, e2e_document, e2e_version, e2e_provenance, e2e_metadata, e2e_assessment
):
    """Validate full pipeline from Source to Retrievable Knowledge."""
    # Step 1: Processing & Semantic Chunking
    raw_text = """
    # Section 1: Fall Armyworm Identification
    Fall armyworm larvae have a distinct inverted Y mark on their head. They feed heavily on maize whorl leaves.

    # Section 2: Management Standards
    Apply recommended biological or chemical controls during early larval stages before deep whorl penetration.
    """

    processor = PlainTextProcessor()
    chunker = SemanticStructuralChunker()
    pipeline = DocumentProcessingPipeline(
            processors=[processor],
        chunker=chunker,
    )

    e2e_version.metadata = e2e_metadata
    e2e_version.provenance = e2e_provenance

    process_result = pipeline.process_document(
        source=e2e_source,
        document=e2e_document,
        version=e2e_version,
        content=raw_text,
        content_type="text/plain",
        chunking_config=ChunkingConfig(max_tokens=100, min_chunk_size=10),
    )

    assert process_result.lifecycle_state == KnowledgeLifecycleState.PROCESSED
    assert len(process_result.knowledge_units) > 0
    assert len(process_result.chunks) > 0

    chunk = process_result.chunks[0]

    # Step 2: Dense Representation Generation
    dense_provider = FakeEmbeddingProvider(dimension=384)
    embedding_engine = KnowledgeEmbeddingEngine(provider=dense_provider)
    dense_record = embedding_engine.embed_chunk(chunk)

    # Step 3: Sparse Representation Generation
    sparse_provider = FakeSparseProvider()
    sparse_engine = KnowledgeSparseEngine(provider=sparse_provider)
    sparse_record = sparse_engine.generate_sparse_chunk(chunk)

    # Step 4: Index Layer Registration & Persistence
    index_adapter = FakeIndexAdapter()
    index_engine = KnowledgeIndexEngine(adapter=index_adapter)

    index_record = index_engine.build_index_record(
        dense_record=dense_record,
        sparse_record=sparse_record,
        knowledge_collection="Crops",
        lifecycle_state=KnowledgeLifecycleState.INDEXED,
    )

    # Step 5: Logical Collection Assignment
    collection_engine = KnowledgeCollectionEngine()
    crops_col = collection_engine.create_collection(
        collection_name="Crops",
        collection_type=CollectionType.CROPS,
        domain="CROPS",
    )

    # Step 6: Explicit Publication (indexing synced via publication engine)
    publication_engine = KnowledgePublicationEngine(
        collection_engine=collection_engine, index_engine=index_engine
    )

    pub_record = publication_engine.publish_knowledge(
        knowledge_object_id=e2e_version.version_id,
        knowledge_object_type=KnowledgeObjectType.DOCUMENT_VERSION,
        collection_id=crops_col.collection_id,
        source_id=e2e_source.source_id,
        document_id=e2e_document.document_id,
        version_id=e2e_version.version_id,
        provenance=e2e_provenance,
        metadata=e2e_metadata,
        index_records=[index_record],
    )

    assert pub_record.publication_status == PublicationStatus.PUBLISHED
    assert pub_record.new_lifecycle_state == KnowledgeLifecycleState.PUBLISHED

    # Step 7: Verify Retrievability
    assert publication_engine.is_retrievable(
        knowledge_object_id=e2e_version.version_id,
        index_record_id=index_record.index_record_id,
        logical_collection=crops_col.collection_id,
    ) is True


# =====================================================================
# 2. BACKWARD LINEAGE & PROVENANCE VALIDATION
# =====================================================================

def test_e2e_backward_lineage_validation(
    e2e_source, e2e_document, e2e_version, e2e_provenance, e2e_metadata
):
    section = Section(
        section_id="sec_01",
        document_id=e2e_document.document_id,
        version_id=e2e_version.version_id,
        title="Identification",
        metadata=e2e_metadata,
        provenance=e2e_provenance,
    )

    unit = KnowledgeUnit(
        knowledge_unit_id="unit_01",
        document_id=e2e_document.document_id,
        version_id=e2e_version.version_id,
        section_id=section.section_id,
        content="Larvae identification marks.",
        metadata=e2e_metadata,
        provenance=e2e_provenance,
    )

    chunk = Chunk(
        chunk_id="chk_01",
        knowledge_unit_id=unit.knowledge_unit_id,
        document_id=e2e_document.document_id,
        version_id=e2e_version.version_id,
        parent_section_id=section.section_id,
        content="Larvae identification marks.",
        metadata=e2e_metadata,
        provenance=e2e_provenance,
    )

    # Valid complete lineage check
    assert validate_canonical_lineage(
        source=e2e_source,
        document=e2e_document,
        version=e2e_version,
        sections=[section],
        units=[unit],
        chunks=[chunk],
    ) is True

    # Broken lineage check (document mismatch)
    broken_doc = Document(
        document_id="doc_mismatch",
        source_id="src_other",
        title="Other Document",
        document_type="GUIDELINE",
    )
    with pytest.raises(LineageValidationError):
        validate_canonical_lineage(
            source=e2e_source,
            document=broken_doc,
            version=e2e_version,
        )


# =====================================================================
# 3. VERSIONING SUPERSESSION & RETIREMENT
# =====================================================================

def test_e2e_versioning_and_supersession(
    e2e_source, e2e_document, e2e_provenance, e2e_metadata
):
    collection_engine = KnowledgeCollectionEngine()
    pub_engine = KnowledgePublicationEngine(collection_engine=collection_engine)

    col = collection_engine.create_collection("Maize")

    # Publish Version 1.0
    pub_engine.publish_knowledge(
        knowledge_object_id="ver_1_0",
        collection_id=col.collection_id,
        source_id=e2e_source.source_id,
        document_id=e2e_document.document_id,
        version_id="ver_1_0",
        provenance=e2e_provenance,
        metadata=e2e_metadata,
    )
    assert pub_engine.is_retrievable("ver_1_0") is True

    # Publish Version 2.0
    pub_engine.publish_knowledge(
        knowledge_object_id="ver_2_0",
        collection_id=col.collection_id,
        source_id=e2e_source.source_id,
        document_id=e2e_document.document_id,
        version_id="ver_2_0",
        provenance=e2e_provenance,
        metadata=e2e_metadata,
    )
    assert pub_engine.is_retrievable("ver_2_0") is True

    # Supersede v1.0 with v2.0
    sup_record = pub_engine.supersede_version(
        old_version_id="ver_1_0",
        new_version_id="ver_2_0",
        document_id=e2e_document.document_id,
        reason="v2.0 introduces updated Fall Armyworm biological controls.",
    )

    assert sup_record.publication_status == PublicationStatus.SUPERSEDED
    assert pub_engine.is_retrievable("ver_1_0") is False
    assert pub_engine.is_retrievable("ver_2_0") is True


# =====================================================================
# 4. REBUILDABILITY FROM CANONICAL SOURCE OF TRUTH
# =====================================================================

def test_e2e_source_of_truth_rebuildability(
    e2e_source, e2e_document, e2e_version, e2e_provenance, e2e_metadata
):
    """Verify that index records can be completely cleared and rebuilt from canonical data."""
    dense_provider = FakeEmbeddingProvider(dimension=128)
    embedding_engine = KnowledgeEmbeddingEngine(provider=dense_provider)

    sparse_provider = FakeSparseProvider()
    sparse_engine = KnowledgeSparseEngine(provider=sparse_provider)

    adapter = FakeIndexAdapter()
    index_engine = KnowledgeIndexEngine(adapter=adapter)

    chunk = Chunk(
        chunk_id="chk_rebuild_1",
        knowledge_unit_id="unit_rebuild_1",
        document_id=e2e_document.document_id,
        version_id=e2e_version.version_id,
        content="Sample maize protection content",
        metadata=e2e_metadata,
        provenance=e2e_provenance,
    )

    dense_record = embedding_engine.embed_chunk(chunk)
    sparse_record = sparse_engine.generate_sparse_chunk(chunk)

    idx_record = index_engine.build_index_record(
        dense_record=dense_record,
        sparse_record=sparse_record,
        knowledge_collection="RebuildCol",
    )
    index_engine.index_record(idx_record)

    assert adapter.get_record("earthmind_knowledge", idx_record.index_record_id) is not None

    # Simulate index wipe
    adapter.collections["earthmind_knowledge"].clear()
    assert adapter.get_record("earthmind_knowledge", idx_record.index_record_id) is None

    # Rebuild from canonical derived records
    rebuilt_res = index_engine.rebuild_index([idx_record])
    assert rebuilt_res.status == "INDEXED"
    assert adapter.get_record("earthmind_knowledge", idx_record.index_record_id) is not None


# =====================================================================
# 5. FAILURE PATH ISOLATION & WEB SEARCH RULE
# =====================================================================

def test_e2e_failure_path_isolation_and_web_search_rule(
    e2e_source, e2e_document, e2e_version, e2e_provenance, e2e_metadata
):
    pub_engine = KnowledgePublicationEngine()

    # 1. Missing provenance causes publication eligibility error
    with pytest.raises(PublicationEligibilityError):
        pub_engine.publish_knowledge(
            knowledge_object_id="ver_bad_prov",
            source_id=e2e_source.source_id,
            document_id=e2e_document.document_id,
            version_id="ver_bad_prov",
            provenance=None,
        )

    # 2. Web search transient result publication blocked
    with pytest.raises(PublicationEligibilityError):
        pub_engine.publish_knowledge(
            knowledge_object_id="web_search_001",
            source_id="src_web",
            document_id="doc_web",
            version_id="ver_web",
            provenance=e2e_provenance,
            metadata=e2e_metadata,
            is_web_result=True,
            is_web_result_reviewed=False,
        )


# =====================================================================
# 6. INTERFACE ISOLATION & QDRANT BOUNDARY AUDIT
# =====================================================================

def test_e2e_interface_isolation_and_qdrant_boundary():
    """Verify that FakeIndexAdapter fulfills IKnowledgeIndexAdapter without calling Qdrant."""
    adapter = FakeIndexAdapter()
    assert adapter.is_available() is True
    assert adapter.health_check() is True

    adapter.create_collection("earthmind_test")
    status = adapter.get_status("earthmind_test")
    assert status["exists"] is True
    assert status["record_count"] == 0
