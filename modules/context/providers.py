from typing import Dict, List, Optional
from modules.context.interfaces import CacheProvider, CompressionProvider, ContextProvider
from modules.context.schemas import ContextItem, ContextRequest, ContextResult


class InMemoryCacheProvider(CacheProvider):
    """In-memory cache provider implementation for B2 Context Manager."""

    def __init__(self):
        self._cache: Dict[str, ContextResult] = {}

    def get(self, request: ContextRequest) -> Optional[ContextResult]:
        return self._cache.get(request.request_id)

    def set(self, request: ContextRequest, result: ContextResult) -> bool:
        self._cache[request.request_id] = result
        return True

    def clear(self) -> None:
        self._cache.clear()


class SimpleCompressionProvider(CompressionProvider):
    """
    Standard replaceable context compression provider.
    Reduces token counts of optional context items to fit target token budget.
    """

    def compress(self, items: List[ContextItem], target_tokens: int) -> List[ContextItem]:
        current_total = sum(item.token_count for item in items)
        if current_total <= target_tokens:
            return items

        compressed_items: List[ContextItem] = []
        for item in items:
            item_copy = item.model_copy(deep=True)
            # Truncate content string if string
            if isinstance(item_copy.content, str) and len(item_copy.content) > 100:
                truncated_length = max(50, len(item_copy.content) // 2)
                item_copy.content = item_copy.content[:truncated_length] + "... [compressed]"
                item_copy.token_count = max(1, item_copy.token_count // 2)
                item_copy.is_compressed = True
            compressed_items.append(item_copy)

        return compressed_items


class DictContextProvider(ContextProvider):
    """
    In-memory dictionary-backed ContextProvider for tests and static context sources.
    """

    def __init__(self, provider_name: str, items: List[ContextItem]):
        self.provider_name = provider_name
        self._items = items

    def get_context(self, request: ContextRequest) -> List[ContextItem]:
        return [item.model_copy(deep=True) for item in self._items]
