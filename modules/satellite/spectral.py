"""Spectral Band Processing Engine for EarthMind Satellite Module (Stage D4)."""
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from core.interfaces.satellite import ISatelliteSpectralProcessor
from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteBandType,
    SatelliteDataFormat,
    SatelliteGeospatialMetadata,
    SatelliteRawDataReference,
    SatelliteSpectralBand,
)
from modules.satellite.errors import (
    SatelliteInvalidArgumentError,
    SatelliteProcessingError,
)

logger = get_logger("modules.satellite.spectral")

SENTINEL2_BAND_MAP: Dict[str, Tuple[SatelliteBandType, str, float, float, float]] = {
    "B01": (SatelliteBandType.COASTAL_AEROSOL, "Coastal aerosol", 443.0, 20.0, 60.0),
    "B02": (SatelliteBandType.BLUE, "Blue", 490.0, 65.0, 10.0),
    "B03": (SatelliteBandType.GREEN, "Green", 560.0, 35.0, 10.0),
    "B04": (SatelliteBandType.RED, "Red", 665.0, 30.0, 10.0),
    "B05": (SatelliteBandType.RED_EDGE_1, "Red Edge 1", 705.0, 15.0, 20.0),
    "B06": (SatelliteBandType.RED_EDGE_2, "Red Edge 2", 740.0, 15.0, 20.0),
    "B07": (SatelliteBandType.RED_EDGE_3, "Red Edge 3", 783.0, 20.0, 20.0),
    "B08": (SatelliteBandType.NIR, "NIR Broad", 842.0, 115.0, 10.0),
    "B8A": (SatelliteBandType.NIR_NARROW, "NIR Narrow", 865.0, 20.0, 20.0),
    "B09": (SatelliteBandType.WATER_VAPOUR, "Water vapour", 945.0, 20.0, 60.0),
    "B11": (SatelliteBandType.SWIR_1, "SWIR 1", 1610.0, 90.0, 20.0),
    "B12": (SatelliteBandType.SWIR_2, "SWIR 2", 2190.0, 180.0, 20.0),
}

LANDSAT_BAND_MAP: Dict[str, Tuple[SatelliteBandType, str, float, float, float]] = {
    "B1": (SatelliteBandType.COASTAL_AEROSOL, "Coastal aerosol", 443.0, 16.0, 30.0),
    "B2": (SatelliteBandType.BLUE, "Blue", 482.0, 60.0, 30.0),
    "B3": (SatelliteBandType.GREEN, "Green", 562.0, 57.0, 30.0),
    "B4": (SatelliteBandType.RED, "Red", 655.0, 37.0, 30.0),
    "B5": (SatelliteBandType.NIR, "NIR", 865.0, 28.0, 30.0),
    "B6": (SatelliteBandType.SWIR_1, "SWIR 1", 1609.0, 85.0, 30.0),
    "B7": (SatelliteBandType.SWIR_2, "SWIR 2", 2201.0, 187.0, 30.0),
    "B10": (SatelliteBandType.THERMAL_1, "TIRS 1", 10895.0, 590.0, 100.0),
    "B11": (SatelliteBandType.THERMAL_2, "TIRS 2", 12005.0, 1010.0, 100.0),
}

class SatelliteSpectralProcessor(ISatelliteSpectralProcessor):
    def __init__(self, default_scale_factor: float = 0.0001):
        self._default_scale_factor = default_scale_factor

    def map_band_to_canonical(self, band_id: str, constellation: str = "Sentinel-2"):
        bid = band_id.upper().strip()
        cname = constellation.upper()
        if "SENTINEL" in cname or "S2" in cname:
            if bid in SENTINEL2_BAND_MAP:
                return SENTINEL2_BAND_MAP[bid]
            for k, val in SENTINEL2_BAND_MAP.items():
                if bid == val[0].value or bid == val[1].upper():
                    return val
        elif "LANDSAT" in cname:
            if bid in LANDSAT_BAND_MAP:
                return LANDSAT_BAND_MAP[bid]
            for k, val in LANDSAT_BAND_MAP.items():
                if bid == val[0].value or bid == val[1].upper():
                    return val
        for btype in SatelliteBandType:
            if bid == btype.value:
                return (btype, btype.value, 600.0, 50.0, 10.0)
        return (SatelliteBandType.OTHER, bid, 550.0, 50.0, 10.0)

    def calculate_band_statistics(self, matrix: np.ndarray) -> Dict[str, float]:
        valid_vals = matrix[np.isfinite(matrix)]
        if valid_vals.size == 0:
            return {"mean": 0.0, "min": 0.0, "max": 0.0, "std_dev": 0.0, "median": 0.0, "valid_pixel_count": 0.0}
        return {
            "mean": float(np.round(float(np.mean(valid_vals)), 5)),
            "min": float(np.round(float(np.min(valid_vals)), 5)),
            "max": float(np.round(float(np.max(valid_vals)), 5)),
            "std_dev": float(np.round(float(np.std(valid_vals)), 5)),
            "median": float(np.round(float(np.median(valid_vals)), 5)),
            "valid_pixel_count": float(valid_vals.size),
        }

    def process_spectral_bands(
        self,
        raw_ref: Optional[SatelliteRawDataReference],
        target_bands: List[str],
        geospatial_crop: Optional[SatelliteGeospatialMetadata] = None,
        band_matrices: Optional[Dict[str, Any]] = None,
        constellation: str = "Sentinel-2",
        scale_factor: Optional[float] = None,
    ) -> Dict[str, SatelliteSpectralBand]:
        if not target_bands:
            raise SatelliteInvalidArgumentError("target_bands list cannot be empty")
        matrices = band_matrices or {}
        processed: Dict[str, SatelliteSpectralBand] = {}
        factor = scale_factor if scale_factor is not None else self._default_scale_factor

        for band_name in target_bands:
            matrix = None
            if band_name in matrices:
                matrix = matrices[band_name]
            else:
                for k, v in matrices.items():
                    if k.upper() == band_name.upper():
                        matrix = v
                        break
            if matrix is None:
                raise SatelliteProcessingError(
                    details=f"Required band '{band_name}' is missing in source dataset",
                    operation="process_spectral_bands",
                )
            arr = np.asarray(matrix, dtype=np.float32)
            finite_vals = arr[np.isfinite(arr)]
            if finite_vals.size > 0 and np.max(finite_vals) > 1.5:
                calibrated_arr = arr * factor
            else:
                calibrated_arr = arr
            band_type, descriptive_name, wavelength, bandwidth, res = self.map_band_to_canonical(
                band_name, constellation=constellation
            )
            stats = self.calculate_band_statistics(calibrated_arr)
            processed[band_name] = SatelliteSpectralBand(
                band_id=band_name,
                band_name=descriptive_name,
                band_type=band_type,
                central_wavelength_nm=wavelength,
                bandwidth_nm=bandwidth,
                spatial_resolution_meters=res,
                measurement_unit="reflectance",
                is_calibrated=True,
                data_format=SatelliteDataFormat.COG,
                band_raster_ref=raw_ref.storage_uri if raw_ref else None,
                statistics=stats,
            )
        return processed
