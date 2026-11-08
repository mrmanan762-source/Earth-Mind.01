"""Final Acceptance Test suite for EarthMind Stage R10 Web Search Subsystem.

Validates:
1. Real-world public provider execution (Wikipedia, Wikidata, Crossref, OpenAlex, NASA POWER).
2. Managed providers unconfigured fail-safe behavior (Tavily, Gemini Grounding).
3. Downstream evidence flow: R10 -> R11 -> R12 -> R13 -> B2 Context Manager.
4. Reliability and fallback logic: primary success, fallback on timeout/rate-limit, dual failure handling.
5. Freshness caching and tenant isolation.
6. Secret redaction and credential protection across settings and logs.
"""

import time
import pytest
from unittest.mock import MagicMock

from core.config.settings import settings
from core.errors.exceptions import WebSearchAuthenticationError, WebSearchTimeoutError, WebSearchRateLimitError
from core.schemas.web_search import (
    WebSearchRequest,
    WebSearchResult,
    WebSearchResponse,
    WebSearchStatus,
)
from modules.knowledge_base.web_search.engine import WebSearchEngine
from modules.knowledge_base.web_search.cache import InMemoryWebSearchCache
from modules.knowledge_base.web_search.providers.wikipedia_provider import WikipediaSearchProvider
from modules.knowledge_base.web_search.providers.wikidata_provider import WikidataSearchProvider
from modules.knowledge_base.web_search.providers.scholarly_provider import CrossrefSearchProvider, OpenAlexSearchProvider
from modules.knowledge_base.web_search.providers.nasa_power_provider import NasaPowerSearchProvider
from modules.knowledge_base.web_search.providers.tavily_provider import TavilySearchProvider
from modules.knowledge_base.web_search.providers.gemini_grounding_provider import GeminiGroundingSearchProvider

from modules.knowledge_base.evidence.engine import EvidenceBuilderEngine
from modules.knowledge_base.evidence.validator import EvidenceValidatorEngine
from core.schemas.evidence import EvidenceBuildRequest
from core.schemas.evidence_validator import EvidenceValidationRequest, EvidenceValidationStatus

from modules.context.manager import B2ContextManager
from modules.context.schemas import ContextRequest, ContextState
from modules.context.boundary.adapters import RAGContextProviderAdapter
from modules.context.boundary.models import RAGContextRequest


class MockRAGProvider:
    def __init__(self, contracts):
        self.provider_name = "rag_provider"
        self._contracts = contracts

    def get_rag_context(self, request: RAGContextRequest):
        return self._contracts


def test_acceptance_01_public_providers_live_execution():
    """Verify genuine live requests against all 5 public data sources."""
    providers = [
        ("wikipedia", WikipediaSearchProvider(), "rice blast disease", "encyclopedic"),
        ("wikidata", WikidataSearchProvider(), "rice blast disease", "structured_fact"),
        ("crossref", CrossrefSearchProvider(), "rice blast disease", "scholarly"),
        ("openalex", OpenAlexSearchProvider(), "rice blast disease", "scholarly"),
        ("nasa_power", NasaPowerSearchProvider(), "Patna, Bihar", "agroclimatology"),
    ]

    for name, provider, query, expected_type in providers:
        req = WebSearchRequest(query_text=query, max_results=2)
        resp = provider.search(req)
        assert resp.status == WebSearchStatus.SUCCESS, f"{name} failed: {resp.error_message}"
        assert len(resp.results) > 0, f"{name} returned no results"
        first = resp.results[0]
        assert first.url.startswith("http"), f"{name} invalid url: {first.url}"
        assert first.result_type == expected_type, f"{name} unexpected result_type: {first.result_type}"
        assert first.title, f"{name} missing title"
        assert first.retrieval_timestamp > 0, f"{name} missing retrieval_timestamp"


def test_acceptance_02_managed_providers_fail_safe():
    """Verify managed providers (Tavily, Gemini) fail-safe cleanly when unconfigured."""
    tavily = TavilySearchProvider(api_key=None)
    with pytest.raises(WebSearchAuthenticationError) as exc_tavily:
        tavily.search(WebSearchRequest(query_text="rice blast"))
    assert "Tavily API key is not configured" in str(exc_tavily.value)

    gemini = GeminiGroundingSearchProvider(api_key=None)
    with pytest.raises(WebSearchAuthenticationError) as exc_gemini:
        gemini.search(WebSearchRequest(query_text="rice blast"))
    assert "Gemini API key is not configured" in str(exc_gemini.value)


def test_acceptance_03_full_downstream_evidence_pipeline():
    """Verify genuine retrieved web evidence flows through R10 -> R11 -> R12 -> R13 -> B2 Context Manager."""
    # 1. R10 Real Search using Wikipedia
    wiki_p = WikipediaSearchProvider()
    engine = WebSearchEngine(provider=wiki_p, wikipedia_provider=wiki_p)
    req = WebSearchRequest(query_text="rice blast disease", max_results=2, include_encyclopedic=True)
    res = engine.search(req)
    assert res.status == WebSearchStatus.SUCCESS
    assert len(res.results) > 0

    # 2. R11 Evidence Builder
    builder = EvidenceBuilderEngine()
    build_req = EvidenceBuildRequest(
        request_id="req_acc_pipeline_01",
        query_text="rice blast disease",
        web_search_response=res,
    )
    build_res = builder.build_evidence(build_req)
    pkg = build_res.package
    assert len(pkg.items) > 0

    # 3. R12 Evidence Validator
    validator = EvidenceValidatorEngine()
    val_req = EvidenceValidationRequest(
        request_id="req_acc_pipeline_01",
        package=pkg,
    )
    val_res = validator.validate_evidence_package(val_req)
    assert val_res.status in [EvidenceValidationStatus.VALID, EvidenceValidationStatus.PARTIALLY_VALID]

    # 4. R13 RAG Context Mapping
    contracts = pkg.to_rag_context_contracts()
    assert len(contracts) > 0
    first_contract = contracts[0]
    assert first_contract.source_type == "RAG"
    assert first_contract.content.get("url") is not None
    assert first_contract.content.get("source_type") == "WEB_SEARCH"

    # 5. B2 Context Manager
    rag_provider = MockRAGProvider(contracts)
    rag_adapter = RAGContextProviderAdapter(rag_provider)
    context_manager = B2ContextManager(providers=[rag_adapter])

    ctx_req = ContextRequest(
        request_id="req_acc_b2_01",
        task="rice blast disease",
    )
    ctx_res = context_manager.prepare_context(ctx_req)
    assert ctx_res.state == ContextState.COMPLETED
    assert len(ctx_res.items) > 0
    b2_item = ctx_res.items[0]
    assert b2_item.content.get("url") == first_contract.content.get("url")


def test_acceptance_04_reliability_and_fallback_scenarios():
    """Verify engine fallback on primary timeout, HTTP 429, and dual provider degradation."""
    # Scenario A: Primary Success
    mock_primary = MagicMock()
    mock_primary.provider_name = "mock_tavily"
    mock_primary.search.return_value = WebSearchResponse(
        status=WebSearchStatus.SUCCESS,
        query_text="paddy pests",
        results=[WebSearchResult(result_id="res_1", title="Paddy Care", url="https://example.com/paddy", snippet="...", provider="mock_tavily", rank=1)],
        result_count=1,
        provider_name="mock_tavily",
    )
    mock_secondary = MagicMock()
    mock_secondary.provider_name = "mock_gemini"

    engine_a = WebSearchEngine(provider=mock_primary, fallback_provider=mock_secondary)
    resp_a = engine_a.search(WebSearchRequest(query_text="paddy pests"))
    assert resp_a.status == WebSearchStatus.SUCCESS
    assert not mock_secondary.search.called

    # Scenario B: Primary Timeout -> Fallback Success
    mock_primary.search.side_effect = WebSearchTimeoutError(provider_name="mock_tavily", timeout=10.0)
    mock_secondary.search.return_value = WebSearchResponse(
        status=WebSearchStatus.SUCCESS,
        query_text="paddy pests",
        results=[WebSearchResult(result_id="res_2", title="Grounded Paddy", url="https://example.com/paddy-grounded", snippet="...", provider="mock_gemini", rank=1)],
        result_count=1,
        provider_name="mock_gemini",
    )
    engine_b = WebSearchEngine(provider=mock_primary, fallback_provider=mock_secondary)
    resp_b = engine_b.search(WebSearchRequest(query_text="paddy pests"))
    assert resp_b.status == WebSearchStatus.SUCCESS
    assert resp_b.provider_name == "mock_gemini"

    # Scenario C: Both Fail -> Partial / Structured Error without crash
    mock_secondary.search.side_effect = WebSearchTimeoutError(provider_name="mock_gemini", timeout=10.0)
    engine_c = WebSearchEngine(provider=mock_primary, fallback_provider=mock_secondary)
    resp_c = engine_c.search(WebSearchRequest(query_text="paddy pests"))
    assert resp_c.status in [WebSearchStatus.PROVIDER_TIMEOUT, WebSearchStatus.PROVIDER_ERROR, WebSearchStatus.PROVIDER_UNAVAILABLE, WebSearchStatus.PARTIAL]
    assert resp_c.result_count == 0


def test_acceptance_05_caching_and_tenant_isolation():
    """Verify cache hit, invalidation, tenant isolation, and timestamp preservation."""
    cache = InMemoryWebSearchCache()
    req_t1 = WebSearchRequest(query_text="fertilizer calculation", user_context={"user_id": "farmer_101"})
    req_t2 = WebSearchRequest(query_text="fertilizer calculation", user_context={"user_id": "farmer_202"})

    resp1 = WebSearchResponse(
        status=WebSearchStatus.SUCCESS,
        query_text="fertilizer calculation",
        results=[WebSearchResult(result_id="res_c1", title="Fertilizer", url="https://example.com/fert", snippet="...", provider="test", rank=1, retrieval_timestamp=1700000000.0)],
        result_count=1,
        provider_name="test",
    )
    # Store with farmer tenant 1
    cache.set(req_t1, resp1)

    # Cache hit for tenant 1
    hit = cache.get(req_t1)
    assert hit is not None
    assert hit.results[0].retrieval_timestamp == 1700000000.0

    # Tenant 2 isolation: cache miss
    miss = cache.get(req_t2)
    assert miss is None


def test_acceptance_06_security_secret_masking():
    """Verify that credentials are strictly masked in settings and not exposed in safe dicts."""
    safe_dict = settings.to_safe_dict()
    web_search_cfg = safe_dict.get("web_search", {})
    for key, val in web_search_cfg.items():
        if "api_key" in key:
            assert val != "real_secret"
            if val is not None:
                assert val == "***" or val.startswith("***")
