"""Data Quality and Validation Engine for EarthMind Satellite Module (Stage D4)."""
from typing import Any, Dict, List, Optional
import numpy as np

from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteDataQuality,
    SatelliteGeospatialMetadata,
    SatelliteSpectralBand,
    SatelliteTemporalMetadata,
)

logger = get_logger("modules.satellite.quality")

class QualityValidationReport:
    def __init__(self, status: str, quality_rating: SatelliteDataQuality, warnings: List[str], errors: List[str], metrics: Dict[str, Any]):
        self.status = status
        self.quality_rating = quality_rating
        self.warnings = warnings
        self.errors = errors
        self.metrics = metrics

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "quality_rating": self.quality_rating.value,
            "warnings": self.warnings,
            "errors": self.errors,
            "metrics": self.metrics,
        }

class SatelliteQualityValidator:
    def validate_processed_dataset(self, processed_bands: Dict[str, SatelliteSpectralBand], geospatial: SatelliteGeospatialMetadata, temporal: SatelliteTemporalMetadata, band_matrices: Optional[Dict[str, np.ndarray]] = None, max_acceptable_nodata_pct: float = 50.0, max_cloud_cover_pct: float = 60.0, cloud_cover_over_target: float = 0.0) -> QualityValidationReport:
        warnings: List[str] = []
        errors: List[str] = []
        metrics: Dict[str, Any] = {}

        if not processed_bands:
            errors.append("No processed spectral bands present")
            return QualityValidationReport("INSUFFICIENT_DATA", SatelliteDataQuality.INCOMPLETE, warnings, errors, {"band_count": 0})

        metrics["band_count"] = len(processed_bands)
        if geospatial is None:
            errors.append("Missing geospatial metadata")
        else:
            if not (-90.0 <= geospatial.latitude <= 90.0 and -180.0 <= geospatial.longitude <= 180.0):
                errors.append(f"Geospatial centroid invalid: ({geospatial.latitude}, {geospatial.longitude})")
            if not geospatial.crs:
                errors.append("Missing CRS in geospatial metadata")

        if temporal is None or not temporal.acquisition_date:
            errors.append("Missing acquisition timestamp")

        total_pixels = 0
        total_nodata_pixels = 0
        if band_matrices:
            shapes = set()
            for bname, mat in band_matrices.items():
                arr = np.asarray(mat, dtype=np.float32)
                shapes.add(arr.shape)
                finite_count = int(np.sum(np.isfinite(arr)))
                total_pixels += arr.size
                total_nodata_pixels += (arr.size - finite_count)
            if len(shapes) > 1:
                warnings.append(f"Inconsistent band raster dimensions: {shapes}")
            nodata_pct = (total_nodata_pixels / total_pixels * 100.0) if total_pixels > 0 else 0.0
            metrics["nodata_percentage"] = float(np.round(nodata_pct, 2))
            if nodata_pct > max_acceptable_nodata_pct:
                warnings.append(f"High NoData percentage: {nodata_pct:.1f}%")

        metrics["cloud_cover_target"] = float(cloud_cover_over_target)
        if cloud_cover_over_target >= 90.0:
            errors.append(f"Target area completely obscured by clouds: {cloud_cover_over_target:.1f}%")
        elif cloud_cover_over_target > max_cloud_cover_pct:
            warnings.append(f"Target area heavily clouded: {cloud_cover_over_target:.1f}%")

        if errors:
            status = "INVALID"
            quality_rating = SatelliteDataQuality.INVALID
        elif cloud_cover_over_target >= 80.0:
            status = "INSUFFICIENT_DATA"
            quality_rating = SatelliteDataQuality.CLOUD_OBSCURED
        elif warnings:
            status = "VALID_WITH_WARNINGS"
            quality_rating = SatelliteDataQuality.DEGRADED if (cloud_cover_over_target > 30.0 or metrics.get("nodata_percentage", 0) > 20.0) else SatelliteDataQuality.ACCEPTABLE
        else:
            status = "VALID"
            quality_rating = SatelliteDataQuality.EXCELLENT if cloud_cover_over_target < 5.0 else SatelliteDataQuality.GOOD

        return QualityValidationReport(status, quality_rating, warnings, errors, metrics)
