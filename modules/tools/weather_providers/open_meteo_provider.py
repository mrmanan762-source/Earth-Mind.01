"""Open-Meteo weather provider adapter for EarthMind Phase 3.

Open-Meteo (https://open-meteo.com/) is a free, public, keyless weather API.
It is the default weather provider because it requires no credentials and
therefore incurs no cost. The adapter never fabricates data: when the upstream
API is unreachable or returns an error, it raises a structured WeatherProviderError.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.config.settings import WeatherConfig
from core.errors.exceptions import (
    WeatherDataUnavailableError,
    WeatherProviderError,
    WeatherProviderUnavailableError,
)
from core.interfaces.weather import IWeatherProvider
from core.schemas.weather import (
    WeatherForecastEntry,
    WeatherObservation,
    WeatherRequest,
    WeatherResponse,
    WeatherStatus,
)

DEFAULT_ENDPOINT = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes (subset) -> short condition label.
_WMO_CONDITIONS = {
    0: "clear", 1: "mainly_clear", 2: "partly_cloudy", 3: "overcast",
    45: "fog", 48: "depositing_rime_fog",
    51: "light_drizzle", 53: "drizzle", 55: "dense_drizzle",
    61: "light_rain", 63: "rain", 65: "heavy_rain",
    71: "light_snow", 73: "snow", 75: "heavy_snow",
    80: "rain_showers", 81: "rain_showers", 82: "violent_rain_showers",
    95: "thunderstorm", 96: "thunderstorm_hail", 99: "thunderstorm_hail",
}


class OpenMeteoWeatherProvider(IWeatherProvider):
    """Adapter for the free, keyless Open-Meteo forecast API."""

    def __init__(
        self,
        config: Optional[WeatherConfig] = None,
        endpoint: Optional[str] = None,
        timeout: Optional[float] = None,
        user_agent: Optional[str] = None,
    ):
        cfg = config or WeatherConfig()
        self._endpoint = endpoint or cfg.endpoint or DEFAULT_ENDPOINT
        self._timeout = timeout if timeout is not None else cfg.timeout
        self._user_agent = user_agent or cfg.user_agent

    @property
    def provider_name(self) -> str:
        return "open_meteo"

    def is_available(self) -> bool:
        # Free, keyless provider: available whenever an endpoint is configured.
        return bool(self._endpoint and self._endpoint.strip())

    def supported_capabilities(self) -> Dict[str, Any]:
        return {
            "current_weather": True,
            "forecast": True,
            "historical": False,
            "requires_credentials": False,
            "units": ["metric", "imperial"],
            "max_forecast_days": 16,
        }

    def get_weather(self, request: WeatherRequest) -> WeatherResponse:
        params = {
            "latitude": request.latitude,
            "longitude": request.longitude,
            "current": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "precipitation",
                    "wind_speed_10m",
                    "wind_direction_10m",
                    "surface_pressure",
                    "weather_code",
                ]
            ),
            "timezone": "UTC",
        }

        if request.include_forecast and request.forecast_days > 0:
            params["daily"] = ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "precipitation_probability_max",
                    "wind_speed_10m_max",
                ]
            )
            params["forecast_days"] = min(request.forecast_days, 16)

        if request.units == "imperial":
            params["temperature_unit"] = "fahrenheit"
            params["wind_speed_unit"] = "mph"
            params["precipitation_unit"] = "inch"

        url = f"{self._endpoint}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url, headers={"User-Agent": self._user_agent, "Accept": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=request.timeout or self._timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise WeatherProviderUnavailableError(
                    self.provider_name, f"HTTP 429: rate limited by Open-Meteo ({exc.reason})."
                ) from exc
            raise WeatherProviderUnavailableError(
                self.provider_name, f"HTTP {exc.code}: {exc.reason}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise WeatherProviderUnavailableError(
                self.provider_name, f"Network error contacting Open-Meteo: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise WeatherProviderError(
                self.provider_name, f"Malformed JSON response: {exc}"
            ) from exc

        return self._normalize(data, request)

    def _normalize(self, data: Dict[str, Any], request: WeatherRequest) -> WeatherResponse:
        current = data.get("current")
        if not current:
            raise WeatherDataUnavailableError(
                self.provider_name, "Open-Meteo response contained no current observation."
            )

        temp_unit = "fahrenheit" if request.units == "imperial" else "celsius"
        wind_unit = "mph" if request.units == "imperial" else "ms"
        precip_unit = "inch" if request.units == "imperial" else "mm"

        observed_at = current.get("time") or datetime.now(timezone.utc).isoformat()
        if isinstance(observed_at, str) and "T" not in observed_at:
            observed_at = f"{observed_at}T00:00:00Z"

        code = current.get("weather_code")
        observation = WeatherObservation(
            observed_at=observed_at,
            is_forecast=False,
            temperature_c=current.get("temperature_2m"),
            humidity_pct=current.get("relative_humidity_2m"),
            precipitation_mm=current.get("precipitation"),
            wind_speed_ms=current.get("wind_speed_10m"),
            wind_direction_deg=current.get("wind_direction_10m"),
            pressure_hpa=current.get("surface_pressure"),
            condition=_WMO_CONDITIONS.get(code, "unknown"),
            units={
                "temperature": temp_unit,
                "wind_speed": wind_unit,
                "precipitation": precip_unit,
                "humidity": "percent",
                "pressure": "hPa",
            },
            provider=self.provider_name,
            metadata={"weather_code": code, "source": "open-meteo current"},
        )

        forecast_entries: List[WeatherForecastEntry] = []
        daily = data.get("daily") or {}
        times = daily.get("time") or []
        for idx, day in enumerate(times):
            forecast_entries.append(
                WeatherForecastEntry(
                    forecast_for=f"{day}T00:00:00Z",
                    issued_at=datetime.now(timezone.utc).isoformat(),
                    is_forecast=True,
                    temperature_min_c=_safe_index(daily.get("temperature_2m_min"), idx),
                    temperature_max_c=_safe_index(daily.get("temperature_2m_max"), idx),
                    precipitation_mm=_safe_index(daily.get("precipitation_sum"), idx),
                    precipitation_probability_pct=_safe_index(
                        daily.get("precipitation_probability_max"), idx
                    ),
                    wind_speed_ms=_safe_index(daily.get("wind_speed_10m_max"), idx),
                    condition=_WMO_CONDITIONS.get(_safe_index(daily.get("weather_code"), idx), "unknown"),
                    units={
                        "temperature": temp_unit,
                        "wind_speed": wind_unit,
                        "precipitation": precip_unit,
                    },
                    provider=self.provider_name,
                )
            )

        return WeatherResponse(
            request_id=request.request_id,
            status=WeatherStatus.SUCCESS,
            provider_name=self.provider_name,
            latitude=data.get("latitude", request.latitude),
            longitude=data.get("longitude", request.longitude),
            location_name=request.location_name,
            observations=[observation],
            forecast=forecast_entries,
            observed_at=observed_at,
            units=observation.units,
            provider_metadata={
                "provider": self.provider_name,
                "timezone": data.get("timezone", "UTC"),
                "model": "open-meteo-forecast",
            },
        )


def _safe_index(values: Optional[List[Any]], idx: int) -> Any:
    if not values or idx >= len(values):
        return None
    return values[idx]
