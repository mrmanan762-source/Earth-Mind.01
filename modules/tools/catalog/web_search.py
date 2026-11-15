"""Web Search tool for EarthMind Phase 3.

Exposes the existing Stage R10 web search subsystem (Tavily primary, Gemini
Google Search Grounding secondary, plus supplementary public providers) through
the controlled tool interface. This tool is a thin adapter: it does NOT
re-implement search, resilience, rate limiting or provider fallback — those
already live in `modules.knowledge_base.web_search`.

Provider adapters are replaceable: the tool accepts an injected
`WebSearchEngine` (or provider) for testing and future substitution.

Requirements honoured:
- Preserve source titles, URLs, snippets and publication dates when available.
- Preserve source provenance for downstream evidence handling.
- Avoid presenting search snippets as verified scientific conclusions
  (results carry an explicit provenance disclaimer).
- Never make live API calls without valid backend credentials: the underlying
  Tavily/Gemini providers raise WebSearchAuthenticationError when unconfigured.
"""

from typing import Any, Dict, List, Optional

from core.config.settings import WebSearchConfig, settings
from core.errors.exceptions import (
    InvalidToolRequestError,
    ToolExecutionError,
    ToolUnavailableError,
    ToolValidationError,
)
from core.schemas.tools import (
    ToolDefinition,
    ToolExecutionConfig,
    ToolPermission,
    ToolSourceReference,
)
from core.schemas.web_search import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchStatus,
)

_MAX_QUERY_LENGTH = 500
_MAX_RESULTS_CEILING = 20

_STATUS_DISCLAIMER = (
    "Search snippets are unverified provider excerpts, not confirmed scientific "
    "conclusions. Treat them as candidate evidence requiring validation."
)


class WebSearchTool:
    """Tool adapter over the EarthMind web search engine."""

    tool_id = "web_search"

    def __init__(self, engine: Optional[Any] = None, config: Optional[WebSearchConfig] = None):
        self._config = config or getattr(settings, "web_search", WebSearchConfig())
        self._engine = engine
        self._engine_error: Optional[str] = None

    # -- lazy engine construction (backend credentials only) ---------------

    def _get_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        try:
            from modules.knowledge_base.web_search.engine import WebSearchEngine

            self._engine = WebSearchEngine(config=self._config)
        except Exception as exc:  # pragma: no cover - defensive
            self._engine_error = str(exc)
            raise ToolExecutionError(
                self.tool_id, f"Web search engine unavailable: {exc}"
            ) from exc
        return self._engine

    def is_available(self) -> bool:
        """The tool is available when at least one configured provider has credentials."""
        if self._engine is not None:
            try:
                primary = getattr(self._engine, "provider", None)
                if primary is not None and hasattr(primary, "is_available"):
                    return bool(primary.is_available())
                return True
            except Exception:
                return True

        # Without an injected engine, availability depends on configured credentials.
        provider = (self._config.provider or "fake").lower().strip()
        if provider in ("fake", "mock"):
            return True
        if provider == "tavily":
            return bool(self._config.tavily_api_key and self._config.tavily_api_key.strip())
        if provider in ("gemini_grounding", "gemini"):
            return bool(self._config.gemini_api_key and self._config.gemini_api_key.strip())
        if provider == "brave":
            return bool(self._config.brave_api_key and self._config.brave_api_key.strip())
        return bool(self._config.api_key and self._config.api_key.strip())

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_id=self.tool_id,
            name="Web Search",
            description=(
                "Retrieve current external information from the web when EarthMind "
                "needs information that may change over time. Uses Tavily as the "
                "primary provider and Gemini Google Search Grounding as the secondary "
                "provider, with source provenance preserved."
            ),
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query text"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": _MAX_RESULTS_CEILING},
                    "language": {"type": "string", "description": "Language code hint, e.g. 'en', 'hi'"},
                    "region": {"type": "string", "description": "Regional/geographic context"},
                    "search_mode": {
                        "type": "string",
                        "enum": ["standard", "academic", "encyclopedic", "climate", "multi"],
                    },
                    "include_scholarly": {"type": "boolean"},
                    "include_agroclimatology": {"type": "boolean"},
                },
                "required": ["query"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "result_count": {"type": "integer"},
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "url": {"type": "string"},
                                "snippet": {"type": "string"},
                                "publication_date": {"type": ["string", "null"]},
                                "provider": {"type": "string"},
                            },
                        },
                    },
                    "provider_name": {"type": "string"},
                    "disclaimer": {"type": "string"},
                },
            },
            required_permissions=[ToolPermission.WEB_SEARCH, ToolPermission.EXTERNAL_NETWORK],
            execution=ToolExecutionConfig(
                timeout_seconds=float(self._config.timeout or 10.0),
                max_retries=1,
                idempotent=True,
                max_concurrency=int(self._config.max_concurrent_requests or 5),
                rate_limit_per_minute=self._config.rate_limits_per_minute.get("tavily"),
                max_request_bytes=8192,
                max_result_bytes=262144,
            ),
            error_contract=[
                "INVALID_TOOL_REQUEST",
                "TOOL_VALIDATION_ERROR",
                "TOOL_UNAVAILABLE",
                "TOOL_EXECUTION_ERROR",
                "TOOL_TIMEOUT",
                "TOOL_RATE_LIMITED",
            ],
            tags=["web", "external", "provenance"],
        )

    def validate_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        query = arguments.get("query", arguments.get("query_text"))
        if not isinstance(query, str) or not query.strip():
            raise InvalidToolRequestError("'query' must be a non-empty string.", tool_id=self.tool_id)
        if len(query) > _MAX_QUERY_LENGTH:
            raise ToolValidationError(
                f"'query' exceeds {_MAX_QUERY_LENGTH} characters.", tool_id=self.tool_id
            )

        cleaned: Dict[str, Any] = {"query": query.strip()}

        max_results = arguments.get("max_results", self._config.max_results)
        if not isinstance(max_results, int) or isinstance(max_results, bool):
            raise ToolValidationError("'max_results' must be an integer.", tool_id=self.tool_id)
        cleaned["max_results"] = max(1, min(max_results, _MAX_RESULTS_CEILING))

        language = arguments.get("language", "en")
        if not isinstance(language, str):
            raise ToolValidationError("'language' must be a string.", tool_id=self.tool_id)
        cleaned["language"] = language.strip() or "en"

        region = arguments.get("region")
        if region is not None and not isinstance(region, str):
            raise ToolValidationError("'region' must be a string.", tool_id=self.tool_id)
        cleaned["region"] = region.strip() if isinstance(region, str) else None

        search_mode = arguments.get("search_mode", "standard")
        if search_mode not in ("standard", "academic", "encyclopedic", "climate", "multi"):
            raise ToolValidationError("'search_mode' is not supported.", tool_id=self.tool_id)
        cleaned["search_mode"] = search_mode

        cleaned["include_scholarly"] = bool(arguments.get("include_scholarly", False))
        cleaned["include_agroclimatology"] = bool(arguments.get("include_agroclimatology", False))
        return cleaned

    def execute(self, arguments: Dict[str, Any], request) -> Dict[str, Any]:
        engine = self._get_engine()

        search_request = WebSearchRequest(
            query_text=arguments["query"],
            request_id=request.request_id,
            max_results=arguments["max_results"],
            language=arguments.get("language", "en"),
            region=arguments.get("region"),
            search_mode=arguments.get("search_mode", "standard"),
            include_scholarly=arguments.get("include_scholarly", False),
            include_agroclimatology=arguments.get("include_agroclimatology", False),
            timeout=float(self._config.timeout or 10.0),
        )

        response: WebSearchResponse = engine.search(search_request)

        results: List[Dict[str, Any]] = []
        sources: List[Dict[str, Any]] = []
        for item in response.results:
            results.append(
                {
                    "title": item.title,
                    "url": item.url,
                    "canonical_url": item.canonical_url,
                    "snippet": item.snippet,
                    "source": item.source,
                    "publication_date": item.publication_date,
                    "last_updated_date": item.last_updated_date,
                    "provider": item.provider,
                    "result_type": item.result_type,
                    "rank": item.rank,
                    "score": item.score,
                }
            )
            sources.append(
                ToolSourceReference(
                    source_type="web",
                    title=item.title,
                    url=item.canonical_url or item.url,
                    provider=item.provider,
                    publication_date=item.publication_date,
                    metadata={"result_id": item.result_id, "rank": item.rank},
                ).model_dump()
            )

        partial = response.status == WebSearchStatus.PARTIAL
        payload = {
            "query": response.query_text,
            "result_count": response.result_count,
            "results": results,
            "provider_name": response.provider_name,
            "provider_statuses": {k: v.value for k, v in response.provider_statuses.items()},
            "status": response.status.value,
            "disclaimer": _STATUS_DISCLAIMER,
        }
        if response.error_message:
            payload["error_message"] = response.error_message

        return {
            "__tool_result__": True,
            "payload": payload,
            "sources": sources,
            "warnings": list(response.warnings) + [_STATUS_DISCLAIMER],
            "partial": partial,
        }
