"""Spatio-Temporal Association Engine for EarthMind Drone Module (Stage D4).

Associates ProcessedSensorMeasurementContract records with spatial and temporal context.
Supports spatial-temporal grouping, time-window and bounding-box queries, and emits
versioned SpatioTemporalAssociationContract artifacts without hallucinating metadata.
"""

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from core.errors.exceptions import (
    DroneInvalidArgumentError,
    GeolocationInvalidError,
    TimestampInvalidError,
)
from core.logging.logger import get_logger
from core.schemas.drone import (
    FieldBoundaryContract,
    ProcessedSensorMeasurementContract,
    SpatialBoundingBox,
    SpatialProcessingReport,
    SpatioTemporalAssociationContract,
    TemporalProcessingReport,
)
from modules.drone.geospatial import GeospatialProcessor
from modules.drone.temporal import TemporalProcessor

logger = get_logger("modules.drone.spatiotemporal")


class SpatioTemporalAssociator:
    """Coordinates Geospatial and Temporal association over processed sensor measurements."""

    def __init__(
        self,
        geospatial_processor: Optional[GeospatialProcessor] = None,
        temporal_processor: Optional[TemporalProcessor] = None,
    ):
        self._geo_processor = geospatial_processor or GeospatialProcessor()
        self._time_processor = temporal_processor or TemporalProcessor()

    @property
    def geospatial_processor(self) -> GeospatialProcessor:
        return self._geo_processor

    @property
    def temporal_processor(self) -> TemporalProcessor:
        return self._time_processor

    def associate(
        self,
        drone_id: str,
        sensor_id: str,
        measurements: List[ProcessedSensorMeasurementContract],
        field_id: Optional[str] = None,
        field_boundary: Optional[Union[FieldBoundaryContract, Dict[str, Any]]] = None,
        declared_crs: Optional[str] = None,
        gap_threshold_seconds: Optional[float] = None,
    ) -> SpatioTemporalAssociationContract:
        """
        Associate processed measurements with comprehensive spatial and temporal reports.
        Emits versioned SpatioTemporalAssociationContract with complete provenance.
        """
        if not drone_id or not drone_id.strip():
            raise DroneInvalidArgumentError(
                details="drone_id must be a non-empty string.",
                operation="associate",
            )
        if not sensor_id or not sensor_id.strip():
            raise DroneInvalidArgumentError(
                details="sensor_id must be a non-empty string.",
                operation="associate",
            )
        if not measurements:
            raise DroneInvalidArgumentError(
                details="measurements list cannot be empty for spatiotemporal association.",
                operation="associate",
            )

        # Step 1: Temporal processing & sequencing
        sequenced_measurements, temporal_report = self._time_processor.sequence_measurements(
            measurements,
            gap_threshold_seconds=gap_threshold_seconds,
        )

        # Step 2: Geospatial processing & evaluation
        spatial_report = self._geo_processor.evaluate_measurements_spatial(
            sequenced_measurements,
            field_boundary=field_boundary,
            declared_crs=declared_crs,
        )

        consolidated_warnings: List[str] = list(temporal_report.warnings)
        consolidated_warnings.extend(spatial_report.warnings)

        consolidated_errors: List[str] = list(spatial_report.errors)

        provenance = {
            "engine": "SpatioTemporalAssociator",
            "version": "1.0",
            "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "input_measurements_count": len(measurements),
            "sequenced_measurements_count": len(sequenced_measurements),
            "temporal_coverage": {
                "start": temporal_report.normalized_start_time,
                "end": temporal_report.normalized_end_time,
                "duration_seconds": temporal_report.duration_seconds,
            },
            "spatial_coverage": {
                "has_spatial": spatial_report.has_spatial_metadata,
                "crs_target": spatial_report.crs_target,
                "points_evaluated": spatial_report.total_points_evaluated,
                "field_boundary_checked": spatial_report.field_boundary_checked,
            },
        }

        return SpatioTemporalAssociationContract(
            contract_name="SpatioTemporalAssociationContract",
            schema_version="1.0",
            association_id=f"sta_{uuid.uuid4().hex[:12]}",
            drone_id=drone_id,
            sensor_id=sensor_id,
            field_id=field_id,
            spatial_report=spatial_report,
            temporal_report=temporal_report,
            measurements_count=len(sequenced_measurements),
            measurements=sequenced_measurements,
            provenance=provenance,
            warnings=consolidated_warnings,
            errors=consolidated_errors,
        )

    def query_by_bounding_box(
        self,
        measurements: List[ProcessedSensorMeasurementContract],
        bounding_box: SpatialBoundingBox,
    ) -> List[ProcessedSensorMeasurementContract]:
        """
        Query and filter measurements located within a given bounding box (EPSG:4326).
        Preserves original measurement objects.
        """
        results: List[ProcessedSensorMeasurementContract] = []
        for m in measurements:
            if m.spatial_reference:
                try:
                    c = self._geo_processor.parse_coordinate_metadata(
                        m.spatial_reference,
                        declared_crs=m.spatial_reference.crs,
                    )
                    if (
                        bounding_box.min_latitude <= c.latitude <= bounding_box.max_latitude
                        and bounding_box.min_longitude <= c.longitude <= bounding_box.max_longitude
                    ):
                        results.append(m)
                except Exception:
                    pass
        return results

    def query_by_time_window(
        self,
        measurements: List[ProcessedSensorMeasurementContract],
        start_time: str,
        end_time: str,
    ) -> List[ProcessedSensorMeasurementContract]:
        """Query measurements within a UTC time window."""
        return self._time_processor.filter_time_window(measurements, start_time, end_time)

    def query_spatiotemporal(
        self,
        measurements: List[ProcessedSensorMeasurementContract],
        bounding_box: Optional[SpatialBoundingBox] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> List[ProcessedSensorMeasurementContract]:
        """Combined spatial and temporal query."""
        res = list(measurements)
        if start_time and end_time:
            res = self.query_by_time_window(res, start_time, end_time)
        if bounding_box:
            res = self.query_by_bounding_box(res, bounding_box)
        return res
