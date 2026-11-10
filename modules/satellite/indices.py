"""Spectral Index Engine for EarthMind Satellite Module (Stage D5)."""
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from core.interfaces.satellite import ISatelliteIndicatorExtractor
from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteDataQuality,
    SatelliteIndicator,
    SatelliteSpectralBand,
)
from modules.satellite.errors import (
    SatelliteIndicatorProcessingError,
    SatelliteInvalidArgumentError,
)

logger = get_logger("modules.satellite.indices")

class SpectralIndexDefinition:
    def __init__(self, name, display_name, required_bands, formula, definition, limitations, valid_range=(-1.0, 1.0)):
        self.name = name
        self.display_name = display_name
        self.required_bands = required_bands
        self.formula = formula
        self.definition = definition
        self.limitations = limitations
        self.valid_range = valid_range

SUPPORTED_INDICES: Dict[str, SpectralIndexDefinition] = {
    "NDVI": SpectralIndexDefinition("NDVI", "Normalized Difference Vegetation Index", ["NIR", "RED"], "(NIR - RED) / (NIR + RED)", "Broadband photosynthetic capacity measurement.", ["Saturates in dense canopies (LAI > 3-4)."]),
    "NDRE": SpectralIndexDefinition("NDRE", "Normalized Difference Red Edge Index", ["NIR", "RED_EDGE_1"], "(NIR - RED_EDGE_1) / (NIR + RED_EDGE_1)", "Red-edge chlorophyll sensitivity in mid-to-late growth.", ["Requires specific red-edge band."]),
    "NDWI_GREEN_NIR": SpectralIndexDefinition("NDWI_GREEN_NIR", "Normalized Difference Water Index (McFeeters)", ["GREEN", "NIR"], "(GREEN - NIR) / (GREEN + NIR)", "Delineates open surface water bodies.", ["Designed for surface water delineation, not canopy moisture or direct soil moisture."]),
    "NDWI_NIR_SWIR": SpectralIndexDefinition("NDWI_NIR_SWIR", "Normalized Difference Water Index (Gao / Moisture)", ["NIR", "SWIR_1"], "(NIR - SWIR_1) / (NIR + SWIR_1)", "Measures liquid water thickness in plant canopies.", ["Reflects canopy water thickness, not absolute soil volumetric moisture content."]),
    "EVI": SpectralIndexDefinition("EVI", "Enhanced Vegetation Index", ["NIR", "RED", "BLUE"], "2.5 * (NIR - RED) / (NIR + 6*RED - 7.5*BLUE + 1.0)", "Optimized high biomass vegetation index.", ["Requires calibrated Blue band."]),
}

class SatelliteSpectralIndexEngine(ISatelliteIndicatorExtractor):
    def __init__(self, version: str = "1.0.0"):
        self._version = version

    def get_supported_indices(self) -> List[str]:
        return list(SUPPORTED_INDICES.keys())

    def _resolve_band(self, band_name: str, processed_bands: Dict[str, Any]) -> np.ndarray:
        if band_name in processed_bands:
            return np.asarray(processed_bands[band_name], dtype=np.float32)
        for k, v in processed_bands.items():
            if k.upper() == band_name.upper():
                return np.asarray(v, dtype=np.float32)
        for k, v in processed_bands.items():
            if isinstance(v, SatelliteSpectralBand):
                if v.band_type.value == band_name.upper() or v.band_id.upper() == band_name.upper():
                    return np.asarray(v.statistics.get("mean", 0.0), dtype=np.float32)
        raise SatelliteIndicatorProcessingError(
            indicator_name=band_name,
            details=f"Required spectral band '{band_name}' is not present in processed dataset bands",
        )

    def calculate_index_matrix(self, indicator_name: str, band_matrices: Dict[str, Any]) -> np.ndarray:
        ind_key = indicator_name.upper().strip()
        if ind_key == "NDWI":
            ind_key = "NDWI_NIR_SWIR"
        if ind_key not in SUPPORTED_INDICES:
            raise SatelliteIndicatorProcessingError(
                indicator_name=indicator_name,
                details=f"Unsupported spectral index '{indicator_name}'",
            )
        spec = SUPPORTED_INDICES[ind_key]
        bands = {bname: self._resolve_band(bname, band_matrices) for bname in spec.required_bands}

        if ind_key == "NDVI":
            denom = bands["NIR"] + bands["RED"]
            with np.errstate(divide="ignore", invalid="ignore"):
                result = np.where(np.abs(denom) > 1e-6, (bands["NIR"] - bands["RED"]) / denom, np.nan)
            return np.clip(result, -1.0, 1.0)
        elif ind_key == "NDRE":
            denom = bands["NIR"] + bands["RED_EDGE_1"]
            with np.errstate(divide="ignore", invalid="ignore"):
                result = np.where(np.abs(denom) > 1e-6, (bands["NIR"] - bands["RED_EDGE_1"]) / denom, np.nan)
            return np.clip(result, -1.0, 1.0)
        elif ind_key == "NDWI_GREEN_NIR":
            denom = bands["GREEN"] + bands["NIR"]
            with np.errstate(divide="ignore", invalid="ignore"):
                result = np.where(np.abs(denom) > 1e-6, (bands["GREEN"] - bands["NIR"]) / denom, np.nan)
            return np.clip(result, -1.0, 1.0)
        elif ind_key == "NDWI_NIR_SWIR":
            denom = bands["NIR"] + bands["SWIR_1"]
            with np.errstate(divide="ignore", invalid="ignore"):
                result = np.where(np.abs(denom) > 1e-6, (bands["NIR"] - bands["SWIR_1"]) / denom, np.nan)
            return np.clip(result, -1.0, 1.0)
        elif ind_key == "EVI":
            denom = bands["NIR"] + 6.0 * bands["RED"] - 7.5 * bands["BLUE"] + 1.0
            with np.errstate(divide="ignore", invalid="ignore"):
                result = np.where(np.abs(denom) > 1e-6, 2.5 * (bands["NIR"] - bands["RED"]) / denom, np.nan)
            return np.clip(result, -1.0, 1.5)

    def extract_indicator(self, indicator_name: str, processed_bands: Dict[str, Any], source_dataset_id: str, band_matrices: Optional[Dict[str, Any]] = None) -> SatelliteIndicator:
        ind_key = indicator_name.upper().strip()
        if ind_key == "NDWI":
            ind_key = "NDWI_NIR_SWIR"
        if ind_key not in SUPPORTED_INDICES:
            raise SatelliteIndicatorProcessingError(indicator_name=indicator_name, details=f"Unsupported spectral index: {indicator_name}")
        spec = SUPPORTED_INDICES[ind_key]
        matrices = band_matrices or processed_bands
        index_matrix = self.calculate_index_matrix(ind_key, matrices)
        finite_vals = index_matrix[np.isfinite(index_matrix)]

        if finite_vals.size == 0:
            stats = {"mean": 0.0, "min": 0.0, "max": 0.0, "std_dev": 0.0, "median": 0.0, "valid_pixel_count": 0}
            quality = SatelliteDataQuality.DEGRADED
            warnings = ["No valid finite pixels in index calculation area"]
        else:
            stats = {
                "mean": float(np.round(float(np.mean(finite_vals)), 4)),
                "min": float(np.round(float(np.min(finite_vals)), 4)),
                "max": float(np.round(float(np.max(finite_vals)), 4)),
                "std_dev": float(np.round(float(np.std(finite_vals)), 4)),
                "median": float(np.round(float(np.median(finite_vals)), 4)),
                "p25": float(np.round(float(np.percentile(finite_vals, 25)), 4)),
                "p75": float(np.round(float(np.percentile(finite_vals, 75)), 4)),
                "valid_pixel_count": int(finite_vals.size),
            }
            quality = SatelliteDataQuality.GOOD
            warnings = []

        return SatelliteIndicator(
            indicator_name=spec.name,
            definition=spec.definition,
            calculation_method=f"{spec.formula} (v{self._version})",
            required_bands=spec.required_bands,
            source_dataset_id=source_dataset_id,
            result_statistics=stats,
            unit="unitless_ratio",
            quality_status=quality,
            limitations=list(spec.limitations),
            warnings=warnings,
        )

    def extract_available_indicators(self, processed_bands: Dict[str, Any], source_dataset_id: str, band_matrices: Optional[Dict[str, Any]] = None) -> List[SatelliteIndicator]:
        matrices = band_matrices or processed_bands
        available_band_keys = set(k.upper() for k in matrices.keys())
        indicators = []
        for ind_key, spec in SUPPORTED_INDICES.items():
            if set(spec.required_bands).issubset(available_band_keys):
                try:
                    ind = self.extract_indicator(ind_key, processed_bands, source_dataset_id, band_matrices=matrices)
                    indicators.append(ind)
                except Exception as exc:
                    logger.warning(f"Could not calculate index: {exc}")
        return indicators
