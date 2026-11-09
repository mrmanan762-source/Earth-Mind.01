"""Agricultural Indicator Extraction Engine for EarthMind Drone Module (Stage D5).

Implements Component 10 (IIndicatorExtractor) protocol.
Extracts supported spectral indices (NDVI, NDRE, NDWI_GAO, NDWI_MCFEETERS)
strictly with validated band inputs and documented formulas.
Distinguishes NDWI variants explicitly without treating different formulas as interchangeable.
Never fabricates missing bands, measurements, or confidence scores.
Never outputs ungrounded agricultural diagnoses or chemical prescriptions.
"""

import math
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from core.interfaces.drone import IIndicatorExtractor
from core.logging.logger import get_logger
from core.schemas.drone import (
    AgriculturalIndicatorContract,
    ProcessedSensorMeasurementContract,
    QualityStatus,
    SensorMetadataContract,
    SpatialBoundingBox,
    SpatialCoordinates,
    SpatialCoverage,
    TemporalCoverage,
)
from modules.drone.errors import (
    DroneInvalidArgumentError,
    IndicatorProcessingFailedError,
    InsufficientDroneDataError,
)
from modules.drone.spectral import SpectralAnalysisEngine

logger = get_logger("modules.drone.indicators")


class IndicatorDefinition:
    """Specification of an agricultural vegetation / moisture indicator."""

    def __init__(
        self,
        name: str,
        display_name: str,
        required_bands: List[str],
        formula_description: str,
        definition: str,
        limitations: List[str],
        valid_range: Tuple[float, float] = (-1.0, 1.0),
    ):
        self.name = name
        self.display_name = display_name
        self.required_bands = required_bands
        self.formula_description = formula_description
        self.definition = definition
        self.limitations = limitations
        self.valid_range = valid_range


# Authoritative indicator catalog defining supported formulas and explicit band dependencies
INDICATOR_CATALOG: Dict[str, IndicatorDefinition] = {
    "NDVI": IndicatorDefinition(
        name="NDVI",
        display_name="Normalized Difference Vegetation Index",
        required_bands=["nir", "red"],
        formula_description="(NIR - Red) / (NIR + Red)",
        definition="Standardized indicator of green photosynthetic biomass and relative plant vigor.",
        limitations=[
            "Saturates in high-biomass and dense multi-layer canopies (LAI > 3-4).",
            "Sensitive to soil brightness background variations in sparse or emergent canopies.",
            "Does not differentiate specific nutrient deficiencies, pest damage, or fungal pathogens.",
        ],
        valid_range=(-1.0, 1.0),
    ),
    "NDRE": IndicatorDefinition(
        name="NDRE",
        display_name="Normalized Difference Red Edge",
        required_bands=["nir", "red_edge"],
        formula_description="(NIR - RedEdge) / (NIR + RedEdge)",
        definition="Canopy chlorophyll-sensitive indicator utilizing the sharp red-edge inflection transition.",
        limitations=[
            "Requires calibrated narrow-band red-edge sensor (705-740 nm).",
            "Less sensitive in early emergence stages with low canopy cover.",
            "Does not constitute confirmed diagnosis of nitrogen deficiency.",
        ],
        valid_range=(-1.0, 1.0),
    ),
    "NDWI_GAO": IndicatorDefinition(
        name="NDWI_GAO",
        display_name="Normalized Difference Water Index (Gao 1996 - Canopy Liquid Water)",
        required_bands=["nir", "swir1"],
        formula_description="(NIR - SWIR) / (NIR + SWIR)",
        definition="Vegetation canopy water content index sensitive to leaf intracellular liquid absorption.",
        limitations=[
            "Requires shortwave infrared (SWIR) spectral band (~1550-1750 nm).",
            "Distinct from McFeeters surface water index; cannot be substituted by green band.",
            "Canopy geometry and dry biomass influence reflectance ratio.",
        ],
        valid_range=(-1.0, 1.0),
    ),
    "NDWI_MCFEETERS": IndicatorDefinition(
        name="NDWI_MCFEETERS",
        display_name="Normalized Difference Water Index (McFeeters 1996 - Surface Water Delineation)",
        required_bands=["green", "nir"],
        formula_description="(Green - NIR) / (Green + NIR)",
        definition="Surface open-water and soil inundation indicator delineating ponding, standing water, and flooding.",
        limitations=[
            "Uses Green and NIR bands; detects water bodies and saturated ponding, NOT leaf intracellular water content.",
            "Can produce false positives over dense dark green vegetation or shadowed terrain.",
            "Cannot be used as a proxy for leaf water potential or plant drought stress.",
        ],
        valid_range=(-1.0, 1.0),
    ),
}


class IndicatorExtractionEngine(IIndicatorExtractor):
    """Component 10: Agricultural indicator extraction implementation."""

    def __init__(self, spectral_engine: Optional[SpectralAnalysisEngine] = None):
        self._spectral_engine = spectral_engine or SpectralAnalysisEngine()
        self._catalog = INDICATOR_CATALOG

    @property
    def supported_indicators(self) -> List[str]:
        return list(self._catalog.keys())

    def get_indicator_definition(self, indicator_name: str) -> Optional[IndicatorDefinition]:
        """Lookup definition by normalized name."""
        norm = indicator_name.upper().strip().replace("-", "_").replace(" ", "_")
        if norm in self._catalog:
            return self._catalog[norm]
        # Common aliases
        if norm in ("NDWI", "NDWI_CANOPY", "NDWI_VEG"):
            return self._catalog["NDWI_GAO"]
        if norm in ("NDWI_WATER", "NDWI_SURFACE", "NDWI_OPENWATER"):
            return self._catalog["NDWI_MCFEETERS"]
        return None

    def _extract_band_channel(
        self,
        measurements: List[ProcessedSensorMeasurementContract],
        canonical_band: str,
    ) -> List[ProcessedSensorMeasurementContract]:
        """Find measurements corresponding to canonical band name."""
        matched = []
        for m in measurements:
            c = self._spectral_engine.canonicalize_band_name(m.channel_name)
            if c == canonical_band:
                matched.append(m)
        return matched

    def _calculate_index_pair(
        self,
        band_a_values: List[float],
        band_b_values: List[float],
        name: str,
    ) -> Tuple[List[float], List[str]]:
        """
        Compute normalized difference (A - B) / (A + B).
        Handles zero-division, negative denominators, and invalid values safely.
        """
        results: List[float] = []
        warnings: List[str] = []

        if len(band_a_values) != len(band_b_values):
            # If lengths differ, pair up to minimum length
            min_len = min(len(band_a_values), len(band_b_values))
            warnings.append(
                f"Input band sample count mismatch for {name}: band A has {len(band_a_values)}, band B has {len(band_b_values)}. Truncating to {min_len}."
            )
            band_a_values = band_a_values[:min_len]
            band_b_values = band_b_values[:min_len]

        for idx, (a, b) in enumerate(zip(band_a_values, band_b_values)):
            if math.isnan(a) or math.isnan(b) or math.isinf(a) or math.isinf(b):
                warnings.append(f"Sample index {idx}: non-finite band inputs ({a}, {b}). Skipping.")
                continue

            denominator = a + b
            if abs(denominator) < 1e-9:
                warnings.append(f"Sample index {idx}: division by zero in {name} (denominator {denominator:.6f} near zero).")
                continue

            val = (a - b) / denominator

            # Clip/check normalized difference bounds [-1.0, 1.0]
            if val < -1.0 or val > 1.0:
                warnings.append(f"Sample index {idx}: index value {val:.4f} outside theoretical [-1.0, 1.0] range.")
                # Bound mathematically to [-1.0, 1.0] if slight float error
                val = max(-1.0, min(1.0, val))

            results.append(val)

        return results, warnings

    def extract_indicator(
        self,
        indicator_name: str,
        measurements: List[ProcessedSensorMeasurementContract],
        sensor_metadata: Optional[SensorMetadataContract] = None,
    ) -> AgriculturalIndicatorContract:
        """
        Extract a single standardized agricultural indicator (NDVI, NDRE, NDWI_GAO, NDWI_MCFEETERS).
        """
        if not indicator_name:
            raise DroneInvalidArgumentError(
                details="Indicator name must be provided.",
                operation="extract_indicator",
            )

        indicator_def = self.get_indicator_definition(indicator_name)
        if not indicator_def:
            raise IndicatorProcessingFailedError(
                indicator_name=indicator_name,
                details=f"Unsupported indicator '{indicator_name}'. Supported indicators: {list(self._catalog.keys())}",
            )

        if not measurements:
            raise InsufficientDroneDataError(
                details=f"No measurements provided for indicator '{indicator_name}'.",
                operation="extract_indicator",
            )

        # Check required bands
        band_measurements: Dict[str, List[ProcessedSensorMeasurementContract]] = {}
        missing_bands: List[str] = []

        for req_band in indicator_def.required_bands:
            matched = self._extract_band_channel(measurements, req_band)
            if not matched:
                missing_bands.append(req_band)
            else:
                band_measurements[req_band] = matched

        if missing_bands:
            raise IndicatorProcessingFailedError(
                indicator_name=indicator_def.name,
                details=f"Missing required spectral band(s) {missing_bands} for {indicator_def.name}. Formula requires: {indicator_def.formula_description}",
            )

        # Gather values
        b1_name, b2_name = indicator_def.required_bands[0], indicator_def.required_bands[1]
        b1_vals = [m.processed_value for m in band_measurements[b1_name]]
        b2_vals = [m.processed_value for m in band_measurements[b2_name]]

        index_vals, calc_warnings = self._calculate_index_pair(b1_vals, b2_vals, indicator_def.name)

        if not index_vals:
            raise IndicatorProcessingFailedError(
                indicator_name=indicator_def.name,
                details=f"Failed to calculate {indicator_def.name}: all values resulted in division-by-zero or non-finite numbers.",
            )

        # Statistical summary
        n = len(index_vals)
        sorted_vals = sorted(index_vals)
        mean_val = sum(sorted_vals) / n
        min_val = sorted_vals[0]
        max_val = sorted_vals[-1]
        variance = sum((x - mean_val) ** 2 for x in sorted_vals) / (n - 1) if n > 1 else 0.0
        std_dev = math.sqrt(variance)
        median_val = sorted_vals[n // 2]

        result_summary = {
            "mean": round(mean_val, 4),
            "min": round(min_val, 4),
            "max": round(max_val, 4),
            "std_dev": round(std_dev, 4),
            "median": round(median_val, 4),
            "sample_count": n,
        }

        # Spatial / temporal coverage derivation
        spatial_cov: Optional[SpatialCoverage] = None
        all_coords = [m.spatial_reference for m in measurements if m.spatial_reference]
        if all_coords:
            lats = [c.latitude for c in all_coords]
            lons = [c.longitude for c in all_coords]
            spatial_cov = SpatialCoverage(
                has_spatial_metadata=True,
                centroid=SpatialCoordinates(
                    latitude=sum(lats) / len(lats),
                    longitude=sum(lons) / len(lons),
                ),
                bounding_box=SpatialBoundingBox(
                    min_latitude=min(lats),
                    max_latitude=max(lats),
                    min_longitude=min(lons),
                    max_longitude=max(lons),
                ),
            )

        all_times = [m.timestamp for m in measurements if m.timestamp]
        temp_cov: Optional[TemporalCoverage] = None
        if all_times:
            sorted_times = sorted(all_times)
            temp_cov = TemporalCoverage(
                start_time=sorted_times[0],
                end_time=sorted_times[-1],
            )

        # Determine quality status
        quality_status = QualityStatus.VALID
        # Check calibration status of input measurements
        cal_statuses = {m.calibration_status for m in band_measurements[b1_name] + band_measurements[b2_name]}
        if any(c == "UNCALIBRATED" for c in cal_statuses):
            calc_warnings.append("Calculated using uncalibrated spectral measurements.")
            quality_status = QualityStatus.DEGRADED
        elif calc_warnings:
            quality_status = QualityStatus.DEGRADED

        # Compile final limitations
        final_limitations = list(indicator_def.limitations)
        if calc_warnings:
            final_limitations.extend(calc_warnings)

        input_meas_ids = [m.measurement_id for m in band_measurements[b1_name] + band_measurements[b2_name]]

        return AgriculturalIndicatorContract(
            indicator_id=f"ind_{uuid.uuid4().hex[:12]}",
            indicator_name=indicator_def.name,
            definition=indicator_def.definition,
            calculation_method=indicator_def.formula_description,
            required_input_measurements=indicator_def.required_bands,
            result=result_summary,
            unit="unitless_ratio",
            spatial_coverage=spatial_cov,
            temporal_coverage=temp_cov,
            processing_version="1.0",
            quality_status=quality_status,
            limitations=final_limitations,
        )

    def extract_available_indicators(
        self,
        measurements: List[ProcessedSensorMeasurementContract],
        sensor_metadata: Optional[SensorMetadataContract] = None,
    ) -> List[AgriculturalIndicatorContract]:
        """
        Extract all possible indicators supported by the available spectral channels.
        Does not fail if some indicators cannot be calculated; returns all successfully calculated ones.
        """
        if not measurements:
            return []

        available_bands = set()
        for m in measurements:
            available_bands.add(self._spectral_engine.canonicalize_band_name(m.channel_name))

        extracted: List[AgriculturalIndicatorContract] = []

        # Evaluate each catalog indicator against available bands
        for ind_name, ind_def in self._catalog.items():
            if all(b in available_bands for b in ind_def.required_bands):
                try:
                    ind = self.extract_indicator(ind_name, measurements, sensor_metadata)
                    extracted.append(ind)
                except Exception as exc:
                    logger.warning(f"Could not compute available indicator '{ind_name}': {exc}")

        return extracted
