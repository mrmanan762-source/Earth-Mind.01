"""Data Quality & Validation Engine for EarthMind Drone Module (Stage D3).

Implements Component 5 (IDataQualityValidator).
Performs data sanity, physical plausibility checks, timestamp validity,
and data gap detection on raw measurements. Never silently discards invalid data.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field

from core.interfaces.drone import IDataQualityValidator
from core.logging.logger import get_logger
from core.schemas.drone import QualityStatus
from modules.drone.errors import (
    DroneInvalidArgumentError,
    InsufficientDroneDataError,
    InvalidSensorDataError,
    QualityValidationFailedError,
    TimestampInvalidError,
)

logger = get_logger("modules.drone.quality")


class MeasurementValidationItem(BaseModel):
    """Validation report for an individual measurement."""
    channel: str
    original_value: Any
    is_valid: bool
    quality_status: QualityStatus
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class DataQualityReport(BaseModel):
    """Overall report returned by Data Quality & Validation Engine."""
    overall_status: QualityStatus
    total_measurements: int
    valid_count: int
    suspect_count: int
    invalid_count: int
    items: List[MeasurementValidationItem] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


# Agronomic and physical boundary rules
PHYSICAL_LIMITS = {
    # Temperature boundaries
    "temperature": {"min": -50.0, "max": 80.0, "units": ["celsius", "degc", "c"]},
    "temperature_k": {"min": 223.15, "max": 353.15, "units": ["kelvin", "k"]},
    "temperature_f": {"min": -58.0, "max": 176.0, "units": ["fahrenheit", "degf", "f"]},
    # Optical reflectance boundaries (fractional ratio)
    "reflectance": {"min": 0.0, "max": 1.0, "units": ["unitless_ratio", "ratio", "fraction", "reflectance"]},
    "reflectance_pct": {"min": 0.0, "max": 100.0, "units": ["percent", "%"]},
    "raw_dn_16": {"min": 0, "max": 65535, "units": ["raw_dn", "dn", "digital_number"]},
    # Environmental
    "relative_humidity": {"min": 0.0, "max": 100.0, "units": ["percent", "%"]},
    "atmospheric_pressure": {"min": 300.0, "max": 1100.0, "units": ["hpa", "mbar"]},
    "solar_irradiance": {"min": 0.0, "max": 2000.0, "units": ["w/m2", "w/m^2"]},
}


class DataQualityValidator(IDataQualityValidator):
    """Component 5: Measurement sanity and physical plausibility validator."""

    def __init__(self, strict_mode: bool = False):
        self._strict_mode = strict_mode

    def validate_quality(self, measurements: List[Dict[str, Any]]) -> QualityStatus:
        """
        Validate physical limits and integrity of extracted measurements.
        Conforms to IDataQualityValidator interface.
        """
        report = self.evaluate_measurements(measurements)
        return report.overall_status

    def evaluate_measurements(
        self,
        measurements: List[Dict[str, Any]],
        collection_timestamp: Optional[str] = None,
        expected_channels: Optional[List[str]] = None,
    ) -> DataQualityReport:
        """
        Detailed evaluation returning DataQualityReport without discarding measurements.
        """
        if measurements is None:
            raise InsufficientDroneDataError(
                details="Measurements list cannot be None.",
                operation="validate_quality",
            )

        if len(measurements) == 0:
            return DataQualityReport(
                overall_status=QualityStatus.INCOMPLETE,
                total_measurements=0,
                valid_count=0,
                suspect_count=0,
                invalid_count=0,
                warnings=["Zero measurements provided for quality validation."],
                errors=["Empty measurement dataset."],
            )

        items: List[MeasurementValidationItem] = []
        warnings: List[str] = []
        errors: List[str] = []

        seen_channels = set()
        duplicate_channels = set()

        for idx, m in enumerate(measurements):
            if not isinstance(m, dict):
                err_msg = f"Measurement item at index {idx} is not a dictionary."
                errors.append(err_msg)
                items.append(
                    MeasurementValidationItem(
                        channel=f"item_{idx}",
                        original_value=m,
                        is_valid=False,
                        quality_status=QualityStatus.INVALID,
                        errors=[err_msg],
                    )
                )
                continue

            channel = m.get("channel") or m.get("channel_name") or m.get("name") or f"channel_{idx}"
            if channel in seen_channels:
                duplicate_channels.add(channel)
            seen_channels.add(channel)

            val = m.get("value") if "value" in m else m.get("original_value")
            unit = str(m.get("unit") or m.get("original_unit") or "unknown").lower().strip()

            item_res = self._validate_single_measurement(channel, val, unit)
            items.append(item_res)

        if duplicate_channels:
            warnings.append(f"Duplicate channel measurements detected: {sorted(list(duplicate_channels))}")

        # Missing expected channels check
        if expected_channels:
            missing = set(expected_channels) - seen_channels
            if missing:
                warnings.append(f"Incomplete dataset: missing expected channels {sorted(list(missing))}")

        # Timestamp validation if provided
        if collection_timestamp is not None:
            ts_valid, ts_err = self._validate_iso8601_timestamp(collection_timestamp)
            if not ts_valid:
                errors.append(f"Invalid collection timestamp '{collection_timestamp}': {ts_err}")

        # Tally counts
        valid_cnt = sum(1 for it in items if it.quality_status == QualityStatus.VALID)
        suspect_cnt = sum(1 for it in items if it.quality_status in (QualityStatus.SUSPECT, QualityStatus.DEGRADED))
        invalid_cnt = sum(1 for it in items if it.quality_status == QualityStatus.INVALID)

        # Bubble up any warnings and errors from individual items
        for it in items:
            for w in it.warnings:
                if w not in warnings:
                    warnings.append(w)
            for e in it.errors:
                if e not in errors:
                    errors.append(e)

        # Derive overall status
        if invalid_cnt > 0 or errors:
            overall = QualityStatus.INVALID
        elif suspect_cnt > 0 or warnings:
            overall = QualityStatus.SUSPECT
        else:
            overall = QualityStatus.VALID

        report = DataQualityReport(
            overall_status=overall,
            total_measurements=len(items),
            valid_count=valid_cnt,
            suspect_count=suspect_cnt,
            invalid_count=invalid_cnt,
            items=items,
            warnings=warnings,
            errors=errors,
        )

        if self._strict_mode and overall == QualityStatus.INVALID:
            raise QualityValidationFailedError(
                details=f"Quality validation failed with {invalid_cnt} invalid measurements: {errors}",
                operation="validate_quality",
            )

        return report

    def _validate_single_measurement(self, channel: str, val: Any, unit: str) -> MeasurementValidationItem:
        """Validate a single channel value against physical rules."""
        item_warnings: List[str] = []
        item_errors: List[str] = []

        if val is None:
            item_errors.append(f"Measurement for channel '{channel}' has missing/None value.")
            return MeasurementValidationItem(
                channel=channel,
                original_value=val,
                is_valid=False,
                quality_status=QualityStatus.INVALID,
                errors=item_errors,
            )

        # Numerical check
        num_val: Optional[float] = None
        if isinstance(val, (int, float)):
            num_val = float(val)
        elif isinstance(val, str):
            try:
                num_val = float(val)
            except ValueError:
                item_errors.append(f"Non-numeric value '{val}' for channel '{channel}'.")
        elif isinstance(val, (list, tuple)):
            # Check array elements
            all_nums = all(isinstance(x, (int, float)) for x in val)
            if not all_nums:
                item_errors.append(f"Array measurement for channel '{channel}' contains non-numeric elements.")
            elif len(val) == 0:
                item_errors.append(f"Array measurement for channel '{channel}' is empty.")
            else:
                # Validate array range
                min_v, max_v = min(val), max(val)
                rule = self._find_physical_rule(channel, unit)
                if rule:
                    if min_v < rule["min"] or max_v > rule["max"]:
                        item_warnings.append(
                            f"Array values [{min_v}, {max_v}] out of physical bounds [{rule['min']}, {rule['max']}] for {channel} ({unit})."
                        )
            q_status = QualityStatus.INVALID if item_errors else (QualityStatus.SUSPECT if item_warnings else QualityStatus.VALID)
            return MeasurementValidationItem(
                channel=channel,
                original_value=val,
                is_valid=(len(item_errors) == 0),
                quality_status=q_status,
                warnings=item_warnings,
                errors=item_errors,
            )
        else:
            item_errors.append(f"Unsupported measurement type '{type(val).__name__}' for channel '{channel}'.")

        if item_errors:
            return MeasurementValidationItem(
                channel=channel,
                original_value=val,
                is_valid=False,
                quality_status=QualityStatus.INVALID,
                errors=item_errors,
            )

        assert num_val is not None

        # Check NaN / Infinity
        import math
        if math.isnan(num_val) or math.isinf(num_val):
            item_errors.append(f"Numerical value is NaN or Inf for channel '{channel}'.")
            return MeasurementValidationItem(
                channel=channel,
                original_value=val,
                is_valid=False,
                quality_status=QualityStatus.INVALID,
                errors=item_errors,
            )

        # Check physical limit rules
        rule = self._find_physical_rule(channel, unit)
        if rule:
            if num_val < rule["min"] or num_val > rule["max"]:
                msg = f"Value {num_val} is outside physical plausibility bounds [{rule['min']}, {rule['max']}] for {channel} (unit={unit})."
                item_warnings.append(msg)

        status = QualityStatus.INVALID if item_errors else (QualityStatus.SUSPECT if item_warnings else QualityStatus.VALID)
        return MeasurementValidationItem(
            channel=channel,
            original_value=val,
            is_valid=(len(item_errors) == 0),
            quality_status=status,
            warnings=item_warnings,
            errors=item_errors,
        )

    def _find_physical_rule(self, channel: str, unit: str) -> Optional[Dict[str, Any]]:
        """Match channel or unit to known physical limits."""
        ch_lower = channel.lower()
        u_lower = unit.lower()

        # Temperature
        if "temp" in ch_lower or "thermal" in ch_lower or u_lower in ("c", "celsius", "degc"):
            if u_lower in ("k", "kelvin"):
                return PHYSICAL_LIMITS["temperature_k"]
            elif u_lower in ("f", "fahrenheit", "degf"):
                return PHYSICAL_LIMITS["temperature_f"]
            else:
                return PHYSICAL_LIMITS["temperature"]

        # Reflectance
        if any(band in ch_lower for band in ("red", "green", "blue", "nir", "re", "swir", "refl")):
            if u_lower in ("%", "percent"):
                return PHYSICAL_LIMITS["reflectance_pct"]
            elif u_lower in ("raw_dn", "dn", "digital_number"):
                return PHYSICAL_LIMITS["raw_dn_16"]
            else:
                return PHYSICAL_LIMITS["reflectance"]

        # General unit lookups
        if u_lower in ("%", "percent") and "humid" in ch_lower:
            return PHYSICAL_LIMITS["relative_humidity"]
        if u_lower in ("hpa", "mbar"):
            return PHYSICAL_LIMITS["atmospheric_pressure"]
        if u_lower in ("w/m2", "w/m^2"):
            return PHYSICAL_LIMITS["solar_irradiance"]

        return None

    def _validate_iso8601_timestamp(self, ts: str) -> Tuple[bool, Optional[str]]:
        """Validate ISO 8601 UTC timestamp format."""
        if not isinstance(ts, str) or not ts.strip():
            return False, "Timestamp must be a non-empty string."

        clean_ts = ts.strip()
        # Accept formats like 2026-11-09T02:50:00Z or with offset
        try:
            if clean_ts.endswith("Z"):
                clean_ts = clean_ts[:-1] + "+00:00"
            dt = datetime.fromisoformat(clean_ts)
            # Ensure it is timezone-aware or UTC
            if dt.tzinfo is None:
                return False, "Timestamp missing explicit timezone / UTC offset."
            return True, None
        except Exception as exc:
            return False, str(exc)
