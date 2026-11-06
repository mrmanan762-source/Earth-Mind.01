"""Providers package for EarthMind Stage R10 Web Search."""

from modules.knowledge_base.web_search.providers.api_provider import APIWebSearchProvider
from modules.knowledge_base.web_search.providers.brave_provider import BraveWebSearchProvider
from modules.knowledge_base.web_search.providers.fake_provider import FakeWebSearchProvider
from modules.knowledge_base.web_search.providers.gemini_grounding_provider import GeminiGroundingSearchProvider
from modules.knowledge_base.web_search.providers.nasa_power_provider import NasaPowerSearchProvider
from modules.knowledge_base.web_search.providers.scholarly_provider import (
    CrossrefSearchProvider,
    OpenAlexSearchProvider,
)
from modules.knowledge_base.web_search.providers.tavily_provider import TavilySearchProvider
from modules.knowledge_base.web_search.providers.wikidata_provider import WikidataSearchProvider
from modules.knowledge_base.web_search.providers.wikipedia_provider import WikipediaSearchProvider

__all__ = [
    "IWebSearchProvider",
    "APIWebSearchProvider",
    "BraveWebSearchProvider",
    "FakeWebSearchProvider",
    "CrossrefSearchProvider",
    "OpenAlexSearchProvider",
    "WikipediaSearchProvider",
    "WikidataSearchProvider",
    "NasaPowerSearchProvider",
    "TavilySearchProvider",
    "GeminiGroundingSearchProvider",
]
