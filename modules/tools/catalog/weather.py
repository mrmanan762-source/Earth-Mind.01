"""Weather tool for EarthMind Phase 3.

Retrieves current weather and forecast information relevant to agricultural
requests through a replaceable provider adapter. The default provider is the
free, keyless Open-Meteo API; a keyed OpenWeather adapter is available when
explicitly configured and authorized.

The tool:
- Requires latitude/longitude input.
- Preserves observation and forecast timestamps.
- Preserves units and provider metadata.
- Distinguishes observed weather from forecast information (explicit flags).
- Handles unavailable or stale data explicitly (is_stale + stale_reason).
- Never invents weather data.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.config.settings import WeatherConfig, settings
from core.errors.exceptions import (
    InvalidToolRequestError,
    ToolUnavailableError,
    ToolValidationError,
)
from core.schemas.tools import (
    ToolDefinition,
    ToolExecutionConfig,
    ToolPermission,
    ToolSourceReference,
)
from core.schemas.weather import WeatherRequest, WeatherResponse, WeatherStatus
from modules.tools.weather_providers.fake_provider import FakeWeatherProvider
from modules.tools.weather_providers.open_meteo_provider import OpenMeteoWeatherProvider
from modules.tools.weather_providers.openweather_provider import OpenWeatherProvider

_MAX_FORECAST_DAYS_CEILING = 16


class WeatherTool:
    """Tool adapter exposing replaceable weather providers."""

    tool_id = "weather"

    def __init__(
        self,
        provider: Optional[Any] = None,
        config: Optional[WeatherConfig] = None,
    ):
        self._config = config or getattr(settings, "weather", WeatherConfig())
        self._provider = provider or self._resolve_provider(self._config)

    def _resolve_provider(self, config: WeatherConfig) -> Any:
        name = (config.provider or "open_meteo").lower().strip()
        if name in ("open_meteo", "openmeteo", "open-meteo"):
            return OpenMeteoWeatherProvider(config=config)
        if name in ("openweather", "open_weather"):
            return OpenWeatherProvider(config=config)
        if name in ("fake", "mock"):
            return FakeWeatherProvider()
        # Unknown provider name -> default to the free keyless provider.
        return OpenMeteoWeatherProvider(config=config)

    def is_available(self) -> bool:
        try:
            return bool(self._provider.is_available())
        except Exception:
            return False

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_id=self.tool_id,
            name="Weather",
            description=(
                "Retrieve current observed weather and forecast information for a "
                "location, preserving timestamps, units and provider metadata. "
                "Distinguishes observed weather from forecast data."
            ),
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "minimum": -90, "maximum": 90},
                    "longitude": {"type": "number", "minimum": -180, "maximum": 180},
                    "location_name": {"type": "string"},
                    "forecast_days": {"type": "integer", "minimum": 0, "maximum": _MAX_FORECAST_DAYS_CEILING},
                    "include_forecast": {"type": "boolean"},
                    "units": {"type": "string", "enum": ["metric", "imperial"]},
                },
                "required": ["latitude", "longitude"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "provider_name": {"type": "string"},
                    "observations": {"type": "array"},
                    "forecast": {"type": "array"},
                    "observed_at": {"type": ["string", "null"]},
                    "is_stale": {"type": "boolean"},
                    "units": {"type": "object"},
                },
            },
            required_permissions=[ToolPermission.WEATHER_DATA, ToolPermission.EXTERNAL_NETWORK],
            execution=ToolExecutionConfig(
                timeout_seconds=float(self._config.timeout or 10.0),
                max_retries=1,
                idempotent=True,
                max_concurrency=int(self._config.max_concurrent_requests or 5),
                rate_limit_per_minute=self._config.rate_limit_per_minute,
                max_request_bytes=4096,
                max_result_bytes=131072,
            ),
            error_contract=[
                "INVALID_TOOL_REQUEST",
                "TOOL_VALIDATION_ERROR",
                "TOOL_UNAVAILABLE",
                "TOOL_EXECUTION_ERROR",
                "TOOL_TIMEOUT",
                "WEATHER_PROVIDER_ERROR",
            ],
            tags=["weather", "external", "agriculture"],
        )

    def validate_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        latitude = arguments.get("latitude")
        longitude = arguments.get("longitude")
        if isinstance(latitude, bool) or not isinstance(latitude, (int, float)):
            raise InvalidToolRequestError("'latitude' must be a number.", tool_id=self.tool_id)
        if isinstance(longitude, bool) or not isinstance(longitude, (int, float)):
            raise InvalidToolRequestError("'longitude' must be a number.", tool_id=self.tool_id)
        if not (-90.0 <= float(latitude) <= 90.0):
            raise ToolValidationError("'latitude' must be between -90 and 90.", tool_id=self.tool_id)
        if not (-180.0 <= float(longitude) <= 180.0):
            raise ToolValidationError("'longitude' must be between -180 and 180.", tool_id=self.tool_id)

        cleaned: Dict[str, Any] = {
            "latitude": float(latitude),
            "longitude": float(longitude),
        }

        location_name = arguments.get("location_name")
        if location_name is not None and not isinstance(location_name, str):
            raise ToolValidationError("'location_name' must be a string.", tool_id=self.tool_id)
        cleaned["location_name"] = location_name.strip() if isinstance(location_name, str) else None

        forecast_days = arguments.get("forecast_days", self._config.forecast_days)
        if isinstance(forecast_days, bool) or not isinstance(forecast_days, int):
            raise ToolValidationError("'forecast_days' must be an integer.", tool_id=self.tool_id)
        cleaned["forecast_days"] = max(0, min(forecast_days, _MAX_FORECAST_DAYS_CEILING))

        cleaned["include_forecast"] = bool(arguments.get("include_forecast", True))

        units = arguments.get("units", self._config.units)
        if units not in ("metric", "imperial"):
            raise ToolValidationError("'units' must be 'metric' or 'imperial'.", tool_id=self.tool_id)
        cleaned["units"] = units
        return cleaned

    def execute(self, arguments: Dict[str, Any], request) -> Dict[str, Any]:
        weather_request = WeatherRequest(
            request_id=request.request_id,
            latitude=arguments["latitude"],
            longitude=arguments["longitude"],
            location_name=arguments.get("location_name"),
            forecast_days=arguments.get("forecast_days", self._config.forecast_days),
            include_forecast=arguments.get("include_forecast", True),
            timeout=float(self._config.timeout or 10.0),
            units=arguments.get("units", "metric"),
        )

        response: WeatherResponse = self._provider.get_weather(weather_request)

        # Explicit staleness evaluation (never silently present stale data as fresh).
        is_stale, stale_reason = self._evaluate_staleness(response.observed_at)
        response.is_stale = is_stale
        response.stale_reason = stale_reason

        observations = [obs.model_dump(mode="json") for obs in response.observations]
        forecast = [entry.model_dump(mode="json") for entry in response.forecast]

        sources: List[Dict[str, Any]] = []
        for obs in response.observations:
            sources.append(
                ToolSourceReference(
                    source_type="weather",
                    title=f"{response.provider_name} observation",
                    provider=response.provider_name,
                    observed_at=obs.observed_at,
                    is_forecast=False,
                    metadata={"latitude": response.latitude, "longitude": response.longitude},
                ).model_dump()
            )
        for entry in response.forecast:
            sources.append(
                ToolSourceReference(
                    source_type="weather",
                    title=f"{response.provider_name} forecast",
                    provider=response.provider_name,
                    observed_at=entry.forecast_for,
                    is_forecast=True,
                    metadata={},
                ).model_dump()
            )

        warnings: List[str] = list(response.warnings)
        if is_stale and stale_reason:
            warnings.append(stale_reason)

        payload = {
            "provider_name": response.provider_name,
            "latitude": response.latitude,
            "longitude": response.longitude,
            "location_name": response.location_name,
            "observations": observations,
            "forecast": forecast,
            "observed_at": response.observed_at,
            "retrieved_at": response.retrieved_at,
            "is_stale": response.is_stale,
            "stale_reason": response.stale_reason,
            "units": response.units,
            "provider_metadata": response.provider_metadata,
            "status": response.status.value,
        }
        if response.error_message:
            payload["error_message"] = response.error_message

        return {
            "__tool_result__": True,
            "payload": payload,
            "sources": sources,
            "warnings": warnings,
            "partial": response.status == WeatherStatus.PARTIAL,
        }

    def _evaluate_staleness(self, observed_at: Optional[str]):
        if not observed_at:
            return True, "Observation timestamp is missing; freshness cannot be confirmed."
        try:
            parsed = observed_at.replace("Z", "+00:00")
            observed_dt = datetime.fromisoformat(parsed)
            if observed_dt.tzinfo is None:
                observed_dt = observed_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return True, f"Observation timestamp '{observed_at}' is not parseable; freshness unknown."

        age_minutes = (datetime.now(timezone.utc) - observed_dt).total_seconds() / 60.0
        if age_minutes > self._config.stale_after_minutes:
            return True, (
                f"Observation is stale: age {age_minutes:.0f} minutes exceeds "
                f"{self._config.stale_after_minutes} minute freshness window."
            )
        return False, None
