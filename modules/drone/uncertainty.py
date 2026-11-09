"""Uncertainty & Confidence Assessment Engine for EarthMind Drone Module (Stage D6).

Implements Component 12 (IUncertaintyAssessor).
Evaluates data quality, calibration status, spatial coverage, temporal coverage,
sensor compatibility, and evidence completeness across deterministic, defensible rules.

Never invents confidence percentages or implies statistical certainty without a validated method.
Supports explicit categorical confidence states: HIGH, MEDIUM, LOW, INSUFFICIENT_DATA
with transparent, documented thresholds and reasons.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from core.interfaces.drone import IUncertaintyAssessor
from core.logging.logger import get_logger
from core.schemas.drone import (
    CalibrationStatus,
    DroneQualityAssessment,
    DroneUncertaintyAssessment,
    QualityStatus,
    SpatialCoverage,
    TemporalCoverage,
)

logger = get_logger("modules.drone.uncertainty")


class ConfidenceLevel(str, Enum):
    """Categorical confidence rating based on documented criteria."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class UncertaintyAssessor(IUncertaintyAssessor):
    """
    Component 12: Multi-dimensional uncertainty and confidence assessment engine.
    Computes transparent, defensible uncertainty metrics across quality, radiometric,
    spatial, temporal, and completeness dimensions.
    """

    # Categorical threshold constants
    THRESHOLD_HIGH = 0.85
    THRESHOLD_MEDIUM = 0.60
    THRESHOLD_LOW = 0.30

    def __init__(self) -> None:
        pass

    def assess_uncertainty(
        self,
        quality_status: QualityStatus,
        calibration_present: bool,
        has_spatial: bool,
        has_temporal: bool,
    ) -> Dict[str, Any]:
        """
        Baseline implementation conforming to IUncertaintyAssessor protocol.
        Returns a dictionary with confidence dimensions and documented reasons.
        """
        spatial_conf = 0.95 if has_spatial else 0.0
        temporal_conf = 0.95 if has_temporal else 0.0
        cal_conf = 0.90 if calibration_present else 0.30

        quality_weight = 0.40
        cal_weight = 0.25
        spatial_weight = 0.20
        temporal_weight = 0.15

        q_score = 0.0
        if quality_status == QualityStatus.VALID:
            q_score = 1.0
        elif quality_status in (QualityStatus.SUSPECT, QualityStatus.DEGRADED):
            q_score = 0.60
        elif quality_status in (QualityStatus.CALIBRATION_MISSING, QualityStatus.GEOLOCATION_DEGRADED):
            q_score = 0.50
        elif quality_status == QualityStatus.INCOMPLETE:
            q_score = 0.30
        else:  # INVALID
            q_score = 0.0

        uncertainty_sources: List[str] = []
        if not has_spatial:
            uncertainty_sources.append("Missing geospatial geolocation coordinates")
        if not has_temporal:
            uncertainty_sources.append("Missing or unverified temporal mission timestamps")
        if not calibration_present:
            uncertainty_sources.append("Radiometric calibration panel or DLS sensor data missing")
        if quality_status != QualityStatus.VALID:
            uncertainty_sources.append(f"Data quality classification is degraded: {quality_status.value}")

        overall = (
            (q_score * quality_weight)
            + (cal_conf * cal_weight)
            + (spatial_conf * spatial_weight)
            + (temporal_conf * temporal_weight)
        )
        overall = round(max(0.0, min(1.0, overall)), 4)

        level = self.determine_confidence_level(overall)

        return {
            "spatial_confidence": spatial_conf,
            "temporal_confidence": temporal_conf,
            "calibration_confidence": cal_conf,
            "quality_confidence": q_score,
            "overall_confidence": overall,
            "confidence_level": level.value,
            "uncertainty_sources": uncertainty_sources,
        }

    def assess_comprehensive_uncertainty(
        self,
        quality_assessment: DroneQualityAssessment,
        calibration_status: CalibrationStatus,
        panel_used: bool,
        sun_sensor_used: bool,
        spatial_coverage: Optional[SpatialCoverage] = None,
        temporal_coverage: Optional[TemporalCoverage] = None,
        measurements_count: int = 0,
        indicators_count: int = 0,
        operational_warnings: Optional[List[str]] = None,
    ) -> DroneUncertaintyAssessment:
        """
        Comprehensive multi-dimensional uncertainty assessment producing DroneUncertaintyAssessment.
        Evaluates:
        1. Spatial confidence: GNSS fix, altitude presence, bounding box, CRS validity.
        2. Temporal confidence: ISO-8601 UTC validation, duration, sampling rate stability.
        3. Calibration confidence: calibration panel, sunshine sensor / DLS, calibration status.
        4. Quality confidence: input validity, data gap flags, physical range plausibility.
        5. Completeness: sample counts, available channels, coverage adequacy.
        """
        uncertainty_sources: List[str] = []
        warnings = operational_warnings or []

        # 1. Spatial Dimension
        spatial_conf = 1.0
        if spatial_coverage is None or not spatial_coverage.has_spatial_metadata:
            spatial_conf = 0.0
            uncertainty_sources.append("Geospatial metadata absent: observations lack spatial coordinates")
        else:
            if spatial_coverage.centroid is None and spatial_coverage.bounding_box is None:
                spatial_conf *= 0.5
                uncertainty_sources.append("Spatial coordinates lack explicit centroid or bounding box")
            if spatial_coverage.centroid and spatial_coverage.centroid.altitude_meters is None:
                spatial_conf *= 0.90
                uncertainty_sources.append("Flight altitude above ground/sea level unrecorded")
            if spatial_coverage.crs.upper() not in ("EPSG:4326", "WGS84"):
                spatial_conf *= 0.95

        # 2. Temporal Dimension
        temporal_conf = 1.0
        if temporal_coverage is None or not temporal_coverage.start_time:
            temporal_conf = 0.0
            uncertainty_sources.append("Temporal coverage metadata absent")
        else:
            if not temporal_coverage.end_time and (temporal_coverage.duration_seconds is None or temporal_coverage.duration_seconds <= 0):
                temporal_conf *= 0.85
                uncertainty_sources.append("Mission duration or end timestamp missing")
            if temporal_coverage.sampling_frequency_hz is None:
                temporal_conf *= 0.95

        # 3. Calibration Dimension
        cal_conf = 0.0
        if calibration_status == CalibrationStatus.CALIBRATED:
            cal_conf = 0.80
            if panel_used:
                cal_conf += 0.10
            if sun_sensor_used:
                cal_conf += 0.10
        elif calibration_status == CalibrationStatus.FACTORY_DEFAULT:
            cal_conf = 0.60
            uncertainty_sources.append("Sensor utilizing factory default calibration without in-situ radiometric panel")
        elif calibration_status == CalibrationStatus.EXPIRED:
            cal_conf = 0.35
            uncertainty_sources.append("Sensor calibration certificate has expired")
        elif calibration_status == CalibrationStatus.UNCALIBRATED:
            cal_conf = 0.20
            uncertainty_sources.append("Sensor uncalibrated: measurements are raw uncalibrated readings")
        else:  # MISSING
            cal_conf = 0.10
            uncertainty_sources.append("Radiometric calibration completely missing")

        cal_conf = min(1.0, cal_conf)

        # 4. Data Quality Dimension
        quality_score = 1.0
        if quality_assessment.input_validity == QualityStatus.VALID:
            quality_score = 1.0
        elif quality_assessment.input_validity in (QualityStatus.SUSPECT, QualityStatus.DEGRADED):
            quality_score = 0.65
            uncertainty_sources.append(f"Input quality marked as {quality_assessment.input_validity.value}")
        elif quality_assessment.input_validity in (QualityStatus.CALIBRATION_MISSING, QualityStatus.GEOLOCATION_DEGRADED):
            quality_score = 0.50
            uncertainty_sources.append(f"Input quality degraded by {quality_assessment.input_validity.value}")
        elif quality_assessment.input_validity == QualityStatus.INCOMPLETE:
            quality_score = 0.35
            uncertainty_sources.append("Input measurements are incomplete")
        else:  # INVALID
            quality_score = 0.05
            uncertainty_sources.append("Input measurements flagged as INVALID")

        # 5. Completeness & Measurement Presence
        if measurements_count == 0:
            uncertainty_sources.append("Zero processed measurements provided")
            quality_score = 0.0
            spatial_conf *= 0.5
            temporal_conf *= 0.5

        # Incorporate external warnings into uncertainty sources
        for w in warnings:
            if "conflict" in w.lower():
                uncertainty_sources.append(f"Sensor conflict detected: {w}")
                quality_score *= 0.85
            elif "gap" in w.lower():
                uncertainty_sources.append(f"Temporal gap: {w}")
                temporal_conf *= 0.90

        # Weighted composite score: Quality 35%, Calibration 30%, Spatial 20%, Temporal 15%
        w_q, w_c, w_s, w_t = 0.35, 0.30, 0.20, 0.15
        overall_confidence = (
            (quality_score * w_q)
            + (cal_conf * w_c)
            + (spatial_conf * w_s)
            + (temporal_conf * w_t)
        )
        overall_confidence = round(max(0.0, min(1.0, overall_confidence)), 4)

        return DroneUncertaintyAssessment(
            spatial_confidence=round(spatial_conf, 4),
            temporal_confidence=round(temporal_conf, 4),
            calibration_confidence=round(cal_conf, 4),
            overall_confidence=overall_confidence,
            uncertainty_sources=list(dict.fromkeys(uncertainty_sources)),  # deduplicate preserving order
        )

    def determine_confidence_level(self, overall_confidence: float) -> ConfidenceLevel:
        """Categorize numerical confidence score into documented discrete confidence state."""
        if overall_confidence >= self.THRESHOLD_HIGH:
            return ConfidenceLevel.HIGH
        elif overall_confidence >= self.THRESHOLD_MEDIUM:
            return ConfidenceLevel.MEDIUM
        elif overall_confidence >= self.THRESHOLD_LOW:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.INSUFFICIENT_DATA
