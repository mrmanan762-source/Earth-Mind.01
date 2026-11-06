"""Wikidata SPARQL Query Service Provider Adapter for EarthMind Stage R10 Web Search.

Implements IWebSearchProvider to retrieve structured facts, entities, scientific names,
identifiers, and relationships from Wikidata.
Official SPARQL endpoint: https://query.wikidata.org/sparql

Uses SPARQL with wikibase:mwapi EntitySearch and label services to resolve entities,
descriptions, scientific names (taxon name wdt:P225), and direct Wikidata entity links.
Categorizes results as result_type='structured_fact'.
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


class WikidataSearchProvider(IWebSearchProvider):
    """Wikidata SPARQL Query Service adapter for structured agricultural and factual entity discovery."""

    def __init__(
        self,
        config: Optional[WebSearchConfig] = None,
        endpoint: Optional[str] = None,
        timeout: Optional[float] = None,
        user_agent: Optional[str] = None,
    ):
        cfg = config or WebSearchConfig()
        self._endpoint = endpoint or cfg.wikidata_endpoint
        self._timeout = timeout if timeout is not None else cfg.timeout
        self._user_agent = user_agent or cfg.user_agent
        self._max_results = cfg.wikidata_max_results

    @property
    def provider_name(self) -> str:
        return "wikidata"

    def is_available(self) -> bool:
        return bool(self._endpoint and self._endpoint.strip())

    def supported_capabilities(self) -> Dict[str, Any]:
        return {
            "structured_entity_search": True,
            "sparql_query_service": True,
            "scientific_taxonomy": True,
            "multilingual_labels": True,
            "max_results_limit": 10,
        }

    def _build_sparql_query(self, query_text: str, limit: int, language: str = "en") -> str:
        """Constructs safe SPARQL query utilizing MediaWiki search extension service on Wikidata."""
        escaped_query = (
            query_text.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", " ")
            .replace("\r", " ")
        )
        sparql = f"""SELECT ?item ?itemLabel ?itemDescription ?taxonName WHERE {{
  SERVICE wikibase:mwapi {{
      bd:serviceParam wikibase:endpoint "www.wikidata.org";
                        wikibase:api "EntitySearch";
                        mwapi:search "{escaped_query}";
                        mwapi:language "{language}".
      ?item wikibase:apiOutputItem mwapi:item.
      ?num wikibase:apiOrdinal true.
  }}
  OPTIONAL {{ ?item wdt:P225 ?taxonName. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language},en". }}
}} LIMIT {limit}"""
        return sparql

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        """Executes SPARQL query against Wikidata query service and returns normalized structured facts."""
        start_time = time.perf_counter()

        if not request.query_text or not request.query_text.strip():
            raise InvalidWebSearchRequestError("Query text cannot be empty.")

        timeout = request.timeout if request.timeout > 0 else self._timeout
        limit = min(request.max_results, self._max_results)
        lang = request.language or "en"

        sparql_query = self._build_sparql_query(request.query_text, limit=limit, language=lang)

        params: Dict[str, str] = {
            "query": sparql_query,
            "format": "json",
        }

        query_str = urllib.parse.urlencode(params)
        full_url = f"{self._endpoint}?{query_str}"

        ua = self._user_agent or "EarthMind-RAG/1.0 (+https://github.com/earthmind)"
        req = urllib.request.Request(
            full_url,
            headers={
                "User-Agent": ua,
                "Accept": "application/sparql-results+json, application/json",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
        except urllib.error.HTTPError as http_err:
            if http_err.code == 429:
                raise WebSearchRateLimitError(self.provider_name, "Wikidata SPARQL service rate limit exceeded.")
            raise WebSearchProviderUnavailableError(
                self.provider_name, f"HTTP {http_err.code}: Wikidata SPARQL API unavailable: {http_err.reason}"
            )
        except TimeoutError:
            raise WebSearchTimeoutError(self.provider_name, timeout)
        except urllib.error.URLError as url_err:
            if isinstance(url_err.reason, TimeoutError) or "timed out" in str(url_err.reason).lower():
                raise WebSearchTimeoutError(self.provider_name, timeout)
            raise WebSearchProviderUnavailableError(
                self.provider_name, f"Network error connecting to Wikidata: {url_err.reason}"
            )
        except json.JSONDecodeError as json_err:
            raise WebSearchExecutionError(
                self.provider_name, f"Failed to parse Wikidata SPARQL JSON response: {json_err}"
            )

        bindings = data.get("results", {}).get("bindings", [])
        if not bindings:
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
        seen_entities = set()

        for idx, binding in enumerate(bindings, start=1):
            item_uri = binding.get("item", {}).get("value", "")
            if not item_uri:
                continue
            qid = item_uri.rstrip("/").split("/")[-1]
            if qid in seen_entities:
                continue
            seen_entities.add(qid)

            label = binding.get("itemLabel", {}).get("value") or qid
            description = binding.get("itemDescription", {}).get("value") or ""
            taxon_name = binding.get("taxonName", {}).get("value")

            snippet_parts = []
            if label:
                snippet_parts.append(f"Entity: {label} ({qid}).")
            if taxon_name:
                snippet_parts.append(f"Taxon / Scientific name: {taxon_name}.")
            if description:
                snippet_parts.append(f"Description: {description}.")

            snippet_text = " ".join(snippet_parts)
            wikidata_url = f"https://www.wikidata.org/wiki/{qid}"

            results.append(
                WebSearchResult(
                    result_id=f"wikidata_{qid}",
                    title=f"{label} ({qid}) - Wikidata",
                    url=wikidata_url,
                    canonical_url=wikidata_url,
                    result_type="structured_fact",
                    snippet=snippet_text,
                    source="wikidata.org",
                    provider=self.provider_name,
                    retrieval_timestamp=now_ts,
                    rank=idx,
                    provenance={
                        "provider": self.provider_name,
                        "qid": qid,
                        "uri": item_uri,
                        "query": request.query_text,
                        "retrieval_timestamp": now_ts,
                    },
                    metadata={
                        "qid": qid,
                        "label": label,
                        "description": description,
                        "taxon_name": taxon_name,
                        "is_structured_fact": True,
                    },
                    request_id=request.request_id,
                )
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return WebSearchResponse(
            request_id=request.request_id,
            status=WebSearchStatus.SUCCESS if results else WebSearchStatus.EMPTY_RESULT,
            query_text=request.query_text,
            results=results,
            result_count=len(results),
            provider_name=self.provider_name,
            execution_time_ms=elapsed_ms,
        )
