"""Multi-Sensor Fusion Engine for EarthMind Drone Module (Stage D5).

Implements Component 11 (IMultiSensorFusionEngine) protocol.
Aligns, correlates, and fuses measurements from concurrent, compatible sensors
(e.g., multispectral + thermal IR + environmental) over the same agricultural area.
Applies explicit spatial and temporal compatibility constraints.
Detects and reports sensor conflicts rather than silently averaging them.
Never fabricates missing data, accuracy claims, or synthetic confidence scores.
"""

import math
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from core.interfaces.drone import IMultiSensorFusionEngine
from core.logging.logger import get_logger
from core.schemas.drone import (
    FusedSensorMeasurementContract,
    MultiSensorFusionReportContract,
    ProcessedSensorMeasurementContract,
    QualityStatus,
    SpatialBoundingBox,
    SpatialCoordinates,
    SpatialCoverage,
    TemporalCoverage,
)
from modules.drone.errors import (
    DroneInvalidArgumentError,
    InsufficientDroneDataError,
    SensorConflictError,
)

logger = get_logger("modules.drone.fusion")


class MultiSensorFusionEngine(IMultiSensorFusionEngine):
    """Component 11: Multi-sensor co-registration and fusion engine."""

    def __init__(
        self,
        max_spatial_distance_meters: float = 15.0,
        max_temporal_delta_seconds: float = 300.0,
        relative_conflict_threshold: float = 0.35,
    ):
        """
        Args:
            max_spatial_distance_meters: Maximum allowable distance between sensor observations to be fused.
            max_temporal_delta_seconds: Maximum allowable time window difference between observations.
            relative_conflict_threshold: Relative discrepancy threshold (|v1 - v2| / mean) to declare conflict on identical channels.
        """
        self._max_spatial_distance = max_spatial_distance_meters
        self._max_temporal_delta = max_temporal_delta_seconds
        self._conflict_threshold = relative_conflict_threshold

    @staticmethod
    def _haversine_distance(coord1: SpatialCoordinates, coord2: SpatialCoordinates) -> float:
        """Calculate great-circle distance in meters between two coordinates."""
        r = 6371000.0  # Earth radius in meters
        phi1 = math.radians(coord1.latitude)
        phi2 = math.radians(coord2.latitude)
        delta_phi = math.radians(coord2.latitude - coord1.latitude)
        delta_lambda = math.radians(coord2.longitude - coord1.longitude)

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return r * c

    @staticmethod
    def _parse_timestamp(ts: str) -> float:
        """Parse ISO 8601 UTC timestamp to epoch seconds."""
        # Clean potential 'Z' or offset
        from datetime import datetime, timezone
        ts_clean = ts.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(ts_clean)
            return dt.timestamp()
        except Exception:
            return 0.0

    def fuse_measurements(
        self,
        sensor_streams: Dict[str, List[ProcessedSensorMeasurementContract]],
        drone_id: str = "drone_default",
        field_id: Optional[str] = None,
    ) -> MultiSensorFusionReportContract:
        """
        Fuse multiple sensor measurement streams.

        Args:
            sensor_streams: Dict of sensor_id -> list of ProcessedSensorMeasurementContracts.
            drone_id: Drone platform identifier.
            field_id: Agricultural field identifier.

        Returns:
            MultiSensorFusionReportContract containing fused measurements, conflicts, and warnings.
        """
        if not sensor_streams:
            raise InsufficientDroneDataError(
                details="No sensor streams provided for multi-sensor fusion.",
                operation="fuse_measurements",
            )

        total_inputs = sum(len(m_list) for m_list in sensor_streams.values())
        sensor_ids = list(sensor_streams.keys())
        warnings: List[str] = []
        conflicts: List[Dict[str, Any]] = []
        incompatible_count = 0
        fused_records: List[FusedSensorMeasurementContract] = []

        if len(sensor_ids) < 2:
            warnings.append(f"Multi-sensor fusion called with only {len(sensor_ids)} sensor stream(s).")

        # Gather all measurements across streams
        all_measurements: List[ProcessedSensorMeasurementContract] = []
        for s_id, m_list in sensor_streams.items():
            all_measurements.extend(m_list)

        # Spatial and temporal coverage derivation
        coords = [m.spatial_reference for m in all_measurements if m.spatial_reference]
        spatial_cov: Optional[SpatialCoverage] = None
        if coords:
            lats = [c.latitude for c in coords]
            lons = [c.longitude for c in coords]
            spatial_cov = SpatialCoverage(
                has_spatial_metadata=True,
                centroid=SpatialCoordinates(
                    latitude=sum(lats) / len(lats),
                    longitude=sum(lons) / len(lons),
                ),
                bounding_box=SpatialBoundingBox(
                    min_latitude=min(lats),
                    max_latitude=max(lats),
                    min_longitude=min(lons),
                    max_longitude=max(lons),
                ),
                field_id=field_id,
            )

        times = [m.timestamp for m in all_measurements if m.timestamp]
        temp_cov: Optional[TemporalCoverage] = None
        if times:
            sorted_t = sorted(times)
            temp_cov = TemporalCoverage(
                start_time=sorted_t[0],
                end_time=sorted_t[-1],
            )

        # Primary stream is the one with the most observations
        sorted_sensors = sorted(sensor_ids, key=lambda sid: len(sensor_streams[sid]), reverse=True)
        primary_sensor_id = sorted_sensors[0]
        other_sensors = sorted_sensors[1:]

        # Fuse observations by pairing primary measurements with temporally and spatially nearest observations from other sensors
        for p_meas in sensor_streams[primary_sensor_id]:
            p_time = self._parse_timestamp(p_meas.timestamp)
            matched_group = [p_meas]
            offsets = []
            deltas = []
            group_conflict = False
            conflict_info = None

            for other_sid in other_sensors:
                best_candidate = None
                best_dist = float("inf")
                best_dt = float("inf")

                for o_meas in sensor_streams[other_sid]:
                    o_time = self._parse_timestamp(o_meas.timestamp)
                    dt = abs(p_time - o_time)
                    if dt > self._max_temporal_delta:
                        continue

                    dist = 0.0
                    if p_meas.spatial_reference and o_meas.spatial_reference:
                        dist = self._haversine_distance(p_meas.spatial_reference, o_meas.spatial_reference)
                        if dist > self._max_spatial_distance:
                            continue

                    if dt < best_dt:
                        best_dt = dt
                        best_dist = dist
                        best_candidate = o_meas

                if best_candidate:
                    matched_group.append(best_candidate)
                    offsets.append(best_dist)
                    deltas.append(best_dt)
                else:
                    incompatible_count += 1

            # Check for conflict between channels with identical meaning/name
            channel_map: Dict[str, List[ProcessedSensorMeasurementContract]] = {}
            for m in matched_group:
                channel_map.setdefault(m.channel_name.lower(), []).append(m)

            for ch_name, m_sublist in channel_map.items():
                if len(m_sublist) > 1:
                    vals = [m.processed_value for m in m_sublist]
                    v_min, v_max = min(vals), max(vals)
                    avg = (v_min + v_max) / 2.0
                    rel_diff = abs(v_max - v_min) / (abs(avg) + 1e-9)

                    if rel_diff > self._conflict_threshold:
                        group_conflict = True
                        conflict_info = {
                            "channel": ch_name,
                            "sensor_ids": [m.source_sensor for m in m_sublist],
                            "values": vals,
                            "relative_difference": round(rel_diff, 4),
                            "threshold": self._conflict_threshold,
                        }
                        conflicts.append(conflict_info)
                        warnings.append(
                            f"Sensor conflict detected on channel '{ch_name}': values {vals} differ by {rel_diff * 100:.1f}% "
                            f"(threshold {self._conflict_threshold * 100:.1f}%). Retaining individual values without silent averaging."
                        )

            # Build fused channels dictionary
            fused_channels: Dict[str, Any] = {}
            for m in matched_group:
                if m.channel_name.lower() in fused_channels:
                    # Multi-sensor channel duplicate: preserve source-keyed reading
                    fused_channels[f"{m.channel_name}_{m.source_sensor}"] = {
                        "value": m.processed_value,
                        "unit": m.normalized_unit,
                        "sensor_id": m.source_sensor,
                        "measurement_id": m.measurement_id,
                    }
                else:
                    fused_channels[m.channel_name.lower()] = {
                        "value": m.processed_value,
                        "unit": m.normalized_unit,
                        "sensor_id": m.source_sensor,
                        "measurement_id": m.measurement_id,
                    }

            fused_record = FusedSensorMeasurementContract(
                timestamp=p_meas.timestamp,
                spatial_reference=p_meas.spatial_reference,
                participating_sensor_ids=[m.source_sensor for m in matched_group],
                participating_measurement_ids=[m.measurement_id for m in matched_group],
                fused_channels=fused_channels,
                fusion_method="spatiotemporal_nearest_neighbor",
                spatial_offset_meters=max(offsets) if offsets else 0.0,
                temporal_delta_seconds=max(deltas) if deltas else 0.0,
                has_conflict=group_conflict,
                conflict_details=conflict_info,
                quality_status=QualityStatus.SUSPECT if group_conflict else QualityStatus.VALID,
                provenance={
                    "primary_sensor": primary_sensor_id,
                    "matched_sensors_count": len(matched_group),
                },
            )
            fused_records.append(fused_record)

        report = MultiSensorFusionReportContract(
            drone_id=drone_id,
            field_id=field_id,
            input_sensor_streams=sensor_ids,
            total_input_measurements=total_inputs,
            fused_measurements_count=len(fused_records),
            fused_measurements=fused_records,
            conflicts_detected_count=len(conflicts),
            conflicts=conflicts,
            incompatible_inputs_count=incompatible_count,
            spatial_coverage=spatial_cov,
            temporal_coverage=temp_cov,
            warnings=warnings,
            provenance={
                "engine": "MultiSensorFusionEngine_v1.0",
                "max_spatial_distance_meters": self._max_spatial_distance,
                "max_temporal_delta_seconds": self._max_temporal_delta,
                "conflict_threshold": self._conflict_threshold,
            },
        )
        return report

    def fuse_sensors(
        self,
        sensor_streams: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Component 11 implementation conforming to IMultiSensorFusionEngine protocol.

        Args:
            sensor_streams: List of dicts representing sensor streams or measurement bundles.

        Returns:
            Dict containing fusion summary, fused measurements, conflicts, and coverage.
        """
        if not isinstance(sensor_streams, list):
            raise DroneInvalidArgumentError(
                details=f"sensor_streams must be a list of dicts, got {type(sensor_streams)}",
                operation="fuse_sensors",
            )

        # Convert dict streams to ProcessedSensorMeasurementContracts
        converted_streams: Dict[str, List[ProcessedSensorMeasurementContract]] = {}
        drone_id = "drone_default"
        field_id = None

        for stream in sensor_streams:
            if not isinstance(stream, dict):
                continue
            sid = stream.get("sensor_id") or "unknown_sensor"
            if "drone_id" in stream:
                drone_id = stream["drone_id"]
            if "field_id" in stream:
                field_id = stream["field_id"]

            raw_meas = stream.get("measurements") or []
            meas_list = []
            for m in raw_meas:
                if isinstance(m, ProcessedSensorMeasurementContract):
                    meas_list.append(m)
                elif isinstance(m, dict):
                    meas_list.append(ProcessedSensorMeasurementContract(**m))
            converted_streams[sid] = meas_list

        report = self.fuse_measurements(
            sensor_streams=converted_streams,
            drone_id=drone_id,
            field_id=field_id,
        )
        return report.model_dump()
