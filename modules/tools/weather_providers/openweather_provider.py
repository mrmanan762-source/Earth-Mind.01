"""OpenWeather provider adapter for EarthMind Phase 3.

OpenWeather (https://openweathermap.org/) is a keyed provider. This adapter is
an optional, replaceable alternative to the keyless Open-Meteo provider.

Contract:
- `is_available()` returns False when no API key is configured.
- `get_weather()` raises WeatherAuthenticationError when credentials are absent,
  and never performs a live request without a valid backend key.
- Requires explicit user authorization before use (it is a paid/freemium tier).

WARNING: OpenWeather's free tier may require registration and some endpoints are
paid. This adapter makes no live call unless a key is supplied in the secure
backend environment.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.config.settings import WeatherConfig
from core.errors.exceptions import (
    WeatherAuthenticationError,
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

DEFAULT_CURRENT_ENDPOINT = "https://api.openweathermap.org/data/2.5/weather"
DEFAULT_FORECAST_ENDPOINT = "https://api.openweathermap.org/data/2.5/forecast"


class OpenWeatherProvider(IWeatherProvider):
    """Adapter for the keyed OpenWeather current-weather and forecast APIs."""

    def __init__(
        self,
        config: Optional[WeatherConfig] = None,
        api_key: Optional[str] = None,
        current_endpoint: Optional[str] = None,
        forecast_endpoint: Optional[str] = None,
        timeout: Optional[float] = None,
        user_agent: Optional[str] = None,
    ):
        cfg = config or WeatherConfig()
        self._api_key = api_key or cfg.api_key
        self._current_endpoint = current_endpoint or cfg.endpoint or DEFAULT_CURRENT_ENDPOINT
        self._forecast_endpoint = forecast_endpoint or DEFAULT_FORECAST_ENDPOINT
        self._timeout = timeout if timeout is not None else cfg.timeout
        self._user_agent = user_agent or cfg.user_agent

    @property
    def provider_name(self) -> str:
        return "openweather"

    def is_available(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    def supported_capabilities(self) -> Dict[str, Any]:
        return {
            "current_weather": True,
            "forecast": True,
            "historical": True,
            "requires_credentials": True,
            "credentials_present": self.is_available(),
            "units": ["metric", "imperial"],
        }

    def get_weather(self, request: WeatherRequest) -> WeatherResponse:
        if not self.is_available():
            raise WeatherAuthenticationError(
                self.provider_name,
                "OpenWeather API key is not configured. Set EARTHMIND_WEATHER_API_KEY "
                "in the secure backend environment.",
            )

        current = self._fetch(
            self._current_endpoint,
            {"lat": request.latitude, "lon": request.longitude, "units": "metric"},
        )
        forecast_entries: List[WeatherForecastEntry] = []
        if request.include_forecast and request.forecast_days > 0:
            forecast = self._fetch(
                self._forecast_endpoint,
                {"lat": request.latitude, "lon": request.longitude, "units": "metric"},
            )
            forecast_entries = self._normalize_forecast(forecast, request.forecast_days)

        return self._normalize_current(current, request, forecast_entries)

    def _fetch(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        query = dict(params)
        query["appid"] = self._api_key
        url = f"{endpoint}?{urllib.parse.urlencode(query)}"
        req = urllib.request.Request(
            url, headers={"User-Agent": self._user_agent, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise WeatherAuthenticationError(
                    self.provider_name, f"HTTP {exc.code}: invalid OpenWeather API key."
                ) from exc
            if exc.code == 429:
                raise WeatherProviderUnavailableError(
                    self.provider_name, "HTTP 429: OpenWeather rate limit exceeded."
                ) from exc
            raise WeatherProviderUnavailableError(
                self.provider_name, f"HTTP {exc.code}: {exc.reason}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise WeatherProviderUnavailableError(
                self.provider_name, f"Network error contacting OpenWeather: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise WeatherProviderError(
                self.provider_name, f"Malformed JSON response: {exc}"
            ) from exc

    def _normalize_current(
        self,
        data: Dict[str, Any],
        request: WeatherRequest,
        forecast_entries: List[WeatherForecastEntry],
    ) -> WeatherResponse:
        main = data.get("main")
        if not main:
            raise WeatherDataUnavailableError(
                self.provider_name, "OpenWeather response contained no observation data."
            )

        weather_list = data.get("weather") or []
        condition = weather_list[0].get("main", "").lower() if weather_list else None
        wind = data.get("wind") or {}
        observed_at = (
            datetime.fromtimestamp(data.get("dt", datetime.now().timestamp()), tz=timezone.utc).isoformat()
            if data.get("dt")
            else datetime.now(timezone.utc).isoformat()
        )

        observation = WeatherObservation(
            observed_at=observed_at,
            is_forecast=False,
            temperature_c=main.get("temp"),
            humidity_pct=main.get("humidity"),
            precipitation_mm=(data.get("rain") or {}).get("1h"),
            wind_speed_ms=wind.get("speed"),
            wind_direction_deg=wind.get("deg"),
            pressure_hpa=main.get("pressure"),
            condition=condition,
            units={
                "temperature": "celsius",
                "wind_speed": "ms",
                "precipitation": "mm",
                "humidity": "percent",
                "pressure": "hPa",
            },
            provider=self.provider_name,
            metadata={"source": "openweather current"},
        )

        return WeatherResponse(
            request_id=request.request_id,
            status=WeatherStatus.SUCCESS,
            provider_name=self.provider_name,
            latitude=data.get("coord", {}).get("lat", request.latitude),
            longitude=data.get("coord", {}).get("lon", request.longitude),
            location_name=data.get("name") or request.location_name,
            observations=[observation],
            forecast=forecast_entries,
            observed_at=observed_at,
            units=observation.units,
            provider_metadata={"provider": self.provider_name, "model": "openweather-2.5"},
        )

    def _normalize_forecast(
        self, data: Dict[str, Any], forecast_days: int
    ) -> List[WeatherForecastEntry]:
        entries: List[WeatherForecastEntry] = []
        # OpenWeather 3-hourly forecast: aggregate by day.
        daily: Dict[str, Dict[str, Any]] = {}
        for item in data.get("list", []):
            day = str(item.get("dt_txt", "")).split(" ")[0]
            if not day:
                continue
            bucket = daily.setdefault(
                day,
                {"min": None, "max": None, "precip": 0.0, "wind": 0.0, "pop": 0.0, "condition": None},
            )
            main = item.get("main") or {}
            temp_min = main.get("temp_min")
            temp_max = main.get("temp_max")
            if temp_min is not None:
                bucket["min"] = temp_min if bucket["min"] is None else min(bucket["min"], temp_min)
            if temp_max is not None:
                bucket["max"] = temp_max if bucket["max"] is None else max(bucket["max"], temp_max)
            bucket["precip"] += (item.get("rain") or {}).get("3h", 0.0)
            bucket["wind"] = max(bucket["wind"], (item.get("wind") or {}).get("speed", 0.0))
            bucket["pop"] = max(bucket["pop"], item.get("pop", 0.0))
            weather_list = item.get("weather") or []
            if weather_list and not bucket["condition"]:
                bucket["condition"] = weather_list[0].get("main", "").lower()

        for day in sorted(daily.keys())[:forecast_days]:
            bucket = daily[day]
            entries.append(
                WeatherForecastEntry(
                    forecast_for=f"{day}T00:00:00Z",
                    issued_at=datetime.now(timezone.utc).isoformat(),
                    is_forecast=True,
                    temperature_min_c=bucket["min"],
                    temperature_max_c=bucket["max"],
                    precipitation_mm=round(bucket["precip"], 2),
                    precipitation_probability_pct=round(bucket["pop"] * 100.0, 1),
                    wind_speed_ms=bucket["wind"],
                    condition=bucket["condition"],
                    units={"temperature": "celsius", "wind_speed": "ms", "precipitation": "mm"},
                    provider=self.provider_name,
                )
            )
        return entries
