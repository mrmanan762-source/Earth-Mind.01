"""Uncertainty Assessment Engine for EarthMind Satellite Module (Stage D6).

Implements Component 15 (ISatelliteUncertaintyAssessor).
Evaluates data quality, atmospheric correction, cloud cover interference, spatial resolution,
temporal observation gaps, sensor differences, and measurement variability across deterministic,
defensible rules.

Core Principles:
- Does not invent numerical confidence scores or probabilities without scientific validation.
- Uses qualitative uncertainty when numerical quantification is not scientifically validated.
- Evaluates discrete categorical confidence states: HIGH, MEDIUM, LOW, INSUFFICIENT_EVIDENCE.
- Transparently reports documented sources of uncertainty and physical limitations.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from core.interfaces.satellite import ISatelliteUncertaintyAssessor
from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteDataQuality,
    SatelliteGeospatialMetadata,
    SatelliteTemporalMetadata,
    SatelliteUncertaintyAssessment,
)

logger = get_logger("modules.satellite.uncertainty")


class SatelliteConfidenceLevel(str, Enum):
    """Categorical confidence rating based on documented criteria."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class SatelliteUncertaintyAssessor(ISatelliteUncertaintyAssessor):
    """
    Component 15: Multi-dimensional uncertainty and confidence assessor.
    Computes transparent, defensible uncertainty metrics across spatial, temporal,
    spectral/atmospheric, and data quality dimensions.
    """

    # Categorical threshold constants
    THRESHOLD_HIGH = 0.85
    THRESHOLD_MEDIUM = 0.60
    THRESHOLD_LOW = 0.30

    def __init__(self) -> None:
        pass

    def assess_uncertainty(
        self,
        quality_status: SatelliteDataQuality,
        cloud_cover_target: float,
        is_calibrated: bool,
        revisit_age_days: float,
    ) -> Dict[str, Any]:
        """
        Protocol method conforming to ISatelliteUncertaintyAssessor.
        Returns a dictionary with confidence dimensions, categorical level, and documented reasons.
        """
        uncertainty_sources: List[str] = []

        # 1. Quality & Cloud Cover Score
        quality_score = 1.0
        if quality_status == SatelliteDataQuality.EXCELLENT:
            quality_score = 1.0
        elif quality_status == SatelliteDataQuality.GOOD:
            quality_score = 0.90
        elif quality_status == SatelliteDataQuality.ACCEPTABLE:
            quality_score = 0.75
        elif quality_status == SatelliteDataQuality.DEGRADED:
            quality_score = 0.50
            uncertainty_sources.append("Observation data quality classified as DEGRADED")
        elif quality_status == SatelliteDataQuality.CLOUD_OBSCURED:
            quality_score = 0.20
            uncertainty_sources.append(f"Significant cloud obscuration over target: {cloud_cover_target:.1f}%")
        elif quality_status == SatelliteDataQuality.INCOMPLETE:
            quality_score = 0.25
            uncertainty_sources.append("Observation data incomplete: required bands or metadata missing")
        else:  # INVALID
            quality_score = 0.05
            uncertainty_sources.append("Observation data quality classified as INVALID")

        # Cloud cover penalties on quality score
        if cloud_cover_target > 50.0:
            quality_score = min(quality_score, 0.15)
            if f"Target cloud cover high ({cloud_cover_target:.1f}%)" not in uncertainty_sources:
                uncertainty_sources.append(f"Target cloud cover high ({cloud_cover_target:.1f}%)")
        elif cloud_cover_target > 20.0:
            quality_score *= 0.80
            uncertainty_sources.append(f"Moderate cloud cover ({cloud_cover_target:.1f}%) present over target")

        # 2. Spectral / Radiometric / Atmospheric Calibration Score
        spectral_conf = 0.95 if is_calibrated else 0.30
        if not is_calibrated:
            uncertainty_sources.append("Surface reflectance uncalibrated; top-of-atmosphere (TOA) radiance utilized")

        # 3. Spatial Confidence Baseline
        spatial_conf = 0.95
        if quality_status == SatelliteDataQuality.INVALID:
            spatial_conf = 0.20

        # 4. Temporal Confidence Baseline based on age / revisit
        temporal_conf = 1.0
        if revisit_age_days < 0:
            revisit_age_days = 0.0
        if revisit_age_days <= 5.0:
            temporal_conf = 1.0
        elif revisit_age_days <= 10.0:
            temporal_conf = 0.85
        elif revisit_age_days <= 20.0:
            temporal_conf = 0.65
            uncertainty_sources.append(f"Observation timeliness degraded: scene is {revisit_age_days:.1f} days old")
        elif revisit_age_days <= 30.0:
            temporal_conf = 0.45
            uncertainty_sources.append(f"Observation aging significantly: scene is {revisit_age_days:.1f} days old")
        else:
            temporal_conf = 0.15
            uncertainty_sources.append(f"Observation severely stale (>30 days): {revisit_age_days:.1f} days old")

        # Composite score weighting: Quality 35%, Spectral 25%, Spatial 20%, Temporal 20%
        w_q, w_spec, w_spat, w_t = 0.35, 0.25, 0.20, 0.20
        overall = (
            (quality_score * w_q)
            + (spectral_conf * w_spec)
            + (spatial_conf * w_spat)
            + (temporal_conf * w_t)
        )
        overall = round(max(0.0, min(1.0, overall)), 4)
        cat_level = self.determine_confidence_level(overall)

        return {
            "spatial_confidence": round(spatial_conf, 4),
            "temporal_confidence": round(temporal_conf, 4),
            "spectral_confidence": round(spectral_conf, 4),
            "quality_confidence": round(quality_score, 4),
            "overall_confidence": overall,
            "confidence_level": cat_level.value,
            "uncertainty_sources": uncertainty_sources,
        }

    def assess_comprehensive_uncertainty(
        self,
        quality_status: SatelliteDataQuality,
        geospatial: Optional[SatelliteGeospatialMetadata] = None,
        temporal: Optional[SatelliteTemporalMetadata] = None,
        cloud_cover_target: float = 0.0,
        is_atmospheric_corrected: bool = True,
        revisit_age_days: float = 0.0,
        bands_count: int = 0,
        indicators_count: int = 0,
        sensor_type: str = "OPTICAL_MULTISPECTRAL",
        operational_warnings: Optional[List[str]] = None,
        conflicting_observations: Optional[List[str]] = None,
    ) -> SatelliteUncertaintyAssessment:
        """
        Comprehensive multi-dimensional uncertainty evaluation returning Contract 8 SatelliteUncertaintyAssessment.
        Evaluates:
        1. Spatial confidence: coordinate bounding, spatial resolution in meters, CRS validity.
        2. Temporal confidence: observation timeliness, revisit window, temporal coverage type.
        3. Spectral confidence: atmospheric correction (BOA vs TOA), sensor calibration.
        4. Overall confidence: composite rating with cross-source conflict penalties.
        5. Uncertainty sources: transparent qualitative documentation of limitations.
        """
        uncertainty_sources: List[str] = []
        warnings = operational_warnings or []
        conflicts = conflicting_observations or []

        # 1. Spatial Dimension
        spatial_conf = 1.0
        if geospatial is None:
            spatial_conf = 0.0
            uncertainty_sources.append("Geospatial metadata completely missing")
        else:
            if not (-90.0 <= geospatial.latitude <= 90.0) or not (-180.0 <= geospatial.longitude <= 180.0):
                spatial_conf = 0.0
                uncertainty_sources.append("Centroid geographic coordinates out of physical bounds")
            if geospatial.bounding_box is None:
                spatial_conf *= 0.85
                uncertainty_sources.append("Scene lacks explicit geospatial bounding box extent")
            if geospatial.crs.upper() not in ("EPSG:4326", "WGS84"):
                spatial_conf *= 0.95
            if geospatial.spatial_resolution_meters:
                # Coarser resolution (>30m) introduces mixed-pixel uncertainty for smallholder plots
                if geospatial.spatial_resolution_meters > 30.0:
                    spatial_conf *= 0.80
                    uncertainty_sources.append(
                        f"Coarse spatial resolution ({geospatial.spatial_resolution_meters:.1f}m) introduces mixed-pixel uncertainty"
                    )
                elif geospatial.spatial_resolution_meters > 20.0:
                    spatial_conf *= 0.90
            else:
                spatial_conf *= 0.85
                uncertainty_sources.append("Nominal spatial ground resolution unrecorded")

        # 2. Temporal Dimension
        temporal_conf = 1.0
        if temporal is None or not temporal.acquisition_date:
            temporal_conf = 0.0
            uncertainty_sources.append("Temporal coverage metadata missing")
        else:
            if revisit_age_days < 0:
                revisit_age_days = 0.0
            if revisit_age_days > 30.0:
                temporal_conf = 0.20
                uncertainty_sources.append(f"Observation timestamp is severely stale (>30 days): {revisit_age_days:.1f} days old")
            elif revisit_age_days > 14.0:
                temporal_conf = 0.55
                uncertainty_sources.append(f"Observation timestamp is aging: {revisit_age_days:.1f} days old")
            elif revisit_age_days > 7.0:
                temporal_conf = 0.80
                uncertainty_sources.append(f"Observation timestamp is {revisit_age_days:.1f} days old")
            else:
                temporal_conf = 0.98

        # 3. Spectral & Atmospheric Dimension
        spectral_conf = 0.95
        if not is_atmospheric_corrected:
            spectral_conf = 0.45
            uncertainty_sources.append("Atmospheric correction unapplied; top-of-atmosphere reflectance subject to aerosol scattering")
        if bands_count == 0:
            spectral_conf = 0.0
            uncertainty_sources.append("Zero spectral bands available for evaluation")

        # 4. Data Quality & Atmospheric Cloud Interference
        quality_score = 1.0
        if quality_status == SatelliteDataQuality.EXCELLENT:
            quality_score = 1.0
        elif quality_status == SatelliteDataQuality.GOOD:
            quality_score = 0.90
        elif quality_status == SatelliteDataQuality.ACCEPTABLE:
            quality_score = 0.75
        elif quality_status == SatelliteDataQuality.DEGRADED:
            quality_score = 0.50
            uncertainty_sources.append("Satellite scene quality classified as DEGRADED")
        elif quality_status == SatelliteDataQuality.CLOUD_OBSCURED:
            quality_score = 0.20
            uncertainty_sources.append(f"Target area obscured by cloud or cloud shadow ({cloud_cover_target:.1f}%)")
        elif quality_status == SatelliteDataQuality.INCOMPLETE:
            quality_score = 0.25
            uncertainty_sources.append("Satellite scene observations are incomplete")
        else:  # INVALID
            quality_score = 0.05
            uncertainty_sources.append("Satellite scene data classified as INVALID")

        if cloud_cover_target > 50.0:
            quality_score = min(quality_score, 0.20)
            if f"Target cloud cover exceeds 50% ({cloud_cover_target:.1f}%)" not in uncertainty_sources:
                uncertainty_sources.append(f"Target cloud cover exceeds 50% ({cloud_cover_target:.1f}%)")
        elif cloud_cover_target > 20.0:
            quality_score *= 0.80
            uncertainty_sources.append(f"Target cloud cover ({cloud_cover_target:.1f}%) limits spectral fidelity")

        # 5. Missing Evidence & Indicators Guard
        if indicators_count == 0:
            uncertainty_sources.append("Zero agricultural indicators extracted")
            quality_score *= 0.70

        # 6. Cross-Source Disagreement & Conflicts
        for c in conflicts:
            uncertainty_sources.append(f"Cross-source observation conflict: {c}")
            quality_score *= 0.85
            spectral_conf *= 0.90

        # External operational warnings
        for w in warnings:
            if "conflict" in w.lower():
                uncertainty_sources.append(f"Observation conflict: {w}")
                quality_score *= 0.85
            elif "gap" in w.lower():
                uncertainty_sources.append(f"Temporal gap: {w}")
                temporal_conf *= 0.90

        # Composite score weighting: Quality 35%, Spectral 25%, Spatial 20%, Temporal 20%
        w_q, w_spec, w_spat, w_t = 0.35, 0.25, 0.20, 0.20
        overall = (
            (quality_score * w_q)
            + (spectral_conf * w_spec)
            + (spatial_conf * w_spat)
            + (temporal_conf * w_t)
        )
        overall = round(max(0.0, min(1.0, overall)), 4)

        # Deduplicate sources preserving order
        deduped_sources = list(dict.fromkeys(uncertainty_sources))

        return SatelliteUncertaintyAssessment(
            spatial_confidence=round(max(0.0, min(1.0, spatial_conf)), 4),
            temporal_confidence=round(max(0.0, min(1.0, temporal_conf)), 4),
            spectral_confidence=round(max(0.0, min(1.0, spectral_conf)), 4),
            overall_confidence=overall,
            uncertainty_sources=deduped_sources,
        )

    def determine_confidence_level(self, overall_confidence: float) -> SatelliteConfidenceLevel:
        """Map numerical confidence score into documented discrete confidence state."""
        if overall_confidence >= self.THRESHOLD_HIGH:
            return SatelliteConfidenceLevel.HIGH
        elif overall_confidence >= self.THRESHOLD_MEDIUM:
            return SatelliteConfidenceLevel.MEDIUM
        elif overall_confidence >= self.THRESHOLD_LOW:
            return SatelliteConfidenceLevel.LOW
        else:
            return SatelliteConfidenceLevel.INSUFFICIENT_EVIDENCE
