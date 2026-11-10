"""Agricultural Indicator Generator for EarthMind Satellite Module (Stage D5)."""
from typing import Any, Dict, List, Optional
import numpy as np

from core.schemas.satellite import SatelliteDataQuality, SatelliteIndicator

class SatelliteIndicatorGenerator:
    def build_indicator_contract(self, indicator_name: str, definition: str, calculation_method: str, required_bands: List[str], source_dataset_id: str, statistics: Dict[str, Any], unit: str = "unitless_ratio", quality_status: SatelliteDataQuality = SatelliteDataQuality.GOOD, limitations: Optional[List[str]] = None, warnings: Optional[List[str]] = None) -> SatelliteIndicator:
        return SatelliteIndicator(
            indicator_name=indicator_name,
            definition=definition,
            calculation_method=calculation_method,
            required_bands=required_bands,
            source_dataset_id=source_dataset_id,
            result_statistics=statistics,
            unit=unit,
            quality_status=quality_status,
            limitations=limitations or [],
            warnings=warnings or [],
        )

    def generate_thermal_indicator(self, thermal_matrix: np.ndarray, source_dataset_id: str) -> SatelliteIndicator:
        arr = np.asarray(thermal_matrix, dtype=np.float32)
        valid = arr[np.isfinite(arr)]
        if valid.size == 0:
            stats = {"mean": 0.0, "min": 0.0, "max": 0.0, "valid_pixel_count": 0}
            quality = SatelliteDataQuality.DEGRADED
        else:
            stats = {
                "mean_celsius": float(np.round(float(np.mean(valid)), 2)),
                "min_celsius": float(np.round(float(np.min(valid)), 2)),
                "max_celsius": float(np.round(float(np.max(valid)), 2)),
                "std_dev_celsius": float(np.round(float(np.std(valid)), 2)),
                "valid_pixel_count": int(valid.size),
            }
            quality = SatelliteDataQuality.GOOD

        return self.build_indicator_contract(
            indicator_name="LAND_SURFACE_TEMPERATURE",
            definition="Radiometric surface temperature measured by thermal infrared sensor.",
            calculation_method="Planck law radiance-to-temperature conversion with atmospheric emissivity correction",
            required_bands=["THERMAL_1"],
            source_dataset_id=source_dataset_id,
            statistics=stats,
            unit="degrees_celsius",
            quality_status=quality,
            limitations=[
                "Thermal resolution is typically coarser (e.g. 100m for Landsat, 1km for MODIS).",
                "Represents canopy/soil skin surface temperature, not sub-surface root zone temperature.",
            ],
        )
