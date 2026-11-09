"""Numerical Analysis Engine for EarthMind Drone Module (Stage D5).

Processes numerical sensor channels (e.g. Thermal IR, Environmental, Soil moisture probes).
Computes summary statistics, preserves units and measurement ranges, and maintains
strict non-diagnostic boundaries (zero disease, stress, or deficiency claims).
"""

import math
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from core.logging.logger import get_logger
from core.schemas.drone import (
    NumericalAnalysisResultContract,
    ProcessedSensorMeasurementContract,
    QualityStatus,
)
from modules.drone.errors import (
    DroneInvalidArgumentError,
    InsufficientDroneDataError,
)

logger = get_logger("modules.drone.numerical")


class NumericalAnalysisEngine:
    """Numerical processing engine for thermal and environmental sensor channels."""

    def __init__(self):
        pass

    def compute_summary_statistics(
        self,
        values: List[float],
    ) -> Dict[str, Any]:
        """Compute sample statistics (mean, min, max, std_dev, median, percentiles)."""
        if not values:
            return {}

        n = len(values)
        sorted_vals = sorted(values)
        mean_v = sum(sorted_vals) / n
        min_v = sorted_vals[0]
        max_v = sorted_vals[-1]

        if n > 1:
            variance = sum((x - mean_v) ** 2 for x in sorted_vals) / (n - 1)
            std_dev = math.sqrt(variance)
        else:
            std_dev = 0.0

        mid = n // 2
        if n % 2 == 1:
            median_v = sorted_vals[mid]
        else:
            median_v = (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0

        def _percentile(p: float) -> float:
            idx = (n - 1) * p
            low = int(math.floor(idx))
            high = int(math.ceil(idx))
            weight = idx - low
            return sorted_vals[low] * (1.0 - weight) + sorted_vals[high] * weight

        return {
            "sample_count": n,
            "mean": round(mean_v, 4),
            "min_value": round(min_v, 4),
            "max_value": round(max_v, 4),
            "std_dev": round(std_dev, 4),
            "median": round(median_v, 4),
            "percentiles": {
                "p25": round(_percentile(0.25), 4),
                "p75": round(_percentile(0.75), 4),
            },
        }

    def process_measurements(
        self,
        measurements: List[ProcessedSensorMeasurementContract],
        channel_name: str,
    ) -> NumericalAnalysisResultContract:
        """
        Aggregate numerical measurements for a given channel into a versioned NumericalAnalysisResultContract.
        """
        if not measurements:
            raise InsufficientDroneDataError(
                details=f"No measurements provided for channel '{channel_name}'.",
                operation="process_measurements",
            )

        matching = [m for m in measurements if m.channel_name.lower() == channel_name.lower()]
        if not matching:
            raise InsufficientDroneDataError(
                details=f"No measurements matching channel '{channel_name}' found.",
                operation="process_measurements",
            )

        values: List[float] = []
        warnings: List[str] = []
        original_units = set()
        normalized_units = set()
        drone_ids = set()
        sensor_ids = set()

        for m in matching:
            v = m.processed_value
            if math.isnan(v) or math.isinf(v):
                warnings.append(f"Ignored non-finite value in measurement {m.measurement_id}: {v}")
            else:
                values.append(v)
            original_units.add(m.original_unit)
            normalized_units.add(m.normalized_unit)
            sensor_ids.add(m.source_sensor)
            if "drone_id" in m.provenance:
                drone_ids.add(m.provenance["drone_id"])

        if not values:
            raise InsufficientDroneDataError(
                details=f"No valid finite numerical values for channel '{channel_name}'.",
                operation="process_measurements",
            )

        stats = self.compute_summary_statistics(values)

        orig_unit = next(iter(original_units)) if len(original_units) == 1 else "mixed"
        norm_unit = next(iter(normalized_units)) if len(normalized_units) == 1 else "mixed"
        if orig_unit == "mixed" or norm_unit == "mixed":
            warnings.append(f"Multiple units detected in channel '{channel_name}': orig={original_units}, norm={normalized_units}")

        drone_id = next(iter(drone_ids)) if drone_ids else "unknown_drone"
        sensor_id = next(iter(sensor_ids)) if sensor_ids else matching[0].source_sensor

        timestamp = matching[0].timestamp

        quality_status = QualityStatus.VALID
        if warnings:
            quality_status = QualityStatus.DEGRADED

        return NumericalAnalysisResultContract(
            drone_id=drone_id,
            sensor_id=sensor_id,
            channel_name=channel_name,
            timestamp=timestamp,
            original_unit=orig_unit,
            normalized_unit=norm_unit,
            sample_count=stats["sample_count"],
            mean=stats["mean"],
            min_value=stats["min_value"],
            max_value=stats["max_value"],
            std_dev=stats["std_dev"],
            median=stats["median"],
            percentiles=stats["percentiles"],
            quality_status=quality_status,
            warnings=warnings,
            provenance={
                "engine": "NumericalAnalysisEngine_v1.0",
                "matching_measurements_count": len(matching),
                "measurement_ids": [m.measurement_id for m in matching],
            },
        )

    def process_thermal_summary(
        self,
        measurements: List[ProcessedSensorMeasurementContract],
        channel_name: str = "thermal_ir",
    ) -> NumericalAnalysisResultContract:
        """
        Specialized thermal measurement processing preserving temperature units (celsius, kelvin, etc.)
        without making agricultural disease or stress diagnoses.
        """
        result = self.process_measurements(measurements, channel_name=channel_name)

        # Sanity validation on thermal ranges (e.g. canopy surface temperature in Celsius [-10, 70])
        norm_u = result.normalized_unit.lower()
        if "celsius" in norm_u or norm_u == "c":
            if result.min_value < -20.0 or result.max_value > 85.0:
                result.warnings.append(
                    f"Thermal reading [{result.min_value}, {result.max_value}] °C outside typical agronomic range [-20, 85] °C."
                )
                result.quality_status = QualityStatus.SUSPECT

        return result
