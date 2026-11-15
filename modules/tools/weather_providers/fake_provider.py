"""Deterministic fake weather provider for EarthMind Phase 3 tests.

Produces reproducible weather data and can simulate provider failure modes. It
is never used in production (enforced by configuration validation).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.errors.exceptions import (
    WeatherAuthenticationError,
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


class FakeWeatherProvider(IWeatherProvider):
    """Deterministic weather provider for offline tests and development."""

    def __init__(
        self,
        simulated_status: Optional[WeatherStatus] = None,
        available: bool = True,
        fixed_observed_at: Optional[str] = None,
    ):
        self._simulated_status = simulated_status
        self._available = available
        self._fixed_observed_at = fixed_observed_at

    @property
    def provider_name(self) -> str:
        return "fake_weather"

    def is_available(self) -> bool:
        return self._available and self._simulated_status != WeatherStatus.PROVIDER_UNAVAILABLE

    def supported_capabilities(self) -> Dict[str, Any]:
        return {
            "current_weather": True,
            "forecast": True,
            "historical": False,
            "requires_credentials": False,
            "deterministic": True,
        }

    def get_weather(self, request: WeatherRequest) -> WeatherResponse:
        if self._simulated_status == WeatherStatus.PROVIDER_UNAVAILABLE:
            raise WeatherProviderUnavailableError(self.provider_name, "Simulated provider outage.")
        if self._simulated_status == WeatherStatus.AUTHENTICATION_FAILURE:
            raise WeatherAuthenticationError(self.provider_name, "Simulated credential failure.")

        observed_at = self._fixed_observed_at or datetime.now(timezone.utc).isoformat()
        observation = WeatherObservation(
            observed_at=observed_at,
            is_forecast=False,
            temperature_c=28.5,
            humidity_pct=64.0,
            precipitation_mm=0.0,
            wind_speed_ms=3.2,
            wind_direction_deg=180.0,
            pressure_hpa=1008.0,
            condition="partly_cloudy",
            units={"temperature": "celsius", "wind_speed": "ms", "precipitation": "mm"},
            provider=self.provider_name,
            metadata={"simulated": True},
        )

        forecast: List[WeatherForecastEntry] = []
        if request.include_forecast and request.forecast_days > 0:
            for day_offset in range(min(request.forecast_days, 16)):
                forecast.append(
                    WeatherForecastEntry(
                        forecast_for=f"day+{day_offset + 1}",
                        issued_at=observed_at,
                        is_forecast=True,
                        temperature_min_c=20.0 + day_offset,
                        temperature_max_c=31.0 + day_offset,
                        precipitation_mm=float(day_offset),
                        precipitation_probability_pct=20.0 + day_offset * 5,
                        wind_speed_ms=2.5 + day_offset * 0.3,
                        condition="light_rain" if day_offset % 2 else "clear",
                        units={"temperature": "celsius", "wind_speed": "ms", "precipitation": "mm"},
                        provider=self.provider_name,
                    )
                )

        return WeatherResponse(
            request_id=request.request_id,
            status=WeatherStatus.SUCCESS,
            provider_name=self.provider_name,
            latitude=request.latitude,
            longitude=request.longitude,
            location_name=request.location_name,
            observations=[observation],
            forecast=forecast,
            observed_at=observed_at,
            units=observation.units,
            provider_metadata={"provider": self.provider_name, "simulated": True},
        )
