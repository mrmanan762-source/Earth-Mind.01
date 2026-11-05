"""Wikipedia (MediaWiki API) Provider Adapter for EarthMind Stage R10 Web Search.

Implements IWebSearchProvider to retrieve encyclopedic background information from Wikipedia.
Uses the official MediaWiki API (action=query):
- Supports multilingual querying (e.g. en.wikipedia.org, hi.wikipedia.org).
- Extracts article page title, full URL, snippet/extract, and page ID.
- Categorizes results as result_type='encyclopedic'.
- Serves as supplementary context; does not override primary agricultural authorities.
"""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup

from core.config.settings import WebSearchConfig
from core.errors.exceptions import (
    InvalidWebSearchRequestError,
    WebSearchExecutionError,
    WebSearchProviderUnavailableError,
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


class WikipediaSearchProvider(IWebSearchProvider):
    """MediaWiki API adapter for Wikipedia article search and extract retrieval."""

    def __init__(
        self,
        config: Optional[WebSearchConfig] = None,
        endpoint: Optional[str] = None,
        timeout: Optional[float] = None,
        user_agent: Optional[str] = None,
    ):
        cfg = config or WebSearchConfig()
        self._endpoint = endpoint or cfg.wikipedia_endpoint
        self._timeout = timeout if timeout is not None else cfg.timeout
        self._user_agent = user_agent or cfg.user_agent
        self._max_results = cfg.wikipedia_max_results

    @property
    def provider_name(self) -> str:
        return "wikipedia"

    def is_available(self) -> bool:
        return bool(self._endpoint and self._endpoint.strip())

    def supported_capabilities(self) -> Dict[str, Any]:
        return {
            "encyclopedic_search": True,
            "multilingual_queries": True,
            "extract_summaries": True,
            "max_results_limit": 10,
        }

    def _resolve_endpoint_for_lang(self, lang: Optional[str]) -> str:
        """Adapts Wikipedia subdomain if language hint is provided (e.g., 'hi' -> hi.wikipedia.org)."""
        if not lang or lang == "en":
            return self._endpoint
        parsed = urllib.parse.urlparse(self._endpoint)
        if "wikipedia.org" in parsed.netloc:
            new_netloc = f"{lang.lower()}.wikipedia.org"
            return urllib.parse.urlunparse((
                parsed.scheme,
                new_netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            ))
        return self._endpoint

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        """Searches Wikipedia using MediaWiki API and retrieves article snippets."""
        start_time = time.perf_counter()

        if not request.query_text or not request.query_text.strip():
            raise InvalidWebSearchRequestError("Query text cannot be empty.")

        timeout = request.timeout if request.timeout > 0 else self._timeout
        limit = min(request.max_results, self._max_results)

        endpoint = self._resolve_endpoint_for_lang(request.language)

        params: Dict[str, str] = {
            "action": "query",
            "list": "search",
            "srsearch": request.query_text,
            "srlimit": str(limit),
            "format": "json",
            "utf8": "1",
        }

        query_str = urllib.parse.urlencode(params)
        full_url = f"{endpoint}?{query_str}"

        req = urllib.request.Request(
            full_url,
            headers={"User-Agent": self._user_agent, "Accept": "application/json"},
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
        except urllib.error.HTTPError as http_err:
            raise WebSearchProviderUnavailableError(
                self.provider_name, f"HTTP {http_err.code}: Wikipedia API unavailable: {http_err.reason}"
            )
        except TimeoutError:
            raise WebSearchTimeoutError(self.provider_name, timeout)
        except urllib.error.URLError as url_err:
            if isinstance(url_err.reason, TimeoutError) or "timed out" in str(url_err.reason).lower():
                raise WebSearchTimeoutError(self.provider_name, timeout)
            raise WebSearchProviderUnavailableError(
                self.provider_name, f"Network error connecting to Wikipedia: {url_err.reason}"
            )
        except json.JSONDecodeError as json_err:
            raise WebSearchExecutionError(
                self.provider_name, f"Failed to parse Wikipedia JSON response: {json_err}"
            )

        search_items = data.get("query", {}).get("search", [])
        if not search_items:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                request_id=request.request_id,
                status=WebSearchStatus.EMPTY_RESULT,
                query_text=request.query_text,
                results=[],
                result_count=0,
                provider_name=self.provider_name,
                execution_time_ms=elapsed_ms,
            )

        now_ts = time.time()
        results: List[WebSearchResult] = []
        base_host = urllib.parse.urlparse(endpoint).netloc

        for idx, item in enumerate(search_items, start=1):
            title = item.get("title", "Wikipedia Article")
            page_id = item.get("pageid", "")
            raw_snippet = item.get("snippet", "")

            # Strip HTML tags from MediaWiki snippet
            soup = BeautifulSoup(raw_snippet, "html.parser")
            clean_snippet = soup.get_text()

            # Construct canonical Wikipedia article URL
            encoded_title = urllib.parse.quote(title.replace(" ", "_"))
            article_url = f"https://{base_host}/wiki/{encoded_title}"

            results.append(
                WebSearchResult(
                    result_id=f"wiki_{page_id}_{idx}",
                    title=f"{title} - Wikipedia",
                    url=article_url,
                    canonical_url=article_url,
                    result_type="encyclopedic",
                    snippet=clean_snippet,
                    source="wikipedia.org",
                    provider=self.provider_name,
                    retrieval_timestamp=now_ts,
                    rank=idx,
                    provenance={
                        "provider": self.provider_name,
                        "page_id": page_id,
                        "query": request.query_text,
                        "retrieval_timestamp": now_ts,
                    },
                    metadata={
                        "language": request.language,
                        "wordcount": item.get("wordcount"),
                    },
                    request_id=request.request_id,
                )
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return WebSearchResponse(
            request_id=request.request_id,
            status=WebSearchStatus.SUCCESS,
            query_text=request.query_text,
            results=results,
            result_count=len(results),
            provider_name=self.provider_name,
            execution_time_ms=elapsed_ms,
        )
