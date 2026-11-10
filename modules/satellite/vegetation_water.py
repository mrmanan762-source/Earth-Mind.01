"""Vegetation and Water Analysis Engine for EarthMind Satellite Module (Stage D5)."""
from typing import Any, Dict, List, Optional
import numpy as np

from modules.satellite.errors import SatelliteInvalidArgumentError

class VegetationWaterAnalyzer:
    def compute_distribution_metrics(self, data_matrix: np.ndarray) -> Dict[str, Any]:
        if data_matrix is None:
            raise SatelliteInvalidArgumentError("data_matrix cannot be None")
        arr = np.asarray(data_matrix, dtype=np.float32)
        total_pixels = int(arr.size)
        valid_mask = np.isfinite(arr)
        valid_pixels = int(np.sum(valid_mask))

        if valid_pixels == 0:
            return {
                "mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "std_dev": 0.0,
                "variance": 0.0, "coefficient_of_variation": 0.0, "valid_pixel_count": 0,
                "invalid_pixel_count": total_pixels, "coverage_valid_percentage": 0.0,
            }

        valid_vals = arr[valid_mask]
        mean_val = float(np.mean(valid_vals))
        std_val = float(np.std(valid_vals))
        cv = float(std_val / mean_val) if abs(mean_val) > 1e-6 else 0.0
        return {
            "mean": float(np.round(mean_val, 4)),
            "median": float(np.round(float(np.median(valid_vals)), 4)),
            "min": float(np.round(float(np.min(valid_vals)), 4)),
            "max": float(np.round(float(np.max(valid_vals)), 4)),
            "std_dev": float(np.round(std_val, 4)),
            "variance": float(np.round(float(np.var(valid_vals)), 4)),
            "coefficient_of_variation": float(np.round(cv, 4)),
            "valid_pixel_count": valid_pixels,
            "invalid_pixel_count": total_pixels - valid_pixels,
            "coverage_valid_percentage": float(np.round(valid_pixels / total_pixels * 100.0, 2)),
        }

    def analyze_vegetation_vigor(self, ndvi_matrix: np.ndarray, ndre_matrix: Optional[np.ndarray] = None, evi_matrix: Optional[np.ndarray] = None) -> Dict[str, Any]:
        ndvi_stats = self.compute_distribution_metrics(ndvi_matrix)
        result = {
            "ndvi_statistics": ndvi_stats,
            "canopy_density_class": "HIGH_DENSITY" if ndvi_stats["mean"] > 0.6 else "MODERATE_DENSITY" if ndvi_stats["mean"] > 0.3 else "SPARSE_OR_EMERGING",
            "spatial_heterogeneity": "HIGH_VARIABILITY" if ndvi_stats["coefficient_of_variation"] > 0.3 else "MODERATE_VARIABILITY" if ndvi_stats["coefficient_of_variation"] > 0.15 else "UNIFORM",
            "limitations": [
                "Vegetation index values represent optical canopy greenness, not direct crop yield.",
                "Values may be influenced by soil background reflectance or weed presence.",
            ],
        }
        if ndre_matrix is not None:
            result["ndre_statistics"] = self.compute_distribution_metrics(ndre_matrix)
        if evi_matrix is not None:
            result["evi_statistics"] = self.compute_distribution_metrics(evi_matrix)
        return result

    def analyze_water_indicators(self, ndwi_canopy_matrix: Optional[np.ndarray] = None, ndwi_water_matrix: Optional[np.ndarray] = None) -> Dict[str, Any]:
        result = {
            "limitations": [
                "Spectral water indicators reflect leaf water thickness or surface water reflection.",
                "Spectral water indices MUST NOT be equated with direct in-situ volumetric soil moisture.",
            ]
        }
        if ndwi_canopy_matrix is not None:
            result["canopy_water_thickness"] = self.compute_distribution_metrics(ndwi_canopy_matrix)
            result["canopy_moisture_relative_state"] = "ELEVATED_CANOPY_MOISTURE" if result["canopy_water_thickness"]["mean"] > 0.2 else "MODERATE_CANOPY_MOISTURE" if result["canopy_water_thickness"]["mean"] > 0.0 else "LOW_CANOPY_MOISTURE"
        if ndwi_water_matrix is not None:
            result["surface_water_delineation"] = self.compute_distribution_metrics(ndwi_water_matrix)
            water_pixels = np.sum(np.asarray(ndwi_water_matrix) > 0.0)
            result["surface_ponding_detected"] = bool(water_pixels > (ndwi_water_matrix.size * 0.05))
        return result
