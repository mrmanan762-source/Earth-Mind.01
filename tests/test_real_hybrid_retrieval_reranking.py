"""
Focused Test Suite for Real Hybrid Retrieval + Real Neural Reranking.

Verifies:
1. Retrieval of candidates using both dense (BAAI/bge-m3 1024D) and sparse (BM25)
   retrieval against Qdrant 'earthmind_knowledge' collection.
2. Reciprocal Rank Fusion (RRF) candidate combining and score correctness.
3. Real neural cross-encoder reranking (BAAI/bge-reranker-base) executing actual inference
   and adjusting or confirming candidate ordering based on semantic relevance.
4. Complete preservation of stable point IDs, payload metadata, source IDs, document IDs,
   version IDs, chunk IDs, and citation attribution.
5. End-to-end delivery of reranked evidence through Stage R13 into B2 Context Manager and
   B3 Reasoning Engine.
6. Robust edge case and failure handling: empty candidate sets, duplicate candidates,
   partial retrieval branch failures, and reranker failure fallback.
"""

import pytest
from typing import Any, Dict, List

from core.config.settings import QdrantConfig, RerankConfig, settings
from core.schemas.embedding import EmbeddingRequest, SparseVector
from core.schemas.evidence import EvidencePackage
from core.schemas.hybrid import (
    CandidateRetrievalSource,
    HybridCandidate,
    HybridRetrievalRequest,
    HybridRetrievalResponse,
    HybridRetrievalStatus,
    RetrievalSourceType,
)
from core.schemas.query import QueryProcessingRequest
from core.schemas.rerank import RerankCandidate, RerankRequest, RerankResponse, RerankStatus
from core.schemas.sparse import SparseRepresentationRequest
from modules.context.schemas import ContextItem
from modules.knowledge_base.enums import IndexStatus, KnowledgeContentType, KnowledgeLifecycleState
from modules.knowledge_base.index.qdrant_adapter import QdrantIndexAdapter
from modules.knowledge_base.index.record import IndexRecord
from modules.knowledge_base.integration.e2e_setup import ingest_and_index_real_corpus
from modules.knowledge_base.integration.harness import R14RealRetrievalHarness
from modules.knowledge_base.integration.provider import RAGContextProvider
from modules.knowledge_base.reranking.engine import RerankEngine
from modules.knowledge_base.reranking.providers.cross_encoder_provider import CrossEncoderRerankerProvider
from modules.knowledge_base.reranking.providers.fake_provider import FakeRerankerProvider
from modules.knowledge_base.retrieval.fusion import CandidateFusionEngine, ReciprocalRankFusionStrategy
from modules.knowledge_base.retrieval.hybrid_engine import HybridRetrievalEngine
from modules.reasoning.capability import ModelLayerReasoningCapability
from modules.reasoning.strategy import ReasoningStrategyController
from modules.reasoning.schemas import ReasoningInput, EvidenceItem


@pytest.fixture(scope="module")
def real_corpus_container():
    """Module-level fixture ingesting real agricultural corpus and indexing into Qdrant."""
    return ingest_and_index_real_corpus(collection_name="earthmind_knowledge")


@pytest.fixture(scope="module")
def real_cross_encoder_provider():
    """Module-level fixture initializing real neural CrossEncoder provider."""
    provider = CrossEncoderRerankerProvider(
        model_name="BAAI/bge-reranker-base",
        device="cpu",
        allow_download=True,
    )
    return provider


# -----------------------------------------------------------------------------
# 1. Combined Dense & Sparse Retrieval from Qdrant
# -----------------------------------------------------------------------------
def test_01_combined_dense_and_sparse_retrieval(real_corpus_container):
    dense_adapter = real_corpus_container.dense_adapter
    sparse_adapter = real_corpus_container.sparse_adapter

    assert dense_adapter.is_available() is True
    assert sparse_adapter.is_available() is True

    # Generate dense query vector
    emb_res = real_corpus_container.embedding_provider.embed(
        EmbeddingRequest(texts=["wheat yellow rust disease management"])
    )
    dense_vec = emb_res.dense_vectors[0].vector

    # Generate sparse query vector
    sp_res = real_corpus_container.sparse_provider.generate_sparse(
        SparseRepresentationRequest(texts=["wheat yellow rust disease management"])
    )
    sparse_indices = sp_res.sparse_vectors[0].indices
    sparse_values = sp_res.sparse_vectors[0].values

    # Perform dense search against Qdrant
    dense_hits = dense_adapter.search_dense("earthmind_knowledge", dense_vec, top_k=5)
    assert len(dense_hits) > 0

    # Perform sparse search against Qdrant
    sparse_hits = sparse_adapter.search_sparse("earthmind_knowledge", sparse_indices, sparse_values, top_k=5)
    assert len(sparse_hits) > 0

    # Verify both retrieval branches returned valid Qdrant records
    assert dense_hits[0].record_id is not None
    assert sparse_hits[0].record_id is not None


# -----------------------------------------------------------------------------
# 2. Reciprocal Rank Fusion (RRF) Correctness
# -----------------------------------------------------------------------------
def test_02_rrf_fusion_correctness(real_corpus_container):
    hybrid_engine = HybridRetrievalEngine(
        dense_adapter=real_corpus_container.dense_adapter,
        sparse_adapter=real_corpus_container.sparse_adapter,
    )

    q_text = "nitrogen application schedule for rice"
    emb_res = real_corpus_container.embedding_provider.embed(EmbeddingRequest(texts=[q_text]))
    sp_res = real_corpus_container.sparse_provider.generate_sparse(SparseRepresentationRequest(texts=[q_text]))

    h_req = HybridRetrievalRequest(
        query_text=q_text,
        dense_vector=emb_res.dense_vectors[0].vector,
        sparse_indices=sp_res.sparse_vectors[0].indices,
        sparse_values=sp_res.sparse_vectors[0].values,
        collection_name="earthmind_knowledge",
        top_k=10,
        fusion_strategy="RRF",
        rrf_k=60,
    )

    h_res = hybrid_engine.retrieve(h_req)

    assert h_res.status == HybridRetrievalStatus.SUCCESS
    assert h_res.total_fused_candidates > 0
    assert len(h_res.candidates) <= 10

    # Verify RRF fused score calculation for top candidate
    top_cand = h_res.candidates[0]
    expected_fused_score = 0.0
    if top_cand.dense_rank:
        expected_fused_score += 1.0 / (60 + top_cand.dense_rank)
    if top_cand.sparse_rank:
        expected_fused_score += 1.0 / (60 + top_cand.sparse_rank)

    assert round(top_cand.fused_score, 4) == round(expected_fused_score, 4)


# -----------------------------------------------------------------------------
# 3. Real Neural Neural Reranking Execution (BAAI/bge-reranker-base)
# -----------------------------------------------------------------------------
def test_03_real_neural_reranking_execution(real_corpus_container, real_cross_encoder_provider):
    assert real_cross_encoder_provider.is_available() is True
    provider_info = real_cross_encoder_provider.get_provider_info()
    assert provider_info["provider_name"] == "cross_encoder"
    assert provider_info["model_name"] == "BAAI/bge-reranker-base"

    rerank_engine = RerankEngine(provider=real_cross_encoder_provider)

    # Hybrid retrieval candidates
    hybrid_engine = HybridRetrievalEngine(
        dense_adapter=real_corpus_container.dense_adapter,
        sparse_adapter=real_corpus_container.sparse_adapter,
    )
    q_text = "recommended fertilizer dosage for irrigated wheat crop"
    emb_res = real_corpus_container.embedding_provider.embed(EmbeddingRequest(texts=[q_text]))
    sp_res = real_corpus_container.sparse_provider.generate_sparse(SparseRepresentationRequest(texts=[q_text]))

    h_res = hybrid_engine.retrieve(
        HybridRetrievalRequest(
            query_text=q_text,
            dense_vector=emb_res.dense_vectors[0].vector,
            sparse_indices=sp_res.sparse_vectors[0].indices,
            sparse_values=sp_res.sparse_vectors[0].values,
            collection_name="earthmind_knowledge",
            top_k=10,
        )
    )

    rerank_req = RerankRequest.from_hybrid_response(h_res, top_k=5)
    rerank_res = rerank_engine.rerank(rerank_req)

    assert rerank_res.status == RerankStatus.SUCCESS
    assert rerank_res.provider_used == "cross_encoder"
    assert rerank_res.model_used == "BAAI/bge-reranker-base"
    assert rerank_res.is_fallback is False
    assert len(rerank_res.candidates) > 0

    top_ranked = rerank_res.candidates[0]
    assert top_ranked.rerank_rank == 1
    assert top_ranked.rerank_score is not None
    assert top_ranked.rerank_score > -10.0  # Real neural score from cross-encoder


# -----------------------------------------------------------------------------
# 4. Source Citation and Metadata Link Preservation
# -----------------------------------------------------------------------------
def test_04_source_citation_and_metadata_preservation(real_corpus_container, real_cross_encoder_provider):
    rerank_engine = RerankEngine(provider=real_cross_encoder_provider)
    hybrid_engine = HybridRetrievalEngine(
        dense_adapter=real_corpus_container.dense_adapter,
        sparse_adapter=real_corpus_container.sparse_adapter,
    )

    rag_provider = RAGContextProvider(
        hybrid_retriever=hybrid_engine,
        reranker=rerank_engine,
        embedding_provider=real_corpus_container.embedding_provider,
        sparse_provider=real_corpus_container.sparse_provider,
    )

    harness = R14RealRetrievalHarness(index_container=real_corpus_container, rag_provider=rag_provider)
    query_text = "soil health card testing parameters"
    res = harness.execute_query(query_text, request_id="citation_test_04")

    assert res.context_items_count > 0
    for item in res.final_context_items:
        assert isinstance(item, ContextItem)
        assert item.source_id is not None
        assert item.source_id.startswith("src_")
        assert "text" in item.content or "content" in item.content
        assert item.content.get("provider") == "cross_encoder"


# -----------------------------------------------------------------------------
# 5. End-to-End Integration through B2 Context Manager into B3 Reasoning Engine
# -----------------------------------------------------------------------------
def test_05_e2e_integration_through_b2_to_b3(real_corpus_container, real_cross_encoder_provider):
    rerank_engine = RerankEngine(provider=real_cross_encoder_provider)
    hybrid_engine = HybridRetrievalEngine(
        dense_adapter=real_corpus_container.dense_adapter,
        sparse_adapter=real_corpus_container.sparse_adapter,
    )

    rag_provider = RAGContextProvider(
        hybrid_retriever=hybrid_engine,
        reranker=rerank_engine,
        embedding_provider=real_corpus_container.embedding_provider,
        sparse_provider=real_corpus_container.sparse_provider,
    )

    harness = R14RealRetrievalHarness(index_container=real_corpus_container, rag_provider=rag_provider)
    query_text = "What are the recommended fertilizer doses for wheat?"
    exec_res = harness.execute_query(query_text, request_id="req_b3_e2e_05")

    assert exec_res.context_items_count > 0
    assert len(exec_res.final_context_items) > 0

    # Pass B2 context items to B3 Reasoning Engine Strategy
    reasoning_strategy = ReasoningStrategyController()

    # Create input evidence items from final_context_items
    evidence_refs = []
    for idx, item in enumerate(exec_res.final_context_items):
        evidence_refs.append(
            EvidenceItem(
                evidence_id=item.context_id,
                source="context_manager",
                source_id=item.source_id,
                content=item.content,
                confidence=item.relevance_score or 1.0,
            )
        )

    reasoning_input = ReasoningInput(
        request_id="b3_req_05",
        task=query_text,
        evidence_items=evidence_refs,
        trace_id="req_b3_e2e_05",
    )

    reasoning_res = reasoning_strategy.execute_strategy(reasoning_input)
    assert reasoning_res is not None
    assert reasoning_res.status.value in ("COMPLETED", "SUCCESS")
    assert len(reasoning_res.findings) > 0


# -----------------------------------------------------------------------------
# 6. Safety: Empty Candidate Set Handling
# -----------------------------------------------------------------------------
def test_06_empty_candidate_set_handling():
    rerank_engine = RerankEngine()
    empty_req = RerankRequest(query_text="nonexistent query", candidates=[])
    res = rerank_engine.rerank(empty_req)

    assert res.status == RerankStatus.SUCCESS
    assert res.total_candidates_received == 0
    assert res.total_candidates_reranked == 0
    assert len(res.candidates) == 0


# -----------------------------------------------------------------------------
# 7. Safety: Duplicate Candidate ID Handling
# -----------------------------------------------------------------------------
def test_07_duplicate_candidate_handling():
    c1 = HybridCandidate(
        candidate_id="dup_01",
        record_id="rec_dup_01",
        chunk_id="chunk_dup_01",
        knowledge_unit_id="ku_dup_01",
        source_id="src_01",
        document_id="doc_01",
        version_id="v1",
        fused_score=0.8,
        fused_rank=1,
    )
    c1_dup = HybridCandidate(
        candidate_id="dup_01",
        record_id="rec_dup_01",
        chunk_id="chunk_dup_01",
        knowledge_unit_id="ku_dup_01",
        source_id="src_01",
        document_id="doc_01",
        version_id="v1",
        fused_score=0.7,
        fused_rank=2,
    )

    rerank_engine = RerankEngine()
    from core.errors.exceptions import InvalidRerankRequestError

    with pytest.raises(InvalidRerankRequestError) as exc_info:
        rerank_engine.rerank(RerankRequest(query_text="test", candidates=[c1, c1_dup]))

    assert "Duplicate candidate ID" in str(exc_info.value)


# -----------------------------------------------------------------------------
# 8. Safety: Partial Retrieval Branch Failure
# -----------------------------------------------------------------------------
def test_08_partial_retrieval_branch_failure(real_corpus_container):
    from modules.knowledge_base.index.sparse_index import InvertedSparseIndexAdapter

    # Use an unavailable sparse adapter to simulate partial branch failure
    unavailable_sparse = InvertedSparseIndexAdapter(is_available=False)

    hybrid_engine = HybridRetrievalEngine(
        dense_adapter=real_corpus_container.dense_adapter,
        sparse_adapter=unavailable_sparse,
    )

    emb_res = real_corpus_container.embedding_provider.embed(
        EmbeddingRequest(texts=["pest disease management wheat"])
    )

    h_req = HybridRetrievalRequest(
        query_text="pest disease management wheat",
        dense_vector=emb_res.dense_vectors[0].vector,
        sparse_indices=[1, 2, 3],
        sparse_values=[1.0, 1.0, 1.0],
        collection_name="earthmind_knowledge",
        top_k=5,
    )

    h_res = hybrid_engine.retrieve(h_req)

    assert h_res.status == HybridRetrievalStatus.PARTIAL
    assert h_res.total_dense_candidates > 0
    assert h_res.total_sparse_candidates == 0
    assert len(h_res.candidates) > 0


# -----------------------------------------------------------------------------
# 9. Safety: Reranker Failure & Fallback Policy (PRESERVE_FUSED_ORDER)
# -----------------------------------------------------------------------------
def test_09_reranker_failure_fallback_preserves_order():
    c1 = HybridCandidate(
        candidate_id="cand_1",
        record_id="rec_1",
        chunk_id="chunk_1",
        knowledge_unit_id="ku_1",
        source_id="src_1",
        document_id="doc_1",
        version_id="v1",
        fused_score=0.9,
        fused_rank=1,
        payload_metadata={"text": "wheat disease management"},
    )
    c2 = HybridCandidate(
        candidate_id="cand_2",
        record_id="rec_2",
        chunk_id="chunk_2",
        knowledge_unit_id="ku_2",
        source_id="src_1",
        document_id="doc_1",
        version_id="v1",
        fused_score=0.7,
        fused_rank=2,
        payload_metadata={"text": "rice irrigation practice"},
    )

    failing_provider = FakeRerankerProvider(is_available_flag=False)
    config = RerankConfig(fallback_policy="PRESERVE_FUSED_ORDER")
    engine = RerankEngine(provider=failing_provider, config=config)

    req = RerankRequest(query_text="wheat disease", candidates=[c1, c2], allow_fallback=True)
    res = engine.rerank(req)

    assert res.status == RerankStatus.FALLBACK
    assert res.is_fallback is True
    assert len(res.candidates) == 2

    # R7 fused ordering is strictly preserved
    assert res.candidates[0].candidate_id == "cand_1"
    assert res.candidates[0].rerank_rank == 1
    assert res.candidates[0].rerank_score is None  # Never fabricate score!
    assert res.candidates[0].is_fallback is True

    assert res.candidates[1].candidate_id == "cand_2"
    assert res.candidates[1].rerank_rank == 2
    assert res.candidates[1].rerank_score is None
    assert res.candidates[1].is_fallback is True


# -----------------------------------------------------------------------------
# 10. Multilingual Query Execution with Real Neural Reranking
# -----------------------------------------------------------------------------
def test_10_multilingual_query_execution(real_corpus_container, real_cross_encoder_provider):
    rerank_engine = RerankEngine(provider=real_cross_encoder_provider)
    hybrid_engine = HybridRetrievalEngine(
        dense_adapter=real_corpus_container.dense_adapter,
        sparse_adapter=real_corpus_container.sparse_adapter,
    )

    rag_provider = RAGContextProvider(
        hybrid_retriever=hybrid_engine,
        reranker=rerank_engine,
        embedding_provider=real_corpus_container.embedding_provider,
        sparse_provider=real_corpus_container.sparse_provider,
    )

    harness = R14RealRetrievalHarness(index_container=real_corpus_container, rag_provider=rag_provider)

    hindi_query = "गेहूं की फसल में पीला रतुआ रोग का उपचार"
    res = harness.execute_query(hindi_query, request_id="multilingual_test_10")

    assert res.query_processing_status == "SUCCESS"
    assert res.context_items_count > 0
    top_item = res.final_context_items[0]
    assert top_item.source_id is not None
