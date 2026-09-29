"""API Web Search Provider Adapter for EarthMind Stage R10 Web Search Integration.

Implements IWebSearchProvider for external web search APIs (e.g., SerpAPI or standard JSON Web Search endpoints).
Handles request formatting, authentication headers, HTTP timeouts, error status mapping, and result normalization.
"""

import json
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


class APIWebSearchProvider(IWebSearchProvider):
    """
    Provider-independent HTTP API adapter for web search services.
    Retrieves web evidence using standard HTTP APIs and normalizes responses into WebSearchResult.
    """

    def __init__(
        self,
        config: Optional[WebSearchConfig] = None,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        user_agent: Optional[str] = None,
    ):
        cfg = config or WebSearchConfig()
        self._endpoint = endpoint or cfg.endpoint
        self._api_key = api_key or cfg.api_key
        self._timeout = timeout if timeout is not None else cfg.timeout
        self._user_agent = user_agent or cfg.user_agent
        self._safe_search = cfg.safe_search

    @property
    def provider_name(self) -> str:
        return "api"

    def is_available(self) -> bool:
        """Available if an endpoint URL is configured."""
        return bool(self._endpoint and self._endpoint.strip())

    def supported_capabilities(self) -> Dict[str, Any]:
        return {
            "safe_search": self._safe_search,
            "regional_filtering": True,
            "multilingual_queries": True,
            "max_results_limit": 100,
            "external_api": True,
        }

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        """Executes HTTP request to web search API and normalizes response."""
        start_time = time.perf_counter()

        if not request.query_text or not request.query_text.strip():
            raise InvalidWebSearchRequestError("Query text cannot be empty.")

        if not self._endpoint:
            raise WebSearchProviderUnavailableError(
                self.provider_name, "Web search API endpoint is not configured."
            )

        timeout = request.timeout if request.timeout > 0 else self._timeout

        # Build request parameters
        params: Dict[str, str] = {
            "q": request.query_text,
            "num": str(min(request.max_results, 50)),
        }
        if request.language:
            params["hl"] = request.language
        if request.region:
            params["gl"] = request.region
        if self._api_key:
            params["api_key"] = self._api_key

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
                    self.provider_name, f"HTTP {http_err.code}: Invalid API key or unauthorized access."
                )
            elif http_err.code == 429:
                raise WebSearchRateLimitError(
                    self.provider_name, f"HTTP {http_err.code}: Rate limit exceeded."
                )
            elif http_err.code in (502, 503, 504):
                raise WebSearchProviderUnavailableError(
                    self.provider_name, f"HTTP {http_err.code}: Provider service unavailable."
                )
            else:
                raise WebSearchExecutionError(
                    self.provider_name, f"HTTP {http_err.code}: Web search request failed."
                )
        except TimeoutError:
            raise WebSearchTimeoutError(self.provider_name, timeout)
        except urllib.error.URLError as url_err:
            if isinstance(url_err.reason, TimeoutError) or "timed out" in str(url_err.reason).lower():
                raise WebSearchTimeoutError(self.provider_name, timeout)
            raise WebSearchProviderUnavailableError(
                self.provider_name, f"Network error connecting to search API: {url_err.reason}"
            )
        except json.JSONDecodeError as json_err:
            raise WebSearchExecutionError(
                self.provider_name, f"Failed to parse provider JSON response: {json_err}"
            )

        # Normalize results from payload
        raw_results = data.get("organic_results") or data.get("results") or data.get("items") or []
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
                trace_info={"endpoint": self._endpoint, "raw_response_keys": list(data.keys())},
            )

        now_ts = time.time()
        normalized_results: List[WebSearchResult] = []
        for idx, item in enumerate(raw_results, start=1):
            link = item.get("link") or item.get("url") or ""
            title = item.get("title") or "Untitled Web Result"
            snippet = item.get("snippet") or item.get("summary") or item.get("description") or ""
            domain = urllib.parse.urlparse(link).netloc if link else None
            res_id = str(item.get("id") or f"web_res_{idx}_{hash(link or title) & 0xffff}")

            normalized_results.append(
                WebSearchResult(
                    result_id=res_id,
                    title=title,
                    url=link,
                    snippet=snippet,
                    source=domain,
                    publication_date=item.get("date") or item.get("published_date"),
                    last_updated_date=item.get("last_updated"),
                    provider=self.provider_name,
                    retrieval_timestamp=now_ts,
                    rank=idx,
                    score=float(item.get("score")) if item.get("score") is not None else None,
                    content=item.get("content") or item.get("body"),
                    provenance={
                        "provider": self.provider_name,
                        "endpoint": self._endpoint,
                        "retrieval_timestamp": now_ts,
                    },
                    metadata={
                        "language": request.language,
                        "region": request.region,
                        "raw_item": {k: v for k, v in item.items() if k in ("position", "displayed_link", "source")},
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
                "endpoint": self._endpoint,
                "requested_max_results": request.max_results,
            },
        )
