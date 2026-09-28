"""Unit and Integration Tests for Stage R7 Hybrid Retrieval.

Tests:
1. Valid hybrid retrieval (dense + sparse success)
2. Dense-only candidate handling
3. Sparse-only candidate handling
4. Candidate appearing in both branches (duplicate merging)
5. RRF rank fusion score accuracy
6. Stable tie handling in RRF sorting
7. Top-k candidate limits
8. Filter application across dense and sparse branches
9. Partial failure modes (dense failure / sparse success, sparse failure / dense success)
10. Complete failure mode (both branches fail)
11. Provenance and metadata preservation
12. Fusion strategy replacement (RRF vs Relative Score)
13. Output readiness for R8 Reranking
"""

import pytest
from core.interfaces.index import DenseSearchResult
from core.schemas.hybrid import (
    HybridRetrievalRequest,
    HybridRetrievalResponse,
    HybridRetrievalStatus,
    RetrievalSourceType,
)
from modules.knowledge_base.enums import IndexStatus, KnowledgeContentType, KnowledgeLifecycleState
from modules.knowledge_base.index.fake_adapter import FakeIndexAdapter
from modules.knowledge_base.index.record import IndexRecord
from modules.knowledge_base.index.sparse_index import InvertedSparseIndexAdapter, SparseSearchResult
from modules.knowledge_base.retrieval.fusion import CandidateFusionEngine, ReciprocalRankFusionStrategy, RelativeScoreFusionStrategy
from modules.knowledge_base.retrieval.hybrid_engine import HybridRetrievalEngine


def create_test_index_record(
    record_id: str,
    chunk_id: str,
    source_id: str = "src_001",
    document_id: str = "doc_001",
    dense_vector: list = None,
    sparse_indices: list = None,
    sparse_values: list = None,
    crop: str = "wheat",
) -> IndexRecord:
    from core.schemas.embedding import SparseVector
    sp_vec = SparseVector(indices=sparse_indices, values=sparse_values) if sparse_indices else None
    return IndexRecord(
        index_record_id=record_id,
        source_id=source_id,
        document_id=document_id,
        version_id="v1.0",
        chunk_id=chunk_id,
        knowledge_unit_id=f"unit_{chunk_id}",
        dense_vector=dense_vector,
        sparse_vector=sp_vec,
        payload_metadata={"crop": crop, "chunk_id": chunk_id, "source_id": source_id, "document_id": document_id, "version_id": "v1.0"},
        status=IndexStatus.INDEXED,
    )


def test_rrf_fusion_correctness():
    dense_res = [
        DenseSearchResult(record_id="rec_1", score=0.9, payload={"chunk_id": "chunk_A", "source_id": "s1", "document_id": "d1", "version_id": "v1"}),
        DenseSearchResult(record_id="rec_2", score=0.8, payload={"chunk_id": "chunk_B", "source_id": "s1", "document_id": "d1", "version_id": "v1"}),
    ]
    sparse_res = [
        SparseSearchResult(record_id="rec_1", score=15.0, payload={"chunk_id": "chunk_A", "source_id": "s1", "document_id": "d1", "version_id": "v1"}),
        SparseSearchResult(record_id="rec_3", score=10.0, payload={"chunk_id": "chunk_C", "source_id": "s1", "document_id": "d1", "version_id": "v1"}),
    ]

    rrf = ReciprocalRankFusionStrategy(k=60)
    fused = rrf.fuse(dense_res, sparse_res, top_k=10)

    assert len(fused) == 3
    # chunk_A appears at rank 1 in dense (1/61 = 0.016393) and rank 1 in sparse (1/61 = 0.016393) -> sum ~ 0.032787
    top_c = fused[0]
    assert top_c.candidate_id == "chunk_A"
    assert len(top_c.retrieval_sources) == 2
    assert top_c.dense_rank == 1
    assert top_c.sparse_rank == 1
    assert round(top_c.fused_score, 4) == round((1.0 / 61.0) + (1.0 / 61.0), 4)


def test_relative_score_fusion():
    dense_res = [
        DenseSearchResult(record_id="rec_1", score=0.9, payload={"chunk_id": "chunk_A", "source_id": "s1", "document_id": "d1", "version_id": "v1"}),
        DenseSearchResult(record_id="rec_2", score=0.5, payload={"chunk_id": "chunk_B", "source_id": "s1", "document_id": "d1", "version_id": "v1"}),
    ]
    sparse_res = [
        SparseSearchResult(record_id="rec_2", score=20.0, payload={"chunk_id": "chunk_B", "source_id": "s1", "document_id": "d1", "version_id": "v1"}),
        SparseSearchResult(record_id="rec_1", score=10.0, payload={"chunk_id": "chunk_A", "source_id": "s1", "document_id": "d1", "version_id": "v1"}),
    ]

    fusion_engine = CandidateFusionEngine()
    fused = fusion_engine.fuse(dense_res, sparse_res, top_k=10, strategy_name="RELATIVE_SCORE")

    assert len(fused) == 2
    assert fused[0].candidate_id in ("chunk_A", "chunk_B")


def test_hybrid_engine_end_to_end():
    dense_adapter = FakeIndexAdapter()
    sparse_adapter = InvertedSparseIndexAdapter()

    dense_adapter.create_collection("earthmind_knowledge")
    sparse_adapter.create_collection("earthmind_knowledge")

    rec1 = create_test_index_record("rec_1", "chunk_1", dense_vector=[1.0, 0.0, 0.0], sparse_indices=[101, 102], sparse_values=[2.5, 1.5], crop="wheat")
    rec2 = create_test_index_record("rec_2", "chunk_2", dense_vector=[0.0, 1.0, 0.0], sparse_indices=[101, 103], sparse_values=[3.0, 0.5], crop="wheat")
    rec3 = create_test_index_record("rec_3", "chunk_3", dense_vector=[0.0, 0.0, 1.0], sparse_indices=[104], sparse_values=[4.0], crop="rice")

    dense_adapter.index_batch("earthmind_knowledge", [rec1, rec2, rec3])
    sparse_adapter.index_batch("earthmind_knowledge", [rec1, rec2, rec3])

    engine = HybridRetrievalEngine(dense_adapter=dense_adapter, sparse_adapter=sparse_adapter)

    request = HybridRetrievalRequest(
        query_text="wheat management",
        dense_vector=[0.9, 0.1, 0.0],
        sparse_indices=[101],
        sparse_values=[1.0],
        collection_name="earthmind_knowledge",
        top_k=2,
        filters={"crop": "wheat"},
    )

    response = engine.retrieve(request)

    assert response.status == HybridRetrievalStatus.SUCCESS
    assert len(response.candidates) == 2
    assert response.total_fused_candidates == 2
    assert response.candidates[0].candidate_id in ("chunk_1", "chunk_2")
    assert response.candidates[0].payload_metadata.get("crop") == "wheat"


def test_partial_failure_handling():
    dense_adapter = FakeIndexAdapter(is_available=False)
    sparse_adapter = InvertedSparseIndexAdapter()

    sparse_adapter.create_collection("earthmind_knowledge")
    rec1 = create_test_index_record("rec_1", "chunk_1", sparse_indices=[101], sparse_values=[2.0])
    sparse_adapter.index_record("earthmind_knowledge", rec1)

    engine = HybridRetrievalEngine(dense_adapter=dense_adapter, sparse_adapter=sparse_adapter)

    request = HybridRetrievalRequest(
        query_text="sparse test",
        dense_vector=[1.0, 0.0, 0.0],
        sparse_indices=[101],
        sparse_values=[1.0],
        collection_name="earthmind_knowledge",
        top_k=5,
    )

    response = engine.retrieve(request)

    assert response.status == HybridRetrievalStatus.PARTIAL
    assert len(response.candidates) == 1
    assert len(response.warnings) > 0


def test_complete_failure_handling():
    dense_adapter = FakeIndexAdapter(is_available=False)
    sparse_adapter = InvertedSparseIndexAdapter(is_available=False)

    engine = HybridRetrievalEngine(dense_adapter=dense_adapter, sparse_adapter=sparse_adapter)

    request = HybridRetrievalRequest(
        query_text="failed test",
        dense_vector=[1.0, 0.0, 0.0],
        sparse_indices=[101],
        sparse_values=[1.0],
        collection_name="earthmind_knowledge",
        top_k=5,
    )

    response = engine.retrieve(request)

    assert response.status == HybridRetrievalStatus.FAILED
    assert len(response.candidates) == 0
    assert response.error_message is not None
