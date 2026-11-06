"""Tavily Search API Provider Adapter for EarthMind Stage R10 Web Search.

Role: Primary Managed Web Search Provider.
Official portal: https://www.tavily.com/

PREPARATION CONTRACT:
- Implements IWebSearchProvider.
- Follows the existing WebSearchProvider contract.
- Supports secure configuration for its API key via EARTHMIND_WEB_SEARCH_TAVILY_API_KEY.
- is_available() returns False when credentials are not configured.
- When credentials are not available, search() fails safely by raising WebSearchAuthenticationError
  without crashing or blocking other providers in WebSearchEngine.
- Never makes a live network request until credentials are configured.
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


class TavilySearchProvider(IWebSearchProvider):
    """Tavily API adapter for managed AI-optimized web search retrieval."""

    def __init__(
        self,
        config: Optional[WebSearchConfig] = None,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout: Optional[float] = None,
        user_agent: Optional[str] = None,
    ):
        cfg = config or WebSearchConfig()
        self._api_key = api_key or cfg.tavily_api_key
        self._endpoint = endpoint or cfg.tavily_endpoint
        self._timeout = timeout if timeout is not None else cfg.timeout
        self._user_agent = user_agent or cfg.user_agent
        self._safe_search = cfg.safe_search

    @property
    def provider_name(self) -> str:
        return "tavily"

    def is_available(self) -> bool:
        """Returns True only when valid API key credentials are configured."""
        return bool(self._endpoint and self._endpoint.strip() and self._api_key and self._api_key.strip())

    def supported_capabilities(self) -> Dict[str, Any]:
        return {
            "managed_search": True,
            "ai_search_optimization": True,
            "answer_synthesis": True,
            "relevance_scoring": True,
            "max_results_limit": 20,
            "requires_credentials": True,
            "credentials_present": self.is_available(),
        }

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        """Executes Tavily search query if credentials configured, else raises WebSearchAuthenticationError."""
        start_time = time.perf_counter()

        if not request.query_text or not request.query_text.strip():
            raise InvalidWebSearchRequestError("Search query text cannot be empty.")

        if not self._api_key or not self._api_key.strip():
            raise WebSearchAuthenticationError(
                self.provider_name,
                "Tavily API key is not configured. Set EARTHMIND_WEB_SEARCH_TAVILY_API_KEY when credentials are available."
            )

        timeout = request.timeout if request.timeout > 0 else self._timeout
        limit = min(max(request.max_results, 1), 20)

        # Build Tavily POST request payload
        payload: Dict[str, Any] = {
            "api_key": self._api_key,
            "query": request.query_text,
            "search_depth": "advanced" if request.search_mode in ("academic", "deep") else "basic",
            "include_answer": True,
            "include_raw_content": False,
            "max_results": limit,
        }

        # Include domain filters if provided
        if request.filters and "include_domains" in request.filters:
            payload["include_domains"] = request.filters["include_domains"]

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._endpoint,
            data=req_data,
            headers={
                "User-Agent": self._user_agent,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status_code = response.getcode()
                raw_body = response.read().decode("utf-8")
                data = json.loads(raw_body)
        except urllib.error.HTTPError as http_err:
            if http_err.code in (401, 403):
                raise WebSearchAuthenticationError(
                    self.provider_name, f"HTTP {http_err.code}: Invalid Tavily API key."
                )
            elif http_err.code == 429:
                raise WebSearchRateLimitError(
                    self.provider_name, f"HTTP {http_err.code}: Tavily API rate limit exceeded."
                )
            elif http_err.code in (500, 502, 503, 504):
                raise WebSearchProviderUnavailableError(
                    self.provider_name, f"HTTP {http_err.code}: Tavily service unavailable."
                )
            else:
                raise WebSearchExecutionError(
                    self.provider_name, f"HTTP {http_err.code}: Tavily search request failed: {http_err.reason}"
                )
        except TimeoutError:
            raise WebSearchTimeoutError(self.provider_name, timeout)
        except urllib.error.URLError as url_err:
            if isinstance(url_err.reason, TimeoutError) or "timed out" in str(url_err.reason).lower():
                raise WebSearchTimeoutError(self.provider_name, timeout)
            raise WebSearchProviderUnavailableError(
                self.provider_name, f"Network error connecting to Tavily: {url_err.reason}"
            )
        except json.JSONDecodeError as json_err:
            raise WebSearchExecutionError(
                self.provider_name, f"Failed to parse Tavily JSON response: {json_err}"
            )

        raw_results = data.get("results", [])
        answer = data.get("answer")

        if not raw_results and not answer:
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
            content_snippet = item.get("content") or ""
            score = item.get("score")
            score_val = float(score) if score is not None else None
            domain = urllib.parse.urlparse(url).netloc if url else None
            res_id = f"tavily_{idx}_{hash(url or title) & 0xffff}"

            normalized_results.append(
                WebSearchResult(
                    result_id=res_id,
                    title=title,
                    url=url,
                    canonical_url=url,
                    result_type="web",
                    snippet=content_snippet,
                    source=domain,
                    provider=self.provider_name,
                    retrieval_timestamp=now_ts,
                    rank=idx,
                    score=score_val,
                    provenance={
                        "provider": self.provider_name,
                        "query": request.query_text,
                        "retrieval_timestamp": now_ts,
                    },
                    metadata={
                        "tavily_score": score,
                        "tavily_answer_summary": answer,
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
                "has_answer": bool(answer),
            },
        )
