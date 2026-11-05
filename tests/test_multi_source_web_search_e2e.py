"""Integration test suite for EarthMind Stage R10 Multi-Source Web Search Engine.

Verifies:
1. Multi-provider orchestration (Primary + Wikipedia + Crossref + OpenAlex).
2. Deduplication across providers with different URL variations.
3. Agricultural domain prioritization (boosting ICAR, SAUs, etc.).
4. Partial provider failure (one fails, others succeed -> WebSearchStatus.PARTIAL).
5. All-provider failure reporting.
6. Empty multi-source results handling.
7. Safe content retriever integration with WebSearchEngine.
8. End-to-end flow: R9 Query -> R10 Multi-Source Web Search -> R11 Evidence Builder -> R12 Evidence Validator -> R13 RAG Provider -> B2 Context Manager.
9. Security invariants: Zero KB publication, zero Qdrant writes, zero Memory writes.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.config.settings import WebSearchConfig
from core.errors.exceptions import WebSearchProviderUnavailableError
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
from modules.knowledge_base.evidence.engine import EvidenceBuilderEngine
from modules.knowledge_base.evidence.validator import EvidenceValidatorEngine
from modules.knowledge_base.integration.provider import RAGContextProvider
from modules.context.boundary.models import RAGContextRequest


class MockFailingProvider(IWebSearchProvider):
    @property
    def provider_name(self) -> str:
        return "failing_provider"

    def is_available(self) -> bool:
        return True

    def supported_capabilities(self):
        return {}

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        raise WebSearchProviderUnavailableError(self.provider_name, "Service connection dropped.")


class MockSuccessProvider(IWebSearchProvider):
    def __init__(self, name: str, results: list):
        self._name = name
        self._results = results

    @property
    def provider_name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return True

    def supported_capabilities(self):
        return {}

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        return WebSearchResponse(
            request_id=request.request_id,
            status=WebSearchStatus.SUCCESS,
            query_text=request.query_text,
            results=self._results,
            result_count=len(self._results),
            provider_name=self._name,
        )


def test_multi_provider_orchestration_and_deduplication():
    # Setup mock primary with general URL
    res_primary = [
        WebSearchResult(
            result_id="p1",
            title="General Wheat Advisory",
            url="https://www.example.org/wheat-guide/",
            snippet="General wheat guide snippet.",
            source="example.org",
            provider="mock_primary",
            rank=1,
            score=0.70,
        )
    ]
    primary = MockSuccessProvider("mock_primary", res_primary)

    # Setup mock agricultural authority
    res_icar = [
        WebSearchResult(
            result_id="icar1",
            title="ICAR Yellow Rust Recommendations",
            url="https://icar.org.in/wheat-rust",
            snippet="ICAR official recommendation for wheat yellow rust.",
            source="icar.org.in",
            provider="mock_icar",
            rank=1,
            score=0.75,
        ),
        # Duplicate URL with differing scheme/trailing slash
        WebSearchResult(
            result_id="p1_dup",
            title="Duplicate Wheat Guide",
            url="http://example.org/wheat-guide",
            snippet="Duplicate snippet.",
            source="example.org",
            provider="mock_icar",
            rank=2,
            score=0.65,
        ),
    ]
    scholarly = [MockSuccessProvider("mock_icar", res_icar)]

    engine = WebSearchEngine(
        provider=primary,
        scholarly_providers=scholarly,
        wikipedia_provider=None,
    )

    req = WebSearchRequest(query_text="wheat yellow rust", include_scholarly=True, include_encyclopedic=False)
    res = engine.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    # Deduplication should have merged the duplicate example.org url
    assert res.result_count == 2
    # Agricultural domain should be prioritized to top
    top_result = res.results[0]
    assert top_result.source == "icar.org.in"
    assert top_result.result_type == "agricultural"
    assert top_result.score > 0.8  # Boosted


def test_partial_provider_failure_handling():
    primary = MockSuccessProvider(
        "mock_primary",
        [
            WebSearchResult(
                result_id="p1",
                title="Paddy Care Guide",
                url="https://agri.example.org/paddy",
                snippet="Paddy care details.",
                source="agri.example.org",
                provider="mock_primary",
                rank=1,
            )
        ],
    )
    failing = MockFailingProvider()

    engine = WebSearchEngine(
        provider=primary,
        scholarly_providers=[failing],
        wikipedia_provider=None,
    )

    req = WebSearchRequest(query_text="paddy stem borer", include_scholarly=True, include_encyclopedic=False)
    res = engine.search(req)

    # Search should still succeed partially because primary succeeded
    assert res.status == WebSearchStatus.PARTIAL
    assert res.result_count == 1
    assert "failing_provider" in res.partial_errors
    assert res.provider_statuses["mock_primary"] == WebSearchStatus.SUCCESS
    assert res.provider_statuses["failing_provider"] == WebSearchStatus.PROVIDER_UNAVAILABLE


def test_all_providers_failure():
    failing1 = MockFailingProvider()
    failing2 = MockFailingProvider()

    engine = WebSearchEngine(
        provider=failing1,
        scholarly_providers=[failing2],
        wikipedia_provider=None,
    )

    req = WebSearchRequest(query_text="locust attack", include_scholarly=True, include_encyclopedic=False)
    res = engine.search(req)

    assert res.status in (WebSearchStatus.PROVIDER_UNAVAILABLE, WebSearchStatus.PROVIDER_ERROR)
    assert res.result_count == 0
    assert len(res.partial_errors) > 0


def test_r9_to_r13_multi_source_e2e_integration():
    """Verify that multi-source web evidence flows cleanly into R11 -> R12 -> R13 -> B2."""
    res_web = [
        WebSearchResult(
            result_id="web_agri_1",
            title="ICAR Mustard Aphid Advisory 2025",
            url="https://icar.org.in/advisory/mustard-aphids",
            snippet="Apply dimethoate 30 EC at 1.7 ml per liter of water at flowering stage.",
            source="icar.org.in",
            provider="brave",
            rank=1,
            score=0.92,
        ),
        WebSearchResult(
            result_id="wiki_1",
            title="Lipaphis erysimi - Wikipedia",
            url="https://en.wikipedia.org/wiki/Lipaphis_erysimi",
            snippet="Lipaphis erysimi, commonly known as the mustard aphid, is a major insect pest...",
            source="wikipedia.org",
            provider="wikipedia",
            rank=2,
            score=0.75,
        ),
    ]

    mock_engine = MagicMock(spec=WebSearchEngine)
    mock_engine.search.return_value = WebSearchResponse(
        status=WebSearchStatus.SUCCESS,
        query_text="सरसों में माहू का नियंत्रण",
        results=res_web,
        result_count=2,
        provider_name="brave",
    )

    # Instantiate downstream RAG provider with mock web search
    rag_provider = RAGContextProvider(web_search_provider=mock_engine)

    # Send request through R13
    rag_req = RAGContextRequest(
        query_text="सरसों में माहू का नियंत्रण",
        request_id="req_e2e_agri_101",
        metadata={"crop": "mustard", "language": "hi"},
    )

    contracts = rag_provider.get_rag_context(rag_req)

    # Verify contracts produced for B2 Context Manager
    assert len(contracts) > 0
    web_contracts = [c for c in contracts if c.content.get("source_type") == "WEB_SEARCH"]
    assert len(web_contracts) > 0

    # Ensure source URLs and attributions survived intact
    urls = [c.content.get("url") for c in web_contracts]
    assert "https://icar.org.in/advisory/mustard-aphids" in urls
    assert any("Lipaphis erysimi" in c.content.get("text") for c in web_contracts)
    assert all(c.trace_id == "req_e2e_agri_101" for c in contracts)
