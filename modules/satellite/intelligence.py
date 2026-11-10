"""Agricultural Intelligence Extraction Engine for EarthMind Satellite Module (Stage D6).

Implements Component 16 (ISatelliteAgronomicFeatureExtractor).
Transforms validated D4/D5 processed satellite measurements and analytical indicators
into structured, traceable agricultural observations.

Strict Non-Diagnostic Principle:
- Objective observation of canopy reflectance, spectral vegetation indices, moisture proxies,
  spatial heterogeneity, and temporal changes.
- Preserves source measurements, units, geospatial coordinates, observation windows,
  calculation methods, and data quality status.
- Strictly prohibits asserting final agricultural root causes, such as diagnosing specific crop diseases,
  nutrient deficiencies, soil fertility ratings, or prescribing irrigation/chemical treatments.
- Sarvam-105B remains EarthMind's primary reasoning engine.
"""

from typing import Any, Dict, List, Optional
import numpy as np

from core.interfaces.satellite import ISatelliteAgronomicFeatureExtractor
from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteDataQuality,
    SatelliteGeospatialMetadata,
    SatelliteIndicator,
    SatelliteTemporalMetadata,
)

logger = get_logger("modules.satellite.intelligence")


class SatelliteAgriculturalIntelligenceEngine(ISatelliteAgronomicFeatureExtractor):
    """
    Component 16: Agricultural intelligence and agronomic feature extraction engine.
    Relates spectral, spatial, and temporal measurements into structured, traceable observations.
    """

    def __init__(self) -> None:
        pass

    def extract_agronomic_features(
        self,
        indicators: List[SatelliteIndicator],
        temporal_history: Optional[List[SatelliteIndicator]] = None,
    ) -> Dict[str, Any]:
        """
        Protocol method conforming to ISatelliteAgronomicFeatureExtractor.
        Synthesizes objective agronomic features without final diagnostic claims.
        """
        vigor_features: Dict[str, Any] = {}
        moisture_features: Dict[str, Any] = {}
        limitations: List[str] = [
            "Satellite observations provide macro-scale canopy spectral properties; they do not constitute leaf-level disease diagnosis.",
            "Water index values represent canopy water content proxy and should not be used as direct soil moisture measurements.",
        ]

        for ind in indicators:
            name_upper = ind.indicator_name.upper()
            stats = ind.result_statistics if isinstance(ind.result_statistics, dict) else {}
            mean_val = stats.get("mean")

            if name_upper in ("NDVI", "NDRE", "EVI"):
                vigor_features[name_upper] = {
                    "mean": mean_val,
                    "min": stats.get("min"),
                    "max": stats.get("max"),
                    "std_dev": stats.get("std_dev"),
                    "median": stats.get("median"),
                    "cv": stats.get("cv"),
                    "unit": ind.unit,
                    "calculation_method": ind.calculation_method,
                    "source_dataset_id": ind.source_dataset_id,
                    "quality_status": ind.quality_status.value,
                }
            elif name_upper in ("NDWI", "NDWI_GAO", "NDWI_MCFEETERS", "NDWI_GREEN_NIR", "NDWI_NIR_SWIR"):
                moisture_features[name_upper] = {
                    "mean": mean_val,
                    "min": stats.get("min"),
                    "max": stats.get("max"),
                    "std_dev": stats.get("std_dev"),
                    "unit": ind.unit,
                    "calculation_method": ind.calculation_method,
                    "source_dataset_id": ind.source_dataset_id,
                    "quality_status": ind.quality_status.value,
                }

        # Temporal trend trajectory analysis if historical indicators are provided
        temporal_trajectory = None
        if temporal_history and len(temporal_history) > 1:
            points: List[float] = []
            for h_ind in temporal_history:
                h_stats = h_ind.result_statistics if isinstance(h_ind.result_statistics, dict) else {}
                m = h_stats.get("mean")
                if m is not None:
                    points.append(float(m))
            if len(points) > 1:
                x = np.arange(len(points))
                slope, _ = np.polyfit(x, points, 1)
                temporal_trajectory = {
                    "trend_direction": "INCREASING" if slope > 0.02 else ("DECREASING" if slope < -0.02 else "STABLE"),
                    "linear_slope": round(float(slope), 4),
                    "observation_count": len(points),
                }

        return {
            "canopy_vigor_observations": vigor_features,
            "canopy_moisture_observations": moisture_features,
            "temporal_trajectory": temporal_trajectory,
            "limitations": limitations,
        }

    def generate_agricultural_intelligence(
        self,
        indicators: List[SatelliteIndicator],
        geospatial: SatelliteGeospatialMetadata,
        temporal: SatelliteTemporalMetadata,
        band_matrices: Optional[Dict[str, np.ndarray]] = None,
        thermal_observations: Optional[Dict[str, Any]] = None,
        radar_observations: Optional[Dict[str, Any]] = None,
        spatial_summary: Optional[Dict[str, Any]] = None,
        change_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        D6 Comprehensive Agricultural Intelligence Generation.
        Synthesizes spectral, spatial, temporal, thermal, and radar measurements
        into structured, traceable observations for downstream reasoning.
        """
        features = self.extract_agronomic_features(indicators)
        vigor = features.get("canopy_vigor_observations", {})
        moisture = features.get("canopy_moisture_observations", {})

        # Spatial heterogeneity & canopy coverage
        spatial_intel = {
            "coverage_area_hectares": geospatial.coverage_area_hectares,
            "spatial_resolution_meters": geospatial.spatial_resolution_meters,
            "crs": geospatial.crs,
            "field_id": geospatial.field_id,
            "farm_id": geospatial.farm_id,
        }
        if spatial_summary:
            spatial_intel["spatial_heterogeneity"] = spatial_summary.get("spatial_heterogeneity")
            spatial_intel["zonal_statistics"] = spatial_summary.get("zonal_statistics")

        # Temporal coverage & dynamics
        temporal_intel = {
            "acquisition_date": temporal.acquisition_date,
            "revisit_interval_days": temporal.revisit_interval_days,
            "temporal_coverage_type": temporal.temporal_coverage_type,
        }
        if change_summary:
            temporal_intel["pixel_change_summary"] = change_summary

        # Thermal observations (e.g. Land Surface Temperature)
        thermal_intel = None
        if thermal_observations:
            thermal_intel = {
                "sensor": thermal_observations.get("sensor", "Thermal_Infrared"),
                "surface_temperature_kelvin_mean": thermal_observations.get("temperature_kelvin_mean"),
                "surface_temperature_celsius_mean": thermal_observations.get("temperature_celsius_mean"),
                "unit": "Celsius",
                "quality": thermal_observations.get("quality", "ACCEPTABLE"),
            }

        # SAR / Radar observations
        radar_intel = None
        if radar_observations:
            radar_intel = {
                "sensor": radar_observations.get("sensor", "SAR_C_BAND"),
                "polarization": radar_observations.get("polarization", "VV_VH"),
                "backscatter_sigma0_db_mean": radar_observations.get("sigma0_dB_mean"),
                "unit": "dB",
                "quality": radar_observations.get("quality", "ACCEPTABLE"),
            }

        limitations = list(features.get("limitations", []))
        if geospatial.spatial_resolution_meters and geospatial.spatial_resolution_meters >= 20.0:
            limitations.append(
                f"Pixel ground resolution is {geospatial.spatial_resolution_meters:.1f}m; individual plant rows are not resolved."
            )

        return {
            "intelligence_type": "AGRICULTURAL_SATELLITE_OBSERVATION",
            "observation_period": {
                "acquisition_date": temporal.acquisition_date,
                "revisit_days": temporal.revisit_interval_days,
            },
            "spatial_context": spatial_intel,
            "temporal_context": temporal_intel,
            "canopy_vigor": vigor,
            "canopy_moisture": moisture,
            "thermal_observations": thermal_intel,
            "radar_observations": radar_intel,
            "derived_indicators_count": len(indicators),
            "limitations": limitations,
            "non_diagnostic_statement": (
                "All satellite-derived indicators represent physical surface reflectance and radiation measurements. "
                "They are provided as objective context for Sarvam-105B reasoning and do not constitute field diagnoses."
            ),
        }
