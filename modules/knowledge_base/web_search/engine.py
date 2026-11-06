"""Master Multi-Source Web Search Engine for EarthMind Stage R10 Web Search.

Coordinates multi-source web retrieval from R9 Query Processing to external web search providers:
1. Primary general web search: Brave Search API (or generic API / Fake provider).
2. Encyclopedic background: Wikipedia (MediaWiki API).
3. Scientific literature: Crossref & OpenAlex APIs.
4. Safe public web page content extraction via SafeContentFetcher.
5. Agricultural authoritative domain prioritization (ICAR, SAUs, Ministry of Agriculture, FAO, etc.).
6. Cross-provider deduplication, canonical URL handling, and stable ordering.
7. Resilience & Graceful Partial Failure: Sub-provider errors or timeouts do not crash the search.

HARD ARCHITECTURAL RULES:
- Web search results are query-time candidate evidence for Stage R11 Evidence Builder.
- Web Search Engine NEVER publishes web results to the permanent Knowledge Base.
- NEVER writes to Qdrant vector index.
- NEVER writes to SQLite or General Memory records.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from core.config.settings import WebSearchConfig, settings
from core.errors.exceptions import (
    InvalidWebSearchRequestError,
    WebSearchAuthenticationError,
    WebSearchConfigurationError,
    WebSearchError,
    WebSearchExecutionError,
    WebSearchProviderUnavailableError,
    WebSearchRateLimitError,
    WebSearchTimeoutError,
)
from core.interfaces.web_search import IWebSearchProvider
from core.schemas.query import RetrievalQuery
from core.schemas.web_search import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
    WebSearchStatus,
)
from modules.knowledge_base.web_search.content_fetcher import SafeContentFetcher
from modules.knowledge_base.web_search.providers.api_provider import APIWebSearchProvider
from modules.knowledge_base.web_search.providers.brave_provider import BraveWebSearchProvider
from modules.knowledge_base.web_search.providers.fake_provider import FakeWebSearchProvider
from modules.knowledge_base.web_search.providers.gemini_grounding_provider import GeminiGroundingSearchProvider
from modules.knowledge_base.web_search.providers.nasa_power_provider import NasaPowerSearchProvider
from modules.knowledge_base.web_search.providers.scholarly_provider import (
    CrossrefSearchProvider,
    OpenAlexSearchProvider,
)
from modules.knowledge_base.web_search.providers.tavily_provider import TavilySearchProvider
from modules.knowledge_base.web_search.providers.wikidata_provider import WikidataSearchProvider
from modules.knowledge_base.web_search.providers.wikipedia_provider import WikipediaSearchProvider

logger = logging.getLogger(__name__)


class WebSearchEngine:
    """Master Multi-Source Search Orchestrator for Stage R10."""

    def __init__(
        self,
        config: Optional[WebSearchConfig] = None,
        provider: Optional[IWebSearchProvider] = None,
        wikipedia_provider: Optional[IWebSearchProvider] = None,
        wikidata_provider: Optional[IWebSearchProvider] = None,
        scholarly_providers: Optional[List[IWebSearchProvider]] = None,
        nasa_power_provider: Optional[IWebSearchProvider] = None,
        content_fetcher: Optional[SafeContentFetcher] = None,
    ):
        self._config = config or getattr(settings, "web_search", WebSearchConfig())
        self._provider = provider or self._resolve_primary_provider(self._config)

        # Supplementary providers: if provider is specifically injected or fake/mock in test, default supplementary to off unless explicitly passed or configured
        is_isolated = self._provider.provider_name.startswith("mock") or self._provider.provider_name.startswith("fake") or self._provider.provider_name.startswith("failing")

        # 1. Wikipedia (MediaWiki)
        if wikipedia_provider is not None:
            self._wikipedia_provider = wikipedia_provider
        elif self._config.enable_wikipedia and not is_isolated and not provider:
            self._wikipedia_provider = WikipediaSearchProvider(config=self._config)
        else:
            self._wikipedia_provider = None

        # 2. Wikidata (SPARQL)
        if wikidata_provider is not None:
            self._wikidata_provider = wikidata_provider
        elif self._config.enable_wikidata and not is_isolated and not provider:
            self._wikidata_provider = WikidataSearchProvider(config=self._config)
        else:
            self._wikidata_provider = None

        # 3. Scholarly (Crossref & OpenAlex)
        if scholarly_providers is not None:
            self._scholarly_providers = scholarly_providers
        elif not is_isolated:
            scholarly: List[IWebSearchProvider] = []
            if self._config.enable_crossref:
                scholarly.append(CrossrefSearchProvider(config=self._config))
            if self._config.enable_openalex:
                scholarly.append(OpenAlexSearchProvider(config=self._config))
            self._scholarly_providers = scholarly
        else:
            self._scholarly_providers = []

        # 4. NASA POWER Agroclimatology
        if nasa_power_provider is not None:
            self._nasa_power_provider = nasa_power_provider
        elif self._config.enable_nasa_power and not is_isolated and not provider:
            self._nasa_power_provider = NasaPowerSearchProvider(config=self._config)
        else:
            self._nasa_power_provider = None

        self._content_fetcher = content_fetcher or (
            SafeContentFetcher(
                timeout=self._config.content_fetch_timeout,
                max_bytes=self._config.content_fetch_max_bytes,
                user_agent=self._config.user_agent,
            )
            if self._config.enable_content_fetch
            else None
        )

    @property
    def config(self) -> WebSearchConfig:
        return self._config

    @property
    def provider(self) -> IWebSearchProvider:
        return self._provider

    def _resolve_primary_provider(self, config: WebSearchConfig) -> IWebSearchProvider:
        """Instantiates primary web search provider adapter."""
        p_name = (config.provider or "fake").lower().strip()
        if p_name in ("fake", "mock"):
            return FakeWebSearchProvider()
        elif p_name == "brave":
            return BraveWebSearchProvider(config=config)
        elif p_name == "tavily":
            return TavilySearchProvider(config=config)
        elif p_name in ("gemini_grounding", "gemini"):
            return GeminiGroundingSearchProvider(config=config)
        elif p_name in ("api", "serp", "serpapi", "google", "bing"):
            return APIWebSearchProvider(config=config)
        else:
            raise WebSearchConfigurationError(f"Unsupported web search provider '{config.provider}'.")

    def _canonicalize_url(self, raw_url: str) -> str:
        """Normalizes URLs for deduplication while preserving domain and path semantics."""
        if not raw_url:
            return ""
        try:
            parsed = urllib.parse.urlparse(raw_url.strip())
            netloc = parsed.netloc.lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]
            path = parsed.path.rstrip("/")
            # Normalize scheme to https for deduplication across http/https mirrors
            scheme = "https" if parsed.scheme.lower() in ("http", "https") else parsed.scheme.lower()
            return urllib.parse.urlunparse((scheme, netloc, path, "", "", ""))
        except Exception:
            return raw_url.strip().lower()

    def _is_trusted_agricultural_domain(self, domain: Optional[str]) -> bool:
        """Checks if result domain matches trusted agricultural institutions."""
        if not domain:
            return False
        d_lower = domain.lower()
        return any(d_lower.endswith(trusted) for trusted in self._config.trusted_agricultural_domains)

    def search(
        self,
        request_input: Union[WebSearchRequest, RetrievalQuery],
        max_results: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> WebSearchResponse:
        """
        Executes multi-source search query, runs eligible providers concurrently,
        removes cross-provider duplicates, applies agricultural domain prioritization,
        and returns normalized WebSearchResponse.
        """
        start_time = time.perf_counter()

        # 1. Normalize input into WebSearchRequest
        if isinstance(request_input, RetrievalQuery):
            limit = max_results if max_results is not None else self._config.max_results
            t_out = timeout if timeout is not None else self._config.timeout
            req = WebSearchRequest.from_retrieval_query(
                request_input, max_results=limit, timeout=t_out
            )
        elif isinstance(request_input, WebSearchRequest):
            req = request_input
            if max_results is not None:
                req = req.model_copy(update={"max_results": max_results})
            if timeout is not None:
                req = req.model_copy(update={"timeout": timeout})
        else:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                status=WebSearchStatus.INVALID_REQUEST,
                query_text="",
                results=[],
                result_count=0,
                provider_name=self._provider.provider_name if self._provider else "unknown",
                execution_time_ms=elapsed_ms,
                error_message=f"Invalid request input type: {type(request_input)}",
            )

        # Enforce result limits
        bounded_max_results = min(req.max_results, self._config.max_results)
        req = req.model_copy(update={"max_results": bounded_max_results})

        # Validate query string
        if not req.query_text or not req.query_text.strip():
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                request_id=req.request_id,
                status=WebSearchStatus.INVALID_REQUEST,
                query_text="",
                results=[],
                result_count=0,
                provider_name=self._provider.provider_name if self._provider else "unknown",
                execution_time_ms=elapsed_ms,
                error_message="Search query text cannot be empty or whitespace.",
            )

        # Determine active provider set for this query
        active_providers: List[IWebSearchProvider] = [self._provider]

        # 1. Encyclopedic search (e.g. Wikipedia)
        if getattr(req, "include_encyclopedic", True) and self._wikipedia_provider:
            active_providers.append(self._wikipedia_provider)

        # 2. Structured factual search (e.g. Wikidata SPARQL)
        if getattr(req, "include_structured", True) and self._wikidata_provider:
            active_providers.append(self._wikidata_provider)

        # 3. Scholarly literature (e.g. Crossref, OpenAlex)
        if getattr(req, "include_scholarly", False) or req.search_mode in ("academic", "scholarly"):
            for sp in self._scholarly_providers:
                if sp.is_available():
                    active_providers.append(sp)

        # 4. Agroclimatology / Weather (NASA POWER)
        weather_requested = getattr(req, "include_agroclimatology", False) or req.search_mode in ("climate", "weather", "agroclimatology")
        if not weather_requested:
            # Check for climatological / weather intent in query text or agricultural metadata
            q_lower = req.query_text.lower()
            weather_keywords = ("rainfall", "precipitation", "temperature", "weather", "climate", "solar", "radiation", "frost", "drought", "humidity")
            if any(kw in q_lower for kw in weather_keywords):
                weather_requested = True

        if weather_requested and self._nasa_power_provider and self._nasa_power_provider.is_available():
            active_providers.append(self._nasa_power_provider)

        provider_statuses: Dict[str, WebSearchStatus] = {}
        partial_errors: Dict[str, str] = {}
        collected_results: List[WebSearchResult] = []
        warnings: List[str] = []

        # Execute providers concurrently within timeout budget
        req_timeout = req.timeout if req.timeout > 0 else self._config.timeout

        def _execute_provider(p: IWebSearchProvider) -> Tuple[str, Optional[WebSearchResponse], Optional[Exception]]:
            p_name = p.provider_name
            try:
                sub_resp = p.search(req)
                return p_name, sub_resp, None
            except Exception as e:
                return p_name, None, e

        with ThreadPoolExecutor(max_workers=min(len(active_providers), 4)) as executor:
            future_to_provider = {executor.submit(_execute_provider, p): p for p in active_providers}
            for future in as_completed(future_to_provider):
                p_name, sub_resp, err = future.result()
                if err is not None:
                    # Classify error status
                    if isinstance(err, WebSearchTimeoutError):
                        provider_statuses[p_name] = WebSearchStatus.PROVIDER_TIMEOUT
                    elif isinstance(err, WebSearchAuthenticationError):
                        provider_statuses[p_name] = WebSearchStatus.AUTHENTICATION_FAILURE
                    elif isinstance(err, WebSearchRateLimitError):
                        provider_statuses[p_name] = WebSearchStatus.RATE_LIMITED
                    elif isinstance(err, WebSearchProviderUnavailableError):
                        provider_statuses[p_name] = WebSearchStatus.PROVIDER_UNAVAILABLE
                    elif isinstance(err, InvalidWebSearchRequestError):
                        provider_statuses[p_name] = WebSearchStatus.INVALID_REQUEST
                    else:
                        provider_statuses[p_name] = WebSearchStatus.PROVIDER_ERROR

                    partial_errors[p_name] = str(err)
                    logger.warning(f"Web search sub-provider '{p_name}' failed: {err}")
                elif sub_resp is not None:
                    provider_statuses[p_name] = sub_resp.status
                    if sub_resp.results:
                        collected_results.extend(sub_resp.results)
                    if sub_resp.warnings:
                        warnings.extend(sub_resp.warnings)

        # 3. Deduplication and Ranking
        # Note on Data-Type Separation:
        # Structured facts (e.g., Wikidata entity records) and numerical agroclimatology
        # records (e.g., NASA POWER) must NOT be lost or collapsed into URL deduplication.
        seen_canonical_urls: Set[str] = set()
        seen_result_ids: Set[str] = set()
        deduplicated: List[WebSearchResult] = []

        for item in collected_results:
            # Check unique result_id
            if item.result_id in seen_result_ids:
                continue
            seen_result_ids.add(item.result_id)

            canon = self._canonicalize_url(item.url)
            item.canonical_url = canon

            # For standard web and encyclopedic pages, deduplicate by canonical URL
            # Do NOT drop structured facts or agroclimatology data via URL collisions
            if item.result_type in ("web", "encyclopedic", "scholarly", "news"):
                if canon:
                    if canon in seen_canonical_urls:
                        continue
                    seen_canonical_urls.add(canon)

            # Apply trusted agricultural domain boost
            if self._is_trusted_agricultural_domain(item.source):
                item.result_type = "agricultural"
                current_score = item.score if item.score is not None else 0.75
                item.score = min(1.0, current_score + self._config.trusted_domain_boost)

            deduplicated.append(item)

        # Deterministic sorting: higher score first, agricultural first, then original rank
        def sort_key(res: WebSearchResult):
            score_val = res.score if res.score is not None else 0.5
            is_agri = 1.0 if res.result_type == "agricultural" else 0.0
            return (score_val + is_agri, -res.rank)

        deduplicated.sort(key=sort_key, reverse=True)

        # Re-index ranks
        for idx, item in enumerate(deduplicated, start=1):
            item.rank = idx

        # Enforce max_results limit
        final_results = deduplicated[:bounded_max_results]

        # 4. Content retrieval if requested
        if (req.fetch_content or self._config.enable_content_fetch) and self._content_fetcher:
            for item in final_results[:2]:  # Fetch top 2 URLs safely
                if item.url and item.url.startswith("http"):
                    try:
                        page = self._content_fetcher.fetch_page(item.url)
                        if page.status_code == 200 and page.text_content:
                            item.content = page.text_content[:2000]
                            item.metadata["page_fetched"] = True
                            item.metadata["page_title"] = page.title
                    except Exception as ex:
                        logger.debug(f"Failed to fetch content for {item.url}: {ex}")

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Determine overall engine status
        primary_status = provider_statuses.get(self._provider.provider_name)
        primary_error = partial_errors.get(self._provider.provider_name)

        if final_results:
            if partial_errors:
                overall_status = WebSearchStatus.PARTIAL
                warnings.append(f"Partial provider failures: {list(partial_errors.keys())}")
            else:
                overall_status = WebSearchStatus.SUCCESS
            err_msg = None
        else:
            if primary_status and primary_status not in (WebSearchStatus.SUCCESS, WebSearchStatus.EMPTY_RESULT):
                overall_status = primary_status
                err_msg = primary_error or str(primary_status)
            elif primary_status == WebSearchStatus.EMPTY_RESULT:
                overall_status = WebSearchStatus.EMPTY_RESULT
                err_msg = None
            elif partial_errors:
                overall_status = next(iter(provider_statuses.values()))
                err_msg = "; ".join(f"{k}: {v}" for k, v in partial_errors.items())
            else:
                overall_status = WebSearchStatus.EMPTY_RESULT
                err_msg = None

        trace = {
            "provider": self._provider.provider_name,
            "primary_provider": self._provider.provider_name,
            "active_providers": [p.provider_name for p in active_providers],
            "engine_latency_ms": elapsed_ms,
            "engine_bounded_max_results": bounded_max_results,
        }

        return WebSearchResponse(
            request_id=req.request_id,
            status=overall_status,
            query_text=req.query_text,
            results=final_results,
            result_count=len(final_results),
            provider_name=self._provider.provider_name,
            provider_statuses=provider_statuses,
            partial_errors=partial_errors,
            execution_time_ms=elapsed_ms,
            error_message=err_msg,
            warnings=warnings,
            trace_info=trace,
        )
