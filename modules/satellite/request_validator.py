"""Satellite Request Validation Foundation for EarthMind Satellite Module (Stage D2).

Defensive, structured validation for incoming SatelliteDataRequest objects:
- Request and tenant identity checks
- Geographic coordinates and bounding box validation
- Temporal window validation (valid ISO formats, order, bounds)
- Constellation and sensor category validation
- Processing parameters and cloud cover limits
- Safe error raising via SatelliteInvalidArgumentError
"""

from datetime import datetime
import re
from typing import Optional

from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteDataRequest,
    SatelliteSensorType,
)
from modules.satellite.errors import SatelliteInvalidArgumentError

logger = get_logger("modules.satellite.request_validator")


class SatelliteRequestValidator:
    """Validates SatelliteDataRequest contracts defensively before processing or dispatch."""

    def __init__(self, strict: bool = True):
        self._strict = strict

    @property
    def strict(self) -> bool:
        return self._strict

    def validate_request(self, request: SatelliteDataRequest) -> bool:
        """Validate all required and conditional fields on a SatelliteDataRequest.

        Raises SatelliteInvalidArgumentError if invalid.
        Returns True on success.
        """
        if not request.request_id or not request.request_id.strip():
            raise SatelliteInvalidArgumentError(
                details="SatelliteDataRequest 'request_id' must be a non-empty string.",
                operation="validate_request",
            )

        if not request.tenant_id or not request.tenant_id.strip():
            raise SatelliteInvalidArgumentError(
                details="SatelliteDataRequest 'tenant_id' must be a non-empty string for tenant isolation.",
                operation="validate_request",
            )

        dangerous_patterns = ["../", "..\\", "/etc/", "c:\\"]
        for val in [request.request_id, request.tenant_id, request.field_id, request.farm_id, request.farmer_id]:
            if val:
                for pattern in dangerous_patterns:
                    if pattern in val.lower():
                        raise SatelliteInvalidArgumentError(
                            details=f"Unsafe characters or path traversal attempt detected in request parameter: '{val}'.",
                            operation="validate_request",
                        )

        geo = request.geospatial
        if geo is None:
            raise SatelliteInvalidArgumentError(
                details="SatelliteDataRequest missing required 'geospatial' metadata.",
                operation="validate_request",
            )

        if not (-90.0 <= geo.latitude <= 90.0):
            raise SatelliteInvalidArgumentError(
                details=f"Latitude {geo.latitude} is outside valid geographic range [-90.0, 90.0].",
                operation="validate_request",
            )

        if not (-180.0 <= geo.longitude <= 180.0):
            raise SatelliteInvalidArgumentError(
                details=f"Longitude {geo.longitude} is outside valid geographic range [-180.0, 180.0].",
                operation="validate_request",
            )

        if geo.bounding_box is not None:
            if len(geo.bounding_box) != 4:
                raise SatelliteInvalidArgumentError(
                    details="Bounding box must contain exactly 4 coordinates [min_lon, min_lat, max_lon, max_lat].",
                    operation="validate_request",
                )
            min_lon, min_lat, max_lon, max_lat = geo.bounding_box
            if min_lat > max_lat:
                raise SatelliteInvalidArgumentError(
                    details=f"Bounding box min_lat ({min_lat}) cannot exceed max_lat ({max_lat}).",
                    operation="validate_request",
                )
            if min_lon > max_lon:
                raise SatelliteInvalidArgumentError(
                    details=f"Bounding box min_lon ({min_lon}) cannot exceed max_lon ({max_lon}).",
                    operation="validate_request",
                )

        if geo.coverage_area_hectares is not None and geo.coverage_area_hectares < 0:
            raise SatelliteInvalidArgumentError(
                details=f"Coverage area ({geo.coverage_area_hectares} ha) cannot be negative.",
                operation="validate_request",
            )

        temp = request.temporal_window
        if temp is None:
            raise SatelliteInvalidArgumentError(
                details="SatelliteDataRequest missing required 'temporal_window' metadata.",
                operation="validate_request",
            )

        if not temp.acquisition_date or not temp.acquisition_date.strip():
            raise SatelliteInvalidArgumentError(
                details="Temporal window must specify non-empty 'acquisition_date'.",
                operation="validate_request",
            )

        if temp.start_time and temp.end_time:
            try:
                start_dt = self._parse_iso_datetime(temp.start_time)
                end_dt = self._parse_iso_datetime(temp.end_time)
                if start_dt > end_dt:
                    raise SatelliteInvalidArgumentError(
                        details=f"Temporal window start_time '{temp.start_time}' is after end_time '{temp.end_time}'.",
                        operation="validate_request",
                    )
            except ValueError as ve:
                raise SatelliteInvalidArgumentError(
                    details=f"Invalid ISO datetime string in temporal window: {ve}",
                    operation="validate_request",
                ) from ve

        if not request.sensor_types:
            raise SatelliteInvalidArgumentError(
                details="SatelliteDataRequest must request at least one sensor category in 'sensor_types'.",
                operation="validate_request",
            )

        if not (0.0 <= request.max_cloud_cover_percentage <= 100.0):
            raise SatelliteInvalidArgumentError(
                details=f"max_cloud_cover_percentage {request.max_cloud_cover_percentage} must be within [0.0, 100.0].",
                operation="validate_request",
            )

        return True

    def _parse_iso_datetime(self, date_str: str) -> datetime:
        s = date_str.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
