"""Scientific Literature Providers for EarthMind Stage R10 Web Search.

Implements IWebSearchProvider adapters for:
1. Crossref API: Scholarly publication metadata, DOI discovery, author attribution, and abstracts.
2. OpenAlex API: Open-access scientific research, citation metrics, and inverted index abstract reconstruction.

Respects polite pool rate limits and includes contact headers.
Categorizes returned evidence items with result_type='scholarly'.
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


class CrossrefSearchProvider(IWebSearchProvider):
    """Crossref REST API adapter for academic publication metadata and DOI search."""

    def __init__(
        self,
        config: Optional[WebSearchConfig] = None,
        endpoint: Optional[str] = None,
        mailto: Optional[str] = None,
        timeout: Optional[float] = None,
        user_agent: Optional[str] = None,
    ):
        cfg = config or WebSearchConfig()
        self._endpoint = endpoint or cfg.crossref_endpoint
        self._mailto = mailto or cfg.crossref_mailto
        self._timeout = timeout if timeout is not None else cfg.timeout
        self._user_agent = user_agent or cfg.user_agent
        self._max_results = cfg.crossref_max_results

    @property
    def provider_name(self) -> str:
        return "crossref"

    def is_available(self) -> bool:
        return bool(self._endpoint and self._endpoint.strip())

    def supported_capabilities(self) -> Dict[str, Any]:
        return {
            "scholarly_search": True,
            "doi_discovery": True,
            "peer_reviewed_metadata": True,
            "max_results_limit": 10,
        }

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        """Executes Crossref API query and normalizes works into WebSearchResult."""
        start_time = time.perf_counter()

        if not request.query_text or not request.query_text.strip():
            raise InvalidWebSearchRequestError("Query text cannot be empty.")

        timeout = request.timeout if request.timeout > 0 else self._timeout
        limit = min(request.max_results, self._max_results)

        params: Dict[str, str] = {
            "query": request.query_text,
            "rows": str(limit),
        }
        if self._mailto:
            params["mailto"] = self._mailto

        query_str = urllib.parse.urlencode(params)
        full_url = f"{self._endpoint}?{query_str}"

        req = urllib.request.Request(
            full_url,
            headers={
                "User-Agent": f"{self._user_agent} (mailto:{self._mailto})" if self._mailto else self._user_agent,
                "Accept": "application/json",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
        except urllib.error.HTTPError as http_err:
            if http_err.code == 429:
                raise WebSearchRateLimitError(self.provider_name, "Crossref API rate limit exceeded.")
            raise WebSearchProviderUnavailableError(
                self.provider_name, f"HTTP {http_err.code}: Crossref API unavailable: {http_err.reason}"
            )
        except TimeoutError:
            raise WebSearchTimeoutError(self.provider_name, timeout)
        except urllib.error.URLError as url_err:
            if isinstance(url_err.reason, TimeoutError) or "timed out" in str(url_err.reason).lower():
                raise WebSearchTimeoutError(self.provider_name, timeout)
            raise WebSearchProviderUnavailableError(
                self.provider_name, f"Network error connecting to Crossref: {url_err.reason}"
            )
        except json.JSONDecodeError as json_err:
            raise WebSearchExecutionError(self.provider_name, f"Failed to parse Crossref JSON: {json_err}")

        items = data.get("message", {}).get("items", [])
        if not items:
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

        for idx, item in enumerate(items, start=1):
            title_list = item.get("title", [])
            title = title_list[0] if title_list else "Untitled Scholarly Work"
            doi = item.get("DOI", "")
            url = item.get("URL") or (f"https://doi.org/{doi}" if doi else "")

            # Author names
            authors = []
            for author in item.get("author", []):
                given = author.get("given", "")
                family = author.get("family", "")
                name = f"{given} {family}".strip()
                if name:
                    authors.append(name)
            author_str = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")

            # Container / Journal
            container_list = item.get("container-title", [])
            journal = container_list[0] if container_list else ""

            # Publication date
            created_parts = item.get("created", {}).get("date-parts", [[]])[0]
            pub_date = "-".join(str(p) for p in created_parts) if created_parts else None

            # Construct clean academic snippet
            snippet_parts = []
            if author_str:
                snippet_parts.append(f"Authors: {author_str}.")
            if journal:
                snippet_parts.append(f"Published in: {journal}.")
            if doi:
                snippet_parts.append(f"DOI: {doi}.")

            abstract = item.get("abstract", "")
            if abstract:
                snippet_parts.append(f"Abstract: {abstract[:400]}...")

            snippet = " ".join(snippet_parts)

            results.append(
                WebSearchResult(
                    result_id=f"crossref_{doi.replace('/', '_') if doi else idx}",
                    title=title,
                    url=url,
                    canonical_url=url,
                    result_type="scholarly",
                    snippet=snippet,
                    source=journal or "Crossref",
                    publication_date=pub_date,
                    provider=self.provider_name,
                    retrieval_timestamp=now_ts,
                    rank=idx,
                    provenance={
                        "provider": self.provider_name,
                        "doi": doi,
                        "query": request.query_text,
                        "retrieval_timestamp": now_ts,
                    },
                    metadata={
                        "authors": authors,
                        "journal": journal,
                        "doi": doi,
                        "is_referenced_by_count": item.get("is-referenced-by-count"),
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


class OpenAlexSearchProvider(IWebSearchProvider):
    """OpenAlex API adapter for open scholarly research and citation discovery."""

    def __init__(
        self,
        config: Optional[WebSearchConfig] = None,
        endpoint: Optional[str] = None,
        email: Optional[str] = None,
        timeout: Optional[float] = None,
        user_agent: Optional[str] = None,
    ):
        cfg = config or WebSearchConfig()
        self._endpoint = endpoint or cfg.openalex_endpoint
        self._email = email or cfg.openalex_email
        self._timeout = timeout if timeout is not None else cfg.timeout
        self._user_agent = user_agent or cfg.user_agent
        self._max_results = cfg.openalex_max_results

    @property
    def provider_name(self) -> str:
        return "openalex"

    def is_available(self) -> bool:
        return bool(self._endpoint and self._endpoint.strip())

    def supported_capabilities(self) -> Dict[str, Any]:
        return {
            "scholarly_search": True,
            "open_access_discovery": True,
            "citation_metrics": True,
            "max_results_limit": 10,
        }

    def _reconstruct_abstract(self, inverted_index: Optional[Dict[str, List[int]]]) -> str:
        """Reconstructs abstract string from OpenAlex inverted index dictionary."""
        if not inverted_index:
            return ""
        try:
            position_word_map: Dict[int, str] = {}
            for word, positions in inverted_index.items():
                for pos in positions:
                    position_word_map[pos] = word
            sorted_positions = sorted(position_word_map.keys())
            return " ".join(position_word_map[p] for p in sorted_positions)
        except Exception:
            return ""

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        """Executes OpenAlex works search query."""
        start_time = time.perf_counter()

        if not request.query_text or not request.query_text.strip():
            raise InvalidWebSearchRequestError("Query text cannot be empty.")

        timeout = request.timeout if request.timeout > 0 else self._timeout
        limit = min(request.max_results, self._max_results)

        params: Dict[str, str] = {
            "search": request.query_text,
            "per-page": str(limit),
        }
        if self._email:
            params["mailto"] = self._email

        query_str = urllib.parse.urlencode(params)
        full_url = f"{self._endpoint}?{query_str}"

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
            if http_err.code == 429:
                raise WebSearchRateLimitError(self.provider_name, "OpenAlex rate limit exceeded.")
            raise WebSearchProviderUnavailableError(
                self.provider_name, f"HTTP {http_err.code}: OpenAlex unavailable: {http_err.reason}"
            )
        except TimeoutError:
            raise WebSearchTimeoutError(self.provider_name, timeout)
        except urllib.error.URLError as url_err:
            if isinstance(url_err.reason, TimeoutError) or "timed out" in str(url_err.reason).lower():
                raise WebSearchTimeoutError(self.provider_name, timeout)
            raise WebSearchProviderUnavailableError(
                self.provider_name, f"Network error connecting to OpenAlex: {url_err.reason}"
            )
        except json.JSONDecodeError as json_err:
            raise WebSearchExecutionError(self.provider_name, f"Failed to parse OpenAlex JSON: {json_err}")

        results_data = data.get("results", [])
        if not results_data:
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

        for idx, item in enumerate(results_data, start=1):
            title = item.get("title") or item.get("display_name") or "Untitled Scholarly Work"
            doi = item.get("doi") or ""
            openalex_id = item.get("id") or f"openalex_{idx}"
            landing_url = (
                item.get("primary_location", {}).get("landing_page_url")
                or doi
                or openalex_id
            )

            # Authors
            authors = []
            for authorship in item.get("authorships", []):
                author_name = authorship.get("author", {}).get("display_name")
                if author_name:
                    authors.append(author_name)
            author_str = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")

            # Venue / Journal
            venue = (
                item.get("primary_location", {}).get("source", {}).get("display_name")
                or ""
            )

            # Abstract reconstruction
            abs_dict = item.get("abstract_inverted_index")
            reconstructed_abs = self._reconstruct_abstract(abs_dict)

            snippet_parts = []
            if author_str:
                snippet_parts.append(f"Authors: {author_str}.")
            if venue:
                snippet_parts.append(f"Venue: {venue}.")
            if reconstructed_abs:
                snippet_parts.append(f"Abstract: {reconstructed_abs[:350]}...")
            elif doi:
                snippet_parts.append(f"DOI: {doi}.")

            results.append(
                WebSearchResult(
                    result_id=f"openalex_{openalex_id.split('/')[-1]}",
                    title=title,
                    url=landing_url,
                    canonical_url=landing_url,
                    result_type="scholarly",
                    snippet=" ".join(snippet_parts),
                    source=venue or "OpenAlex",
                    publication_date=item.get("publication_date"),
                    provider=self.provider_name,
                    retrieval_timestamp=now_ts,
                    rank=idx,
                    provenance={
                        "provider": self.provider_name,
                        "openalex_id": openalex_id,
                        "doi": doi,
                        "retrieval_timestamp": now_ts,
                    },
                    metadata={
                        "cited_by_count": item.get("cited_by_count", 0),
                        "is_oa": item.get("open_access", {}).get("is_oa", False),
                        "authors": authors,
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
