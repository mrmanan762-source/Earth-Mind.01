"""Master Multi-Source Web Search Engine for EarthMind Stage R10 Web Search.

Coordinates multi-source web retrieval from R9 Query Processing to external web search providers:
1. Primary general web search: Tavily (Primary managed provider) with automatic, resilient
   fallback to Gemini Grounding (Secondary managed provider), or Brave / Generic API / Fake provider.
2. Supplementary providers: Wikipedia (MediaWiki), Wikidata (SPARQL), Scientific Literature (Crossref/OpenAlex),
   and Agroclimatology (NASA POWER).
3. Resilience & Hardening:
   - Circuit Breaker pattern (CLOSED, OPEN, HALF_OPEN) per provider.
   - Provider Rate Limiting & Concurrency Throttling (RPM + semaphores).
   - Local Estimated Quota Management preventing billing triggers or paid tier overages.
   - Intelligent Multi-Tier Freshness Caching (LRU with category-specific TTLs and farmer tenant isolation).
   - Provider Fallback: Tavily failures do not crash the search pipeline; fallback cleanly routes to Gemini Grounding.
   - URL Canonicalization with tracking parameter stripping (utm_*, fbclid, etc.).
   - Contradiction Detection: Flags and preserves opposing agronomic evidence without discarding either side.
   - Telemetry: Integrates latency, hits/misses, circuits, retries, and fallbacks into MetricsCollector.

HARD ARCHITECTURAL RULES:
- Web search results are query-time candidate evidence for Stage R11 Evidence Builder.
- Web Search Engine NEVER publishes web results to the permanent Knowledge Base.
- NEVER writes to Qdrant vector index.
- NEVER writes to SQLite or General Memory records.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import time
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
from core.observability.metrics import metrics_collector
from core.schemas.query import RetrievalQuery
from core.schemas.web_search import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
    WebSearchStatus,
)
from modules.knowledge_base.web_search.cache import IWebSearchCache, InMemoryWebSearchCache
from modules.knowledge_base.web_search.content_fetcher import SafeContentFetcher
from modules.knowledge_base.web_search.evidence_processor import EvidenceProcessor
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
from modules.knowledge_base.web_search.resilience import (
    CircuitBreakerOpenError,
    QuotaExceededError,
    ResilienceManager,
)

logger = logging.getLogger(__name__)


class WebSearchEngine:
    """Master Multi-Source Search Orchestrator for Stage R10 with Resilience & Caching."""

    def __init__(
        self,
        config: Optional[WebSearchConfig] = None,
        provider: Optional[IWebSearchProvider] = None,
        fallback_provider: Optional[IWebSearchProvider] = None,
        wikipedia_provider: Optional[IWebSearchProvider] = None,
        wikidata_provider: Optional[IWebSearchProvider] = None,
        scholarly_providers: Optional[List[IWebSearchProvider]] = None,
        nasa_power_provider: Optional[IWebSearchProvider] = None,
        content_fetcher: Optional[SafeContentFetcher] = None,
        cache: Optional[IWebSearchCache] = None,
        resilience_manager: Optional[ResilienceManager] = None,
    ):
        self._config = config or getattr(settings, "web_search", WebSearchConfig())
        self._provider = provider or self._resolve_primary_provider(self._config)

        # Fallback provider resolution
        if fallback_provider is not None:
            self._fallback_provider = fallback_provider
        elif self._config.enable_provider_fallback:
            self._fallback_provider = self._resolve_fallback_provider(self._config)
        else:
            self._fallback_provider = None

        # Check if isolated test provider
        is_isolated = (
            self._provider.provider_name.startswith("mock")
            or self._provider.provider_name.startswith("fake")
            or self._provider.provider_name.startswith("failing")
        )

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
        elif not is_isolated and not provider:
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

        # Resilience & Caching subsystems
        self._cache = cache or InMemoryWebSearchCache(config=self._config)
        self._resilience = resilience_manager or ResilienceManager(config=self._config)
        self._evidence_processor = EvidenceProcessor(config=self._config)

    @property
    def config(self) -> WebSearchConfig:
        return self._config

    @property
    def provider(self) -> IWebSearchProvider:
        return self._provider

    @property
    def fallback_provider(self) -> Optional[IWebSearchProvider]:
        return self._fallback_provider

    @property
    def cache(self) -> IWebSearchCache:
        return self._cache

    @property
    def resilience(self) -> ResilienceManager:
        return self._resilience

    def _resolve_primary_provider(self, config: WebSearchConfig) -> IWebSearchProvider:
        """Instantiates primary web search provider adapter."""
        p_name = (config.provider or "fake").lower().strip()
        if p_name in ("fake", "mock"):
            return FakeWebSearchProvider()
        elif p_name == "tavily":
            return TavilySearchProvider(config=config)
        elif p_name in ("gemini_grounding", "gemini"):
            return GeminiGroundingSearchProvider(config=config)
        elif p_name == "brave":
            return BraveWebSearchProvider(config=config)
        elif p_name in ("api", "serp", "serpapi", "google", "bing"):
            return APIWebSearchProvider(config=config)
        else:
            raise WebSearchConfigurationError(f"Unsupported web search provider '{config.provider}'.")

    def _resolve_fallback_provider(self, config: WebSearchConfig) -> Optional[IWebSearchProvider]:
        """Instantiates secondary fallback provider adapter."""
        fb_name = (config.secondary_provider or "gemini_grounding").lower().strip()
        primary_name = (config.provider or "fake").lower().strip()

        # Prevent fallback loop
        if fb_name == primary_name:
            return None

        if fb_name in ("gemini_grounding", "gemini"):
            return GeminiGroundingSearchProvider(config=config)
        elif fb_name == "tavily":
            return TavilySearchProvider(config=config)
        elif fb_name == "brave":
            return BraveWebSearchProvider(config=config)
        elif fb_name in ("fake", "mock"):
            return FakeWebSearchProvider()
        return None

    def search(
        self,
        request_input: Union[WebSearchRequest, RetrievalQuery],
        max_results: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> WebSearchResponse:
        """
        Executes multi-source search query with intelligent caching, provider fallback,
        circuit-breaker isolation, rate limiting, URL canonicalization, and contradiction preservation.
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

        # 2. Check Cache
        cached_response = self._cache.get(req)
        if cached_response is not None:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            cached_response.execution_time_ms = elapsed_ms
            logger.debug(f"Cache hit for query: '{req.query_text[:30]}...'")
            return cached_response

        # Determine primary provider execution strategy (with fallback)
        provider_statuses: Dict[str, WebSearchStatus] = {}
        partial_errors: Dict[str, str] = {}
        collected_results: List[WebSearchResult] = []
        warnings: List[str] = []
        fallback_occurred = False
        primary_used_name = self._provider.provider_name

        def _execute_primary_with_fallback(primary_req: WebSearchRequest) -> Optional[WebSearchResponse]:
            nonlocal fallback_occurred, primary_used_name
            is_managed = self._provider.provider_name in ("tavily", "gemini_grounding")

            try:
                # Execute primary provider wrapped in resilience
                resp = self._resilience.execute_with_resilience(
                    self._provider.provider_name,
                    lambda: self._provider.search(primary_req),
                    is_managed_provider=is_managed,
                )
                provider_statuses[self._provider.provider_name] = resp.status
                return resp
            except Exception as primary_err:
                primary_name = self._provider.provider_name
                logger.warning(f"Primary web search provider '{primary_name}' failed: {primary_err}")
                partial_errors[primary_name] = str(primary_err)

                # Classify primary error status
                if isinstance(primary_err, WebSearchTimeoutError):
                    provider_statuses[primary_name] = WebSearchStatus.PROVIDER_TIMEOUT
                elif isinstance(primary_err, WebSearchAuthenticationError):
                    provider_statuses[primary_name] = WebSearchStatus.AUTHENTICATION_FAILURE
                elif isinstance(primary_err, (WebSearchRateLimitError, QuotaExceededError)):
                    provider_statuses[primary_name] = WebSearchStatus.RATE_LIMITED
                elif isinstance(primary_err, (WebSearchProviderUnavailableError, CircuitBreakerOpenError)):
                    provider_statuses[primary_name] = WebSearchStatus.PROVIDER_UNAVAILABLE
                else:
                    provider_statuses[primary_name] = WebSearchStatus.PROVIDER_ERROR

                # Record dependency event in telemetry
                metrics_collector.record_dependency_event(
                    primary_name,
                    operation_success=False,
                    is_retry=False,
                    recovery_success=False,
                )

                # Check if fallback is possible and permitted
                # Note: Do not fallback on invalid query request.
                can_fallback = (
                    self._fallback_provider is not None
                    and not isinstance(primary_err, InvalidWebSearchRequestError)
                )

                if can_fallback:
                    fb_provider = self._fallback_provider
                    fb_name = fb_provider.provider_name
                    fb_is_managed = fb_name in ("tavily", "gemini_grounding")

                    try:
                        logger.info(
                            f"Initiating controlled fallback from '{primary_name}' to secondary provider '{fb_name}'..."
                        )
                        fb_resp = self._resilience.execute_with_resilience(
                            fb_name,
                            lambda: fb_provider.search(primary_req),
                            is_managed_provider=fb_is_managed,
                        )
                        fallback_occurred = True
                        primary_used_name = fb_name
                        provider_statuses[fb_name] = fb_resp.status
                        warnings.append(
                            f"Primary provider '{primary_name}' failed; successfully recovered using fallback '{fb_name}'."
                        )
                        metrics_collector.record_dependency_event(
                            fb_name,
                            operation_success=True,
                            is_retry=False,
                            recovery_success=True,
                        )
                        return fb_resp
                    except Exception as fb_err:
                        logger.warning(f"Secondary fallback provider '{fb_name}' also failed: {fb_err}")
                        partial_errors[fb_name] = str(fb_err)
                        if isinstance(fb_err, WebSearchTimeoutError):
                            provider_statuses[fb_name] = WebSearchStatus.PROVIDER_TIMEOUT
                        elif isinstance(fb_err, WebSearchAuthenticationError):
                            provider_statuses[fb_name] = WebSearchStatus.AUTHENTICATION_FAILURE
                        elif isinstance(fb_err, (WebSearchRateLimitError, QuotaExceededError)):
                            provider_statuses[fb_name] = WebSearchStatus.RATE_LIMITED
                        elif isinstance(fb_err, (WebSearchProviderUnavailableError, CircuitBreakerOpenError)):
                            provider_statuses[fb_name] = WebSearchStatus.PROVIDER_UNAVAILABLE
                        else:
                            provider_statuses[fb_name] = WebSearchStatus.PROVIDER_ERROR

                        warnings.append(f"Fallback provider '{fb_name}' failed: {fb_err}")
                        metrics_collector.record_dependency_event(
                            fb_name,
                            operation_success=False,
                            is_retry=False,
                            recovery_success=False,
                        )
                return None

        # Build active supplementary providers
        supplementary_providers: List[IWebSearchProvider] = []

        if getattr(req, "include_encyclopedic", True) and self._wikipedia_provider:
            supplementary_providers.append(self._wikipedia_provider)

        if getattr(req, "include_structured", True) and self._wikidata_provider:
            supplementary_providers.append(self._wikidata_provider)

        if getattr(req, "include_scholarly", False) or req.search_mode in ("academic", "scholarly"):
            for sp in self._scholarly_providers:
                if sp.is_available():
                    supplementary_providers.append(sp)

        # Weather / Agroclimatology intent
        weather_requested = (
            getattr(req, "include_agroclimatology", False)
            or req.search_mode in ("climate", "weather", "agroclimatology")
        )
        if not weather_requested:
            q_lower = req.query_text.lower()
            weather_keywords = ("rainfall", "precipitation", "temperature", "weather", "climate", "solar", "radiation", "frost", "drought", "humidity")
            if any(kw in q_lower for kw in weather_keywords):
                weather_requested = True

        if weather_requested and self._nasa_power_provider and self._nasa_power_provider.is_available():
            supplementary_providers.append(self._nasa_power_provider)

        # Concurrently execute primary (with fallback) and supplementary providers
        def _execute_supplementary(p: IWebSearchProvider) -> Tuple[str, Optional[WebSearchResponse], Optional[Exception]]:
            p_name = p.provider_name
            try:
                sub_resp = self._resilience.execute_with_resilience(
                    p_name,
                    lambda: p.search(req),
                    is_managed_provider=False,
                )
                return p_name, sub_resp, None
            except Exception as e:
                return p_name, None, e

        # Execute primary with fallback first
        primary_response = _execute_primary_with_fallback(req)
        if primary_response and primary_response.results:
            collected_results.extend(primary_response.results)
        if primary_response and primary_response.warnings:
            warnings.extend(primary_response.warnings)

        # Execute supplementary providers concurrently
        if supplementary_providers:
            with ThreadPoolExecutor(max_workers=min(len(supplementary_providers), 4)) as executor:
                future_to_provider = {executor.submit(_execute_supplementary, p): p for p in supplementary_providers}
                for future in as_completed(future_to_provider):
                    p_name, sub_resp, err = future.result()
                    if err is not None:
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

        # 3. Deduplication, Contradiction Detection, Freshness & Ranking
        query_crop = None
        query_region = req.region
        if req.agricultural_metadata:
            query_crop = req.agricultural_metadata.get("crop")
            query_region = query_region or req.agricultural_metadata.get("region")

        final_results, conflict_notes = self._evidence_processor.deduplicate_and_rank(
            collected_results=collected_results,
            query_crop=query_crop,
            query_region=query_region,
            max_results=bounded_max_results,
        )
        if conflict_notes:
            warnings.extend(conflict_notes)

        # 4. Safe Content Extraction if requested
        if (req.fetch_content or self._config.enable_content_fetch) and self._content_fetcher:
            for item in final_results[:2]:
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
        primary_status = provider_statuses.get(primary_used_name)
        primary_error = partial_errors.get(primary_used_name)

        if final_results:
            # If fallback occurred and yielded results, or only sub-providers had errors
            if fallback_occurred and not any(p for p in partial_errors if p != self._provider.provider_name):
                # Fallback successfully fulfilled primary search
                overall_status = WebSearchStatus.SUCCESS
            elif partial_errors:
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
            "provider": primary_used_name,
            "primary_provider": self._provider.provider_name,
            "fallback_occurred": fallback_occurred,
            "engine_latency_ms": elapsed_ms,
            "engine_bounded_max_results": bounded_max_results,
            "circuit_breakers": {
                p: self._resilience.get_circuit_breaker(p).get_status()
                for p in provider_statuses.keys()
            },
        }

        response = WebSearchResponse(
            request_id=req.request_id,
            status=overall_status,
            query_text=req.query_text,
            results=final_results,
            result_count=len(final_results),
            provider_name=primary_used_name,
            provider_statuses=provider_statuses,
            partial_errors=partial_errors,
            execution_time_ms=elapsed_ms,
            error_message=err_msg,
            warnings=warnings,
            trace_info=trace,
        )

        # Cache response for future queries
        if overall_status in (WebSearchStatus.SUCCESS, WebSearchStatus.PARTIAL) and final_results:
            self._cache.set(req, response)

        # Record search metrics in telemetry collector
        try:
            metrics_collector.record_retrieval_stage(
                stage_name="web_search",
                latency_ms=elapsed_ms,
                candidate_count=len(final_results),
                success=(overall_status in (WebSearchStatus.SUCCESS, WebSearchStatus.PARTIAL)),
                degraded=fallback_occurred or bool(partial_errors),
            )
        except Exception:
            pass

        return response
