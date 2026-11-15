"""Data contracts for EarthMind Phase 3 weather retrieval.

Defines provider-agnostic weather request/observation/forecast/response models
used by the Weather tool and its replaceable provider adapters. Observed weather
is kept strictly distinct from forecast information, and provider metadata,
units and timestamps are preserved for downstream provenance handling.
"""

from datetime import datetime, timezone
from enum import Enum
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WeatherStatus(str, Enum):
    """Execution status for a weather retrieval operation."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    INVALID_REQUEST = "INVALID_REQUEST"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    RATE_LIMITED = "RATE_LIMITED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    PROVIDER_ERROR = "PROVIDER_ERROR"


class WeatherObservation(BaseModel):
    """A single observed weather measurement at a point in time."""

    observed_at: str = Field(..., description="ISO 8601 UTC timestamp of the observation")
    is_forecast: bool = Field(False, description="Always False for observed weather")
    temperature_c: Optional[float] = Field(None, description="Air temperature in degrees Celsius")
    humidity_pct: Optional[float] = Field(None, ge=0.0, le=100.0, description="Relative humidity percentage")
    precipitation_mm: Optional[float] = Field(None, ge=0.0, description="Precipitation in millimetres")
    wind_speed_ms: Optional[float] = Field(None, ge=0.0, description="Wind speed in metres per second")
    wind_direction_deg: Optional[float] = Field(None, ge=0.0, le=360.0, description="Wind direction in degrees")
    pressure_hpa: Optional[float] = Field(None, description="Atmospheric pressure in hectopascals")
    condition: Optional[str] = Field(None, description="Short human readable condition, e.g. 'rain'")
    units: Dict[str, str] = Field(default_factory=dict, description="Unit map for the numeric fields")
    provider: Optional[str] = Field(None, description="Provider identifier")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional provider metadata")


class WeatherForecastEntry(BaseModel):
    """A single forecast period (explicitly flagged as forecast, never observed)."""

    forecast_for: str = Field(..., description="ISO 8601 UTC date/time the forecast applies to")
    issued_at: Optional[str] = Field(None, description="ISO 8601 UTC timestamp the forecast was issued")
    is_forecast: bool = Field(True, description="Always True for forecast entries")
    temperature_min_c: Optional[float] = Field(None)
    temperature_max_c: Optional[float] = Field(None)
    precipitation_mm: Optional[float] = Field(None, ge=0.0)
    precipitation_probability_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    wind_speed_ms: Optional[float] = Field(None, ge=0.0)
    humidity_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    condition: Optional[str] = Field(None)
    units: Dict[str, str] = Field(default_factory=dict)
    provider: Optional[str] = Field(None)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WeatherRequest(BaseModel):
    """Provider-agnostic weather retrieval request."""

    request_id: Optional[str] = Field(None, description="Correlation / request tracing id")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    location_name: Optional[str] = Field(None, description="Optional human readable location label")
    start_date: Optional[str] = Field(None, description="Optional ISO 8601 start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="Optional ISO 8601 end date (YYYY-MM-DD)")
    forecast_days: int = Field(3, ge=0, le=16, description="Number of forecast days to request")
    include_forecast: bool = Field(True, description="Whether forecast data is requested")
    timeout: float = Field(10.0, gt=0.0, description="Per-request execution timeout in seconds")
    units: str = Field("metric", description="Preferred unit system ('metric' or 'imperial')")


class WeatherResponse(BaseModel):
    """Provider-agnostic weather retrieval response with provenance preserved."""

    request_id: Optional[str] = Field(None)
    status: WeatherStatus = Field(WeatherStatus.SUCCESS)
    provider_name: str = Field("unknown", description="Weather provider identifier used")
    latitude: Optional[float] = Field(None)
    longitude: Optional[float] = Field(None)
    location_name: Optional[str] = Field(None)
    observations: List[WeatherObservation] = Field(default_factory=list, description="Observed measurements")
    forecast: List[WeatherForecastEntry] = Field(default_factory=list, description="Forecast entries")
    observed_at: Optional[str] = Field(None, description="ISO 8601 timestamp of the latest observation")
    retrieved_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp when the data was retrieved",
    )
    is_stale: bool = Field(False, description="True when the observation exceeds the configured freshness window")
    stale_reason: Optional[str] = Field(None)
    units: Dict[str, str] = Field(default_factory=dict, description="Unit map for the response")
    provider_metadata: Dict[str, Any] = Field(default_factory=dict, description="Provider and model metadata")
    error_message: Optional[str] = Field(None)
    warnings: List[str] = Field(default_factory=list)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def unix_to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
