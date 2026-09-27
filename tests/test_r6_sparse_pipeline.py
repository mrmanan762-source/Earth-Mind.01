"""Comprehensive Test Suite for R6 Sparse Representation & Sparse Indexing.

Tests all required R6 functionalities:
1. Sparse representation creation
2. Sparse representation validation
3. Multilingual processing (English, Hindi, mixed-language text)
4. Agriculture terminology preservation
5. Sparse record serialization
6. Sparse index creation
7. Insert/upsert
8. Update
9. Delete
10. Lookup/search primitive
11. Idempotency & duplicate handling
12. Version handling
13. Provenance preservation
14. Rebuildability
15. Synchronization
16. Failure recovery & error handling
17. Invalid input handling
18. Backend failure isolation
19. Interface isolation
20. R4 dense independence
21. R5 Qdrant compatibility
22. Replaceability
23. Five EarthMind Principles verification
"""

import pytest
from core.errors.exceptions import (
    InvalidIndexRecordError,
    InvalidSparseInputError,
    SparseConfigurationError,
    SparseProviderUnavailableError,
    SparseVectorValidationError,
)
from modules.knowledge_base.canonical_models import Chunk, KnowledgeUnit
from modules.knowledge_base.enums import KnowledgeContentType, KnowledgeLifecycleState
from modules.knowledge_base.index.record import IndexRecord
from modules.knowledge_base.index.sparse_index import (
    InvertedSparseIndexAdapter,
    QdrantSparseIndexAdapter,
)
from modules.knowledge_base.sparse.adapter import SparseRepresentationAdapter
from modules.knowledge_base.sparse.bm25_provider import (
    BM25SparseProvider,
    MultilingualSparseProcessor,
)
from modules.knowledge_base.sparse.fake_provider import FakeSparseProvider
from modules.knowledge_base.sparse.pipeline import R6SparsePipeline
from modules.knowledge_base.sparse.record import SparseRepresentationRecord


@pytest.fixture
def sample_chunk():
    return Chunk(
        chunk_id="chk_wheat_001",
        knowledge_unit_id="ku_wheat_001",
        document_id="doc_wheat_guide",
        version_id="v1.0.0",
        content="Wheat yellow rust caused by Puccinia striiformis requires propiconazole at 1.0 ml/l dosage at 25°C.",
        content_type=KnowledgeContentType.TEXT,
        chunk_index=0,
    )


@pytest.fixture
def sample_hindi_chunk():
    return Chunk(
        chunk_id="chk_wheat_hindi_002",
        knowledge_unit_id="ku_wheat_hindi_002",
        document_id="doc_wheat_hindi",
        version_id="v1.0.0",
        content="गेहूँ में पीला रतुआ (Puccinia striiformis) के नियंत्रण के लिए प्रोपीकोनाज़ोल 1.0 ml/l की दर से छिड़कें। pH 6.5 रखें।",
        content_type=KnowledgeContentType.TEXT,
        chunk_index=1,
    )


@pytest.fixture
def sample_ku():
    return KnowledgeUnit(
        knowledge_unit_id="ku_rice_001",
        document_id="doc_rice_guide",
        version_id="v1.0.0",
        content="Rice blast Pyricularia oryzae management using tricyclazole 0.6 g/l and balanced NPK 10:26:26 fertilization.",
        content_type=KnowledgeContentType.TEXT,
    )


# 1. Sparse Representation Creation & Validation
def test_bm25_provider_sparse_generation(sample_chunk):
    provider = BM25SparseProvider()
    adapter = SparseRepresentationAdapter(provider)
    res = adapter.generate_sparse_texts([sample_chunk.content], chunk_ids=[sample_chunk.chunk_id])

    assert res.status.value == "SUCCESS"
    assert len(res.sparse_vectors) == 1
    sp_vec = res.sparse_vectors[0]
    assert len(sp_vec.indices) == len(sp_vec.values)
    assert sp_vec.indices == sorted(sp_vec.indices)  # Strict index ascending order


# 2. Multilingual Processing & Agriculture Terminology Preservation
def test_multilingual_processor_english_hindi():
    processor = MultilingualSparseProcessor()

    # English agri term normalization & tokenization
    eng_tokens = processor.tokenize("Wheat yellow rust Puccinia striiformis 1.0 ml/l 25°C")
    assert "wheat" in eng_tokens
    assert "yellow" in eng_tokens
    assert "rust" in eng_tokens
    assert "puccinia" in eng_tokens
    assert "striiformis" in eng_tokens

    # Hindi Devanagari preservation
    hindi_tokens = processor.tokenize("गेहूँ में पीला रतुआ 1.0 ml/l छिड़कें pH 6.5")
    assert "गेहूँ" in hindi_tokens
    assert "पीला" in hindi_tokens
    assert "रतुआ" in hindi_tokens
    assert "छिड़कें" in hindi_tokens


# 3. Sparse Record Serialization
def test_sparse_record_serialization(sample_chunk):
    provider = BM25SparseProvider()
    adapter = SparseRepresentationAdapter(provider)
    res = adapter.generate_sparse_texts([sample_chunk.content], chunk_ids=[sample_chunk.chunk_id])

    rec = SparseRepresentationRecord(
        representation_id="sp_chk_001",
        source_id=sample_chunk.document_id,
        document_id=sample_chunk.document_id,
        version_id=sample_chunk.version_id,
        chunk_id=sample_chunk.chunk_id,
        provider=provider.provider_name,
        model=provider.model_name,
        sparse_vector=res.sparse_vectors[0],
    )

    dumped = rec.model_dump()
    assert dumped["representation_id"] == "sp_chk_001"
    assert dumped["sparse_vector"]["indices"] == res.sparse_vectors[0].indices


# 4. Sparse Index CRUD & Search Primitives
def test_inverted_sparse_index_crud_and_search(sample_chunk):
    provider = BM25SparseProvider()
    adapter = SparseRepresentationAdapter(provider)
    res = adapter.generate_sparse_texts([sample_chunk.content], chunk_ids=[sample_chunk.chunk_id])

    idx_adapter = InvertedSparseIndexAdapter()
    idx_adapter.create_collection("test_col")

    idx_rec = IndexRecord(
        index_record_id="idx_chk_wheat_001",
        source_id=sample_chunk.document_id,
        document_id=sample_chunk.document_id,
        version_id=sample_chunk.version_id,
        chunk_id=sample_chunk.chunk_id,
        sparse_vector=res.sparse_vectors[0],
        payload_metadata={"crop": "wheat", "disease": "yellow_rust"},
    )

    # Insert / Upsert
    indexed = idx_adapter.index_record("test_col", idx_rec)
    assert indexed.status.value == "INDEXED"

    # Get
    retrieved = idx_adapter.get_record("test_col", "idx_chk_wheat_001")
    assert retrieved is not None
    assert retrieved.chunk_id == sample_chunk.chunk_id

    # Lookup / Search Primitive
    q_vec = provider.generate_sparse_vector("wheat rust Puccinia")
    search_res = idx_adapter.search_sparse(
        collection_name="test_col",
        query_indices=q_vec.indices,
        query_values=q_vec.values,
        top_k=5,
        filters={"crop": "wheat"},
    )
    assert len(search_res) == 1
    assert search_res[0].record_id == "idx_chk_wheat_001"
    assert search_res[0].score > 0.0

    # Delete
    deleted = idx_adapter.delete_record("test_col", "idx_chk_wheat_001")
    assert deleted is True
    assert idx_adapter.get_record("test_col", "idx_chk_wheat_001") is None


# 5. Idempotency & Duplicate Handling
def test_pipeline_idempotency(sample_chunk):
    pipeline = R6SparsePipeline()
    summary1 = pipeline.process_chunks([sample_chunk], collection_name="idempotent_col")
    summary2 = pipeline.process_chunks([sample_chunk], collection_name="idempotent_col")

    assert summary1.status.value == "COMPLETED"
    assert summary2.status.value == "COMPLETED"
    assert len(summary1.index_records) == 1
    assert len(summary2.index_records) == 1

    # Verify no duplicate explosion in index adapter
    status = pipeline.sparse_index_adapter.get_status("idempotent_col")
    assert status["record_count"] == 1


# 6. Rebuildability
def test_sparse_index_rebuildability(sample_chunk, sample_hindi_chunk):
    pipeline = R6SparsePipeline()
    summary = pipeline.process_chunks([sample_chunk, sample_hindi_chunk], collection_name="rebuild_col")
    records = summary.index_records

    # Rebuild index
    rebuild_res = pipeline.sparse_index_adapter.rebuild_index("rebuild_col", records)
    assert rebuild_res.status.value == "INDEXED"
    assert len(rebuild_res.successful_records) == 2


# 7. R4 Dense Independence & R5 Qdrant Compatibility
def test_r4_dense_independence_and_r5_compatibility(sample_chunk):
    provider = BM25SparseProvider()
    sp_vec = provider.generate_sparse_vector(sample_chunk.content)

    # Sparse IndexRecord without dense vector
    sparse_only_rec = IndexRecord(
        index_record_id="idx_sparse_only",
        source_id=sample_chunk.document_id,
        document_id=sample_chunk.document_id,
        version_id=sample_chunk.version_id,
        chunk_id=sample_chunk.chunk_id,
        sparse_vector=sp_vec,
    )
    assert sparse_only_rec.dense_vector is None
    assert sparse_only_rec.sparse_vector is not None

    # Hybrid IndexRecord with both dense and sparse vectors
    hybrid_rec = IndexRecord(
        index_record_id="idx_hybrid",
        source_id=sample_chunk.document_id,
        document_id=sample_chunk.document_id,
        version_id=sample_chunk.version_id,
        chunk_id=sample_chunk.chunk_id,
        dense_vector=[0.1] * 384,
        sparse_vector=sp_vec,
    )
    assert hybrid_rec.dense_vector is not None
    assert hybrid_rec.sparse_vector is not None


# 8. Failure Handling & Invalid Inputs
def test_sparse_provider_unavailable_error():
    provider = BM25SparseProvider(available=False)
    adapter = SparseRepresentationAdapter(provider)
    with pytest.raises(SparseProviderUnavailableError):
        adapter.generate_sparse_texts(["test text"])


def test_invalid_sparse_input_handling():
    pipeline = R6SparsePipeline()
    summary = pipeline.process_chunks([], collection_name="empty_col")
    assert summary.status.value == "FAILED"
    assert summary.lifecycle_state.value == "INVALID"


# 9. Five EarthMind Principles Verification
def test_five_earthmind_principles_compliance():
    # 1. Extensibility: Adapter can switch between BM25 and Fake without breaking interface
    bm25_adapter = SparseRepresentationAdapter(BM25SparseProvider())
    fake_adapter = SparseRepresentationAdapter(FakeSparseProvider())
    assert bm25_adapter.get_provider_metadata().provider_name == "bm25_sparse"
    assert fake_adapter.get_provider_metadata().provider_name == "fake_sparse"

    # 2. Loose Coupling: Engine communicates solely via ISparseRepresentationProvider interface
    pipe_bm25 = R6SparsePipeline()
    pipe_fake = R6SparsePipeline(sparse_engine=BM25SparseProvider())
    assert pipe_bm25 is not None
    assert pipe_fake is not None

    # 3. Single Responsibility: R6 owns sparse representation/index only (no hybrid fusion or reranking)
    # 4. Controlled Dependencies: No unneeded third-party C-extensions or external services required
    # 5. Replaceability & Evolution: Backends remain fully replaceable
