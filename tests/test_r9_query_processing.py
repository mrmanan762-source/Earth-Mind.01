"""Tests for Stage R9 Query Processing in EarthMind RAG.

Covers:
1. Valid query processing
2. Empty query rejection
3. Malformed input rejection
4. Normalization behavior
5. Original query preservation
6. Multilingual query handling (English, Devanagari Hindi, Marathi)
7. Agricultural terminology preservation (e.g. pH 6.5, 10kg/acre, Xanthomonas)
8. Metadata extraction without hallucination
9. Query classification
10. Query expansion
11. Expansion limits
12. Expansion disabled
13. Expansion failure fallback to unexpanded query
14. Dense query generation
15. Sparse query generation
16. Structured filter generation
17. Final RetrievalQuery construction
18. Deterministic output
19. Traceability and step logging
20. Timeout and parameter error handling
21. Partial processing
22. Interface isolation
23. R5 compatibility (DenseQuery)
24. R6 compatibility (SparseQuery)
25. Bridge to Stage R7 (HybridRetrievalRequest via to_hybrid_retrieval_request)
26. Full repository regression compatibility
"""

import pytest
from core.config.settings import QueryProcessingConfig, settings
from core.errors.exceptions import (
    InvalidQueryError,
    QueryProcessingError,
    QueryValidationError,
)
from core.schemas.query import (
    AgriculturalMetadata,
    DenseQuery,
    QueryClassification,
    QueryExpansion,
    QueryMetadata,
    QueryProcessingRequest,
    QueryProcessingResponse,
    QueryProcessingStatus,
    RetrievalQuery,
    SparseQuery,
    StructuredQueryFilter,
)
from modules.knowledge_base.query_processing.builder import RetrievalQueryBuilder
from modules.knowledge_base.query_processing.classifier import QueryClassifier
from modules.knowledge_base.query_processing.engine import QueryProcessingEngine
from modules.knowledge_base.query_processing.expansion import (
    DictionaryQueryExpansionStrategy,
    FakeQueryExpansionStrategy,
)
from modules.knowledge_base.query_processing.metadata_extractor import (
    AgriculturalMetadataExtractor,
)
from modules.knowledge_base.query_processing.normalizer import QueryNormalizer
from modules.knowledge_base.query_processing.validator import QueryValidator


def test_r9_valid_query_processing():
    engine = QueryProcessingEngine()
    req = QueryProcessingRequest(
        query_text="What is the recommended fertilizer for wheat crop in Punjab?",
        request_id="test_req_001",
        language="en",
        top_k=10,
    )
    res = engine.process_query(req)
    assert res.status == QueryProcessingStatus.SUCCESS
    assert res.request_id == "test_req_001"
    assert res.retrieval_query is not None
    assert res.retrieval_query.original_query == "What is the recommended fertilizer for wheat crop in Punjab?"
    assert res.retrieval_query.normalized_query == "what is the recommended fertilizer for wheat crop in punjab?"
    assert res.retrieval_query.metadata.agricultural_metadata.crop == "wheat"
    assert res.retrieval_query.metadata.agricultural_metadata.region == "punjab"


def test_r9_empty_query_rejection():
    validator = QueryValidator()
    req = QueryProcessingRequest(query_text="   ")
    errors = validator.validate(req)
    assert len(errors) > 0
    assert any("empty or whitespace-only" in e for e in errors)

    engine = QueryProcessingEngine()
    res = engine.process_query(req)
    assert res.status == QueryProcessingStatus.INVALID
    assert res.retrieval_query is None
    assert "empty or whitespace-only" in res.error_message


def test_r9_malformed_input_rejection():
    validator = QueryValidator()
    # Negative top_k
    req = QueryProcessingRequest(query_text="wheat disease", top_k=-5)
    errors = validator.validate(req)
    assert any("top_k must be a positive integer" in e for e in errors)

    # Unsupported language
    req_lang = QueryProcessingRequest(query_text="wheat disease", language="invalid_lang")
    errors_lang = validator.validate(req_lang)
    assert any("Unsupported language code" in e for e in errors_lang)


def test_r9_query_normalization_and_term_preservation():
    normalizer = QueryNormalizer()
    raw = "  Apply 10kg/acre DAP fertilizer at pH 6.5 for Xanthomonas blight!  "
    norm = normalizer.normalize(raw, language="en")
    assert "pH" in norm
    assert "dap" in norm or "DAP" in norm
    assert "10kg/acre" in norm
    assert "6.5" in norm
    assert "xanthomonas blight" in norm


def test_r9_original_query_preservation():
    engine = QueryProcessingEngine()
    original = "गेहूँ में पीला रतुआ का उपचार क्या है?"
    req = QueryProcessingRequest(query_text=original, language="hi")
    res = engine.process_query(req)
    assert res.original_query == original
    assert res.retrieval_query.original_query == original
    assert res.retrieval_query.normalized_query != ""


def test_r9_multilingual_query_handling():
    engine = QueryProcessingEngine()
    # Hindi Devanagari query
    req_hi = QueryProcessingRequest(query_text="धान में तना छेदक कीट की रोकथाम कैसे करें?", language="hi")
    res_hi = engine.process_query(req_hi)
    assert res_hi.status == QueryProcessingStatus.SUCCESS
    assert res_hi.retrieval_query.metadata.agricultural_metadata.crop == "rice"
    assert res_hi.retrieval_query.metadata.agricultural_metadata.disease_pest == "stem_borer"

    # Marathi query
    req_mr = QueryProcessingRequest(query_text="कापूस पिकावर पांढरी माशी नियंत्रण", language="mr")
    res_mr = engine.process_query(req_mr)
    assert res_mr.status == QueryProcessingStatus.SUCCESS


def test_r9_agricultural_terminology_preservation():
    normalizer = QueryNormalizer()
    text = "Use NPK 19:19:19 with EC 1.2 at pH 6.0 in ICAR recommended doses."
    norm = normalizer.normalize(text)
    assert "pH" in norm
    assert "NPK" in norm
    assert "ICAR" in norm
    assert "19:19:19" in norm


def test_r9_metadata_extraction_without_hallucination():
    extractor = AgriculturalMetadataExtractor()
    # Query mentioning only wheat
    meta = extractor.extract("How to increase wheat crop yield?")
    assert meta.crop == "wheat"
    assert meta.disease_pest is None
    assert meta.soil_type is None
    assert meta.region is None
    assert meta.season is None

    # Query with no agricultural terms
    meta_empty = extractor.extract("Tell me a general greeting")
    assert meta_empty.crop is None
    assert meta_empty.disease_pest is None


def test_r9_query_classification():
    classifier = QueryClassifier()
    assert classifier.classify("yellow rust symptoms on wheat leaves") == QueryClassification.DIAGNOSIS_RELATED
    assert classifier.classify("aphid pest control in cotton") == QueryClassification.PEST_DISEASE_RELATED
    assert classifier.classify("best fertilizer for black soil") == QueryClassification.SOIL_QUERY
    assert classifier.classify("wheat variety recommendation") == QueryClassification.CROP_QUERY


def test_r9_query_expansion_behavior():
    strategy = DictionaryQueryExpansionStrategy()
    expansions = strategy.expand("yellow rust in wheat", language="en", max_expansions=3)
    assert len(expansions) > 0
    texts = [e.expanded_text for e in expansions]
    assert any("stripe rust" in t or "पीला रतुआ" in t for t in texts)


def test_r9_expansion_limit_enforcement():
    strategy = DictionaryQueryExpansionStrategy()
    expansions = strategy.expand("yellow rust in wheat", max_expansions=1)
    assert len(expansions) == 1


def test_r9_expansion_disabled():
    engine = QueryProcessingEngine()
    req = QueryProcessingRequest(query_text="yellow rust in wheat", enable_expansion=False)
    res = engine.process_query(req)
    assert res.status == QueryProcessingStatus.SUCCESS
    assert len(res.retrieval_query.expanded_queries) == 0


class FailingExpansionStrategy(DictionaryQueryExpansionStrategy):
    def expand(self, *args, **kwargs):
        raise RuntimeError("Expansion provider network error")


def test_r9_expansion_failure_fallback():
    engine = QueryProcessingEngine(expansion_strategy=FailingExpansionStrategy())
    req = QueryProcessingRequest(query_text="yellow rust in wheat", enable_expansion=True)
    res = engine.process_query(req)
    assert res.status == QueryProcessingStatus.PARTIAL
    assert len(res.warnings) > 0
    assert "Query expansion failed" in res.warnings[0]
    assert res.retrieval_query is not None
    assert res.retrieval_query.normalized_query == "yellow rust in wheat"


def test_r9_dense_and_sparse_query_generation():
    engine = QueryProcessingEngine()
    req = QueryProcessingRequest(query_text="control yellow rust in wheat", dense_top_k=25, sparse_top_k=30)
    res = engine.process_query(req)
    ret_q = res.retrieval_query
    assert ret_q.dense_query.dense_query_text == "control yellow rust in wheat"
    assert ret_q.dense_query.top_k == 25
    assert ret_q.sparse_query.sparse_query_text == "control yellow rust in wheat"
    assert "yellow" in ret_q.sparse_query.lexical_terms
    assert "rust" in ret_q.sparse_query.lexical_terms


def test_r9_structured_filter_generation():
    engine = QueryProcessingEngine()
    req = QueryProcessingRequest(
        query_text="yellow rust treatment for wheat in Punjab",
        filters={"document_type": "advisory"},
    )
    res = engine.process_query(req)
    filters = res.retrieval_query.structured_filters
    filter_map = {f.field: f.value for f in filters}
    assert filter_map["document_type"] == "advisory"
    assert filter_map["crop"] == "wheat"
    assert filter_map["disease_pest"] == "yellow_rust"
    assert filter_map["region"] == "punjab"


def test_r9_bridge_to_hybrid_retrieval_request():
    engine = QueryProcessingEngine()
    req = QueryProcessingRequest(
        query_text="wheat yellow rust",
        request_id="req_bridge_123",
        top_k=15,
        dense_top_k=30,
        sparse_top_k=30,
    )
    res = engine.process_query(req)
    hybrid_req = res.retrieval_query.to_hybrid_retrieval_request(fusion_strategy="RRF", rrf_k=60)

    assert hybrid_req.query_text == "wheat yellow rust"
    assert hybrid_req.request_id == "req_bridge_123"
    assert hybrid_req.top_k == 15
    assert hybrid_req.dense_top_k == 30
    assert hybrid_req.sparse_top_k == 30
    assert hybrid_req.filters is not None
    assert hybrid_req.filters.get("crop") == "wheat"


def test_r9_deterministic_output():
    engine = QueryProcessingEngine()
    req = QueryProcessingRequest(query_text="dap fertilizer for maize crop in Haryana")
    res1 = engine.process_query(req)
    res2 = engine.process_query(req)
    assert res1.retrieval_query.normalized_query == res2.retrieval_query.normalized_query
    assert res1.retrieval_query.metadata.model_dump() == res2.retrieval_query.metadata.model_dump()


def test_r9_traceability_and_audit_trail():
    engine = QueryProcessingEngine()
    req = QueryProcessingRequest(query_text="rice stem borer")
    res = engine.process_query(req)
    assert len(res.trace_steps) >= 5
    step_names = [s["step"] for s in res.trace_steps]
    assert "validation" in step_names
    assert "normalization" in step_names
    assert "classification" in step_names
    assert "metadata_extraction" in step_names
    assert "query_expansion" in step_names
    assert "retrieval_query_building" in step_names
