"""
Stage R14 End-to-End Real Retrieval Integration Test Suite.

Verifies that the COMPLETE EarthMind RAG pipeline executes end-to-end using REAL
retrieval components and REAL knowledge data from the R3 agricultural corpus.
Tests all 22 required operational, functional, and safety dimensions defined by Stage R14.
"""

import pytest
from typing import Any, Dict, List

from core.errors.exceptions import RAGPipelineExecutionError
from core.schemas.embedding import EmbeddingRequest
from core.schemas.evidence import EvidencePackage, EvidenceItem
from core.schemas.hybrid import HybridRetrievalRequest
from core.schemas.query import QueryProcessingRequest, QueryProcessingStatus
from core.schemas.sparse import SparseRepresentationRequest
from modules.context.boundary.models import RAGContextContract
from modules.context.schemas import ContextItem
from modules.knowledge_base.integration.e2e_setup import ingest_and_index_real_corpus
from modules.knowledge_base.integration.harness import R14RealRetrievalHarness
from modules.knowledge_base.integration.provider import RAGContextProvider
from modules.knowledge_base.retrieval.hybrid_engine import HybridRetrievalEngine


@pytest.fixture(scope="module")
def real_container():
    """Module-level fixture initializing real ingestion and real vector indices once."""
    return ingest_and_index_real_corpus(collection_name="earthmind_knowledge")


@pytest.fixture
def real_harness(real_container):
    """Fixture providing R14RealRetrievalHarness wired to real container."""
    return R14RealRetrievalHarness(index_container=real_container, enable_web_search=False)


# -----------------------------------------------------------------------------
# 1. Real End-to-End Retrieval
# -----------------------------------------------------------------------------
def test_01_real_end_to_end_retrieval(real_harness):
    result = real_harness.execute_query(
        query_text="What are the recommended fertilizer doses for rice cultivation?",
        request_id="req_e2e_01",
    )
    assert result.request_id == "req_e2e_01"
    assert result.query_processing_status == "SUCCESS"
    assert result.validation_status == "VALID"
    assert result.context_items_count > 0
    assert len(result.final_context_items) == result.context_items_count


# -----------------------------------------------------------------------------
# 2. Real R9 Query Processing
# -----------------------------------------------------------------------------
def test_02_real_r9_query_processing(real_harness):
    qp = real_harness.rag_provider.query_processor
    qp_req = QueryProcessingRequest(query_text="rice cultivation fertilizer dosages")
    qp_res = qp.process_query(qp_req)

    assert qp_res.status == QueryProcessingStatus.SUCCESS
    assert qp_res.retrieval_query is not None
    assert qp_res.retrieval_query.normalized_query == "rice cultivation fertilizer dosages"
    assert qp_res.retrieval_query.metadata.agricultural_metadata.crop == "rice"


# -----------------------------------------------------------------------------
# 3. Real Dense Retrieval
# -----------------------------------------------------------------------------
def test_03_real_dense_retrieval(real_container):
    provider = real_container.embedding_provider
    emb_res = provider.embed(EmbeddingRequest(texts=["balanced fertilizer management"]))
    query_vec = emb_res.dense_vectors[0].vector

    dense_adapter = real_container.dense_adapter
    results = dense_adapter.search_dense("earthmind_knowledge", query_vec, top_k=5)

    assert len(results) > 0
    assert results[0].record_id.startswith("rec_chk_")
    assert results[0].score > 0.0


# -----------------------------------------------------------------------------
# 4. Real Sparse Retrieval
# -----------------------------------------------------------------------------
def test_04_real_sparse_retrieval(real_container):
    provider = real_container.sparse_provider
    sp_res = provider.generate_sparse(SparseRepresentationRequest(texts=["pest disease management wheat"]))
    indices = sp_res.sparse_vectors[0].indices
    values = sp_res.sparse_vectors[0].values

    sparse_adapter = real_container.sparse_adapter
    results = sparse_adapter.search_sparse("earthmind_knowledge", indices, values, top_k=5)

    assert len(results) > 0
    assert results[0].record_id.startswith("rec_chk_")


# -----------------------------------------------------------------------------
# 5. Real Hybrid Retrieval
# -----------------------------------------------------------------------------
def test_05_real_hybrid_retrieval(real_container):
    hybrid_engine = HybridRetrievalEngine(
        dense_adapter=real_container.dense_adapter,
        sparse_adapter=real_container.sparse_adapter,
    )
    emb_res = real_container.embedding_provider.embed(EmbeddingRequest(texts=["micro irrigation drip manual"]))
    dense_vec = emb_res.dense_vectors[0].vector
    sp_res = real_container.sparse_provider.generate_sparse(SparseRepresentationRequest(texts=["micro irrigation drip manual"]))

    h_req = HybridRetrievalRequest(
        query_text="micro irrigation drip manual",
        dense_vector=dense_vec,
        sparse_indices=sp_res.sparse_vectors[0].indices,
        sparse_values=sp_res.sparse_vectors[0].values,
        collection_name="earthmind_knowledge",
        top_k=5,
    )

    h_res = hybrid_engine.retrieve(h_req)
    assert h_res.status.value == "SUCCESS"
    assert len(h_res.candidates) > 0


# -----------------------------------------------------------------------------
# 6. Real Reranking
# -----------------------------------------------------------------------------
def test_06_real_reranking(real_harness):
    res = real_harness.execute_query(
        query_text="recommended fertilizer doses for rice",
        request_id="req_rerank_06",
    )
    assert res.context_items_count > 0
    item = res.final_context_items[0]
    assert item.relevance_score is not None


# -----------------------------------------------------------------------------
# 7. Real Evidence Building
# -----------------------------------------------------------------------------
def test_07_real_evidence_building(real_harness):
    res = real_harness.execute_query(
        query_text="soil health card sampling guidelines",
        request_id="req_eb_07",
    )
    assert res.evidence_items_count > 0
    contract = res.final_context_items[0]
    assert contract.source_id is not None


# -----------------------------------------------------------------------------
# 8. Real Evidence Validation
# -----------------------------------------------------------------------------
def test_08_real_evidence_validation(real_harness):
    res = real_harness.execute_query(
        query_text="yellow rust disease management in wheat",
        request_id="req_val_08",
    )
    assert res.validation_status == "VALID"
    assert res.errors == []


# -----------------------------------------------------------------------------
# 9. Real R13 → B2 Integration
# -----------------------------------------------------------------------------
def test_09_real_r13_to_b2_integration(real_harness):
    res = real_harness.execute_query(
        query_text="balanced fertilizer application guidelines",
        request_id="req_r13_b2_09",
    )
    assert res.rag_contracts_count > 0
    assert res.context_items_count == res.rag_contracts_count
    for item in res.final_context_items:
        assert isinstance(item, ContextItem)
        assert item.classification.value in ("GENERAL_KNOWLEDGE", "GENERAL_AGRICULTURE_KNOWLEDGE")


# -----------------------------------------------------------------------------
# 10. Real Agricultural Query Categories
# -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query, expected_category",
    [
        ("rice crop nitrogen fertilizer dosage", "crop"),
        ("wheat yellow rust disease control", "disease"),
        ("black soil organic carbon testing", "soil"),
        ("punjab kharif season irrigation schedule", "region_season"),
        ("drip irrigation lateral flushing practice", "practice"),
    ],
)
def test_10_real_agricultural_query_categories(real_harness, query, expected_category):
    res = real_harness.execute_query(query_text=query, request_id=f"req_agri_{expected_category}")
    assert res.query_processing_status == "SUCCESS"
    assert res.context_items_count > 0


# -----------------------------------------------------------------------------
# 11. Multilingual Query Execution
# -----------------------------------------------------------------------------
def test_11_multilingual_query_execution(real_harness):
    # Test Devanagari Hindi agricultural query
    hindi_query = "धान की फसल में खाद प्रबंधन"
    res = real_harness.execute_query(query_text=hindi_query, request_id="req_hi_11")

    assert res.query_processing_status == "SUCCESS"
    assert res.context_items_count > 0


# -----------------------------------------------------------------------------
# 12. Provenance Preservation
# -----------------------------------------------------------------------------
def test_12_provenance_preservation(real_harness):
    res = real_harness.execute_query("soil health card guidelines", request_id="req_prov_12")

    assert res.context_items_count > 0
    item = res.final_context_items[0]
    assert item.source_id.startswith("src_")
    assert item.trace_id == "req_prov_12"


# -----------------------------------------------------------------------------
# 13. Source-Type Preservation
# -----------------------------------------------------------------------------
def test_13_source_type_preservation(real_harness):
    res = real_harness.execute_query("micro irrigation drip manual", request_id="req_st_13")

    assert res.context_items_count > 0
    item = res.final_context_items[0]
    assert item.source_type.value in ("RAG", "KNOWLEDGE_BASE", "OFFICIAL_ADVISORY", "RESEARCH_DOCUMENT")


# -----------------------------------------------------------------------------
# 14. Traceability
# -----------------------------------------------------------------------------
def test_14_traceability(real_harness):
    trc = "trace_uuid_9999"
    res = real_harness.execute_query(
        query_text="good agricultural practices icar guidelines",
        request_id="req_trc_14",
        trace_id=trc,
    )
    assert res.request_id == "req_trc_14"
    assert res.trace_id == trc
    for item in res.final_context_items:
        assert item.trace_id == trc


# -----------------------------------------------------------------------------
# 15. Empty Retrieval Handling
# -----------------------------------------------------------------------------
def test_15_empty_retrieval_handling(real_harness):
    res = real_harness.execute_query(
        query_text="",
        request_id="req_empty_15",
    )
    assert res.context_items_count == 0
    assert res.errors == []


# -----------------------------------------------------------------------------
# 16. Backend Failure Handling
# -----------------------------------------------------------------------------
def test_16_backend_failure_handling(real_container):
    from modules.knowledge_base.index.qdrant_adapter import QdrantIndexAdapter
    from core.config.settings import QdrantConfig

    class FailingDenseAdapter(QdrantIndexAdapter):
        def is_available(self):
            return False

        def search_dense(self, *args, **kwargs):
            raise RuntimeError("Backend Qdrant connection lost.")

    failing_hybrid = HybridRetrievalEngine(
        dense_adapter=FailingDenseAdapter(config=QdrantConfig(location=":memory:")),
        sparse_adapter=real_container.sparse_adapter,
    )
    provider = RAGContextProvider(
        hybrid_retriever=failing_hybrid,
        embedding_provider=real_container.embedding_provider,
        sparse_provider=real_container.sparse_provider,
    )

    harness = R14RealRetrievalHarness(index_container=real_container, rag_provider=provider)
    res = harness.execute_query("wheat rust management", request_id="req_fail_16")

    assert res.query_processing_status == "SUCCESS"


# -----------------------------------------------------------------------------
# 17. Partial Retrieval Branch Failure
# -----------------------------------------------------------------------------
def test_17_partial_retrieval_branch_failure(real_container):
    real_container.sparse_adapter.set_availability(False)

    hybrid_engine = HybridRetrievalEngine(
        dense_adapter=real_container.dense_adapter,
        sparse_adapter=real_container.sparse_adapter,
    )
    provider = RAGContextProvider(
        hybrid_retriever=hybrid_engine,
        embedding_provider=real_container.embedding_provider,
        sparse_provider=real_container.sparse_provider,
    )

    harness = R14RealRetrievalHarness(index_container=real_container, rag_provider=provider)
    res = harness.execute_query("fertilizer application guidelines", request_id="req_partial_17")

    real_container.sparse_adapter.set_availability(True)

    assert res.query_processing_status == "SUCCESS"
    assert res.context_items_count > 0


# -----------------------------------------------------------------------------
# 18. Reranker Failure & Fallback Handling
# -----------------------------------------------------------------------------
def test_18_reranker_failure_and_fallback(real_container):
    from modules.knowledge_base.reranking.engine import RerankEngine

    class FailingRerankerProvider:
        def is_available(self):
            return False

        def get_provider_info(self):
            return {"provider_name": "failing_reranker", "model_name": "none"}

        def rerank(self, *args, **kwargs):
            raise RuntimeError("Reranker execution timeout.")

    failing_rerank_engine = RerankEngine(provider=FailingRerankerProvider())
    hybrid_retriever = HybridRetrievalEngine(
        dense_adapter=real_container.dense_adapter,
        sparse_adapter=real_container.sparse_adapter,
    )
    provider = RAGContextProvider(
        hybrid_retriever=hybrid_retriever,
        reranker=failing_rerank_engine,
        embedding_provider=real_container.embedding_provider,
        sparse_provider=real_container.sparse_provider,
    )

    harness = R14RealRetrievalHarness(index_container=real_container, rag_provider=provider)
    res = harness.execute_query("fertilizer guidelines for crops", request_id="req_rf_18")

    assert res.query_processing_status == "SUCCESS"
    assert res.context_items_count > 0


# -----------------------------------------------------------------------------
# 19. Web Search Optional Execution Path
# -----------------------------------------------------------------------------
def test_19_web_search_optional_execution_path(real_container):
    harness_disabled = R14RealRetrievalHarness(index_container=real_container, enable_web_search=False)
    res_disabled = harness_disabled.execute_query("rice cultivation", request_id="req_ws_off_19")
    assert res_disabled.web_search_count == 0

    harness_enabled = R14RealRetrievalHarness(index_container=real_container, enable_web_search=True)
    res_enabled = harness_enabled.execute_query("rice cultivation", request_id="req_ws_on_19")
    assert res_enabled.query_processing_status == "SUCCESS"


# -----------------------------------------------------------------------------
# 20. Pure Real Path Execution (No Mock Leakage in Primary Path)
# -----------------------------------------------------------------------------
def test_20_pure_real_path_execution(real_harness):
    emb_prov = real_harness.index_container.embedding_provider
    sp_prov = real_harness.index_container.sparse_provider

    emb_meta = emb_prov.get_provider_metadata()
    sp_meta = sp_prov.get_provider_metadata()

    assert emb_meta.is_mock is False
    assert sp_meta.is_mock is False
    assert emb_prov.provider_name == "self_hosted"
    assert sp_prov.provider_name == "bm25_sparse"


# -----------------------------------------------------------------------------
# 21. Deterministic Result Contract
# -----------------------------------------------------------------------------
def test_21_deterministic_result_contract(real_harness):
    q = "nitrogen fertilizer dosage for rice"
    res1 = real_harness.execute_query(query_text=q, request_id="req_det_21_a")
    res2 = real_harness.execute_query(query_text=q, request_id="req_det_21_b")

    assert res1.context_items_count == res2.context_items_count
    assert res1.final_context_items[0].entity_id == res2.final_context_items[0].entity_id


# -----------------------------------------------------------------------------
# 22. Downstream B2 Context Manager Contract Compatibility
# -----------------------------------------------------------------------------
def test_22_b2_compatibility(real_harness):
    res = real_harness.execute_query("soil health card parameters", request_id="req_b2_22")

    assert res.context_items_count > 0
    for item in res.final_context_items:
        assert hasattr(item, "context_id")
        assert hasattr(item, "classification")
        assert hasattr(item, "ownership")
        assert hasattr(item, "scope")
        assert hasattr(item, "persistence_intent")
        assert item.ownership.value == "RAG_OWNED"
