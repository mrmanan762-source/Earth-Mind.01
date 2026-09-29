"""Generic IWebSearchProvider Interface for EarthMind Stage R10 Web Search Integration."""

from typing import Any, Dict, Protocol, runtime_checkable
from core.schemas.web_search import WebSearchRequest, WebSearchResponse


@runtime_checkable
class IWebSearchProvider(Protocol):
    """Generic, provider-agnostic interface for external web search retrieval."""

    @property
    def provider_name(self) -> str:
        """Return the unique identifier string of the search provider."""
        ...

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        """Execute a web search query and return a normalized WebSearchResponse.

        Args:
            request: Structured WebSearchRequest containing query and context.

        Returns:
            Normalized WebSearchResponse containing WebSearchResult list and status.
        """
        ...

    def is_available(self) -> bool:
        """Return operational availability status of the web search provider."""
        ...

    def supported_capabilities(self) -> Dict[str, Any]:
        """Return capabilities supported by provider (e.g., safe_search, filtering, region)."""
        ...
