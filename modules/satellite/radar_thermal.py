"""SAR (Radar) and Thermal Processing Foundations for EarthMind Satellite Module (Stage D4)."""
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from core.logging.logger import get_logger
from core.schemas.satellite import SatelliteBandType, SatelliteDataFormat, SatelliteSpectralBand
from modules.satellite.errors import SatelliteInvalidArgumentError

logger = get_logger("modules.satellite.radar_thermal")

class SatelliteSARProcessor:
    SUPPORTED_POLARIZATIONS = ("VV", "VH", "HH", "HV")

    def process_sar_band(self, raw_matrix: Any, polarization: str, is_linear_amplitude: bool = True, calibration_constant: float = 1.0, spatial_resolution_meters: float = 10.0) -> SatelliteSpectralBand:
        pol_clean = polarization.upper().strip()
        if pol_clean not in self.SUPPORTED_POLARIZATIONS:
            raise SatelliteInvalidArgumentError(f"Unsupported SAR polarization: {polarization}")
        arr = np.asarray(raw_matrix, dtype=np.float32)
        if arr.size == 0:
            raise SatelliteInvalidArgumentError("SAR raw matrix cannot be empty")
        if is_linear_amplitude:
            power = np.square(arr) * calibration_constant
            power_safe = np.where(power > 1e-7, power, 1e-7)
            sigma0_db = 10.0 * np.log10(power_safe)
        else:
            sigma0_db = arr
        band_type = getattr(SatelliteBandType, f"SAR_{pol_clean}", SatelliteBandType.OTHER)
        finite_vals = sigma0_db[np.isfinite(sigma0_db)]
        stats = {
            "mean": float(np.round(float(np.mean(finite_vals)), 3)) if finite_vals.size > 0 else 0.0,
            "min": float(np.round(float(np.min(finite_vals)), 3)) if finite_vals.size > 0 else 0.0,
            "max": float(np.round(float(np.max(finite_vals)), 3)) if finite_vals.size > 0 else 0.0,
            "std_dev": float(np.round(float(np.std(finite_vals)), 3)) if finite_vals.size > 0 else 0.0,
        }
        return SatelliteSpectralBand(
            band_id=f"SAR_{pol_clean}",
            band_name=f"SAR {pol_clean} Backscatter",
            band_type=band_type,
            central_wavelength_nm=55500000.0,
            spatial_resolution_meters=spatial_resolution_meters,
            measurement_unit="sigma0_dB",
            is_calibrated=True,
            data_format=SatelliteDataFormat.COG,
            statistics=stats,
        )

class SatelliteThermalProcessor:
    def convert_kelvin_to_celsius(self, kelvin_data: np.ndarray) -> np.ndarray:
        return kelvin_data - 273.15

    def process_thermal_band(self, raw_matrix: Any, band_id: str = "TIRS_1", scale_factor: float = 0.00341802, offset: float = 149.0, spatial_resolution_meters: float = 100.0) -> SatelliteSpectralBand:
        arr = np.asarray(raw_matrix, dtype=np.float32)
        if arr.size == 0:
            raise SatelliteInvalidArgumentError("Thermal raw matrix cannot be empty")
        finite = arr[np.isfinite(arr)]
        if finite.size > 0 and np.max(finite) > 1000.0:
            st_kelvin = arr * scale_factor + offset
            st_celsius = self.convert_kelvin_to_celsius(st_kelvin)
        elif finite.size > 0 and np.max(finite) > 200.0:
            st_celsius = self.convert_kelvin_to_celsius(arr)
        else:
            st_celsius = arr
        valid_celsius = st_celsius[np.isfinite(st_celsius)]
        stats = {
            "mean_celsius": float(np.round(float(np.mean(valid_celsius)), 2)) if valid_celsius.size > 0 else 0.0,
            "min_celsius": float(np.round(float(np.min(valid_celsius)), 2)) if valid_celsius.size > 0 else 0.0,
            "max_celsius": float(np.round(float(np.max(valid_celsius)), 2)) if valid_celsius.size > 0 else 0.0,
            "std_dev_celsius": float(np.round(float(np.std(valid_celsius)), 2)) if valid_celsius.size > 0 else 0.0,
        }
        band_type = SatelliteBandType.THERMAL_1 if "1" in band_id else SatelliteBandType.THERMAL_2
        return SatelliteSpectralBand(
            band_id=band_id,
            band_name=f"Thermal Infrared ({band_id})",
            band_type=band_type,
            central_wavelength_nm=10895.0,
            bandwidth_nm=590.0,
            spatial_resolution_meters=spatial_resolution_meters,
            measurement_unit="celsius",
            is_calibrated=True,
            data_format=SatelliteDataFormat.COG,
            statistics=stats,
        )
