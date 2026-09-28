"""Comprehensive Unit and Integration Tests for Stage R8 Reranking."""

import pytest
import time
from typing import List, Dict, Any

from core.config.settings import RerankConfig, Settings
from core.errors.exceptions import (
    InvalidRerankRequestError,
    InvalidRerankerResponseError,
    RerankerConfigurationError,
    RerankerExecutionError,
    RerankerProviderUnavailableError,
    RerankerTimeoutError,
)
from core.interfaces.reranker import IRerankerProvider
from core.schemas.hybrid import (
    CandidateRetrievalSource,
    HybridCandidate,
    HybridRetrievalRequest,
    HybridRetrievalResponse,
    HybridRetrievalStatus,
    RetrievalSourceType,
)
from core.schemas.rerank import (
    RerankCandidate,
    RerankRequest,
    RerankResponse,
    RerankScoreResult,
    RerankStatus,
)
from modules.knowledge_base.index.record import IndexRecord
from modules.knowledge_base.reranking.engine import RerankEngine
from modules.knowledge_base.reranking.providers.cross_encoder_provider import CrossEncoderRerankerProvider
from modules.knowledge_base.reranking.providers.fake_provider import FakeRerankerProvider


# --- Helper Fixtures & Objects ---

def make_sample_hybrid_candidate(
    candidate_id: str,
    fused_score: float,
    fused_rank: int,
    dense_score: float = 0.9,
    dense_rank: int = 1,
    sparse_score: float = 0.8,
    sparse_rank: int = 1,
    text: str = "Sample text content",
    metadata: Dict[str, Any] = None,
    provenance: Any = "source_doc_v1_provenance_chain",
) -> HybridCandidate:
    meta = metadata or {
        "crop": "Wheat",
        "disease": "Rust",
        "soil": "Clay",
        "region": "Punjab",
        "season": "Rabi",
        "text": text,
    }
    rec = IndexRecord(
        index_record_id=f"rec_{candidate_id}",
        source_id="src_001",
        document_id="doc_001",
        version_id="ver_001",
        chunk_id=f"chunk_{candidate_id}",
        dense_vector=[0.1, 0.2, 0.3],
        payload_metadata=meta,
    )
    return HybridCandidate(
        candidate_id=candidate_id,
        record_id=rec.index_record_id,
        chunk_id=f"chunk_{candidate_id}",
        knowledge_unit_id=f"ku_{candidate_id}",
        source_id="src_001",
        document_id="doc_001",
        version_id="ver_001",
        fused_score=fused_score,
        fused_rank=fused_rank,
        dense_score=dense_score,
        dense_rank=dense_rank,
        sparse_score=sparse_score,
        sparse_rank=sparse_rank,
        retrieval_sources=[
            CandidateRetrievalSource(
                source_type=RetrievalSourceType.DENSE,
                rank=dense_rank,
                score=dense_score,
            ),
            CandidateRetrievalSource(
                source_type=RetrievalSourceType.SPARSE,
                rank=sparse_rank,
                score=sparse_score,
            ),
        ],
        payload_metadata=meta,
        provenance=provenance,
        record=rec,
    )


# --- 1. RerankRequest Validation ---

def test_rerank_request_validation_valid():
    c1 = make_sample_hybrid_candidate("c1", 0.8, 1)
    req = RerankRequest(query_text="wheat disease", candidates=[c1], top_k=5)
    assert req.query_text == "wheat disease"
    assert len(req.candidates) == 1
    assert req.top_k == 5


def test_rerank_request_validation_empty_query():
    c1 = make_sample_hybrid_candidate("c1", 0.8, 1)
    engine = RerankEngine()
    req = RerankRequest(query_text="   ", candidates=[c1])
    with pytest.raises(InvalidRerankRequestError) as exc_info:
        engine.rerank(req)
    assert "Query text cannot be empty" in str(exc_info.value)


# --- 2. RerankResponse Validation ---

def test_rerank_response_validation():
    resp = RerankResponse(
        query_text="test query",
        status=RerankStatus.SUCCESS,
        candidates=[],
        total_candidates_received=0,
        total_candidates_reranked=0,
    )
    assert resp.status == RerankStatus.SUCCESS
    assert resp.is_fallback is False


# --- 3. Provider Interface Contract ---

def test_provider_interface_contract():
    provider = FakeRerankerProvider()
    assert isinstance(provider, IRerankerProvider)
    assert provider.is_available() is True
    info = provider.get_provider_info()
    assert "provider_name" in info


# --- 4. Fake Provider Execution ---

def test_fake_provider_scoring():
    provider = FakeRerankerProvider(scores={"c1": 0.95, "c2": 0.25})
    docs = [
        {"candidate_id": "c1", "text": "wheat disease control"},
        {"candidate_id": "c2", "text": "rice irrigation"},
    ]
    results = provider.rerank("wheat disease", docs)
    assert len(results) == 2
    assert results[0].candidate_id == "c1"
    assert results[0].score == 0.95
    assert results[1].candidate_id == "c2"
    assert results[1].score == 0.25


# --- 5. Successful Reranking Execution ---

def test_successful_reranking():
    c1 = make_sample_hybrid_candidate("c1", fused_score=0.6, fused_rank=2, text="rice pest control")
    c2 = make_sample_hybrid_candidate("c2", fused_score=0.9, fused_rank=1, text="wheat yellow rust treatment")
    provider = FakeRerankerProvider(scores={"c1": 0.3, "c2": 0.98})
    engine = RerankEngine(provider=provider)

    req = RerankRequest(query_text="wheat rust", candidates=[c1, c2])
    res = engine.rerank(req)

    assert res.status == RerankStatus.SUCCESS
    assert len(res.candidates) == 2
    assert res.candidates[0].candidate_id == "c2"
    assert res.candidates[0].rerank_rank == 1
    assert res.candidates[0].rerank_score == 0.98
    assert res.candidates[1].candidate_id == "c1"
    assert res.candidates[1].rerank_rank == 2


# --- 6. Score Preservation ---

def test_upstream_score_preservation():
    c1 = make_sample_hybrid_candidate(
        "c1", fused_score=0.75, fused_rank=1, dense_score=0.88, dense_rank=1, sparse_score=0.62, sparse_rank=2
    )
    provider = FakeRerankerProvider(scores={"c1": 0.91})
    engine = RerankEngine(provider=provider)
    res = engine.rerank(RerankRequest(query_text="wheat", candidates=[c1]))

    cand = res.candidates[0]
    assert cand.fused_score == 0.75
    assert cand.dense_score == 0.88
    assert cand.sparse_score == 0.62
    assert cand.rerank_score == 0.91


# --- 7. Rank Preservation ---

def test_upstream_rank_preservation():
    c1 = make_sample_hybrid_candidate(
        "c1", fused_score=0.75, fused_rank=2, dense_rank=3, sparse_rank=1
    )
    provider = FakeRerankerProvider(scores={"c1": 0.85})
    engine = RerankEngine(provider=provider)
    res = engine.rerank(RerankRequest(query_text="wheat", candidates=[c1]))

    cand = res.candidates[0]
    assert cand.fused_rank == 2
    assert cand.dense_rank == 3
    assert cand.sparse_rank == 1
    assert cand.rerank_rank == 1


# --- 8. Rerank Score Ordering ---

def test_rerank_score_ordering():
    c1 = make_sample_hybrid_candidate("c1", 0.9, 1, text="doc one")
    c2 = make_sample_hybrid_candidate("c2", 0.8, 2, text="doc two")
    c3 = make_sample_hybrid_candidate("c3", 0.7, 3, text="doc three")

    # Override scores so c3 is best, c1 is middle, c2 is worst
    provider = FakeRerankerProvider(scores={"c1": 0.5, "c2": 0.1, "c3": 0.99})
    engine = RerankEngine(provider=provider)
    res = engine.rerank(RerankRequest(query_text="test", candidates=[c1, c2, c3]))

    assert [c.candidate_id for c in res.candidates] == ["c3", "c1", "c2"]
    assert [c.rerank_rank for c in res.candidates] == [1, 2, 3]


# --- 9. Deterministic Tie-Breaking ---

def test_deterministic_tie_breaking():
    # c1 and c2 have identical rerank score (0.8)
    c1 = make_sample_hybrid_candidate("c1", fused_score=0.6, fused_rank=2)
    c2 = make_sample_hybrid_candidate("c2", fused_score=0.9, fused_rank=1)

    provider = FakeRerankerProvider(scores={"c1": 0.8, "c2": 0.8})
    engine = RerankEngine(provider=provider)
    res = engine.rerank(RerankRequest(query_text="wheat", candidates=[c1, c2]))

    # c2 wins tie-breaker because fused_rank is 1 (lower/better than c1's fused_rank 2)
    assert res.candidates[0].candidate_id == "c2"
    assert res.candidates[1].candidate_id == "c1"

    # Secondary tie-breaker: candidate_id alphabetical if fused_rank identical
    c3 = make_sample_hybrid_candidate("cand_b", fused_score=0.5, fused_rank=1)
    c4 = make_sample_hybrid_candidate("cand_a", fused_score=0.5, fused_rank=1)
    provider_2 = FakeRerankerProvider(scores={"cand_b": 0.8, "cand_a": 0.8})
    engine_2 = RerankEngine(provider=provider_2)
    res_2 = engine_2.rerank(RerankRequest(query_text="wheat", candidates=[c3, c4]))

    assert res_2.candidates[0].candidate_id == "cand_a"
    assert res_2.candidates[1].candidate_id == "cand_b"


# --- 10. Candidate Identity Preservation ---

def test_candidate_identity_preservation():
    c1 = make_sample_hybrid_candidate("c1_unique_id", 0.8, 1)
    provider = FakeRerankerProvider(scores={"c1_unique_id": 0.9})
    engine = RerankEngine(provider=provider)
    res = engine.rerank(RerankRequest(query_text="query", candidates=[c1]))

    cand = res.candidates[0]
    assert cand.candidate_id == "c1_unique_id"
    assert cand.record_id == "rec_c1_unique_id"
    assert cand.chunk_id == "chunk_c1_unique_id"
    assert cand.knowledge_unit_id == "ku_c1_unique_id"
    assert cand.source_id == "src_001"
    assert cand.document_id == "doc_001"
    assert cand.version_id == "ver_001"


# --- 11. Provenance Preservation ---

def test_provenance_preservation():
    c1 = make_sample_hybrid_candidate("c1", 0.8, 1, provenance="exact_provenance_object_123")
    provider = FakeRerankerProvider(scores={"c1": 0.9})
    engine = RerankEngine(provider=provider)
    res = engine.rerank(RerankRequest(query_text="query", candidates=[c1]))

    assert res.candidates[0].provenance == "exact_provenance_object_123"


# --- 12. Metadata Preservation ---

def test_agricultural_metadata_preservation():
    meta = {
        "crop": "Cotton",
        "disease": "Blight",
        "soil": "Black Soil",
        "region": "Gujarat",
        "season": "Kharif",
        "dosage": "2g/L",
    }
    c1 = make_sample_hybrid_candidate("c1", 0.8, 1, metadata=meta)
    provider = FakeRerankerProvider(scores={"c1": 0.9})
    engine = RerankEngine(provider=provider)
    res = engine.rerank(RerankRequest(query_text="cotton blight", candidates=[c1]))

    payload = res.candidates[0].payload_metadata
    assert payload["crop"] == "Cotton"
    assert payload["disease"] == "Blight"
    assert payload["soil"] == "Black Soil"
    assert payload["region"] == "Gujarat"
    assert payload["season"] == "Kharif"
    assert payload["dosage"] == "2g/L"


# --- 13. Multilingual Input Handling ---

def test_multilingual_input_handling():
    # Hindi / Devanagari query and text
    hindi_query = "गेहूं में पीला रतुआ रोग नियंत्रण"
    c1 = make_sample_hybrid_candidate("c1", 0.8, 1, text="गेहूं में पीला रतुआ रोग के उपचार के लिए कवकनाशी का छिड़काव करें।")
    c2 = make_sample_hybrid_candidate("c2", 0.7, 2, text="चावल की खेती में सिंचाई प्रबंधन।")

    provider = FakeRerankerProvider(scores={"c1": 0.92, "c2": 0.15})
    engine = RerankEngine(provider=provider)
    res = engine.rerank(RerankRequest(query_text=hindi_query, candidates=[c1, c2]))

    assert res.status == RerankStatus.SUCCESS
    assert res.candidates[0].candidate_id == "c1"
    assert res.candidates[0].rerank_score == 0.92


# --- 14. Candidate Limit Enforcement ---

def test_candidate_limit_enforcement():
    cands = [make_sample_hybrid_candidate(f"c{i}", 1.0 - (i * 0.1), i + 1) for i in range(10)]
    config = RerankConfig(max_candidate_count=5)
    engine = RerankEngine(config=config)

    # Exceeding max_candidate_count raises error
    req_too_many = RerankRequest(query_text="query", candidates=cands)
    with pytest.raises(InvalidRerankRequestError) as exc:
        engine.rerank(req_too_many)
    assert "exceeds maximum allowed limit" in str(exc.value)

    # top_k limiting
    config_ok = RerankConfig(max_candidate_count=20)
    engine_ok = RerankEngine(config=config_ok)
    req_limit = RerankRequest(query_text="query", candidates=cands[:8], top_k=3)
    res = engine_ok.rerank(req_limit)
    assert len(res.candidates) == 3


# --- 15. Provider Failure Handling ---

def test_provider_failure_handling_no_fallback():
    c1 = make_sample_hybrid_candidate("c1", 0.8, 1)
    failing_provider = FakeRerankerProvider(should_raise=RerankerExecutionError("fake", "Internal model crash"))
    config = RerankConfig(fallback_policy="FAIL")
    engine = RerankEngine(provider=failing_provider, config=config)

    req = RerankRequest(query_text="query", candidates=[c1], allow_fallback=False)
    res = engine.rerank(req)

    assert res.status == RerankStatus.FAILED
    assert "Internal model crash" in res.error_message


# --- 16. Timeout Handling ---

def test_timeout_handling():
    c1 = make_sample_hybrid_candidate("c1", 0.8, 1)
    slow_provider = FakeRerankerProvider(delay_seconds=2.0)
    config = RerankConfig(fallback_policy="FAIL")
    engine = RerankEngine(provider=slow_provider, config=config)

    req = RerankRequest(query_text="query", candidates=[c1], timeout=0.1, allow_fallback=False)
    res = engine.rerank(req)

    assert res.status == RerankStatus.TIMEOUT


# --- 17. Unavailable Provider Handling ---

def test_unavailable_provider_handling():
    c1 = make_sample_hybrid_candidate("c1", 0.8, 1)
    unavail_provider = FakeRerankerProvider(is_available_flag=False)
    config = RerankConfig(fallback_policy="FAIL")
    engine = RerankEngine(provider=unavail_provider, config=config)

    req = RerankRequest(query_text="query", candidates=[c1], allow_fallback=False)
    res = engine.rerank(req)

    assert res.status == RerankStatus.UNAVAILABLE


# --- 18. Invalid Provider Response Handling ---

def test_invalid_provider_response_handling():
    c1 = make_sample_hybrid_candidate("c1", 0.8, 1)
    # Provider returns empty results dict missing c1
    provider = FakeRerankerProvider(scores={})
    # Remove default overlap score generation by raising on doc
    provider.rerank = lambda query_text, documents, top_k=None, timeout=None: [RerankScoreResult(candidate_id="other", score=0.5)]

    config = RerankConfig(fallback_policy="FAIL")
    engine = RerankEngine(provider=provider, config=config)

    req = RerankRequest(query_text="query", candidates=[c1], allow_fallback=False)
    res = engine.rerank(req)

    assert res.status == RerankStatus.FAILED
    assert "did not return score" in res.error_message


# --- 19 & 20. Configured Fallback & Fallback Marking ---

def test_configured_fallback_marking():
    c1 = make_sample_hybrid_candidate("c1", fused_score=0.6, fused_rank=2)
    c2 = make_sample_hybrid_candidate("c2", fused_score=0.9, fused_rank=1)

    unavail_provider = FakeRerankerProvider(is_available_flag=False)
    config = RerankConfig(fallback_policy="PRESERVE_FUSED_ORDER")
    engine = RerankEngine(provider=unavail_provider, config=config)

    req = RerankRequest(query_text="query", candidates=[c1, c2], allow_fallback=True)
    res = engine.rerank(req)

    assert res.status == RerankStatus.FALLBACK
    assert res.is_fallback is True
    assert len(res.candidates) == 2

    # Verify R7 fused ordering preserved
    assert res.candidates[0].candidate_id == "c2"
    assert res.candidates[0].rerank_rank == 1
    assert res.candidates[0].rerank_score is None  # NO fabricated score!
    assert res.candidates[0].is_fallback is True

    assert res.candidates[1].candidate_id == "c1"
    assert res.candidates[1].rerank_rank == 2
    assert res.candidates[1].rerank_score is None
    assert res.candidates[1].is_fallback is True


# --- 21. Empty Candidate Set ---

def test_empty_candidate_set():
    engine = RerankEngine()
    req = RerankRequest(query_text="wheat disease", candidates=[])
    res = engine.rerank(req)

    assert res.status == RerankStatus.SUCCESS
    assert len(res.candidates) == 0
    assert res.total_candidates_received == 0
    assert res.total_candidates_reranked == 0


# --- 22. Duplicate Candidate Handling ---

def test_duplicate_candidate_handling():
    c1 = make_sample_hybrid_candidate("c1", 0.8, 1)
    c1_duplicate = make_sample_hybrid_candidate("c1", 0.8, 2)

    engine = RerankEngine()
    req = RerankRequest(query_text="query", candidates=[c1, c1_duplicate])

    with pytest.raises(InvalidRerankRequestError) as exc:
        engine.rerank(req)
    assert "Duplicate candidate ID" in str(exc.value)


# --- 23. Deterministic Output ---

def test_deterministic_output():
    c1 = make_sample_hybrid_candidate("c1", 0.7, 2, text="wheat disease treatment")
    c2 = make_sample_hybrid_candidate("c2", 0.9, 1, text="wheat pest control")

    provider = FakeRerankerProvider(scores={"c1": 0.85, "c2": 0.85})
    engine = RerankEngine(provider=provider)

    req = RerankRequest(query_text="wheat disease", candidates=[c1, c2])

    res1 = engine.rerank(req)
    res2 = engine.rerank(req)

    assert [c.candidate_id for c in res1.candidates] == [c.candidate_id for c in res2.candidates]
    assert [c.rerank_rank for c in res1.candidates] == [c.rerank_rank for c in res2.candidates]


# --- 24. R7 → R8 Integration ---

def test_r7_to_r8_integration():
    c1 = make_sample_hybrid_candidate("c1", 0.6, 2, text="rice Blast diagnosis")
    c2 = make_sample_hybrid_candidate("c2", 0.9, 1, text="wheat Rust treatment")

    hybrid_response = HybridRetrievalResponse(
        request_id="req_r7_001",
        query_text="wheat Rust disease",
        status=HybridRetrievalStatus.SUCCESS,
        candidates=[c2, c1],
        total_fused_candidates=2,
    )

    rerank_request = RerankRequest.from_hybrid_response(hybrid_response, top_k=10)
    assert rerank_request.request_id == "req_r7_001"
    assert rerank_request.query_text == "wheat Rust disease"
    assert len(rerank_request.candidates) == 2

    provider = FakeRerankerProvider(scores={"c1": 0.1, "c2": 0.99})
    engine = RerankEngine(provider=provider)

    rerank_response = engine.rerank(rerank_request)

    assert rerank_response.request_id == "req_r7_001"
    assert rerank_response.status == RerankStatus.SUCCESS
    assert rerank_response.candidates[0].candidate_id == "c2"
    assert rerank_response.candidates[0].fused_score == 0.9
    assert rerank_response.candidates[0].fused_rank == 1
    assert rerank_response.candidates[0].rerank_rank == 1
    assert rerank_response.candidates[0].rerank_score == 0.99


# --- 25. R8 → R11 Contract Readiness ---

def test_r8_to_r11_contract_readiness():
    c1 = make_sample_hybrid_candidate("c1", 0.8, 1, text="downstream evidence context")
    provider = FakeRerankerProvider(scores={"c1": 0.95})
    engine = RerankEngine(provider=provider)

    res = engine.rerank(RerankRequest(query_text="evidence query", candidates=[c1]))

    assert isinstance(res, RerankResponse)
    assert res.status == RerankStatus.SUCCESS
    assert len(res.candidates) == 1

    cand: RerankCandidate = res.candidates[0]
    # Check all downstream R11 Evidence Builder required fields
    assert hasattr(cand, "candidate_id")
    assert hasattr(cand, "record_id")
    assert hasattr(cand, "chunk_id")
    assert hasattr(cand, "knowledge_unit_id")
    assert hasattr(cand, "source_id")
    assert hasattr(cand, "document_id")
    assert hasattr(cand, "version_id")
    assert hasattr(cand, "fused_score")
    assert hasattr(cand, "fused_rank")
    assert hasattr(cand, "dense_score")
    assert hasattr(cand, "dense_rank")
    assert hasattr(cand, "sparse_score")
    assert hasattr(cand, "sparse_rank")
    assert hasattr(cand, "rerank_score")
    assert hasattr(cand, "rerank_rank")
    assert hasattr(cand, "retrieval_sources")
    assert hasattr(cand, "payload_metadata")
    assert hasattr(cand, "provenance")
    assert hasattr(cand, "record")


# --- Score Normalization Tests ---

def test_min_max_score_normalization():
    c1 = make_sample_hybrid_candidate("c1", 0.8, 1, text="text 1")
    c2 = make_sample_hybrid_candidate("c2", 0.7, 2, text="text 2")

    provider = FakeRerankerProvider(scores={"c1": 10.0, "c2": 2.0})
    config = RerankConfig(score_normalization_policy="MIN_MAX")
    engine = RerankEngine(provider=provider, config=config)

    res = engine.rerank(RerankRequest(query_text="test", candidates=[c1, c2]))

    # Min-max scales 10.0 -> 1.0 and 2.0 -> 0.0
    assert res.candidates[0].candidate_id == "c1"
    assert res.candidates[0].rerank_score == 1.0
    assert res.candidates[1].candidate_id == "c2"
    assert res.candidates[1].rerank_score == 0.0


def test_sigmoid_score_normalization():
    c1 = make_sample_hybrid_candidate("c1", 0.8, 1, text="text 1")
    provider = FakeRerankerProvider(scores={"c1": 0.0})
    config = RerankConfig(score_normalization_policy="SIGMOID")
    engine = RerankEngine(provider=provider, config=config)

    res = engine.rerank(RerankRequest(query_text="test", candidates=[c1]))
    # sigmoid(0.0) = 0.5
    assert res.candidates[0].rerank_score == 0.5
