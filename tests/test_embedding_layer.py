"""Focused tests for C.2 Step 9 — Embedding Layer in EarthMind."""

import time
import pytest
from pydantic import ValidationError

from core.interfaces.embedding import IEmbeddingProvider
from core.schemas.embedding import (
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingStatus,
    SparseVector,
)
from core.errors.exceptions import (
    InvalidEmbeddingInputError,
    EmbeddingProviderUnavailableError,
    EmbeddingTimeoutError,
    EmbeddingDimensionMismatchError,
)
from modules.knowledge_base.enums import (
    KnowledgeContentType,
    KnowledgeLifecycleState,
    ProcessingStatus,
)
from modules.knowledge_base.canonical_models import (
    Chunk,
    Document,
    DocumentVersion,
    KnowledgeUnit,
    Source,
)
from modules.knowledge_base.provenance import Provenance
from modules.knowledge_base.embedding.fake_provider import FakeEmbeddingProvider
from modules.knowledge_base.embedding.adapter import EmbeddingAdapter
from modules.knowledge_base.embedding.record import EmbeddingRecord
from modules.knowledge_base.embedding.engine import (
    KnowledgeEmbeddingEngine,
    EmbeddingBatchResult,
)


@pytest.fixture
def sample_canonical_hierarchy():
    """Fixture providing Source, Document, Version, KnowledgeUnit, and Chunk."""
    source = Source(
        source_id="src_agri_01",
        source_name="FAO Agronomy Guide",
        source_type="GOVERNMENT_EXTENSION",
    )
    doc = Document(
        document_id="doc_maize_01",
        source_id=source.source_id,
        title="Maize Irrigation Guidelines",
        document_type="GUIDELINE",
    )
    version = DocumentVersion(
        version_id="ver_maize_1.0",
        document_id=doc.document_id,
        version_number="1.0.0",
    )
    ku = KnowledgeUnit(
        knowledge_unit_id="ku_001",
        document_id=doc.document_id,
        version_id=version.version_id,
        content_type=KnowledgeContentType.TEXT,
        content="Maize crops require 500-800 mm of water per growing season depending on climate.",
    )
    chunk = Chunk(
        chunk_id="chk_001",
        knowledge_unit_id=ku.knowledge_unit_id,
        document_id=doc.document_id,
        version_id=version.version_id,
        content="Maize crops require 500-800 mm of water per growing season depending on climate.",
        content_type=KnowledgeContentType.TEXT,
    )
    return {
        "source": source,
        "document": doc,
        "version": version,
        "unit": ku,
        "chunk": chunk,
    }


def test_1_embedding_request_creation():
    """Verify EmbeddingRequest payload creation and validation."""
    req = EmbeddingRequest(
        texts=["Irrigation schedule for wheat."],
        chunk_ids=["chk_100"],
        source_id="src_agri_01",
        include_sparse=True,
    )
    assert req.validate_request() is True
    assert req.texts == ["Irrigation schedule for wheat."]
    assert req.chunk_ids == ["chk_100"]
    assert req.include_sparse is True


def test_2_provider_abstraction_usage():
    """Verify engine depends strictly on IEmbeddingProvider/EmbeddingAdapter abstraction."""
    provider = FakeEmbeddingProvider(dimension=256)
    adapter = EmbeddingAdapter(provider)
    engine = KnowledgeEmbeddingEngine(adapter=adapter)

    assert isinstance(engine.adapter.provider, IEmbeddingProvider)
    assert engine.adapter.get_dimension() == 256


def test_3_mock_provider_execution():
    """Verify FakeEmbeddingProvider execution generates deterministic vectors offline."""
    provider = FakeEmbeddingProvider(dimension=128)
    adapter = EmbeddingAdapter(provider)
    res = adapter.embed_texts(["Soil testing for phosphorus."])

    assert res.status == EmbeddingStatus.SUCCESS
    assert len(res.embeddings[0]) == 128
    assert res.provider_metadata.is_mock is True


def test_4_embedding_result_validation(sample_canonical_hierarchy):
    """Verify embedding result structure and dimension validation."""
    engine = KnowledgeEmbeddingEngine()
    chk = sample_canonical_hierarchy["chunk"]

    rec = engine.embed_chunk(chk)
    assert isinstance(rec, EmbeddingRecord)
    assert rec.status == "ACTIVE"
    assert rec.dimension == 384
    assert len(rec.dense_vector) == 384


def test_5_provider_model_version_traceability(sample_canonical_hierarchy):
    """Verify provider, model, model version, and creation time traceability."""
    provider = FakeEmbeddingProvider(
        provider_name="custom_vendor",
        model_name="agri-embed-v2",
        model_version="2.1.0",
    )
    engine = KnowledgeEmbeddingEngine(provider=provider)
    chk = sample_canonical_hierarchy["chunk"]

    rec = engine.embed_chunk(chk)
    assert rec.provider == "custom_vendor"
    assert rec.model == "agri-embed-v2"
    assert rec.model_version == "2.1.0"
    assert rec.created_at is not None


def test_6_dense_representation_metadata(sample_canonical_hierarchy):
    """Verify metadata attached to dense vector representation."""
    engine = KnowledgeEmbeddingEngine()
    chk = sample_canonical_hierarchy["chunk"]

    rec = engine.embed_chunk(chk)
    assert rec.representation_type in ("DENSE", "HYBRID")
    assert rec.dense_vector is not None
    assert rec.dimension == len(rec.dense_vector)


def test_7_sparse_representation_compatibility(sample_canonical_hierarchy):
    """Verify sparse representation foundation when requested."""
    engine = KnowledgeEmbeddingEngine()
    chk = sample_canonical_hierarchy["chunk"]

    rec = engine.embed_chunk(chk, include_sparse=True)
    assert rec.representation_type == "HYBRID"
    assert rec.sparse_vector is not None
    assert isinstance(rec.sparse_vector, SparseVector)
    assert len(rec.sparse_vector.terms) > 0


def test_8_canonical_chunk_traceability(sample_canonical_hierarchy):
    """Verify embedding record remains explicitly traceable to canonical Chunk."""
    engine = KnowledgeEmbeddingEngine()
    chk = sample_canonical_hierarchy["chunk"]

    rec = engine.embed_chunk(chk)
    assert rec.chunk_id == chk.chunk_id
    assert rec.knowledge_unit_id == chk.knowledge_unit_id


def test_9_document_version_traceability(sample_canonical_hierarchy):
    """Verify document_id and version_id are preserved in embedding record."""
    engine = KnowledgeEmbeddingEngine()
    chk = sample_canonical_hierarchy["chunk"]

    rec = engine.embed_chunk(chk)
    assert rec.document_id == sample_canonical_hierarchy["document"].document_id
    assert rec.version_id == sample_canonical_hierarchy["version"].version_id


def test_10_embedding_version_distinction(sample_canonical_hierarchy):
    """Verify new embedding generation produces distinct embedding_id when provider/model changes."""
    chk = sample_canonical_hierarchy["chunk"]

    # Version A
    engine_a = KnowledgeEmbeddingEngine(provider=FakeEmbeddingProvider(provider_name="vendor_a"))
    rec_a = engine_a.embed_chunk(chk)

    # Version B
    engine_b = KnowledgeEmbeddingEngine(provider=FakeEmbeddingProvider(provider_name="vendor_b"))
    rec_b = engine_b.embed_chunk(chk)

    assert rec_a.embedding_id != rec_b.embedding_id
    assert rec_a.provider == "vendor_a"
    assert rec_b.provider == "vendor_b"


def test_11_regeneration_does_not_destroy_canonical_knowledge(sample_canonical_hierarchy):
    """Verify regenerating embedding creates new record without altering original Chunk content."""
    engine = KnowledgeEmbeddingEngine()
    chk = sample_canonical_hierarchy["chunk"]
    original_content = chk.content

    rec_1 = engine.embed_chunk(chk)
    rec_2 = engine.regenerate_embedding(chk, previous_record=rec_1)

    # Original canonical chunk content and IDs remain untouched
    assert chk.content == original_content
    assert chk.chunk_id == "chk_001"

    # Previous embedding record marked SUPERSEDED
    assert rec_1.status == "SUPERSEDED"
    assert rec_2.status == "ACTIVE"
    assert rec_1.embedding_id != rec_2.embedding_id


def test_12_multimodal_input_compatibility(sample_canonical_hierarchy):
    """Verify structured dictionary and table content types are converted to text representations."""
    engine = KnowledgeEmbeddingEngine()

    # Table KU
    ku_table = KnowledgeUnit(
        knowledge_unit_id="ku_tbl_1",
        document_id="doc_1",
        version_id="ver_1",
        content_type=KnowledgeContentType.TABLE,
        content={"columns": ["pH", "Moisture"], "rows": [[6.5, "22%"], [7.0, "18%"]]},
    )
    rec_table = engine.embed_knowledge_unit(ku_table)
    assert rec_table.status == "ACTIVE"
    assert rec_table.content_type == KnowledgeContentType.TABLE


def test_13_unsupported_representation_handling():
    """Verify explicit error when raw unsupported multimodal binary content is provided without multimodal provider."""
    engine = KnowledgeEmbeddingEngine()

    ku_image = KnowledgeUnit(
        knowledge_unit_id="ku_img_1",
        document_id="doc_1",
        version_id="ver_1",
        content_type=KnowledgeContentType.IMAGE,
        content=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR...",
    )

    with pytest.raises(InvalidEmbeddingInputError) as exc_info:
        engine.embed_knowledge_unit(ku_image)
    assert "Unsupported raw non-text content type" in str(exc_info.value)


def test_14_batch_embedding(sample_canonical_hierarchy):
    """Verify batch embedding generation for chunks."""
    engine = KnowledgeEmbeddingEngine()
    doc_id = sample_canonical_hierarchy["document"].document_id
    ver_id = sample_canonical_hierarchy["version"].version_id

    chunks = [
        Chunk(chunk_id=f"chk_batch_{i}", knowledge_unit_id="ku_001", document_id=doc_id, version_id=ver_id, content=f"Batch sentence {i}")
        for i in range(5)
    ]

    res = engine.embed_chunks_batch(chunks)
    assert res.lifecycle_state == KnowledgeLifecycleState.EMBEDDED
    assert res.total_count == 5
    assert res.success_count == 5
    assert len(res.records) == 5


def test_15_input_output_ordering_preservation(sample_canonical_hierarchy):
    """Verify batch processing preserves input ordering strictly."""
    engine = KnowledgeEmbeddingEngine()
    doc_id = sample_canonical_hierarchy["document"].document_id
    ver_id = sample_canonical_hierarchy["version"].version_id

    chunks = [
        Chunk(chunk_id="chk_alpha", knowledge_unit_id="ku_1", document_id=doc_id, version_id=ver_id, content="Alpha content"),
        Chunk(chunk_id="chk_beta", knowledge_unit_id="ku_1", document_id=doc_id, version_id=ver_id, content="Beta content"),
        Chunk(chunk_id="chk_gamma", knowledge_unit_id="ku_1", document_id=doc_id, version_id=ver_id, content="Gamma content"),
    ]

    res = engine.embed_chunks_batch(chunks)
    assert res.records[0].chunk_id == "chk_alpha"
    assert res.records[1].chunk_id == "chk_beta"
    assert res.records[2].chunk_id == "chk_gamma"


def test_16_partial_batch_failure_handling(sample_canonical_hierarchy):
    """Verify partial batch failure handling preserves valid items while capturing errors."""
    engine = KnowledgeEmbeddingEngine()
    doc_id = sample_canonical_hierarchy["document"].document_id
    ver_id = sample_canonical_hierarchy["version"].version_id

    chunks = [
        Chunk(chunk_id="chk_valid_1", knowledge_unit_id="ku_1", document_id=doc_id, version_id=ver_id, content="Valid text 1"),
        Chunk(chunk_id="chk_invalid_img", knowledge_unit_id="ku_1", document_id=doc_id, version_id=ver_id, content=b"binary", content_type=KnowledgeContentType.IMAGE),
        Chunk(chunk_id="chk_valid_2", knowledge_unit_id="ku_1", document_id=doc_id, version_id=ver_id, content="Valid text 2"),
    ]

    res = engine.embed_chunks_batch(chunks, allow_partial=True)
    assert res.lifecycle_state == KnowledgeLifecycleState.EMBEDDED
    assert res.total_count == 3
    assert res.success_count == 2
    assert res.failed_count == 1
    assert res.failed_items[0]["index"] == 1
    assert res.failed_items[0]["chunk_id"] == "chk_invalid_img"


def test_17_provider_failure_handling(sample_canonical_hierarchy):
    """Verify explicit failure result when provider is unavailable."""
    provider = FakeEmbeddingProvider(available=False)
    engine = KnowledgeEmbeddingEngine(provider=provider)
    chk = sample_canonical_hierarchy["chunk"]

    with pytest.raises(EmbeddingProviderUnavailableError):
        engine.embed_chunk(chk)

    # Batch test returns failed batch result
    res_batch = engine.embed_chunks_batch([chk])
    assert res_batch.lifecycle_state == KnowledgeLifecycleState.FAILED
    assert res_batch.status == ProcessingStatus.FAILED


def test_18_timeout_and_error_handling(sample_canonical_hierarchy):
    """Verify handling of simulated timeout errors from provider."""
    provider = FakeEmbeddingProvider(simulated_error="timeout")
    engine = KnowledgeEmbeddingEngine(provider=provider)
    chk = sample_canonical_hierarchy["chunk"]

    with pytest.raises(EmbeddingTimeoutError):
        engine.embed_chunk(chk)


def test_19_dimension_validation(sample_canonical_hierarchy):
    """Verify dimension validation in EmbeddingRecord."""
    # Attempt creating record with mismatched vector length and explicit dimension
    with pytest.raises(ValidationError) as exc_info:
        EmbeddingRecord(
            embedding_id="emb_err",
            source_id="src_1",
            document_id="doc_1",
            version_id="ver_1",
            chunk_id="chk_1",
            provider="fake",
            model="test",
            dimension=384,
            dense_vector=[0.1, 0.2, 0.3],  # Length 3 != 384
        )
    assert "dimension mismatch" in str(exc_info.value).lower()


def test_20_provenance_preservation(sample_canonical_hierarchy):
    """Verify embedding processing step is appended to provenance chain."""
    engine = KnowledgeEmbeddingEngine()
    chk = sample_canonical_hierarchy["chunk"]

    rec = engine.embed_chunk(chk)
    assert rec.provenance is not None
    assert rec.provenance.processing_stage == "EMBEDDING"
    assert rec.provenance.representation_provider["provider_name"] == "fake"
    assert len(rec.provenance.processing_steps) >= 1


def test_21_lifecycle_integration(sample_canonical_hierarchy):
    """Verify KnowledgeLifecycleState transitions to EMBEDDED upon successful generation."""
    engine = KnowledgeEmbeddingEngine()
    chk = sample_canonical_hierarchy["chunk"]

    res_batch = engine.embed_chunks_batch([chk])
    assert res_batch.lifecycle_state == KnowledgeLifecycleState.EMBEDDED


def test_22_no_direct_vector_db_dependency():
    """Verify embedding module imports do not depend on Qdrant, ORMs, or external vector DB drivers."""
    import modules.knowledge_base.embedding as emb_mod

    module_dir = dir(emb_mod)
    assert "EmbeddingRecord" in module_dir
    assert "KnowledgeEmbeddingEngine" in module_dir

    # Check source code text to ensure no vector store imports exist
    import inspect
    from modules.knowledge_base.embedding import engine, record

    for mod in [engine, record]:
        src = inspect.getsource(mod)
        assert "qdrant" not in src.lower()
        assert "pinecone" not in src.lower()
        assert "milvus" not in src.lower()
        assert "sqlalchemy" not in src.lower()
