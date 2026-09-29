"""Unit tests for Stage R10 Web Search Integration in EarthMind RAG.

Verifies:
1. Valid search request
2. Invalid request
3. Provider invocation
4. Normalized result conversion
5. Multiple search results
6. Empty results
7. Provider timeout
8. Provider unavailable
9. Authentication failure
10. Rate-limit handling
11. Provider error
12. Result-limit enforcement
13. Provenance preservation
14. URL preservation
15. Timestamp preservation
16. Provider identity preservation
17. Multilingual query handling
18. Agricultural metadata preservation
19. Fake-provider execution
20. No automatic KB publication
21. No direct Qdrant access
22. Provider replacement compatibility
23. Deterministic response structure
24. Traceability and request correlation ID
"""

import json
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from core.config.settings import WebSearchConfig
from core.errors.exceptions import (
    InvalidWebSearchRequestError,
    WebSearchAuthenticationError,
    WebSearchConfigurationError,
    WebSearchExecutionError,
    WebSearchProviderUnavailableError,
    WebSearchRateLimitError,
    WebSearchTimeoutError,
)
from core.interfaces.web_search import IWebSearchProvider
from core.schemas.query import (
    AgriculturalMetadata,
    DenseQuery,
    QueryMetadata,
    RetrievalQuery,
    SparseQuery,
)
from core.schemas.web_search import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
    WebSearchStatus,
)
from modules.knowledge_base.web_search.engine import WebSearchEngine
from modules.knowledge_base.web_search.providers.api_provider import APIWebSearchProvider
from modules.knowledge_base.web_search.providers.fake_provider import FakeWebSearchProvider


# Custom Mock Provider for interface testing
class CustomMockWebSearchProvider(IWebSearchProvider):
    @property
    def provider_name(self) -> str:
        return "custom_mock"

    def is_available(self) -> bool:
        return True

    def supported_capabilities(self) -> Dict[str, Any]:
        return {"custom": True}

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        return WebSearchResponse(
            request_id=request.request_id,
            status=WebSearchStatus.SUCCESS,
            query_text=request.query_text,
            results=[
                WebSearchResult(
                    result_id="custom_1",
                    title="Custom Mock Title",
                    url="https://custom.example.org/doc",
                    snippet="Custom snippet text",
                    provider=self.provider_name,
                    rank=1,
                    request_id=request.request_id,
                )
            ],
            result_count=1,
            provider_name=self.provider_name,
            execution_time_ms=5.0,
        )


@pytest.fixture
def fake_provider() -> FakeWebSearchProvider:
    return FakeWebSearchProvider()


@pytest.fixture
def engine(fake_provider) -> WebSearchEngine:
    return WebSearchEngine(provider=fake_provider)


# 1. Valid search request
def test_valid_search_request(engine):
    req = WebSearchRequest(
        query_text="wheat yellow rust fungicide advisory",
        request_id="req_valid_001",
        max_results=5,
        language="en",
        region="Punjab",
    )
    res = engine.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    assert res.request_id == "req_valid_001"
    assert res.query_text == "wheat yellow rust fungicide advisory"
    assert res.provider_name == "fake"
    assert res.result_count > 0
    assert len(res.results) <= 5


# 2. Invalid request
def test_invalid_search_request(engine):
    req_empty = WebSearchRequest(query_text="", request_id="req_invalid_1")
    res1 = engine.search(req_empty)
    assert res1.status == WebSearchStatus.INVALID_REQUEST
    assert "cannot be empty" in res1.error_message.lower()

    req_blank = WebSearchRequest(query_text="   ", request_id="req_invalid_2")
    res2 = engine.search(req_blank)
    assert res2.status == WebSearchStatus.INVALID_REQUEST

    with pytest.raises(InvalidWebSearchRequestError):
        fake_provider = FakeWebSearchProvider()
        fake_provider.search(WebSearchRequest(query_text=""))


# 3. Provider invocation
def test_provider_invocation(engine):
    req = WebSearchRequest(query_text="rice blast control", request_id="req_prov_1")
    res = engine.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    assert res.provider_name == engine.provider.provider_name
    assert res.trace_info.get("provider") == "fake"


# 4. Normalized result conversion
def test_normalized_result_conversion(engine):
    req = WebSearchRequest(query_text="cotton pink bollworm management", request_id="req_norm_1")
    res = engine.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    assert len(res.results) > 0
    item = res.results[0]

    assert isinstance(item, WebSearchResult)
    assert isinstance(item.result_id, str) and item.result_id
    assert isinstance(item.title, str) and item.title
    assert isinstance(item.url, str) and item.url.startswith("http")
    assert isinstance(item.snippet, str) and item.snippet
    assert isinstance(item.provider, str) and item.provider == "fake"
    assert isinstance(item.retrieval_timestamp, float)
    assert isinstance(item.rank, int) and item.rank >= 1


# 5. Multiple search results
def test_multiple_search_results(engine):
    req = WebSearchRequest(query_text="fertilizer dosage recommendations", max_results=5)
    res = engine.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    assert len(res.results) == 5
    ranks = [r.rank for r in res.results]
    assert ranks == [1, 2, 3, 4, 5]


# 6. Empty results
def test_empty_results_handling(engine, fake_provider):
    fake_provider.set_simulated_status(WebSearchStatus.EMPTY_RESULT)
    req = WebSearchRequest(query_text="obscure uncommon agricultural term")
    res = engine.search(req)

    assert res.status == WebSearchStatus.EMPTY_RESULT
    assert res.result_count == 0
    assert res.results == []


# 7. Provider timeout
def test_provider_timeout_handling(engine, fake_provider):
    fake_provider.set_simulated_status(WebSearchStatus.PROVIDER_TIMEOUT)
    req = WebSearchRequest(query_text="soil nutrient analysis", timeout=1.0)
    res = engine.search(req)

    assert res.status == WebSearchStatus.PROVIDER_TIMEOUT
    assert "timed out" in res.error_message.lower()


# 8. Provider unavailable
def test_provider_unavailable_handling(engine, fake_provider):
    fake_provider.set_simulated_status(WebSearchStatus.PROVIDER_UNAVAILABLE)
    req = WebSearchRequest(query_text="drip irrigation guide")
    res = engine.search(req)

    assert res.status == WebSearchStatus.PROVIDER_UNAVAILABLE
    assert "unavailable" in res.error_message.lower()


# 9. Authentication failure
def test_authentication_failure_handling(engine, fake_provider):
    fake_provider.set_simulated_status(WebSearchStatus.AUTHENTICATION_FAILURE)
    req = WebSearchRequest(query_text="organic farming certification")
    res = engine.search(req)

    assert res.status == WebSearchStatus.AUTHENTICATION_FAILURE
    assert "authentication" in res.error_message.lower() or "key" in res.error_message.lower()


# 10. Rate-limit handling
def test_rate_limit_handling(engine, fake_provider):
    fake_provider.set_simulated_status(WebSearchStatus.RATE_LIMITED)
    req = WebSearchRequest(query_text="pm kisan scheme details")
    res = engine.search(req)

    assert res.status == WebSearchStatus.RATE_LIMITED
    assert "rate limit" in res.error_message.lower()


# 11. Provider error
def test_provider_error_handling(engine, fake_provider):
    fake_provider.set_simulated_status(WebSearchStatus.PROVIDER_ERROR)
    req = WebSearchRequest(query_text="locust attack preventive measures")
    res = engine.search(req)

    assert res.status == WebSearchStatus.PROVIDER_ERROR
    assert "error" in res.error_message.lower()


# 12. Result-limit enforcement
def test_result_limit_enforcement(engine):
    req_small = WebSearchRequest(query_text="maize fall armyworm", max_results=3)
    res_small = engine.search(req_small)
    assert len(res_small.results) == 3

    # Engine config max results check
    cfg = WebSearchConfig(max_results=4)
    eng_bounded = WebSearchEngine(config=cfg, provider=FakeWebSearchProvider())
    req_large = WebSearchRequest(query_text="maize fall armyworm", max_results=10)
    res_bounded = eng_bounded.search(req_large)
    assert len(res_bounded.results) <= 4


# 13. Provenance preservation
def test_provenance_preservation(engine):
    req = WebSearchRequest(query_text="mustard aphid spray timing")
    res = engine.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    for item in res.results:
        assert isinstance(item.provenance, dict)
        assert item.provenance.get("provider") == "fake"
        assert item.provenance.get("query") == "mustard aphid spray timing"


# 14. URL preservation
def test_url_preservation(engine):
    req = WebSearchRequest(query_text="sugarcane red rot control")
    res = engine.search(req)

    urls = [r.url for r in res.results]
    assert len(urls) > 0
    for u in urls:
        assert u.startswith("https://")
        assert "." in u


# 15. Timestamp preservation
def test_timestamp_preservation(engine):
    start_ts = time.time()
    req = WebSearchRequest(query_text="potato late blight fungicide")
    res = engine.search(req)

    for item in res.results:
        assert item.retrieval_timestamp >= start_ts
        assert item.publication_date is not None


# 16. Provider identity preservation
def test_provider_identity_preservation(engine):
    req = WebSearchRequest(query_text="paddy weedicide recommendations")
    res = engine.search(req)

    assert res.provider_name == "fake"
    for item in res.results:
        assert item.provider == "fake"


# 17. Multilingual query handling
def test_multilingual_query_handling(engine):
    # Hindi query
    req_hi = WebSearchRequest(
        query_text="गेहूं में पीला रतुआ रोग का इलाज",
        language="hi",
        request_id="req_hi_101",
    )
    res_hi = engine.search(req_hi)
    assert res_hi.status == WebSearchStatus.SUCCESS
    assert res_hi.query_text == "गेहूं में पीला रतुआ रोग का इलाज"
    assert res_hi.result_count > 0

    # Marathi query
    req_mr = WebSearchRequest(
        query_text="कापूस पिकावरील बोंड अळी नियंत्रण",
        language="mr",
        request_id="req_mr_102",
    )
    res_mr = engine.search(req_mr)
    assert res_mr.status == WebSearchStatus.SUCCESS
    assert res_mr.query_text == "कापूस पिकावरील बोंड अळी नियंत्रण"


# 18. Agricultural metadata preservation
def test_agricultural_metadata_preservation(engine):
    agri_meta = {
        "crop": "wheat",
        "disease_pest": "yellow_rust",
        "region": "Haryana",
        "season": "Rabi",
    }
    req = WebSearchRequest(
        query_text="yellow rust treatment",
        agricultural_metadata=agri_meta,
        region="Haryana",
    )
    res = engine.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    item = res.results[0]
    assert item.metadata.get("agricultural_metadata") == agri_meta
    assert item.metadata.get("region") == "Haryana"


# 19. Fake-provider execution
def test_fake_provider_execution():
    provider = FakeWebSearchProvider()
    assert provider.provider_name == "fake"
    assert provider.is_available() is True
    assert "safe_search" in provider.supported_capabilities()

    req = WebSearchRequest(query_text="soybean girdling beetle")
    res = provider.search(req)
    assert res.status == WebSearchStatus.SUCCESS
    assert len(res.results) > 0


# 20. No automatic KB publication
def test_no_automatic_kb_publication(engine):
    """
    R10 Web Search is purely a retrieval step.
    Verify that executing a search generates WebSearchResponse candidates only
    and makes NO calls or modifications to KB publication state.
    """
    req = WebSearchRequest(query_text="chickpea wilt treatment")
    res = engine.search(req)

    assert isinstance(res, WebSearchResponse)
    # Confirm output contains candidate WebSearchResult objects, not published KB items
    for item in res.results:
        assert hasattr(item, "url")
        assert not hasattr(item, "publication_state")
        assert not hasattr(item, "is_published")


# 21. No direct Qdrant access
def test_no_direct_qdrant_access(engine):
    """
    Verify WebSearchEngine does not instantiate or interact with Qdrant vector index.
    """
    with patch("modules.knowledge_base.index.qdrant_adapter.QdrantIndexAdapter") as mock_qdrant:
        req = WebSearchRequest(query_text="groundnut leaf spot advisory")
        res = engine.search(req)

        assert res.status == WebSearchStatus.SUCCESS
        mock_qdrant.assert_not_called()


# 22. Provider replacement compatibility
def test_provider_replacement_compatibility():
    custom_prov = CustomMockWebSearchProvider()
    custom_engine = WebSearchEngine(provider=custom_prov)

    req = WebSearchRequest(query_text="test replacement provider", request_id="req_custom_1")
    res = custom_engine.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    assert res.provider_name == "custom_mock"
    assert len(res.results) == 1
    assert res.results[0].title == "Custom Mock Title"


# 23. Deterministic response structure
def test_deterministic_response_structure(engine):
    req = WebSearchRequest(query_text="tomato early blight spray", request_id="req_det_1")
    res1 = engine.search(req)
    res2 = engine.search(req)

    assert res1.status == res2.status
    assert res1.result_count == res2.result_count
    assert [r.title for r in res1.results] == [r.title for r in res2.results]
    assert [r.url for r in res1.results] == [r.url for r in res2.results]


# 24. Traceability and request correlation ID
def test_traceability_and_request_correlation_id(engine):
    corr_id = "corr_trace_12345"
    req = WebSearchRequest(query_text="apple scab advisory", request_id=corr_id)
    res = engine.search(req)

    assert res.request_id == corr_id
    for item in res.results:
        assert item.request_id == corr_id
    assert "engine_latency_ms" in res.trace_info


# Test R9 RetrievalQuery bridge to R10 WebSearchRequest
def test_from_retrieval_query_bridge(engine):
    retrieval_query = RetrievalQuery(
        original_query="धान में झुलसा रोग की दवा",
        normalized_query="धान झुलसा रोग दवा",
        dense_query=DenseQuery(dense_query_text="धान झुलसा रोग दवा"),
        sparse_query=SparseQuery(sparse_query_text="धान झुलसा रोग दवा"),
        metadata=QueryMetadata(
            language="hi",
            agricultural_metadata=AgriculturalMetadata(
                crop="rice", disease_pest="blast", region="Bihar"
            ),
        ),
        top_k=10,
        request_id="req_r9_r10_bridge_101",
    )

    res = engine.search(retrieval_query)

    assert res.status == WebSearchStatus.SUCCESS
    assert res.request_id == "req_r9_r10_bridge_101"
    assert res.query_text == "धान झुलसा रोग दवा"
    assert res.result_count > 0


# Test APIWebSearchProvider with mocked HTTP response
@patch("urllib.request.urlopen")
def test_api_provider_http_success(mock_urlopen):
    mock_body = json.dumps({
        "organic_results": [
            {
                "id": "item_1",
                "title": "API Search Result Title",
                "link": "https://api.example.com/res1",
                "snippet": "API search result snippet text.",
                "date": "2025-01-15",
                "score": 0.92,
            }
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = mock_body
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    cfg = WebSearchConfig(endpoint="https://api.example.com/search", api_key="test_key")
    provider = APIWebSearchProvider(config=cfg)
    assert provider.is_available() is True

    req = WebSearchRequest(query_text="test api search", request_id="req_api_1")
    res = provider.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    assert res.result_count == 1
    assert res.results[0].title == "API Search Result Title"
    assert res.results[0].url == "https://api.example.com/res1"
    assert res.results[0].score == 0.92


# Test APIWebSearchProvider HTTP errors
@patch("urllib.request.urlopen")
def test_api_provider_http_errors(mock_urlopen):
    import urllib.error

    cfg = WebSearchConfig(endpoint="https://api.example.com/search", api_key="bad_key")
    provider = APIWebSearchProvider(config=cfg)
    req = WebSearchRequest(query_text="test error handling")

    # 401 Auth Error
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "https://api.example.com", 401, "Unauthorized", {}, None
    )
    with pytest.raises(WebSearchAuthenticationError):
        provider.search(req)

    # 429 Rate Limit
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "https://api.example.com", 429, "Too Many Requests", {}, None
    )
    with pytest.raises(WebSearchRateLimitError):
        provider.search(req)

    # 503 Unavailable
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "https://api.example.com", 503, "Service Unavailable", {}, None
    )
    with pytest.raises(WebSearchProviderUnavailableError):
        provider.search(req)


def test_engine_provider_resolution():
    cfg_fake = WebSearchConfig(provider="fake")
    eng_fake = WebSearchEngine(config=cfg_fake)
    assert isinstance(eng_fake.provider, FakeWebSearchProvider)

    cfg_api = WebSearchConfig(provider="api", endpoint="https://search.example.com")
    eng_api = WebSearchEngine(config=cfg_api)
    assert isinstance(eng_api.provider, APIWebSearchProvider)

    cfg_unknown = WebSearchConfig(provider="unsupported_provider_xyz")
    with pytest.raises(WebSearchConfigurationError):
        WebSearchEngine(config=cfg_unknown)
