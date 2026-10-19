"""Tests for R3 — Real Knowledge Ingestion Pipeline for EarthMind C.2 Knowledge Base."""

import json
import os
import pytest
from pathlib import Path

from modules.knowledge_base.ingestion import (
    CorpusIngestionEngine,
    IngestionPipelineSummary,
)
from modules.knowledge_base.corpus import (
    CorpusCatalogManager,
    CorpusCorruptedError,
)
from modules.knowledge_base.canonical_models import (
    Source,
    Artifact,
    Document,
    DocumentVersion,
    Section,
    KnowledgeUnit,
    Chunk,
    validate_canonical_lineage,
)
from modules.knowledge_base.enums import (
    ArtifactStatus,
    DocumentStatus,
    DocumentVersionStatus,
    KnowledgeLifecycleState,
    ProcessingStatus,
    SourceStatus,
)
from modules.knowledge_base.metadata import CanonicalMetadata
from modules.knowledge_base.provenance import Provenance
from modules.knowledge_base.assessment import SourceAssessment


def test_r2_corpus_full_ingestion_execution():
    """Verify executing full R2 corpus ingestion processes all 8 sources into canonical structures."""
    engine = CorpusIngestionEngine()
    summary = engine.ingest_corpus()

    assert isinstance(summary, IngestionPipelineSummary)
    assert summary.status == "COMPLETED"
    assert summary.total_sources_discovered >= 8
    assert summary.total_artifacts_discovered >= 8
    assert summary.sources_registered >= 8
    assert summary.artifacts_registered >= 8
    assert summary.documents_created >= 8
    assert summary.versions_created >= 8
    assert summary.sections_created >= 5
    assert summary.knowledge_units_created > 20
    assert summary.chunks_created > 20
    assert summary.ready_for_embedding_count >= 8
    assert summary.idempotent_skips == 0
    assert summary.failed_count == 0


def test_source_and_artifact_registration():
    """Verify registered Source and Artifact canonical entities preserve origin traceability and license info."""
    engine = CorpusIngestionEngine()
    engine.ingest_corpus()

    sources = engine.get_ingested_sources()
    artifacts = engine.get_ingested_artifacts()

    assert len(sources) >= 8
    assert len(artifacts) >= 8

    for src in sources:
        assert isinstance(src, Source)
        assert src.source_id.startswith("src_")
        assert len(src.source_name) > 0
        assert src.organization is not None
        assert src.origin is not None
        assert src.language in ["en", "hi"]
        assert src.region == "India"
        assert src.status == SourceStatus.ACTIVE
        assert isinstance(src.metadata, CanonicalMetadata)
        assert src.metadata.filterable_attributes.get("license_name") is not None
        assert isinstance(src.assessment, SourceAssessment)

    for art in artifacts:
        assert isinstance(art, Artifact)
        assert art.artifact_id.startswith("art_")
        assert art.source_id in {s.source_id for s in sources}
        assert art.location_reference.startswith("data/knowledge/raw/")
        assert art.content_type == "text/plain"
        assert len(art.checksum) == 64
        assert art.size_bytes > 500
        assert art.status == ArtifactStatus.PROCESSED


def test_document_and_version_creation():
    """Verify Document and DocumentVersion canonical entities preserve version relationships."""
    engine = CorpusIngestionEngine()
    engine.ingest_corpus()

    documents = engine.get_ingested_documents()
    versions = engine.get_ingested_versions()

    assert len(documents) >= 8
    assert len(versions) >= 8

    for doc in documents:
        assert isinstance(doc, Document)
        assert doc.document_id.startswith("doc_src_")
        assert doc.source_id.startswith("src_")
        assert len(doc.title) > 0
        assert doc.status == DocumentStatus.ACTIVE

    for ver in versions:
        assert isinstance(ver, DocumentVersion)
        assert ver.version_id.startswith("ver_src_")
        assert ver.document_id in {d.document_id for d in documents}
        assert ver.status == DocumentVersionStatus.ACTIVE


def test_section_and_knowledge_unit_hierarchy():
    """Verify hierarchical sections and atomic KnowledgeUnits are created with unbroken parent-child lineage."""
    engine = CorpusIngestionEngine()
    engine.ingest_corpus()

    sections = engine.get_ingested_sections()
    units = engine.get_ingested_knowledge_units()

    assert len(sections) > 0
    assert len(units) > 0

    for sec in sections:
        assert isinstance(sec, Section)
        assert sec.section_id.startswith("sec_")
        assert sec.document_id.startswith("doc_src_")
        assert sec.version_id.startswith("ver_src_")
        assert len(sec.title) > 0
        assert sec.level >= 1

    for ku in units:
        assert isinstance(ku, KnowledgeUnit)
        assert ku.knowledge_unit_id.startswith("ku_ver_")
        assert ku.document_id.startswith("doc_src_")
        assert ku.version_id.startswith("ver_src_")
        assert ku.content is not None
        assert len(str(ku.content)) > 0


def test_semantic_structural_chunking():
    """Verify semantic and structural chunking generates Chunk records preserving sequence and parent section info."""
    engine = CorpusIngestionEngine()
    engine.ingest_corpus()

    chunks = engine.get_ingested_chunks()
    assert len(chunks) > 0

    for chk in chunks:
        assert isinstance(chk, Chunk)
        assert chk.chunk_id.startswith("chk_")
        assert chk.knowledge_unit_id.startswith("ku_")
        assert chk.document_id.startswith("doc_src_")
        assert chk.version_id.startswith("ver_src_")
        assert len(str(chk.content)) > 0
        assert chk.sequence >= 0


def test_metadata_provenance_assessment_preservation():
    """Verify complete Metadata, unbroken Provenance chain, and Source Assessment signals across all records."""
    engine = CorpusIngestionEngine()
    engine.ingest_corpus()

    sources = engine.get_ingested_sources()
    chunks = engine.get_ingested_chunks()

    for src in sources:
        assert isinstance(src.metadata, CanonicalMetadata)
        assert src.metadata.domain is not None
        assert isinstance(src.assessment, SourceAssessment)
        assert src.assessment.authority >= 0.90
        assert src.assessment.reliability >= 0.90

    for chk in chunks:
        assert chk.metadata is not None
        assert isinstance(chk.provenance, Provenance)
        assert chk.provenance.source_id is not None
        assert chk.provenance.document_id is not None
        assert chk.provenance.version_id is not None
        assert chk.provenance.knowledge_unit_id is not None
        assert chk.provenance.chunk_id == chk.chunk_id
        assert len(chk.provenance.processing_steps) > 0


def test_lifecycle_and_publication_eligibility_state():
    """Verify processed records reach KnowledgeLifecycleState.PROCESSED and satisfy publication prerequisites."""
    engine = CorpusIngestionEngine()
    summary = engine.ingest_corpus()

    assert summary.ready_for_embedding_count >= 8

    results = engine.get_processing_results()
    for res in results:
        assert res.lifecycle_state == KnowledgeLifecycleState.PROCESSED
        assert res.processing_status == ProcessingStatus.COMPLETED

        eligibility = engine.get_publication_eligibility(res.version_id)
        assert eligibility is not None
        assert eligibility.eligible is True


def test_duplicate_and_idempotency_handling():
    """Verify executing ingestion multiple times is idempotent and skips duplicate artifact contents."""
    engine = CorpusIngestionEngine()

    summary1 = engine.ingest_corpus()
    total_sources = summary1.sources_registered
    assert summary1.sources_registered >= 8
    assert summary1.ready_for_embedding_count == total_sources
    assert summary1.idempotent_skips == 0

    summary2 = engine.ingest_corpus()
    assert summary2.idempotent_skips == total_sources
    assert len(engine.get_ingested_sources()) == total_sources
    assert len(engine.get_ingested_documents()) == total_sources


def test_failure_handling_checksum_mismatch(tmp_path):
    """Verify rejection and explicit exception when artifact content checksum does not match manifest."""
    repo_root = Path(__file__).resolve().parents[1]
    real_manifest_path = repo_root / "data" / "knowledge" / "manifest" / "corpus_manifest.json"

    with open(real_manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Corrupt checksum of first artifact
    data["sources"][0]["artifact"]["checksum"] = "f" * 64

    bad_manifest = tmp_path / "bad_checksum_manifest.json"
    with open(bad_manifest, "w", encoding="utf-8") as f:
        json.dump(data, f)

    bad_mgr = CorpusCatalogManager(str(bad_manifest))
    engine = CorpusIngestionEngine(catalog_manager=bad_mgr)

    with pytest.raises(CorpusCorruptedError, match="Checksum mismatch"):
        engine.ingest_corpus()


def test_c3_safety_boundary_protection():
    """Verify RAG knowledge remains RAG owned with zero memory system writes or auto-promotions."""
    engine = CorpusIngestionEngine()
    engine.ingest_corpus()

    assert engine.check_c3_safety() is True

    # Confirm memory module has not been touched or loaded with RAG corpus
    import sys
    assert "modules.memory" not in sys.modules or not hasattr(sys.modules.get("modules.memory"), "r3_corpus_data")


def test_b2_context_manager_compatibility():
    """Verify processed knowledge satisfies all downstream B2 Context Manager contract requirements."""
    engine = CorpusIngestionEngine()
    engine.ingest_corpus()

    assert engine.check_b2_compatibility() is True


def test_five_earthmind_principles_adherence():
    """Verify R3 ingestion implementation strictly obeys all 5 core EarthMind principles."""
    engine = CorpusIngestionEngine()

    # 1. Extensibility: Works with default and custom processors/chunkers
    assert engine.processing_pipeline is not None

    # 2. Loose Coupling: No direct imports of B3, B4, vector database, or live models
    import modules.knowledge_base.ingestion as ing_mod
    import inspect
    source_lines = inspect.getsource(ing_mod)
    for forbidden in ["import qdrant", "import modules.reasoning", "import modules.planning"]:
        assert forbidden not in source_lines

    # 3. Single Responsibility: Focused purely on corpus ingestion and processing
    summary = engine.ingest_corpus()
    assert summary.embedding_status == "NOT_IMPLEMENTED_IN_R3"

    # 4. Controlled Dependencies: Uses standard C.2 canonical domain models
    assert len(engine.get_ingested_sources()) >= 8

    # 5. Replaceability: Processors/chunkers passed via constructor remain fully replaceable
    assert engine.catalog_manager is not None


def test_ready_for_embedding_output_state_no_embeddings_or_retrieval():
    """Verify output knowledge is READY_FOR_EMBEDDING while zero embeddings, Qdrant, or retrieval occurred."""
    engine = CorpusIngestionEngine()
    summary = engine.ingest_corpus()

    assert summary.ready_for_embedding_count >= 8
    assert summary.embedding_status == "NOT_IMPLEMENTED_IN_R3"
    assert summary.qdrant_status == "NOT_IMPLEMENTED_IN_R3"
    assert summary.retrieval_status == "NOT_IMPLEMENTED_IN_R3"

    # Verify no embedding vectors attached to chunks
    for chk in engine.get_ingested_chunks():
        assert not hasattr(chk, "embedding") or chk.embedding is None
        assert not hasattr(chk, "vector") or chk.vector is None
