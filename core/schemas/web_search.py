"""Data Contracts for EarthMind Stage R10 Web Search Integration.

Defines Pydantic models for:
- WebSearchStatus: Execution status enum for search operations
- WebSearchResult: Single normalized web search candidate
- WebSearchRequest: Input search request payload from R9/RAG
- WebSearchResponse: Output search payload ready for Stage R11 Evidence Builder
"""

from enum import Enum
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from core.schemas.query import RetrievalQuery


class WebSearchStatus(str, Enum):
    """Execution status for R10 web search operation."""
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    INVALID_REQUEST = "INVALID_REQUEST"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    EMPTY_RESULT = "EMPTY_RESULT"


class WebSearchResult(BaseModel):
    """Normalized search candidate result produced by Stage R10."""
    result_id: str = Field(..., description="Unique provider or normalized result identifier")
    title: str = Field(..., description="Page or snippet title")
    url: str = Field(..., description="Canonical source web URL")
    snippet: str = Field(..., description="Content text excerpt or snippet")
    source: Optional[str] = Field(None, description="Domain name or publisher name")
    publication_date: Optional[str] = Field(None, description="Publication timestamp string if available")
    last_updated_date: Optional[str] = Field(None, description="Last updated timestamp string if available")
    provider: str = Field(..., description="Web search provider identifier")
    retrieval_timestamp: float = Field(default_factory=time.time, description="Unix timestamp when search was executed")
    rank: int = Field(1, description="1-based position in search provider output")
    score: Optional[float] = Field(None, description="Provider-assigned relevance score if available")
    content: Optional[str] = Field(None, description="Full page extract or body content if available")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Lineage and metadata provenance")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional result metadata")
    request_id: Optional[str] = Field(None, description="Correlation / request tracing ID")


class WebSearchRequest(BaseModel):
    """Incoming request payload for Stage R10 Web Search Engine."""
    query_text: str = Field(..., description="Search query string")
    request_id: Optional[str] = Field(None, description="Correlation / request tracing ID")
    max_results: int = Field(10, description="Maximum number of search results requested")
    language: Optional[str] = Field("en", description="Language code hint")
    region: Optional[str] = Field(None, description="Regional or geographic context")
    agricultural_metadata: Optional[Dict[str, Any]] = Field(None, description="Extracted agricultural fields from R9")
    filters: Optional[Dict[str, Any]] = Field(None, description="Search filter options")
    timeout: float = Field(10.0, description="Per-request execution timeout in seconds")
    user_context: Optional[Dict[str, Any]] = Field(None, description="Upstream user/farm context")

    @classmethod
    def from_retrieval_query(
        cls,
        retrieval_query: "RetrievalQuery",
        max_results: int = 10,
        timeout: float = 10.0,
    ) -> "WebSearchRequest":
        """
        Bridge factory method converting a Stage R9 RetrievalQuery into a WebSearchRequest.
        """
        agri_meta = None
        lang = "en"
        region = None
        if retrieval_query.metadata:
            lang = retrieval_query.metadata.language or "en"
            if retrieval_query.metadata.agricultural_metadata:
                agri_meta = retrieval_query.metadata.agricultural_metadata.model_dump(exclude_none=True)
                region = retrieval_query.metadata.agricultural_metadata.region or retrieval_query.metadata.agricultural_metadata.state

        return cls(
            query_text=retrieval_query.normalized_query or retrieval_query.original_query,
            request_id=retrieval_query.request_id,
            max_results=max_results,
            language=lang,
            region=region,
            agricultural_metadata=agri_meta,
            timeout=timeout,
        )


class WebSearchResponse(BaseModel):
    """Output payload from Stage R10 Web Search, ready for Stage R11 Evidence Builder."""
    request_id: Optional[str] = Field(None, description="Correlation / request tracing ID")
    status: WebSearchStatus = Field(WebSearchStatus.SUCCESS, description="Execution status enum")
    query_text: str = Field(..., description="Query string used for search")
    results: List[WebSearchResult] = Field(default_factory=list, description="Normalized search results")
    result_count: int = Field(0, description="Total number of results returned")
    provider_name: str = Field("unknown", description="Web search provider identifier used")
    execution_time_ms: float = Field(0.0, description="Latency in milliseconds")
    error_message: Optional[str] = Field(None, description="Error details if status is non-SUCCESS")
    warnings: List[str] = Field(default_factory=list, description="Operational warning messages")
    trace_info: Dict[str, Any] = Field(default_factory=dict, description="Traceability audit trail dictionary")
