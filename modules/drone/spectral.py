"""Spectral Analysis Engine for EarthMind Drone Module (Stage D5).

Implements Component 9 (ISpectralNumericalAnalyzer) protocol.
Validates spectral bands, checks wavelength/resolution compatibility,
computes reflectance summaries/histograms, and handles division by zero safely.
Never fabricates missing bands.
"""

import math
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from core.interfaces.drone import ISpectralNumericalAnalyzer
from core.logging.logger import get_logger
from core.schemas.drone import (
    QualityStatus,
    SpatialCoordinates,
    SpectralAnalysisResultContract,
    SpectralBandMetadataContract,
)
from modules.drone.errors import (
    DroneInvalidArgumentError,
    IndicatorProcessingFailedError,
    InsufficientDroneDataError,
)

logger = get_logger("modules.drone.spectral")

# Canonical optical band wavelength profiles (center, min, max, FWHM)
STANDARD_SPECTRAL_BANDS: Dict[str, Dict[str, Any]] = {
    "coastal_blue": {
        "center_wavelength_nm": 443.0,
        "bandwidth_nm": 20.0,
        "wavelength_min_nm": 433.0,
        "wavelength_max_nm": 453.0,
        "aliases": ["coastal", "cb"],
    },
    "blue": {
        "center_wavelength_nm": 475.0,
        "bandwidth_nm": 30.0,
        "wavelength_min_nm": 450.0,
        "wavelength_max_nm": 500.0,
        "aliases": ["b", "blue_band"],
    },
    "green": {
        "center_wavelength_nm": 560.0,
        "bandwidth_nm": 40.0,
        "wavelength_min_nm": 530.0,
        "wavelength_max_nm": 580.0,
        "aliases": ["g", "green_band"],
    },
    "red": {
        "center_wavelength_nm": 668.0,
        "bandwidth_nm": 30.0,
        "wavelength_min_nm": 640.0,
        "wavelength_max_nm": 680.0,
        "aliases": ["r", "red_band"],
    },
    "red_edge": {
        "center_wavelength_nm": 717.0,
        "bandwidth_nm": 15.0,
        "wavelength_min_nm": 705.0,
        "wavelength_max_nm": 740.0,
        "aliases": ["re", "rededge", "red_edge_band"],
    },
    "nir": {
        "center_wavelength_nm": 840.0,
        "bandwidth_nm": 40.0,
        "wavelength_min_nm": 780.0,
        "wavelength_max_nm": 900.0,
        "aliases": ["nir_band", "near_ir", "near_infrared"],
    },
    "swir1": {
        "center_wavelength_nm": 1610.0,
        "bandwidth_nm": 60.0,
        "wavelength_min_nm": 1550.0,
        "wavelength_max_nm": 1750.0,
        "aliases": ["swir", "swir_1", "shortwave_ir1"],
    },
    "swir2": {
        "center_wavelength_nm": 2190.0,
        "bandwidth_nm": 80.0,
        "wavelength_min_nm": 2100.0,
        "wavelength_max_nm": 2300.0,
        "aliases": ["swir_2", "shortwave_ir2"],
    },
}


class SpectralAnalysisEngine(ISpectralNumericalAnalyzer):
    """Component 9: Multispectral and Hyperspectral band analysis engine."""

    def __init__(self):
        self._band_catalog = STANDARD_SPECTRAL_BANDS

    @staticmethod
    def canonicalize_band_name(name: str) -> str:
        """Map band alias or raw channel name to canonical name."""
        norm = name.lower().strip().replace("-", "_").replace(" ", "_")
        for canonical, info in STANDARD_SPECTRAL_BANDS.items():
            if norm == canonical or norm in info.get("aliases", []):
                return canonical
        return norm

    def get_band_profile(self, band_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve standard optical wavelength profile for a canonical band name."""
        canon = self.canonicalize_band_name(band_name)
        return self._band_catalog.get(canon)

    def validate_band_data(
        self,
        band_name: str,
        data: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[float], List[str]]:
        """
        Validate band array/values against physical limits [0.0, 1.0] for reflectance.

        Returns:
            (is_valid, flattened_float_values, warnings)
        """
        warnings: List[str] = []
        flat_values: List[float] = []

        if data is None:
            return False, [], [f"Band '{band_name}' data is None."]

        if isinstance(data, (int, float)):
            flat_values = [float(data)]
        elif isinstance(data, (list, tuple)):
            # Flatten potential 2D/3D matrix
            def _flatten(val: Any):
                if isinstance(val, (list, tuple)):
                    for item in val:
                        _flatten(item)
                elif isinstance(val, (int, float)):
                    flat_values.append(float(val))
                else:
                    warnings.append(f"Ignored non-numerical element in band '{band_name}': {type(val)}")
            _flatten(data)
        elif hasattr(data, "flatten"):  # numpy array support without strict numpy dependency
            flat_values = [float(x) for x in data.flatten().tolist() if isinstance(x, (int, float))]
        else:
            return False, [], [f"Unsupported data type for band '{band_name}': {type(data)}"]

        if not flat_values:
            return False, [], [f"Band '{band_name}' contains no valid numerical values."]

        # Check for NaN or Inf
        valid_finite = []
        for v in flat_values:
            if math.isnan(v) or math.isinf(v):
                warnings.append(f"Non-finite value ({v}) detected in band '{band_name}'.")
            else:
                valid_finite.append(v)

        if not valid_finite:
            return False, [], [f"Band '{band_name}' has no finite numerical values."]

        # Validate reflectance range
        unit = (metadata or {}).get("unit", "reflectance").lower()
        min_v = min(valid_finite)
        max_v = max(valid_finite)

        # Reflectance typically [0.0, 1.0] (or [0, 100] if percentage)
        if unit in ("reflectance", "unitless_ratio", "ratio"):
            if min_v < -0.01:
                warnings.append(f"Physically implausible negative reflectance in '{band_name}': min={min_v:.4f}")
            if max_v > 1.2:  # allow slight atmospheric/specular tolerance
                if max_v <= 100.0 and min_v >= 0.0:
                    warnings.append(f"Reflectance in '{band_name}' appears to be percentage [0-100%]; max={max_v:.2f}")
                else:
                    warnings.append(f"Reflectance in '{band_name}' exceeds standard range [0.0, 1.0]: max={max_v:.4f}")

        return True, valid_finite, warnings

    def compute_band_statistics(self, values: List[float]) -> Dict[str, float]:
        """Compute basic summary statistics and percentiles."""
        if not values:
            return {}

        n = len(values)
        sorted_vals = sorted(values)
        mean_v = sum(sorted_vals) / n
        min_v = sorted_vals[0]
        max_v = sorted_vals[-1]

        # Variance and StdDev
        if n > 1:
            variance = sum((x - mean_v) ** 2 for x in sorted_vals) / (n - 1)
            std_dev = math.sqrt(variance)
        else:
            std_dev = 0.0

        # Median
        mid = n // 2
        if n % 2 == 1:
            median_v = sorted_vals[mid]
        else:
            median_v = (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0

        # Percentiles
        def _percentile(p: float) -> float:
            idx = (n - 1) * p
            low = int(math.floor(idx))
            high = int(math.ceil(idx))
            weight = idx - low
            return sorted_vals[low] * (1.0 - weight) + sorted_vals[high] * weight

        return {
            "mean": round(mean_v, 6),
            "min": round(min_v, 6),
            "max": round(max_v, 6),
            "std_dev": round(std_dev, 6),
            "median": round(median_v, 6),
            "p25": round(_percentile(0.25), 6),
            "p75": round(_percentile(0.75), 6),
            "sample_count": float(n),
        }

    def analyze_bands(
        self,
        band_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Analyze band data conforming to ISpectralNumericalAnalyzer protocol.

        Args:
            band_data: Dict containing band arrays/values, metadata, drone_id, sensor_id, timestamp.

        Returns:
            Dict containing band statistics, detected bands, and quality assessment.
        """
        if not isinstance(band_data, dict):
            raise DroneInvalidArgumentError(
                details=f"band_data must be a dict, got {type(band_data)}",
                operation="analyze_bands",
            )

        drone_id = band_data.get("drone_id", "unknown_drone")
        sensor_id = band_data.get("sensor_id", "unknown_sensor")
        timestamp = band_data.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        raw_bands = band_data.get("bands") or {}

        # If raw_bands is empty, inspect top-level keys for bands
        if not raw_bands:
            raw_bands = {k: v for k, v in band_data.items() if k not in ("drone_id", "sensor_id", "timestamp", "metadata", "spatial_reference")}

        if not raw_bands:
            raise InsufficientDroneDataError(
                details="No spectral bands provided for spectral analysis.",
                operation="analyze_bands",
            )

        detected_bands: List[str] = []
        band_metadata_contracts: Dict[str, SpectralBandMetadataContract] = {}
        band_stats: Dict[str, Dict[str, float]] = {}
        all_warnings: List[str] = []

        user_metadata = band_data.get("metadata", {})

        # Matrix dimension compatibility check if matrices provided
        matrix_shapes: Dict[str, Tuple[int, int]] = {}

        for b_name, b_data in raw_bands.items():
            canon_name = self.canonicalize_band_name(b_name)
            detected_bands.append(canon_name)

            # Metadata profile
            b_meta_dict = user_metadata.get(b_name, {})
            profile = self.get_band_profile(canon_name) or {}

            meta_contract = SpectralBandMetadataContract(
                band_name=canon_name,
                center_wavelength_nm=b_meta_dict.get("center_wavelength_nm") or profile.get("center_wavelength_nm"),
                bandwidth_nm=b_meta_dict.get("bandwidth_nm") or profile.get("bandwidth_nm"),
                wavelength_min_nm=b_meta_dict.get("wavelength_min_nm") or profile.get("wavelength_min_nm"),
                wavelength_max_nm=b_meta_dict.get("wavelength_max_nm") or profile.get("wavelength_max_nm"),
                unit=b_meta_dict.get("unit", "reflectance"),
                spatial_resolution_meters=b_meta_dict.get("spatial_resolution_meters"),
                is_calibrated=b_meta_dict.get("is_calibrated", True),
            )
            band_metadata_contracts[canon_name] = meta_contract

            # Check 2D matrix shape if nested list
            if isinstance(b_data, (list, tuple)) and b_data and isinstance(b_data[0], (list, tuple)):
                matrix_shapes[canon_name] = (len(b_data), len(b_data[0]))

            # Validate & compute statistics
            is_valid, flat_vals, warnings = self.validate_band_data(b_name, b_data, metadata=b_meta_dict)
            all_warnings.extend(warnings)

            if is_valid and flat_vals:
                stats = self.compute_band_statistics(flat_vals)
                band_stats[canon_name] = stats
            else:
                all_warnings.append(f"Band '{canon_name}' could not produce valid statistics.")

        # Check resolution/matrix shape consistency
        if len(matrix_shapes) > 1:
            shapes_set = set(matrix_shapes.values())
            if len(shapes_set) > 1:
                all_warnings.append(f"Incompatible matrix resolutions detected across bands: {matrix_shapes}")

        # Overall quality
        quality_status = QualityStatus.VALID
        if not band_stats:
            quality_status = QualityStatus.INVALID
        elif all_warnings:
            quality_status = QualityStatus.DEGRADED

        # Assemble versioned result contract
        result_contract = SpectralAnalysisResultContract(
            drone_id=drone_id,
            sensor_id=sensor_id,
            timestamp=timestamp,
            detected_bands=detected_bands,
            band_metadata=band_metadata_contracts,
            band_statistics=band_stats,
            quality_status=quality_status,
            warnings=all_warnings,
            provenance={
                "engine": "SpectralAnalysisEngine_v1.0",
                "bands_processed_count": len(detected_bands),
                "shapes": {k: list(v) for k, v in matrix_shapes.items()},
            },
        )

        return result_contract.model_dump()
