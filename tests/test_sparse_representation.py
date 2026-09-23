"""Focused tests for C.2 Step 10 — Sparse Representation in EarthMind."""

import math
import pytest
from pydantic import ValidationError

from core.interfaces.sparse import ISparseRepresentationProvider
from core.schemas.embedding import SparseVector, EmbeddingStatus
from core.schemas.sparse import (
    SparseRepresentationRequest,
    SparseRepresentationResponse,
    validate_sparse_vector,
)
from core.errors.exceptions import (
    InvalidSparseInputError,
    SparseProviderUnavailableError,
    SparseVectorValidationError,
    EmbeddingTimeoutError,
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
from modules.knowledge_base.sparse.fake_provider import FakeSparseProvider
from modules.knowledge_base.sparse.adapter import SparseRepresentationAdapter
from modules.knowledge_base.sparse.record import SparseRepresentationRecord
from modules.knowledge_base.sparse.engine import KnowledgeSparseEngine, SparseBatchResult
from modules.knowledge_base.embedding.engine import KnowledgeEmbeddingEngine
from modules.knowledge_base.embedding.record import EmbeddingRecord


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


def test_1_sparse_request_creation():
    """Verify SparseRepresentationRequest payload creation and validation."""
    req = SparseRepresentationRequest(
        texts=["Irrigation schedule for wheat."],
        chunk_ids=["chk_100"],
        source_id="src_agri_01",
        vocabulary_id="agri-vocab-30k",
    )
    assert req.validate_request() is True
    assert req.texts == ["Irrigation schedule for wheat."]
    assert req.chunk_ids == ["chk_100"]
    assert req.vocabulary_id == "agri-vocab-30k"


def test_2_sparse_provider_abstraction():
    """Verify engine depends strictly on ISparseRepresentationProvider/SparseRepresentationAdapter interface."""
    provider = FakeSparseProvider(vocabulary_size=10000)
    adapter = SparseRepresentationAdapter(provider)
    engine = KnowledgeSparseEngine(adapter=adapter)

    assert isinstance(engine.adapter.provider, ISparseRepresentationProvider)
    assert engine.adapter.get_vocabulary_size() == 10000


def test_3_mock_sparse_provider_execution():
    """Verify FakeSparseProvider execution generates deterministic sparse vectors offline."""
    provider = FakeSparseProvider(vocabulary_size=20000)
    adapter = SparseRepresentationAdapter(provider)
    res = adapter.generate_sparse_texts(["Soil testing for phosphorus."])

    assert res.status == EmbeddingStatus.SUCCESS
    assert len(res.sparse_vectors) == 1
    assert len(res.sparse_vectors[0].indices) > 0
    assert res.provider_metadata.is_mock is True


def test_4_sparse_result_validation(sample_canonical_hierarchy):
    """Verify sparse representation record structure and validation."""
    engine = KnowledgeSparseEngine()
    chk = sample_canonical_hierarchy["chunk"]

    rec = engine.generate_sparse_chunk(chk)
    assert isinstance(rec, SparseRepresentationRecord)
    assert rec.status == "ACTIVE"
    assert rec.representation_type == "SPARSE"
    assert isinstance(rec.sparse_vector, SparseVector)
    assert len(rec.sparse_vector.indices) == len(rec.sparse_vector.values)


def test_5_index_value_alignment():
    """Verify validation enforces index/value alignment (equal lengths)."""
    sv = SparseVector(indices=[1, 2, 3], values=[0.5, 0.8], terms={"a": 0.5, "b": 0.8})
    with pytest.raises(ValueError) as exc_info:
        validate_sparse_vector(sv)
    assert "index/value count mismatch" in str(exc_info.value).lower()


def test_6_invalid_index_handling():
    """Verify validation detects negative indices or indices exceeding vocabulary size."""
    # Negative index
    sv_neg = SparseVector(indices=[-5, 10], values=[0.1, 0.2])
    with pytest.raises(ValueError) as exc_info:
        validate_sparse_vector(sv_neg)
    assert "non-negative integer" in str(exc_info.value).lower()

    # Out of vocabulary index
    sv_oov = SparseVector(indices=[100, 50000], values=[0.1, 0.2])
    with pytest.raises(ValueError) as exc_info:
        validate_sparse_vector(sv_oov, vocabulary_size=30000)
    assert "exceeds vocabulary size" in str(exc_info.value).lower()


def test_7_invalid_weight_handling():
    """Verify validation detects non-finite weights (NaN or infinity)."""
    sv_nan = SparseVector(indices=[1, 2], values=[0.5, float("nan")])
    with pytest.raises(ValueError) as exc_info:
        validate_sparse_vector(sv_nan)
    assert "finite real number" in str(exc_info.value).lower()

    sv_inf = SparseVector(indices=[1, 2], values=[0.5, float("inf")])
    with pytest.raises(ValueError) as exc_info:
        validate_sparse_vector(sv_inf)
    assert "finite real number" in str(exc_info.value).lower()


def test_8_provider_model_version_traceability(sample_canonical_hierarchy):
    """Verify provider, model, model version, vocabulary_id, and creation time traceability."""
    provider = FakeSparseProvider(
        provider_name="custom_bm25",
        model_name="agri-bm25-v1",
        model_version="1.2.0",
        vocabulary_id="agri-en-50k",
        vocabulary_size=50000,
    )
    engine = KnowledgeSparseEngine(provider=provider)
    chk = sample_canonical_hierarchy["chunk"]

    rec = engine.generate_sparse_chunk(chk)
    assert rec.provider == "custom_bm25"
    assert rec.model == "agri-bm25-v1"
    assert rec.model_version == "1.2.0"
    assert rec.vocabulary_id == "agri-en-50k"
    assert rec.vocabulary_size == 50000
    assert rec.created_at is not None


def test_9_canonical_chunk_traceability(sample_canonical_hierarchy):
    """Verify sparse record remains explicitly traceable to canonical Chunk."""
    engine = KnowledgeSparseEngine()
    chk = sample_canonical_hierarchy["chunk"]

    rec = engine.generate_sparse_chunk(chk)
    assert rec.chunk_id == chk.chunk_id
    assert rec.knowledge_unit_id == chk.knowledge_unit_id


def test_10_document_version_traceability(sample_canonical_hierarchy):
    """Verify document_id and version_id are preserved in sparse representation record."""
    engine = KnowledgeSparseEngine()
    chk = sample_canonical_hierarchy["chunk"]

    rec = engine.generate_sparse_chunk(chk)
    assert rec.document_id == sample_canonical_hierarchy["document"].document_id
    assert rec.version_id == sample_canonical_hierarchy["version"].version_id


def test_11_provenance_preservation(sample_canonical_hierarchy):
    """Verify sparse generation processing step is appended to provenance chain."""
    engine = KnowledgeSparseEngine()
    chk = sample_canonical_hierarchy["chunk"]

    rec = engine.generate_sparse_chunk(chk)
    assert rec.provenance is not None
    assert rec.provenance.processing_stage == "SPARSE_REPRESENTATION"
    assert rec.provenance.representation_provider["provider_name"] == "fake_sparse"
    assert len(rec.provenance.processing_steps) >= 1


def test_12_lifecycle_integration(sample_canonical_hierarchy):
    """Verify KnowledgeLifecycleState transitions to EMBEDDED upon successful sparse generation."""
    engine = KnowledgeSparseEngine()
    chk = sample_canonical_hierarchy["chunk"]

    res_batch = engine.generate_sparse_chunks_batch([chk])
    assert res_batch.lifecycle_state == KnowledgeLifecycleState.EMBEDDED


def test_13_deterministic_representation_ordering():
    """Verify feature/index ordering is strictly deterministic in generated sparse vectors."""
    provider = FakeSparseProvider(vocabulary_size=30000)
    adapter = SparseRepresentationAdapter(provider)

    res1 = adapter.generate_sparse_texts(["Nitrogen fertilizer application timing."])
    res2 = adapter.generate_sparse_texts(["Nitrogen fertilizer application timing."])

    indices1 = res1.sparse_vectors[0].indices
    indices2 = res2.sparse_vectors[0].indices

    # Verify indices are sorted in ascending order
    assert indices1 == sorted(indices1)
    # Verify deterministic output across identical calls
    assert indices1 == indices2
    assert res1.sparse_vectors[0].values == res2.sparse_vectors[0].values


def test_14_batch_processing(sample_canonical_hierarchy):
    """Verify batch sparse representation generation for chunks."""
    engine = KnowledgeSparseEngine()
    doc_id = sample_canonical_hierarchy["document"].document_id
    ver_id = sample_canonical_hierarchy["version"].version_id

    chunks = [
        Chunk(
            chunk_id=f"chk_batch_sp_{i}",
            knowledge_unit_id="ku_001",
            document_id=doc_id,
            version_id=ver_id,
            content=f"Batch sentence for sparse test {i}",
        )
        for i in range(5)
    ]

    res = engine.generate_sparse_chunks_batch(chunks)
    assert res.lifecycle_state == KnowledgeLifecycleState.EMBEDDED
    assert res.total_count == 5
    assert res.success_count == 5
    assert len(res.records) == 5


def test_15_batch_ordering_preservation(sample_canonical_hierarchy):
    """Verify batch processing preserves input ordering strictly."""
    engine = KnowledgeSparseEngine()
    doc_id = sample_canonical_hierarchy["document"].document_id
    ver_id = sample_canonical_hierarchy["version"].version_id

    chunks = [
        Chunk(chunk_id="chk_alpha_sp", knowledge_unit_id="ku_1", document_id=doc_id, version_id=ver_id, content="Alpha text"),
        Chunk(chunk_id="chk_beta_sp", knowledge_unit_id="ku_1", document_id=doc_id, version_id=ver_id, content="Beta text"),
        Chunk(chunk_id="chk_gamma_sp", knowledge_unit_id="ku_1", document_id=doc_id, version_id=ver_id, content="Gamma text"),
    ]

    res = engine.generate_sparse_chunks_batch(chunks)
    assert res.records[0].chunk_id == "chk_alpha_sp"
    assert res.records[1].chunk_id == "chk_beta_sp"
    assert res.records[2].chunk_id == "chk_gamma_sp"


def test_16_partial_batch_failure_handling(sample_canonical_hierarchy):
    """Verify partial batch failure handling preserves valid items while capturing errors."""
    engine = KnowledgeSparseEngine()
    doc_id = sample_canonical_hierarchy["document"].document_id
    ver_id = sample_canonical_hierarchy["version"].version_id

    chunks = [
        Chunk(chunk_id="chk_v1", knowledge_unit_id="ku_1", document_id=doc_id, version_id=ver_id, content="Valid text 1"),
        Chunk(
            chunk_id="chk_img_err",
            knowledge_unit_id="ku_1",
            document_id=doc_id,
            version_id=ver_id,
            content=b"binary_image",
            content_type=KnowledgeContentType.IMAGE,
        ),
        Chunk(chunk_id="chk_v2", knowledge_unit_id="ku_1", document_id=doc_id, version_id=ver_id, content="Valid text 2"),
    ]

    res = engine.generate_sparse_chunks_batch(chunks, allow_partial=True)
    assert res.lifecycle_state == KnowledgeLifecycleState.EMBEDDED
    assert res.total_count == 3
    assert res.success_count == 2
    assert res.failed_count == 1
    assert res.failed_items[0]["index"] == 1
    assert res.failed_items[0]["chunk_id"] == "chk_img_err"


def test_17_provider_failure_handling(sample_canonical_hierarchy):
    """Verify explicit failure result when provider is unavailable."""
    provider = FakeSparseProvider(available=False)
    engine = KnowledgeSparseEngine(provider=provider)
    chk = sample_canonical_hierarchy["chunk"]

    with pytest.raises(SparseProviderUnavailableError):
        engine.generate_sparse_chunk(chk)

    # Batch test returns failed batch result
    res_batch = engine.generate_sparse_chunks_batch([chk])
    assert res_batch.lifecycle_state == KnowledgeLifecycleState.FAILED
    assert res_batch.status == ProcessingStatus.FAILED


def test_18_unsupported_input_handling():
    """Verify explicit error when raw unsupported multimodal binary content is provided."""
    engine = KnowledgeSparseEngine()

    ku_image = KnowledgeUnit(
        knowledge_unit_id="ku_img_sp_1",
        document_id="doc_1",
        version_id="ver_1",
        content_type=KnowledgeContentType.IMAGE,
        content=b"\x89PNG\r\n\x1a\n\x00...",
    )

    with pytest.raises(InvalidSparseInputError) as exc_info:
        engine.generate_sparse_knowledge_unit(ku_image)
    assert "Unsupported raw non-text content type" in str(exc_info.value)


def test_19_dense_and_sparse_coexistence(sample_canonical_hierarchy):
    """Verify dense and sparse representations coexist independently for the same canonical chunk."""
    dense_engine = KnowledgeEmbeddingEngine()
    sparse_engine = KnowledgeSparseEngine()

    chk = sample_canonical_hierarchy["chunk"]

    dense_rec = dense_engine.embed_chunk(chk)
    sparse_rec = sparse_engine.generate_sparse_chunk(chk)

    # Both reference the same canonical chunk & lineage
    assert dense_rec.chunk_id == chk.chunk_id
    assert sparse_rec.chunk_id == chk.chunk_id
    assert dense_rec.document_id == chk.document_id
    assert sparse_rec.document_id == chk.document_id

    # Their payloads remain independent
    assert dense_rec.dense_vector is not None
    assert dense_rec.representation_type == "DENSE"
    assert sparse_rec.sparse_vector is not None
    assert sparse_rec.representation_type == "SPARSE"
    assert dense_rec.embedding_id != sparse_rec.representation_id


def test_20_no_direct_vector_db_dependency():
    """Verify sparse representation module imports do not depend on vector DBs or ORMs."""
    import modules.knowledge_base.sparse as sparse_mod

    module_dir = dir(sparse_mod)
    assert "SparseRepresentationRecord" in module_dir
    assert "KnowledgeSparseEngine" in module_dir

    import inspect
    from modules.knowledge_base.sparse import engine, record, adapter

    for mod in [engine, record, adapter]:
        src = inspect.getsource(mod)
        assert "qdrant" not in src.lower()
        assert "pinecone" not in src.lower()
        assert "milvus" not in src.lower()
        assert "elasticsearch" not in src.lower()
        assert "sqlalchemy" not in src.lower()
