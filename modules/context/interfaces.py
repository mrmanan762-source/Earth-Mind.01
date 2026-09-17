from typing import Protocol, List, Optional
from modules.context.schemas import ContextRequest, ContextItem, ContextResult


class ContextProvider(Protocol):
    """Interface for upstream context providers (Conversation, Memory, Weather, etc.)"""
    provider_name: str

    def get_context(self, request: ContextRequest) -> List[ContextItem]:
        """Fetch context items for the request."""
        ...


class CacheProvider(Protocol):
    """Interface for context caching providers."""

    def get(self, request: ContextRequest) -> Optional[ContextResult]:
        """Get cached ContextResult if hit and valid, else None."""
        ...

    def set(self, request: ContextRequest, result: ContextResult) -> bool:
        """Cache ContextResult."""
        ...


class CompressionProvider(Protocol):
    """Interface for replaceable context compression engines."""

    def compress(self, items: List[ContextItem], target_tokens: int) -> List[ContextItem]:
        """Compress context items to fit within target token budget."""
        ...
