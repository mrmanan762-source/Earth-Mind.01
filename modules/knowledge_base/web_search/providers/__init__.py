"""Web Search Provider Adapters package."""

from modules.knowledge_base.web_search.providers.fake_provider import FakeWebSearchProvider
from modules.knowledge_base.web_search.providers.api_provider import APIWebSearchProvider

__all__ = [
    "FakeWebSearchProvider",
    "APIWebSearchProvider",
]
