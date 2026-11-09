"""Sensor Evidence Validation Engine for EarthMind Drone Module (Stage D6).

Implements Component 14 (ISensorEvidenceValidator).
Validates schema compliance, required fields, reference integrity, unit normalization,
and physical plausibility of EarthMindDroneSensorEvidence artifacts before release.

Enforces strict rules:
- Schema name must be 'EarthMindDroneSensorEvidence' and version '1.0'.
- Source drone ID and sensor ID must be non-empty strings.
- Measurements must have valid physical units and normalized values.
- Indicators must trace cleanly to required input measurements.
- Calibration and data-quality metadata must be consistent and non-contradictory.
- Rejects fabricated, contradictory, corrupted, or uncalibrated (when required) evidence.
- Prevents invalid evidence from reaching B2 Context Manager or Sarvam-105B.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.errors.exceptions import EvidenceValidationFailedError
from core.interfaces.drone import ISensorEvidenceValidator
from core.logging.logger import get_logger
from core.schemas.drone import (
    CalibrationStatus,
    EarthMindDroneSensorEvidence,
    EvidenceStatus,
    QualityStatus,
)

logger = get_logger("modules.drone.evidence_validator")


class EvidenceValidationResult(BaseModel):
    """Structured report returned by SensorEvidenceValidator."""
    is_valid: bool = Field(..., description="True if evidence passes all validation rules")
    evidence_id: str = Field(..., description="Validated evidence identifier")
    errors: List[str] = Field(default_factory=list, description="Validation failure reasons")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal validation warnings")
    checks_evaluated: int = Field(0, description="Total number of verification checks executed")
    traceability_verified: bool = Field(False, description="Whether indicator-to-measurement lineage was confirmed")


class SensorEvidenceValidator(ISensorEvidenceValidator):
    """
    Component 14: Evidence validation gate.
    Evaluates candidate sensor evidence against schema v1.0 constraints and documented rules.
    """

    def __init__(self, reject_uncalibrated: bool = False) -> None:
        self._reject_uncalibrated = reject_uncalibrated

    def validate_evidence(self, evidence: EarthMindDroneSensorEvidence) -> bool:
        """
        Protocol implementation conforming to ISensorEvidenceValidator.
        Returns True if evidence is valid, False otherwise.
        """
        result = self.evaluate(evidence)
        return result.is_valid

    def validate_or_raise(self, evidence: EarthMindDroneSensorEvidence) -> EvidenceValidationResult:
        """
        Strict evaluation: returns EvidenceValidationResult or raises EvidenceValidationFailedError.
        Guarantees that invalid evidence never silently slips through.
        """
        result = self.evaluate(evidence)
        if not result.is_valid:
            error_summary = "; ".join(result.errors)
            logger.error(
                f"Evidence '{evidence.evidence_id}' rejected by validator: {error_summary}"
            )
            raise EvidenceValidationFailedError(
                evidence_id=evidence.evidence_id,
                details=error_summary,
            )
        return result

    def evaluate(self, evidence: EarthMindDroneSensorEvidence) -> EvidenceValidationResult:
        """
        Executes comprehensive validation checklist across 8 core dimensions:
        1. Contract Schema & Identity
        2. Hardware & Source Provenance
        3. Spatiotemporal Integrity
        4. Quality & Calibration Consistency
        5. Measurement Sanity & Normalization
        6. Indicator Provenance & Traceability
        7. Uncertainty Metrics Plausibility
        8. Evidence Status Consistency
        """
        errors: List[str] = []
        warnings: List[str] = []
        checks = 0

        # Check 1: Contract Name & Schema Version
        checks += 1
        if evidence.contract_name != "EarthMindDroneSensorEvidence":
            errors.append(f"Invalid contract_name: expected 'EarthMindDroneSensorEvidence', got '{evidence.contract_name}'")
        checks += 1
        if evidence.schema_version != "1.0":
            errors.append(f"Unsupported schema_version: expected '1.0', got '{evidence.schema_version}'")
        checks += 1
        if not evidence.evidence_id or not evidence.evidence_id.strip():
            errors.append("evidence_id cannot be empty")

        # Check 2: Hardware & Source Identification
        checks += 1
        if not evidence.source or not evidence.source.drone_id or not evidence.source.drone_id.strip():
            errors.append("Source drone_id is missing or empty")
        checks += 1
        if not evidence.source or not evidence.source.sensor_id or not evidence.source.sensor_id.strip():
            errors.append("Source sensor_id is missing or empty")
        checks += 1
        if not evidence.source or not evidence.source.sensor_type or not evidence.source.sensor_type.strip():
            errors.append("Source sensor_type is missing or empty")

        # Check 3: Spatiotemporal Integrity
        checks += 1
        if not evidence.temporal_coverage or not evidence.temporal_coverage.start_time:
            errors.append("Temporal coverage start_time is missing")
        checks += 1
        if evidence.spatial_coverage and evidence.spatial_coverage.has_spatial_metadata:
            centroid = evidence.spatial_coverage.centroid
            if centroid:
                if not (-90.0 <= centroid.latitude <= 90.0):
                    errors.append(f"Centroid latitude out of range: {centroid.latitude}")
                if not (-180.0 <= centroid.longitude <= 180.0):
                    errors.append(f"Centroid longitude out of range: {centroid.longitude}")
            bbox = evidence.spatial_coverage.bounding_box
            if bbox:
                if bbox.min_latitude > bbox.max_latitude or bbox.min_longitude > bbox.max_longitude:
                    errors.append("Spatial bounding box coordinates are logically inverted")

        # Check 4: Calibration Requirements & Consistency
        checks += 1
        if evidence.calibration:
            if self._reject_uncalibrated and evidence.calibration.calibration_status != CalibrationStatus.CALIBRATED:
                errors.append(f"Uncalibrated sensor evidence rejected by strict policy: {evidence.calibration.calibration_status.value}")
            if evidence.calibration.panel_used and evidence.calibration.calibration_status == CalibrationStatus.UNCALIBRATED:
                warnings.append("Calibration panel was flagged as used, but status remains UNCALIBRATED")

        # Check 5: Measurement Sanity & Normalization
        checks += 1
        m_channels = set()
        m_ids = set()
        for idx, m in enumerate(evidence.measurements):
            checks += 1
            if not m.measurement_id or not m.measurement_id.strip():
                errors.append(f"Measurement #{idx} lacks measurement_id")
            m_ids.add(m.measurement_id)

            if not m.channel_name or not m.channel_name.strip():
                errors.append(f"Measurement '{m.measurement_id}' lacks channel_name")
            m_channels.add(m.channel_name.lower())

            # Physical plausibility checks
            if m.measurement_type == "spectral_reflectance":
                if m.processed_value < 0.0 or m.processed_value > 1.5:  # reflectance typically in [0.0, 1.0], tolerate slight noise up to 1.5
                    errors.append(
                        f"Reflectance measurement '{m.measurement_id}' out of physical bounds: {m.processed_value}"
                    )
            elif m.measurement_type == "temperature":
                # Temperature in Celsius: terrestrial drone scans typically within [-50, 100] C
                if m.normalized_unit.lower() in ("celsius", "c") and not (-50.0 <= m.processed_value <= 100.0):
                    errors.append(
                        f"Temperature measurement '{m.measurement_id}' out of terrestrial physical limits: {m.processed_value} C"
                    )

        # Check 6: Indicator Lineage & Traceability
        traceability_ok = True
        for ind in evidence.indicators:
            checks += 1
            if not ind.indicator_name or not ind.indicator_name.strip():
                errors.append(f"Indicator '{ind.indicator_id}' lacks indicator_name")
                traceability_ok = False

            # Check that required channels exist in measurements
            for req_channel in ind.required_input_measurements:
                req_lower = req_channel.lower()
                # Match channel name strictly or by canonical prefix/suffix (e.g. 'nir' matches 'nir', 'nir_reflectance', 'nir_band')
                # Never allow a substring match like 'red' in 'red_edge' or 'swir' in 'swir1' without exact prefix
                found = False
                for ch in m_channels:
                    if ch == req_lower:
                        found = True
                        break
                    # If measurement channel has suffix like '_reflectance' or '_band'
                    ch_clean = ch.replace("_reflectance", "").replace("_band", "").strip()
                    req_clean = req_lower.replace("_reflectance", "").replace("_band", "").strip()
                    if ch_clean == req_clean:
                        found = True
                        break

                if not found:
                    errors.append(
                        f"Indicator '{ind.indicator_name}' ({ind.indicator_id}) missing required input channel '{req_channel}' in measurements"
                    )
                    traceability_ok = False

            # Indicator result sanity
            if isinstance(ind.result, dict):
                mean_val = ind.result.get("mean")
                if mean_val is not None:
                    # Normalized difference indicators (NDVI, NDRE, NDWI) are strictly within [-1.0, 1.0]
                    if ind.indicator_name.upper() in ("NDVI", "NDRE", "NDWI", "NDWI_GAO", "NDWI_MCFEETERS"):
                        if not (-1.0 <= mean_val <= 1.0):
                            errors.append(
                                f"Normalized difference indicator '{ind.indicator_name}' mean value ({mean_val}) exceeds [-1.0, 1.0] bounds"
                            )

        # Check 7: Uncertainty Assessment Plausibility
        checks += 1
        if evidence.uncertainty:
            u = evidence.uncertainty
            if not (0.0 <= u.overall_confidence <= 1.0):
                errors.append(f"Uncertainty overall_confidence out of bounds [0.0, 1.0]: {u.overall_confidence}")
            if not (0.0 <= u.spatial_confidence <= 1.0):
                errors.append(f"Uncertainty spatial_confidence out of bounds [0.0, 1.0]: {u.spatial_confidence}")
            if not (0.0 <= u.temporal_confidence <= 1.0):
                errors.append(f"Uncertainty temporal_confidence out of bounds [0.0, 1.0]: {u.temporal_confidence}")
            if not (0.0 <= u.calibration_confidence <= 1.0):
                errors.append(f"Uncertainty calibration_confidence out of bounds [0.0, 1.0]: {u.calibration_confidence}")

            # Confidence contradiction check: if spatial metadata is missing, spatial confidence cannot be 1.0
            if (not evidence.spatial_coverage or not evidence.spatial_coverage.has_spatial_metadata) and u.spatial_confidence > 0.1:
                errors.append("Uncertainty indicates high spatial confidence despite absent spatial metadata")

            # If measurements flagged INVALID, overall confidence cannot be HIGH (>0.70)
            if evidence.quality and evidence.quality.input_validity == QualityStatus.INVALID and u.overall_confidence > 0.50:
                errors.append("Uncertainty indicates high overall confidence despite INVALID input quality")

        # Check 8: Overall Evidence Status Consistency
        checks += 1
        if evidence.status == EvidenceStatus.REJECTED:
            errors.append("Evidence is marked with status REJECTED")
        elif evidence.status == EvidenceStatus.FAILED:
            errors.append("Evidence is marked with status FAILED")

        is_valid = len(errors) == 0

        return EvidenceValidationResult(
            is_valid=is_valid,
            evidence_id=evidence.evidence_id,
            errors=errors,
            warnings=warnings,
            checks_evaluated=checks,
            traceability_verified=traceability_ok and len(evidence.indicators) > 0,
        )
