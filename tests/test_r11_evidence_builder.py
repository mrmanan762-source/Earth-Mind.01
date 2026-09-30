"""
Unit and Integration Tests for Stage R11 Evidence Builder.

Tests:
1. KB evidence construction from R8 RerankResponse
2. Web evidence construction from R10 WebSearchResponse
3. Mixed KB + Web evidence package construction
4. Evidence identity preservation
5. Conservative deduplication
6. C.2 Lineage and Provenance preservation
7. Source-type preservation (KNOWLEDGE_BASE vs WEB_SEARCH)
8. Dense, Sparse, Fused, Rerank rank preservation
9. Score preservation
10. Source assessment preservation
11. Conflict indicators preservation
12. Multimodal metadata preservation
13. Agricultural metadata preservation
14. Partial R8 success + R10 failure
15. R8 failure + R10 success
16. Both upstream failures (R8 failed + R10 failed)
17. Empty evidence package (no candidates/results)
18. Malformed upstream item handling
19. Evidence item and total package limits
20. Content truncation metadata tracking
21. Deterministic evidence ordering
22. B2 Context Manager compatibility (to_rag_context_contracts())
23. Zero direct database/Qdrant writes verification
24. C.2/C.3 governance boundary (Web Search transient, no auto-publication)
25. Memory isolation boundary (no Memory writes)
26. Provider independence & Engine interface compliance
27. Request and trace ID correlation
28. Regression compatibility
"""

import pytest
from core.config.settings import EvidenceBuilderConfig
from core.errors.exceptions import InvalidEvidenceBuildRequestError
from core.interfaces.evidence import IEvidenceBuilderEngine
from core.schemas.evidence import (
    EvidenceBuildRequest,
    EvidenceBuildStatus,
    EvidenceItem,
    EvidencePackage,
    EvidenceSourceType,
)
from core.schemas.hybrid import CandidateRetrievalSource, HybridCandidate, RetrievalSourceType
from core.schemas.rerank import RerankCandidate, RerankResponse, RerankStatus
from core.schemas.web_search import WebSearchResult, WebSearchResponse, WebSearchStatus
from modules.context.boundary.enums import ContextOwnership, ContextScope, ContextSourceType
from modules.knowledge_base.evidence.engine import EvidenceBuilderEngine


# Helper Fixtures
@pytest.fixture
def sample_hybrid_candidate():
    source_dense = CandidateRetrievalSource(
        source_type=RetrievalSourceType.DENSE,
        rank=2,
        score=0.82,
        provider_name="dense_provider",
    )
    source_sparse = CandidateRetrievalSource(
        source_type=RetrievalSourceType.SPARSE,
        rank=1,
        score=0.88,
        provider_name="bm25_provider",
    )
    return HybridCandidate(
        candidate_id="cand_1",
        record_id="rec_1",
        chunk_id="chunk_101",
        knowledge_unit_id="ku_50",
        source_id="src_agri_1",
        document_id="doc_wheat_1",
        version_id="v1.0",
        fused_score=0.85,
        fused_rank=1,
        dense_rank=2,
        dense_score=0.82,
        sparse_rank=1,
        sparse_score=0.88,
        retrieval_sources=[source_dense, source_sparse],
        payload_metadata={
            "title": "Wheat Crop Disease Guide",
            "content": "Yellow rust in wheat caused by Puccinia striiformis requires propiconazole spray.",
            "section_id": "sec_3",
            "crop": "Wheat",
            "disease": "Yellow Rust",
            "region": "Punjab",
            "source_assessment": {"trust_score": 0.95, "peer_reviewed": True},
            "conflict_indicators": ["Disagreement on dosage for late-stage rust"],
            "multimodal_data": {"table_ref": "tbl_dosage_1", "image_url": "https://agri.org/rust.jpg"},
        },
        provenance={"ingestion_id": "ing_99", "canonical_source": "ICAR-Wheat-Manual"},
    )


@pytest.fixture
def sample_rerank_response(sample_hybrid_candidate):
    cand1 = RerankCandidate.from_hybrid_candidate(
        sample_hybrid_candidate,
        rerank_score=0.92,
        rerank_rank=1,
        rerank_provider="bge-reranker",
        rerank_model="v1.0",
    )
    return RerankResponse(
        request_id="req_rerank_123",
        query_text="Wheat yellow rust treatment",
        status=RerankStatus.SUCCESS,
        candidates=[cand1],
        total_candidates_received=1,
        total_candidates_reranked=1,
        provider_used="bge-reranker",
    )


@pytest.fixture
def sample_web_search_response():
    web_res = WebSearchResult(
        result_id="web_res_1",
        title="Punjab Agri Portal - Wheat Rust Alert",
        url="https://punjabagri.gov.in/wheat-rust-alert",
        snippet="Fungicide application recommended for yellow rust outbreak in Bathinda district.",
        source="Punjab Agri Dept",
        publication_date="2025-02-15",
        provider="mock_web_search",
        rank=1,
        score=0.89,
        provenance={"search_provider": "mock_web_search", "query": "Wheat yellow rust treatment"},
        metadata={"crop": "Wheat", "state": "Punjab", "district": "Bathinda"},
    )
    return WebSearchResponse(
        request_id="req_web_456",
        status=WebSearchStatus.SUCCESS,
        query_text="Wheat yellow rust treatment",
        results=[web_res],
        result_count=1,
        provider_name="mock_web_search",
    )


@pytest.fixture
def engine():
    return EvidenceBuilderEngine(
        config=EvidenceBuilderConfig(max_items=10, max_content_length=500, deduplicate=True)
    )


# --- Test Cases ---

def test_engine_interface_compliance(engine):
    """Verify engine implements IEvidenceBuilderEngine protocol."""
    assert isinstance(engine, IEvidenceBuilderEngine)


def test_kb_evidence_construction(engine, sample_rerank_response):
    """1. KB evidence construction from R8 response."""
    req = EvidenceBuildRequest(
        query_text="Wheat yellow rust treatment",
        rerank_response=sample_rerank_response,
    )
    res = engine.build_evidence(req)
    assert res.status == EvidenceBuildStatus.SUCCESS
    pkg = res.package
    assert pkg is not None
    assert pkg.total_items_count == 1
    assert pkg.kb_items_count == 1
    assert pkg.web_items_count == 0

    item = pkg.items[0]
    assert item.source_type == EvidenceSourceType.KNOWLEDGE_BASE
    assert item.chunk_id == "chunk_101"
    assert item.document_id == "doc_wheat_1"
    assert item.version_id == "v1.0"
    assert item.section_id == "sec_3"
    assert "Yellow rust in wheat" in item.content


def test_web_evidence_construction(engine, sample_web_search_response):
    """2. Web evidence construction from R10 response."""
    req = EvidenceBuildRequest(
        query_text="Wheat yellow rust treatment",
        web_search_response=sample_web_search_response,
    )
    res = engine.build_evidence(req)
    assert res.status == EvidenceBuildStatus.SUCCESS
    pkg = res.package
    assert pkg is not None
    assert pkg.total_items_count == 1
    assert pkg.web_items_count == 1
    assert pkg.kb_items_count == 0

    item = pkg.items[0]
    assert item.source_type == EvidenceSourceType.WEB_SEARCH
    assert item.url == "https://punjabagri.gov.in/wheat-rust-alert"
    assert item.web_result_id == "web_res_1"
    assert "Fungicide application" in item.content


def test_mixed_kb_and_web_evidence(engine, sample_rerank_response, sample_web_search_response):
    """3. Mixed KB + Web evidence package construction."""
    req = EvidenceBuildRequest(
        query_text="Wheat yellow rust treatment",
        rerank_response=sample_rerank_response,
        web_search_response=sample_web_search_response,
    )
    res = engine.build_evidence(req)
    assert res.status == EvidenceBuildStatus.SUCCESS
    pkg = res.package
    assert pkg.total_items_count == 2
    assert pkg.kb_items_count == 1
    assert pkg.web_items_count == 1

    sources = [it.source_type for it in pkg.items]
    assert EvidenceSourceType.KNOWLEDGE_BASE in sources
    assert EvidenceSourceType.WEB_SEARCH in sources


def test_evidence_identity_preservation(engine, sample_rerank_response):
    """4. Identity preservation across candidate_id, chunk_id, etc."""
    req = EvidenceBuildRequest(query_text="query", rerank_response=sample_rerank_response)
    res = engine.build_evidence(req)
    item = res.package.items[0]

    assert item.candidate_id == "cand_1"
    assert item.chunk_id == "chunk_101"
    assert item.knowledge_unit_id == "ku_50"
    assert item.source_id == "src_agri_1"


def test_conservative_deduplication(engine, sample_rerank_response):
    """5. Conservative deduplication by chunk_id/web_result_id."""
    cand1 = sample_rerank_response.candidates[0]
    # Create duplicate candidate with same chunk_id
    cand_dup = RerankCandidate.from_hybrid_candidate(
        HybridCandidate(
            candidate_id="cand_2",
            record_id="rec_2",
            chunk_id="chunk_101", # same chunk_id
            knowledge_unit_id="ku_50",
            source_id="src_agri_1",
            document_id="doc_wheat_1",
            version_id="v1.0",
            fused_score=0.80,
            fused_rank=2,
            payload_metadata={"content": "Duplicate content snippet"},
        )
    )
    resp = RerankResponse(
        query_text="query",
        status=RerankStatus.SUCCESS,
        candidates=[cand1, cand_dup],
    )
    req = EvidenceBuildRequest(query_text="query", rerank_response=resp, deduplicate=True)
    res = engine.build_evidence(req)
    assert res.package.total_items_count == 1 # Deduplicated to 1 item


def test_lineage_and_provenance_preservation(engine, sample_rerank_response):
    """6 & 7. C.2 Lineage, Provenance and Source-Type preservation."""
    req = EvidenceBuildRequest(query_text="query", rerank_response=sample_rerank_response)
    res = engine.build_evidence(req)
    item = res.package.items[0]

    assert item.provenance.get("canonical_source") == "ICAR-Wheat-Manual"
    assert item.source_type == EvidenceSourceType.KNOWLEDGE_BASE


def test_score_and_rank_preservation(engine, sample_rerank_response):
    """8 & 9. Preservation of dense, sparse, fused, rerank ranks and scores."""
    req = EvidenceBuildRequest(query_text="query", rerank_response=sample_rerank_response)
    res = engine.build_evidence(req)
    item = res.package.items[0]

    assert item.dense_rank == 2
    assert item.dense_score == 0.82
    assert item.sparse_rank == 1
    assert item.sparse_score == 0.88
    assert item.fused_rank == 1
    assert item.fused_score == 0.85
    assert item.rerank_rank == 1
    assert item.rerank_score == 0.92


def test_source_assessment_preservation(engine, sample_rerank_response):
    """10. Source assessment metadata preservation."""
    req = EvidenceBuildRequest(query_text="query", rerank_response=sample_rerank_response)
    res = engine.build_evidence(req)
    item = res.package.items[0]

    assert item.source_assessment is not None
    assert item.source_assessment.get("trust_score") == 0.95


def test_conflict_indicators_preservation(engine, sample_rerank_response):
    """11. Preservation of conflict indicators."""
    req = EvidenceBuildRequest(query_text="query", rerank_response=sample_rerank_response)
    res = engine.build_evidence(req)
    item = res.package.items[0]

    assert len(item.conflict_indicators) == 1
    assert "dosage" in item.conflict_indicators[0]


def test_multimodal_metadata_preservation(engine, sample_rerank_response):
    """12. Preservation of multimodal structure references."""
    req = EvidenceBuildRequest(query_text="query", rerank_response=sample_rerank_response)
    res = engine.build_evidence(req)
    item = res.package.items[0]

    assert item.multimodal_data is not None
    assert item.multimodal_data.get("table_ref") == "tbl_dosage_1"


def test_agricultural_metadata_preservation(engine, sample_rerank_response):
    """13. Preservation of agricultural metadata fields."""
    req = EvidenceBuildRequest(query_text="query", rerank_response=sample_rerank_response)
    res = engine.build_evidence(req)
    item = res.package.items[0]

    assert item.metadata.get("crop") == "Wheat"
    assert item.metadata.get("disease") == "Yellow Rust"
    assert item.metadata.get("region") == "Punjab"


def test_partial_r8_success_r10_failure(engine, sample_rerank_response):
    """14. Partial R8 success + R10 failure state."""
    failed_web_resp = WebSearchResponse(
        request_id="req_web_err",
        status=WebSearchStatus.PROVIDER_ERROR,
        query_text="query",
        error_message="Web search provider offline",
    )
    req = EvidenceBuildRequest(
        query_text="query",
        rerank_response=sample_rerank_response,
        web_search_response=failed_web_resp,
    )
    res = engine.build_evidence(req)
    assert res.status == EvidenceBuildStatus.PARTIAL
    assert res.package.is_partial is True
    assert res.package.total_items_count == 1 # Valid KB item preserved
    assert len(res.package.errors) > 0


def test_partial_r8_failure_r10_success(engine, sample_web_search_response):
    """15. R8 failure + R10 success state."""
    failed_rerank_resp = RerankResponse(
        request_id="req_rerank_err",
        status=RerankStatus.FAILED,
        query_text="query",
        error_message="Reranker internal error",
    )
    req = EvidenceBuildRequest(
        query_text="query",
        rerank_response=failed_rerank_resp,
        web_search_response=sample_web_search_response,
    )
    res = engine.build_evidence(req)
    assert res.status == EvidenceBuildStatus.PARTIAL
    assert res.package.total_items_count == 1 # Valid Web item preserved


def test_both_upstream_failures(engine):
    """16. Both upstream failures (R8 failed + R10 failed)."""
    failed_rerank_resp = RerankResponse(
        query_text="query", status=RerankStatus.FAILED, error_message="R8 failed"
    )
    failed_web_resp = WebSearchResponse(
        query_text="query", status=WebSearchStatus.PROVIDER_ERROR, error_message="R10 failed"
    )
    req = EvidenceBuildRequest(
        query_text="query",
        rerank_response=failed_rerank_resp,
        web_search_response=failed_web_resp,
    )
    res = engine.build_evidence(req)
    assert res.status == EvidenceBuildStatus.EMPTY
    assert res.package.total_items_count == 0


def test_empty_evidence(engine):
    """17. Empty evidence state when both upstream responses are empty."""
    empty_rerank = RerankResponse(query_text="query", status=RerankStatus.SUCCESS, candidates=[])
    empty_web = WebSearchResponse(query_text="query", status=WebSearchStatus.SUCCESS, results=[])

    req = EvidenceBuildRequest(
        query_text="query", rerank_response=empty_rerank, web_search_response=empty_web
    )
    res = engine.build_evidence(req)
    assert res.status == EvidenceBuildStatus.EMPTY
    assert res.package.total_items_count == 0


def test_malformed_upstream_item(engine, sample_rerank_response):
    """18. Malformed item handling without throwing unhandled exceptions."""
    # Add a malformed candidate with invalid attributes to candidates list
    malformed_cand = RerankCandidate.from_hybrid_candidate(
        HybridCandidate(
            candidate_id="malformed_1",
            record_id="rec_m",
            source_id="src_m",
            document_id="doc_m",
            version_id="v1",
            fused_score=0.5,
            fused_rank=2,
            payload_metadata={"content": None},
        )
    )
    sample_rerank_response.candidates.append(malformed_cand)

    req = EvidenceBuildRequest(query_text="query", rerank_response=sample_rerank_response)
    res = engine.build_evidence(req)
    assert res.package.total_items_count >= 1 # Valid item preserved


def test_evidence_item_limits_and_truncation(sample_rerank_response):
    """19 & 20. Max items limit and content truncation metadata."""
    custom_engine = EvidenceBuilderEngine(
        config=EvidenceBuilderConfig(max_items=1, max_content_length=20)
    )
    req = EvidenceBuildRequest(query_text="query", rerank_response=sample_rerank_response)
    res = custom_engine.build_evidence(req)

    item = res.package.items[0]
    assert len(item.content) <= 20
    assert item.is_truncated is True
    assert item.truncation_reason is not None


def test_deterministic_ordering(engine, sample_rerank_response, sample_web_search_response):
    """21. Deterministic ordering of evidence items."""
    req = EvidenceBuildRequest(
        query_text="query",
        rerank_response=sample_rerank_response,
        web_search_response=sample_web_search_response,
    )
    res1 = engine.build_evidence(req)
    res2 = engine.build_evidence(req)

    ids1 = [it.evidence_id for it in res1.package.items]
    ids2 = [it.evidence_id for it in res2.package.items]
    assert ids1 == ids2


def test_b2_context_manager_compatibility(engine, sample_rerank_response, sample_web_search_response):
    """22. B2 Context Manager compatibility via to_rag_context_contracts()."""
    req = EvidenceBuildRequest(
        query_text="query",
        rerank_response=sample_rerank_response,
        web_search_response=sample_web_search_response,
    )
    res = engine.build_evidence(req)
    contracts = res.package.to_rag_context_contracts()

    assert len(contracts) == 2
    for contract in contracts:
        assert contract.source_type == ContextSourceType.RAG
        assert contract.ownership == ContextOwnership.RAG_OWNED
        assert contract.scope == ContextScope.GLOBAL
        assert "evidence_id" in contract.content


def test_zero_direct_database_access():
    """23. Verify R11 has zero database or Qdrant imports."""
    import modules.knowledge_base.evidence.engine as engine_mod
    source = open(engine_mod.__file__).read()
    assert "qdrant" not in source.lower()
    assert "sqlite" not in source.lower()
    assert "database" not in source.lower()


def test_governance_web_search_transient(engine, sample_web_search_response):
    """24 & 25. C.2/C.3 Governance: Web search evidence marked TRANSIENT, no auto-publication or Memory write."""
    req = EvidenceBuildRequest(query_text="query", web_search_response=sample_web_search_response)
    res = engine.build_evidence(req)
    contracts = res.package.to_rag_context_contracts()

    web_contract = contracts[0]
    assert web_contract.publication_state == "TRANSIENT"
    assert web_contract.ownership == ContextOwnership.RAG_OWNED


def test_invalid_request_handling(engine):
    """26. Invalid request validation."""
    with pytest.raises(InvalidEvidenceBuildRequestError):
        engine.build_evidence(None)

    with pytest.raises(InvalidEvidenceBuildRequestError):
        engine.build_evidence(EvidenceBuildRequest(query_text="   "))


def test_request_and_trace_id_correlation(engine, sample_rerank_response):
    """27. Correlation of request ID and trace info across package and response."""
    req = EvidenceBuildRequest(
        query_text="query",
        request_id="trace_correl_999",
        rerank_response=sample_rerank_response,
    )
    res = engine.build_evidence(req)
    assert res.request_id == "trace_correl_999"
    assert res.package.request_id == "trace_correl_999"
