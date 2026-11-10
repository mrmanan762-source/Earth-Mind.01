"""Geospatial Analysis Engine for EarthMind Satellite Module (Stage D5)."""
from typing import Any, Dict, List, Optional
import numpy as np
from shapely.geometry import Polygon

from modules.satellite.errors import SatelliteInvalidArgumentError

class SatelliteSpatialAnalyzer:
    def calculate_coverage_area_hectares(self, pixel_count: int, spatial_resolution_meters: float) -> float:
        if pixel_count < 0 or spatial_resolution_meters <= 0:
            return 0.0
        return float(np.round((float(pixel_count) * (spatial_resolution_meters ** 2)) / 10000.0, 4))

    def compute_zonal_statistics(self, raster_data: np.ndarray, spatial_resolution_meters: float = 10.0, zones: Optional[Dict[str, np.ndarray]] = None) -> Dict[str, Any]:
        arr = np.asarray(raster_data, dtype=np.float32)
        valid_mask = np.isfinite(arr)
        valid_count = int(np.sum(valid_mask))
        overall_stats = {
            "total_pixels": int(arr.size),
            "valid_pixels": valid_count,
            "total_area_hectares": self.calculate_coverage_area_hectares(arr.size, spatial_resolution_meters),
            "valid_area_hectares": self.calculate_coverage_area_hectares(valid_count, spatial_resolution_meters),
            "spatial_resolution_meters": spatial_resolution_meters,
            "mean": float(np.round(float(np.mean(arr[valid_mask])), 4)) if valid_count > 0 else 0.0,
            "min": float(np.round(float(np.min(arr[valid_mask])), 4)) if valid_count > 0 else 0.0,
            "max": float(np.round(float(np.max(arr[valid_mask])), 4)) if valid_count > 0 else 0.0,
            "std_dev": float(np.round(float(np.std(arr[valid_mask])), 4)) if valid_count > 0 else 0.0,
        }
        zonal_results = {"overall": overall_stats}
        if zones:
            for zone_name, zone_mask in zones.items():
                zmask = np.asarray(zone_mask, dtype=bool) & valid_mask
                zcount = int(np.sum(zmask))
                zonal_results[zone_name] = {
                    "valid_pixels": zcount,
                    "area_hectares": self.calculate_coverage_area_hectares(zcount, spatial_resolution_meters),
                    "mean": float(np.round(float(np.mean(arr[zmask])), 4)) if zcount > 0 else 0.0,
                    "min": float(np.round(float(np.min(arr[zmask])), 4)) if zcount > 0 else 0.0,
                    "max": float(np.round(float(np.max(arr[zmask])), 4)) if zcount > 0 else 0.0,
                    "std_dev": float(np.round(float(np.std(arr[zmask])), 4)) if zcount > 0 else 0.0,
                }
        return zonal_results
