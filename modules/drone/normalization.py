"""Unit Normalization Engine for EarthMind Drone Module (Stage D3).

Implements Component 6 (ICalibrationNormalizer unit conversion).
Converts supported measurements into standard canonical SI/scientific units.
Validates source units and conversion rules.
Rejects unknown or incompatible units.
Preserves original values and units alongside normalized values.
"""

from typing import Any, Dict, Optional, Tuple

from core.logging.logger import get_logger
from modules.drone.errors import (
    DroneInvalidArgumentError,
    UnitConversionFailedError,
)

logger = get_logger("modules.drone.normalization")

# Canonical Unit Taxonomy
# Temperature: "celsius" (°C) or "kelvin" (K). EarthMind agronomic canonical: "celsius"
# Spectral: "unitless_ratio" (0.0 to 1.0)
# Pressure: "hpa" (hectopascals)
# Irradiance: "w/m2" (watts per square meter)
# Distance / Altitude: "meters" (m)
# Percentage: "percent" (%) or normalized to ratio

CANONICAL_UNITS = {
    "temperature": "celsius",
    "spectral": "unitless_ratio",
    "pressure": "hpa",
    "irradiance": "w/m2",
    "distance": "meters",
    "humidity": "percent",
}


class UnitNormalizer:
    """Normalizes physical units into canonical scientific standards."""

    def normalize(
        self,
        value: float,
        source_unit: str,
        channel_name: str = "",
        target_unit: Optional[str] = None,
    ) -> Tuple[float, str, str]:
        """
        Normalize a numerical measurement to standard canonical unit.

        Args:
            value: raw or calibrated numeric value.
            source_unit: string representing original unit.
            channel_name: optional hint for measurement type (e.g. 'red', 'temperature').
            target_unit: optional explicit desired unit.

        Returns:
            Tuple[float, str, str]:
                (normalized_value, canonical_unit, conversion_method)

        Raises:
            UnitConversionFailedError if conversion is impossible or unit is unknown.
        """
        if not source_unit or not source_unit.strip():
            raise UnitConversionFailedError(
                from_unit="EMPTY",
                to_unit=target_unit or "canonical",
                details="Source unit cannot be empty.",
            )

        src = source_unit.strip().lower()
        ch = channel_name.strip().lower()

        # 1. Temperature conversions
        if src in ("celsius", "degc", "c", "°c"):
            if target_unit and target_unit.lower() in ("kelvin", "k"):
                return round(value + 273.15, 4), "kelvin", "celsius_to_kelvin"
            return round(value, 4), "celsius", "identity_celsius"

        if src in ("fahrenheit", "degf", "f", "°f"):
            celsius_val = (value - 32.0) * (5.0 / 9.0)
            if target_unit and target_unit.lower() in ("kelvin", "k"):
                return round(celsius_val + 273.15, 4), "kelvin", "fahrenheit_to_kelvin"
            return round(celsius_val, 4), "celsius", "fahrenheit_to_celsius"

        if src in ("kelvin", "k"):
            celsius_val = value - 273.15
            if target_unit and target_unit.lower() in ("kelvin", "k"):
                return round(value, 4), "kelvin", "identity_kelvin"
            return round(celsius_val, 4), "celsius", "kelvin_to_celsius"

        if src in ("millikelvin", "mk"):
            celsius_val = (value / 1000.0) - 273.15
            return round(celsius_val, 4), "celsius", "millikelvin_to_celsius"

        if src in ("centikelvin", "ck"):
            # FLIR Lepton raw radiometric often centikelvin (100 * K)
            celsius_val = (value / 100.0) - 273.15
            return round(celsius_val, 4), "celsius", "centikelvin_to_celsius"

        # 2. Spectral / Reflectance conversions
        if src in ("unitless_ratio", "ratio", "fraction", "reflectance"):
            return round(value, 6), "unitless_ratio", "identity_ratio"

        if src in ("percent", "%"):
            return round(value / 100.0, 6), "unitless_ratio", "percent_to_ratio"

        if src in ("raw_dn", "dn", "digital_number"):
            # 16-bit DN scaling to [0.0, 1.0] reflectance if DN > 1.0
            if value > 1.0:
                # Assume 16-bit maximum (65535) or 8-bit (255)
                max_dn = 65535.0 if value > 255 else 255.0
                ratio = max(0.0, min(1.0, value / max_dn))
                return round(ratio, 6), "unitless_ratio", f"dn_to_ratio(max={int(max_dn)})"
            return round(value, 6), "unitless_ratio", "identity_ratio"

        # 3. Pressure conversions
        if src in ("hpa", "mbar"):
            return round(value, 2), "hpa", "identity_hpa"

        if src in ("pa", "pascal"):
            return round(value / 100.0, 2), "hpa", "pascal_to_hpa"

        if src in ("bar",):
            return round(value * 1000.0, 2), "hpa", "bar_to_hpa"

        if src in ("atm", "atmosphere"):
            return round(value * 1013.25, 2), "hpa", "atm_to_hpa"

        # 4. Solar Irradiance conversions
        if src in ("w/m2", "w/m^2", "watt/m2", "w_m2"):
            return round(value, 3), "w/m2", "identity_irradiance"

        if src in ("kw/m2", "kw/m^2"):
            return round(value * 1000.0, 3), "w/m2", "kw_to_w_m2"

        # 5. Distance / Altitude conversions
        if src in ("meters", "meter", "m"):
            return round(value, 3), "meters", "identity_meters"

        if src in ("feet", "foot", "ft"):
            return round(value * 0.3048, 3), "meters", "feet_to_meters"

        if src in ("centimeters", "cm"):
            return round(value / 100.0, 3), "meters", "cm_to_meters"

        # 6. Relative Humidity
        if src in ("rh_percent", "%rh", "rh"):
            return round(value, 2), "percent", "identity_rh_percent"

        # Check if known canonical unit directly
        if src in CANONICAL_UNITS.values():
            return round(value, 4), src, f"identity_{src}"

        # Unrecognized / unsupported unit
        raise UnitConversionFailedError(
            from_unit=source_unit,
            to_unit=target_unit or "canonical",
            details=f"Unrecognized or unsupported unit '{source_unit}' for channel '{channel_name}'.",
        )
