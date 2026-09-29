"""Fake Web Search Provider for EarthMind Stage R10 Web Search Integration.

Provides deterministic, structured agricultural mock search results for unit testing,
development, offline execution, and error simulation.
"""

import time
from typing import Any, Dict, List, Optional
from core.errors.exceptions import (
    InvalidWebSearchRequestError,
    WebSearchAuthenticationError,
    WebSearchExecutionError,
    WebSearchProviderUnavailableError,
    WebSearchRateLimitError,
    WebSearchTimeoutError,
)
from core.interfaces.web_search import IWebSearchProvider
from core.schemas.web_search import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
    WebSearchStatus,
)


class FakeWebSearchProvider(IWebSearchProvider):
    """
    Deterministic fake provider for web search testing and fallback execution.
    Supports simulation of provider errors (unavailable, timeout, auth, rate limit, empty).
    """

    def __init__(
        self,
        simulated_status: Optional[WebSearchStatus] = None,
        simulated_delay: float = 0.0,
        available: bool = True,
    ):
        self._simulated_status = simulated_status
        self._simulated_delay = simulated_delay
        self._available = available

    @property
    def provider_name(self) -> str:
        return "fake"

    def is_available(self) -> bool:
        return self._available and self._simulated_status != WebSearchStatus.PROVIDER_UNAVAILABLE

    def supported_capabilities(self) -> Dict[str, Any]:
        return {
            "safe_search": True,
            "regional_filtering": True,
            "multilingual_queries": True,
            "agricultural_metadata_context": True,
            "max_results_limit": 50,
        }

    def set_simulated_status(self, status: Optional[WebSearchStatus]) -> None:
        """Dynamically configure simulated failure status for testing."""
        self._simulated_status = status

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        """Executes search or simulates provider error based on configuration."""
        start_time = time.perf_counter()

        # Check basic request validity
        if not request.query_text or not request.query_text.strip():
            raise InvalidWebSearchRequestError("Query text cannot be empty or blank.")

        # Simulate requested delay if set
        if self._simulated_delay > 0:
            time.sleep(self._simulated_delay)

        # Handle simulated failure modes
        if self._simulated_status == WebSearchStatus.PROVIDER_UNAVAILABLE:
            raise WebSearchProviderUnavailableError("fake", "Simulated provider offline state.")
        elif self._simulated_status == WebSearchStatus.PROVIDER_TIMEOUT:
            raise WebSearchTimeoutError("fake", request.timeout)
        elif self._simulated_status == WebSearchStatus.AUTHENTICATION_FAILURE:
            raise WebSearchAuthenticationError("fake", "Simulated invalid API key or credentials.")
        elif self._simulated_status == WebSearchStatus.RATE_LIMITED:
            raise WebSearchRateLimitError("fake", "Simulated 429 rate limit exceeded.")
        elif self._simulated_status == WebSearchStatus.PROVIDER_ERROR:
            raise WebSearchExecutionError("fake", "Simulated provider internal error.")
        elif self._simulated_status == WebSearchStatus.EMPTY_RESULT:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                request_id=request.request_id,
                status=WebSearchStatus.EMPTY_RESULT,
                query_text=request.query_text,
                results=[],
                result_count=0,
                provider_name=self.provider_name,
                execution_time_ms=elapsed_ms,
                trace_info={"provider": self.provider_name, "simulated": True},
            )

        # Generate deterministic mock results
        mock_results = self._generate_mock_results(request)

        # Apply result limit requested
        limit = min(request.max_results, 50)
        final_results = mock_results[:limit]

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return WebSearchResponse(
            request_id=request.request_id,
            status=WebSearchStatus.SUCCESS,
            query_text=request.query_text,
            results=final_results,
            result_count=len(final_results),
            provider_name=self.provider_name,
            execution_time_ms=elapsed_ms,
            trace_info={
                "provider": self.provider_name,
                "simulated": True,
                "requested_max_results": request.max_results,
                "language": request.language,
                "region": request.region,
            },
        )

    def _generate_mock_results(self, request: WebSearchRequest) -> List[WebSearchResult]:
        """Builds realistic agricultural search candidates matching query & metadata."""
        query = request.query_text
        lang = request.language or "en"
        agri_meta = request.agricultural_metadata or {}
        crop = agri_meta.get("crop", "crop")
        disease = agri_meta.get("disease_pest", "pest")
        region = request.region or agri_meta.get("region", "India")

        now_ts = time.time()

        raw_candidates = [
            {
                "title": f"ICAR Advisory on {crop.capitalize()} Management in {region}",
                "url": f"https://icar.org.in/advisory/{crop}-management-{region.lower().replace(' ', '-')}",
                "snippet": f"Official ICAR recommendations for managing {crop} health, preventing {disease}, and improving yield under current seasonal conditions in {region}.",
                "source": "icar.org.in",
                "pub_date": "2025-01-10T08:00:00Z",
                "score": 0.95,
            },
            {
                "title": f"KVK Farmer Bulletin: {query}",
                "url": f"https://kvk.agricoop.gov.in/bulletins/{query.lower().replace(' ', '-')}",
                "snippet": f"Krishi Vigyan Kendra extension advisory regarding {query}. Details dosage, application timing, and soil precautions.",
                "source": "agricoop.gov.in",
                "pub_date": "2025-01-20T11:15:00Z",
                "score": 0.89,
            },
            {
                "title": f"Agricultural Portal Update on {crop} Diseases",
                "url": f"https://agriportal.in/news/{crop}-{disease}",
                "snippet": f"Recent field reports and expert insights on treating {disease} in {crop} across agricultural zones.",
                "source": "agriportal.in",
                "pub_date": "2025-02-01T14:30:00Z",
                "score": 0.82,
            },
            {
                "title": f"State Department of Agriculture Guidance for {region}",
                "url": f"https://agri.{region.lower().replace(' ', '')}.gov.in/guidelines",
                "snippet": f"Government subsidy programs, certified seed sources, and crop care instructions for farmers in {region}.",
                "source": f"agri.{region.lower().replace(' ', '')}.gov.in",
                "pub_date": "2025-02-05T09:00:00Z",
                "score": 0.78,
            },
            {
                "title": f"Research Article: Best Practices for {crop} Cultivation",
                "url": f"https://journal.agriscience.org/articles/{crop}-best-practices",
                "snippet": f"Peer-reviewed study analyzing yield outcomes and integrated pest management strategies for {crop} farming.",
                "source": "agriscience.org",
                "pub_date": "2024-12-15T16:00:00Z",
                "score": 0.72,
            },
        ]

        results: List[WebSearchResult] = []
        for idx, item in enumerate(raw_candidates, start=1):
            res_id = f"fake_web_{idx}_{hash(query) & 0xffff}"
            results.append(
                WebSearchResult(
                    result_id=res_id,
                    title=item["title"],
                    url=item["url"],
                    snippet=item["snippet"],
                    source=item["source"],
                    publication_date=item["pub_date"],
                    last_updated_date=item["pub_date"],
                    provider=self.provider_name,
                    retrieval_timestamp=now_ts,
                    rank=idx,
                    score=item["score"],
                    content=f"Full extract of article from {item['source']}: {item['snippet']}",
                    provenance={
                        "provider": self.provider_name,
                        "query": query,
                        "retrieval_timestamp": now_ts,
                        "language": lang,
                    },
                    metadata={
                        "language": lang,
                        "region": region,
                        "agricultural_metadata": agri_meta,
                    },
                    request_id=request.request_id,
                )
            )

        return results
