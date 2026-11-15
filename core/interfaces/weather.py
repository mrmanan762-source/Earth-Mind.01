"""Generic weather provider interface for EarthMind Phase 3.

Mirrors the existing `IWebSearchProvider` boundary so weather providers are
replaceable and independently testable.
"""

from typing import Any, Dict, Protocol, runtime_checkable

from core.schemas.weather import WeatherRequest, WeatherResponse


@runtime_checkable
class IWeatherProvider(Protocol):
    """Provider-agnostic interface for external weather retrieval."""

    @property
    def provider_name(self) -> str:
        """Return the unique identifier string of the weather provider."""
        ...

    def is_available(self) -> bool:
        """Return operational availability status of the weather provider."""
        ...

    def supported_capabilities(self) -> Dict[str, Any]:
        """Return capabilities supported by the provider (forecast, history, units)."""
        ...

    def get_weather(self, request: WeatherRequest) -> WeatherResponse:
        """Fetch current weather and/or forecast and return a normalized response."""
        ...
