"""Calibration Engine for EarthMind Drone Module (Stage D3).

Handles sensor calibration evaluation and radiometric transformation parameters.
Evaluates calibration panels, sunshine / downwelling irradiance sensors (DLS),
and factory calibration certificates.
Explicitly distinguishes CALIBRATED, UNCALIBRATED, FACTORY_DEFAULT, EXPIRED, MISSING.
Never fabricates calibration coefficients.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from core.logging.logger import get_logger
from core.schemas.drone import CalibrationStatus
from modules.drone.errors import (
    CalibrationUnavailableError,
    DroneInvalidArgumentError,
    SensorMetadataMissingError,
)

logger = get_logger("modules.drone.calibration")


class CalibrationAssessment(BaseModel):
    """Result of evaluating calibration metadata."""
    status: CalibrationStatus
    panel_used: bool = False
    sun_sensor_used: bool = False
    calibration_timestamp: Optional[str] = None
    applied_coefficients: Dict[str, float] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    is_valid_for_processing: bool = True


class CalibrationEngine:
    """Evaluates and applies sensor calibration parameters."""

    def __init__(self, max_calibration_age_days: int = 365):
        self._max_calibration_age_days = max_calibration_age_days

    def evaluate_calibration(
        self,
        calibration_metadata: Optional[Dict[str, Any]],
        sensor_profile: Optional[Dict[str, Any]] = None,
        observation_timestamp: Optional[str] = None,
    ) -> CalibrationAssessment:
        """
        Evaluate calibration metadata to determine validity and coefficients.

        Args:
            calibration_metadata: dict containing panel info, DLS, or calibration coeffs.
            sensor_profile: optional SensorMetadataContract dictionary for factory specs.
            observation_timestamp: ISO 8601 UTC timestamp of current flight.

        Returns:
            CalibrationAssessment
        """
        warnings: List[str] = []
        errors: List[str] = []

        if not calibration_metadata:
            # Check if sensor profile provides factory defaults
            if sensor_profile and sensor_profile.get("calibration_metadata"):
                factory_cal = sensor_profile["calibration_metadata"]
                return CalibrationAssessment(
                    status=CalibrationStatus.FACTORY_DEFAULT,
                    panel_used=False,
                    sun_sensor_used=False,
                    calibration_timestamp=factory_cal.get("calibration_timestamp"),
                    applied_coefficients=factory_cal.get("coefficients", {}),
                    warnings=["No flight-specific calibration metadata provided; utilizing sensor factory defaults."],
                    is_valid_for_processing=True,
                )

            return CalibrationAssessment(
                status=CalibrationStatus.MISSING,
                panel_used=False,
                sun_sensor_used=False,
                warnings=["Sensor calibration metadata is completely absent."],
                is_valid_for_processing=False,
            )

        # Check declared status or infer it
        declared_status = calibration_metadata.get("status") or calibration_metadata.get("calibration_status")
        panel_used = bool(calibration_metadata.get("panel_used", False))
        sun_sensor_used = bool(calibration_metadata.get("sun_sensor_used", False))
        cal_ts = calibration_metadata.get("calibration_timestamp") or calibration_metadata.get("timestamp")
        coeffs = calibration_metadata.get("coefficients") or calibration_metadata.get("calibration_factors") or {}

        # Validate coefficients dictionary
        valid_coeffs: Dict[str, float] = {}
        if isinstance(coeffs, dict):
            for k, v in coeffs.items():
                try:
                    num_v = float(v)
                    if num_v <= 0.0:
                        warnings.append(f"Non-positive calibration coefficient {num_v} for channel '{k}'.")
                    valid_coeffs[k] = num_v
                except (ValueError, TypeError):
                    warnings.append(f"Non-numeric calibration coefficient for channel '{k}': {v}")

        # Check expiration / age if timestamps available
        if cal_ts and observation_timestamp:
            try:
                cal_dt = self._parse_iso_ts(cal_ts)
                obs_dt = self._parse_iso_ts(observation_timestamp)
                age_days = (obs_dt - cal_dt).total_seconds() / 86400.0

                if age_days < 0:
                    warnings.append(f"Calibration timestamp ({cal_ts}) is in the future relative to observation ({observation_timestamp}).")
                elif age_days > self._max_calibration_age_days:
                    warnings.append(f"Calibration is expired ({age_days:.1f} days old > max {self._max_calibration_age_days} days).")
                    return CalibrationAssessment(
                        status=CalibrationStatus.EXPIRED,
                        panel_used=panel_used,
                        sun_sensor_used=sun_sensor_used,
                        calibration_timestamp=cal_ts,
                        applied_coefficients=valid_coeffs,
                        warnings=warnings,
                        is_valid_for_processing=False,
                    )
            except Exception as exc:
                warnings.append(f"Could not calculate calibration age: {exc}")

        # Determine final status
        if declared_status:
            status_str = str(declared_status).upper()
            if status_str in CalibrationStatus.__members__:
                status = CalibrationStatus[status_str]
            else:
                warnings.append(f"Unrecognized declared calibration status '{declared_status}'. Defaulting to UNCALIBRATED.")
                status = CalibrationStatus.UNCALIBRATED
        elif panel_used or sun_sensor_used or valid_coeffs:
            status = CalibrationStatus.CALIBRATED
        else:
            status = CalibrationStatus.UNCALIBRATED

        is_valid = status in (CalibrationStatus.CALIBRATED, CalibrationStatus.FACTORY_DEFAULT)

        return CalibrationAssessment(
            status=status,
            panel_used=panel_used,
            sun_sensor_used=sun_sensor_used,
            calibration_timestamp=cal_ts,
            applied_coefficients=valid_coeffs,
            warnings=warnings,
            errors=errors,
            is_valid_for_processing=is_valid,
        )

    def apply_calibration_transform(
        self,
        raw_val: float,
        channel: str,
        assessment: CalibrationAssessment,
    ) -> Tuple[float, str]:
        """
        Apply calibration coefficient if available.

        Returns:
            (calibrated_value, processing_method)
        """
        if assessment.status == CalibrationStatus.CALIBRATED and channel in assessment.applied_coefficients:
            factor = assessment.applied_coefficients[channel]
            calibrated_val = raw_val * factor
            method = f"calibrated_radiometric_scaling(factor={factor})"
            return calibrated_val, method

        if assessment.status == CalibrationStatus.FACTORY_DEFAULT and channel in assessment.applied_coefficients:
            factor = assessment.applied_coefficients[channel]
            calibrated_val = raw_val * factor
            method = f"factory_default_scaling(factor={factor})"
            return calibrated_val, method

        # Uncalibrated: pass-through raw numerical value
        return raw_val, f"uncalibrated_pass_through(status={assessment.status.value})"

    def _parse_iso_ts(self, ts: str) -> datetime:
        clean = ts.strip()
        if clean.endswith("Z"):
            clean = clean[:-1] + "+00:00"
        return datetime.fromisoformat(clean)
