"""Generic IRerankerProvider Interface for EarthMind Stage R8 Reranking."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.schemas.rerank import RerankScoreResult


@runtime_checkable
class IRerankerProvider(Protocol):
    """Generic, provider-agnostic interface for document/candidate reranking."""

    def rerank(
        self,
        query_text: str,
        documents: List[Dict[str, Any]],
        top_k: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> List["RerankScoreResult"]:
        """Compute relevance scores for a query across a list of candidate documents.

        Args:
            query_text: The user query string.
            documents: List of document dictionaries, each containing at least
                       'candidate_id' (str) and 'text' (str).
            top_k: Optional integer limit on scored results returned.
            timeout: Optional per-request execution timeout in seconds.

        Returns:
            List of RerankScoreResult containing candidate_id and computed score.
        """
        ...

    def is_available(self) -> bool:
        """Return operational availability status of the reranker provider."""
        ...

    def get_provider_info(self) -> Dict[str, Any]:
        """Return provider identification, model details, and capabilities."""
        ...
