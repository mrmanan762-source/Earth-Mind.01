"""Brave Search API Provider Adapter for EarthMind Stage R10 Web Search.

Implements IWebSearchProvider for the official Brave Search API:
- Endpoint: https://api.search.brave.com/res/v1/web/search
- Header authentication: X-Subscription-Token
- Parameters: q, count, offset, country, search_lang, freshness, safesearch
- Normalizes organic web results, news, and snippets into standard WebSearchResult models.
- Maps HTTP status codes into EarthMind exception hierarchy (401/403 -> WebSearchAuthenticationError,
  429 -> WebSearchRateLimitError, 5xx -> WebSearchProviderUnavailableError).
"""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from core.config.settings import WebSearchConfig
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

logger = logging.getLogger(__name__)


class BraveWebSearchProvider(IWebSearchProvider):
    """Brave Search API adapter."""

    def __init__(
        self,
        config: Optional[WebSearchConfig] = None,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout: Optional[float] = None,
        user_agent: Optional[str] = None,
    ):
        cfg = config or WebSearchConfig()
        self._api_key = api_key or cfg.brave_api_key or cfg.api_key
        self._endpoint = endpoint or cfg.brave_endpoint
        self._timeout = timeout if timeout is not None else cfg.timeout
        self._user_agent = user_agent or cfg.user_agent
        self._safe_search = cfg.safe_search
        self._default_country = cfg.brave_country or "in"
        self._default_lang = cfg.brave_search_lang or "en"
        self._enable_llm_context = cfg.brave_enable_llm_context

    @property
    def provider_name(self) -> str:
        return "brave"

    def is_available(self) -> bool:
        """Available if endpoint is configured and api_key is present."""
        return bool(self._endpoint and self._endpoint.strip() and self._api_key and self._api_key.strip())

    def supported_capabilities(self) -> Dict[str, Any]:
        return {
            "safe_search": self._safe_search,
            "regional_filtering": True,
            "multilingual_queries": True,
            "freshness_filtering": True,
            "news_search": True,
            "max_results_limit": 20,
            "official_api": True,
        }

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        """Executes Brave Search API query and returns normalized response."""
        start_time = time.perf_counter()

        if not request.query_text or not request.query_text.strip():
            raise InvalidWebSearchRequestError("Search query text cannot be empty.")

        if not self._api_key or not self._api_key.strip():
            raise WebSearchAuthenticationError(
                self.provider_name, "Brave Search API key (EARTHMIND_BRAVE_API_KEY) is missing or not configured."
            )

        timeout = request.timeout if request.timeout > 0 else self._timeout

        # Build query parameters
        params: Dict[str, str] = {
            "q": request.query_text,
            "count": str(min(max(request.max_results, 1), 20)),
            "safesearch": "strict" if self._safe_search else "off",
        }

        # Language and country hints
        country = request.region or self._default_country
        if country:
            params["country"] = country.lower()

        lang = request.language or self._default_lang
        if lang:
            params["search_lang"] = lang.lower()

        # Handle optional freshness filters
        if request.filters and "freshness" in request.filters:
            params["freshness"] = str(request.filters["freshness"])

        url_parts = urllib.parse.urlparse(self._endpoint)
        existing_params = urllib.parse.parse_qs(url_parts.query)
        for k, v in existing_params.items():
            if k not in params:
                params[k] = v[0]

        query_string = urllib.parse.urlencode(params)
        full_url = urllib.parse.urlunparse((
            url_parts.scheme,
            url_parts.netloc,
            url_parts.path,
            url_parts.params,
            query_string,
            url_parts.fragment,
        ))

        req = urllib.request.Request(
            full_url,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "application/json",
                "X-Subscription-Token": self._api_key,
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status_code = response.getcode()
                raw_body = response.read().decode("utf-8")
                data = json.loads(raw_body)
        except urllib.error.HTTPError as http_err:
            if http_err.code in (401, 403):
                raise WebSearchAuthenticationError(
                    self.provider_name, f"HTTP {http_err.code}: Invalid Brave Search subscription token."
                )
            elif http_err.code == 429:
                raise WebSearchRateLimitError(
                    self.provider_name, f"HTTP {http_err.code}: Brave Search API rate limit exceeded."
                )
            elif http_err.code in (500, 502, 503, 504):
                raise WebSearchProviderUnavailableError(
                    self.provider_name, f"HTTP {http_err.code}: Brave Search service unavailable."
                )
            else:
                raise WebSearchExecutionError(
                    self.provider_name, f"HTTP {http_err.code}: Brave Search request failed: {http_err.reason}"
                )
        except TimeoutError:
            raise WebSearchTimeoutError(self.provider_name, timeout)
        except urllib.error.URLError as url_err:
            if isinstance(url_err.reason, TimeoutError) or "timed out" in str(url_err.reason).lower():
                raise WebSearchTimeoutError(self.provider_name, timeout)
            raise WebSearchProviderUnavailableError(
                self.provider_name, f"Network error connecting to Brave Search: {url_err.reason}"
            )
        except json.JSONDecodeError as json_err:
            raise WebSearchExecutionError(
                self.provider_name, f"Failed to parse Brave Search JSON response: {json_err}"
            )

        # Parse organic web results
        web_section = data.get("web", {})
        raw_results = web_section.get("results", [])

        if not raw_results:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                request_id=request.request_id,
                status=WebSearchStatus.EMPTY_RESULT,
                query_text=request.query_text,
                results=[],
                result_count=0,
                provider_name=self.provider_name,
                execution_time_ms=elapsed_ms,
                trace_info={"endpoint": self._endpoint, "provider": self.provider_name},
            )

        now_ts = time.time()
        normalized_results: List[WebSearchResult] = []

        for idx, item in enumerate(raw_results, start=1):
            url = item.get("url") or ""
            title = item.get("title") or "Untitled Web Result"
            description = item.get("description") or ""
            domain = urllib.parse.urlparse(url).netloc if url else None
            res_id = str(item.get("id") or f"brave_{idx}_{hash(url or title) & 0xffff}")

            # Extract extra snippet descriptions if available
            snippets = [description] if description else []
            extra_snippets = item.get("extra_snippets") or []
            snippets.extend(extra_snippets)
            combined_snippet = " \n".join(snippets).strip()

            # Publication timestamp if provided by Brave
            pub_date = item.get("page_age") or item.get("published_date")

            normalized_results.append(
                WebSearchResult(
                    result_id=res_id,
                    title=title,
                    url=url,
                    canonical_url=url,
                    result_type="web",
                    snippet=combined_snippet or description,
                    source=domain,
                    publication_date=str(pub_date) if pub_date else None,
                    provider=self.provider_name,
                    retrieval_timestamp=now_ts,
                    rank=idx,
                    provenance={
                        "provider": self.provider_name,
                        "query": request.query_text,
                        "retrieval_timestamp": now_ts,
                    },
                    metadata={
                        "language": request.language,
                        "country": country,
                        "family_friendly": item.get("family_friendly", True),
                    },
                    request_id=request.request_id,
                )
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return WebSearchResponse(
            request_id=request.request_id,
            status=WebSearchStatus.SUCCESS,
            query_text=request.query_text,
            results=normalized_results,
            result_count=len(normalized_results),
            provider_name=self.provider_name,
            execution_time_ms=elapsed_ms,
            trace_info={
                "provider": self.provider_name,
                "requested_max_results": request.max_results,
                "country": country,
                "language": lang,
            },
        )
