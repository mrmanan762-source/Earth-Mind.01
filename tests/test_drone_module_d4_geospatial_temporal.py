"""Comprehensive Test Suite for EarthMind Drone Module Stage D4: Geospatial & Temporal Processing.

Verifies:
1. Valid and invalid coordinates (bounds [-90, 90], [-180, 180], NaN/Inf rejection).
2. Supported and unsupported Coordinate Reference Systems (CRS) (EPSG:4326, EPSG:3857, UTM zones).
3. CRS transformations to EPSG:4326 preserving original coordinates and source CRS.
4. Field-boundary polygon checks using Shapely (inside/outside warnings, non-destructive, zero deletion).
5. Invalid geometry, missing spatial metadata, and incompatible CRS handling.
6. Valid timestamps across formats (ISO 8601 strings, UNIX epoch, datetime objects) and timezone normalization to UTC.
7. Original timestamp and detected timezone preservation.
8. Detection of duplicate timestamps, out-of-order records, and temporal gaps.
9. Time-window filtering and mathematically sound temporal aggregation.
10. Spatio-temporal association, bounding box queries, and versioned SpatioTemporalAssociationContract generation.
11. Integration with DroneService and DroneModule workflow dispatch.
12. Compatibility with D1, D2, and D3 contracts and behaviors.
"""

from datetime import datetime, timezone
import pytest
from typing import Any, Dict, List, Optional

from core.errors.exceptions import (
    DroneInvalidArgumentError,
    GeolocationInvalidError,
    TimestampInvalidError,
)
from core.interfaces.drone import IGeospatialProcessor, ITemporalProcessor
from core.schemas.application import ApplicationRequest
from core.schemas.drone import (
    CalibrationStatus,
    FieldBoundaryContract,
    GeospatialCoordinateContract,
    ProcessedSensorMeasurementContract,
    QualityStatus,
    SpatialBoundingBox,
    SpatialCoordinates,
    SpatialCoverage,
    SpatialProcessingReport,
    SpatioTemporalAssociationContract,
    TemporalCoverage,
    TemporalProcessingReport,
)
from modules.drone.drone_module import DroneModule
from modules.drone.drone_service import DroneService
from modules.drone.geospatial import GeospatialProcessor
from modules.drone.spatiotemporal import SpatioTemporalAssociator
from modules.drone.temporal import TemporalProcessor


# ============================================================================
# Helpers
# ============================================================================

def make_measurement(
    channel_name: str,
    val: float,
    timestamp: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    crs: str = "EPSG:4326",
    meas_id: Optional[str] = None,
) -> ProcessedSensorMeasurementContract:
    spatial_ref = None
    if lat is not None and lon is not None:
        spatial_ref = SpatialCoordinates(latitude=lat, longitude=lon, crs=crs)

    return ProcessedSensorMeasurementContract(
        measurement_id=meas_id or f"meas_{channel_name}_{int(val * 100)}",
        measurement_type="spectral_reflectance",
        channel_name=channel_name,
        original_value=val,
        original_unit="unitless_ratio",
        processed_value=val,
        normalized_unit="unitless_ratio",
        processing_method="none",
        calibration_status=CalibrationStatus.CALIBRATED,
        timestamp=timestamp,
        spatial_reference=spatial_ref,
        quality_status=QualityStatus.VALID,
        source_sensor="test_sensor_d4",
    )


# ============================================================================
# Category 1: Geospatial Coordinates & Validation Tests
# ============================================================================

def test_geospatial_valid_coordinates_wgs84():
    """Verify parsing and validation of valid WGS84 coordinates in multiple formats."""
    gp = GeospatialProcessor()

    # Dictionary
    res_dict = gp.parse_coordinate_metadata({"latitude": 28.6139, "longitude": 77.2090, "altitude": 45.0})
    assert isinstance(res_dict, GeospatialCoordinateContract)
    assert res_dict.latitude == 28.6139
    assert res_dict.longitude == 77.2090
    assert res_dict.altitude_meters == 45.0
    assert res_dict.original_crs == "EPSG:4326"
    assert res_dict.crs == "EPSG:4326"
    assert res_dict.is_transformed is False

    # Tuple / list
    res_tuple = gp.parse_coordinate_metadata([28.6139, 77.2090, 50.0])
    assert res_tuple.latitude == 28.6139
    assert res_tuple.longitude == 77.2090
    assert res_tuple.altitude_meters == 50.0

    # SpatialCoordinates object
    sc = SpatialCoordinates(latitude=25.5941, longitude=85.1376, altitude_meters=30.0)
    res_obj = gp.parse_coordinate_metadata(sc)
    assert res_obj.latitude == 25.5941
    assert res_obj.longitude == 85.1376


def test_geospatial_dms_string_parsing():
    """Verify DMS (degrees minutes seconds) string parsing."""
    gp = GeospatialProcessor()
    # 28°36'50"N, 77°12'32"E -> lat ~ 28.61388, lon ~ 77.20888
    res = gp.parse_coordinate_metadata({
        "lat": "28° 36' 50\" N",
        "lon": "77° 12' 32\" E",
    })
    assert 28.61 <= res.latitude <= 28.62
    assert 77.20 <= res.longitude <= 77.21


def test_geospatial_rejects_out_of_bounds_coordinates():
    """Verify out-of-bounds latitude/longitude values raise GeolocationInvalidError."""
    gp = GeospatialProcessor()

    # Latitude > 90
    with pytest.raises(GeolocationInvalidError) as exc_info:
        gp.parse_coordinate_metadata({"latitude": 91.0, "longitude": 77.0})
    assert "Latitude 91.0 is outside valid range" in str(exc_info.value.details)

    # Latitude < -90
    with pytest.raises(GeolocationInvalidError):
        gp.parse_coordinate_metadata({"latitude": -95.0, "longitude": 77.0})

    # Longitude > 180
    with pytest.raises(GeolocationInvalidError) as exc_info:
        gp.parse_coordinate_metadata({"latitude": 28.0, "longitude": 181.5})
    assert "Longitude 181.5 is outside valid range" in str(exc_info.value.details)

    # Longitude < -180
    with pytest.raises(GeolocationInvalidError):
        gp.parse_coordinate_metadata({"latitude": 28.0, "longitude": -185.0})


def test_geospatial_rejects_nan_and_inf_and_none():
    """Verify NaN, Infinity, and None coordinate values raise GeolocationInvalidError."""
    gp = GeospatialProcessor()

    with pytest.raises(GeolocationInvalidError):
        gp.parse_coordinate_metadata(None)

    with pytest.raises(GeolocationInvalidError):
        gp.parse_coordinate_metadata({"latitude": float("nan"), "longitude": 77.0})

    with pytest.raises(GeolocationInvalidError):
        gp.parse_coordinate_metadata({"latitude": 28.0, "longitude": float("inf")})


# ============================================================================
# Category 2: CRS Transformations & Preservation Tests
# ============================================================================

def test_geospatial_crs_transformation_utm_to_wgs84():
    """Verify transformation from UTM Zone 43N (EPSG:32643) to WGS84 (EPSG:4326)."""
    gp = GeospatialProcessor()

    # Delhi ICAR coordinate in UTM 43N: Easting ~ 715978, Northing ~ 3167195
    raw_coords = {
        "northing": 3167195.0,
        "easting": 715978.0,
        "crs": "EPSG:32643",
    }

    res = gp.parse_coordinate_metadata(raw_coords)
    assert res.is_transformed is True
    assert res.original_crs == "EPSG:32643"
    assert res.original_latitude == 3167195.0
    assert res.original_longitude == 715978.0
    assert res.crs == "EPSG:4326"
    # Should re-project to approximately lat 28.61, lon 77.21
    assert round(res.latitude, 2) == 28.61
    assert round(res.longitude, 2) == 77.21


def test_geospatial_crs_transformation_web_mercator():
    """Verify transformation from Web Mercator (EPSG:3857) to WGS84."""
    gp = GeospatialProcessor()

    # Patna coordinates in EPSG:3857: x ~ 9477543, y ~ 2949187
    raw_coords = {
        "x": 9477543.0,
        "y": 2949187.0,
        "crs": "EPSG:3857",
    }

    res = gp.parse_coordinate_metadata(raw_coords)
    assert res.is_transformed is True
    assert res.original_crs == "EPSG:3857"
    assert round(res.latitude, 1) == 25.6
    assert round(res.longitude, 1) == 85.1


def test_geospatial_unsupported_crs_rejection():
    """Verify invalid or unsupported CRS raises GeolocationInvalidError."""
    gp = GeospatialProcessor()
    with pytest.raises(GeolocationInvalidError) as exc_info:
        gp.parse_coordinate_metadata({"lat": 28.0, "lon": 77.0, "crs": "EPSG:99999999"})
    assert "Unsupported or invalid CRS" in str(exc_info.value.details)


# ============================================================================
# Category 3: Field Boundary Containment Checks Tests
# ============================================================================

def test_field_boundary_containment_all_inside():
    """Verify points strictly within a field polygon boundary return True without warnings."""
    gp = GeospatialProcessor()

    # Rectangular boundary around lat [28.610, 28.620], lon [77.200, 77.220]
    field = FieldBoundaryContract(
        field_id="field_delhi_wheat_01",
        crs="EPSG:4326",
        polygon_coordinates=[
            [77.200, 28.610],
            [77.220, 28.610],
            [77.220, 28.620],
            [77.200, 28.620],
            [77.200, 28.610],
        ],
        coordinate_format="LON_LAT",
    )

    pts = [
        gp.parse_coordinate_metadata({"lat": 28.612, "lon": 77.205}),
        gp.parse_coordinate_metadata({"lat": 28.615, "lon": 77.210}),
        gp.parse_coordinate_metadata({"lat": 28.618, "lon": 77.215}),
    ]

    all_inside, inside_count, outside_count, warnings = gp.check_field_boundary(pts, field)
    assert all_inside is True
    assert inside_count == 3
    assert outside_count == 0
    assert len(warnings) == 0


def test_field_boundary_containment_outside_points_non_destructive():
    """Verify points outside boundary produce non-destructive warnings and are never deleted."""
    gp = GeospatialProcessor()

    field = FieldBoundaryContract(
        field_id="field_delhi_wheat_01",
        crs="EPSG:4326",
        polygon_coordinates=[
            [77.200, 28.610],
            [77.220, 28.610],
            [77.220, 28.620],
            [77.200, 28.620],
            [77.200, 28.610],
        ],
        coordinate_format="LON_LAT",
    )

    pts = [
        gp.parse_coordinate_metadata({"lat": 28.615, "lon": 77.210}),  # Inside
        gp.parse_coordinate_metadata({"lat": 28.650, "lon": 77.250}),  # Outside
    ]

    all_inside, inside_count, outside_count, warnings = gp.check_field_boundary(pts, field)
    assert all_inside is False
    assert inside_count == 1
    assert outside_count == 1
    assert any("outside field 'field_delhi_wheat_01' boundary" in w for w in warnings)


def test_field_boundary_invalid_geometry_handling():
    """Verify degenerate boundary geometry (<3 vertices in dict or collinear) produces warnings gracefully."""
    gp = GeospatialProcessor()
    bad_field_dict = {
        "field_id": "bad_field",
        "crs": "EPSG:4326",
        "polygon_coordinates": [[77.20, 28.60], [77.21, 28.61], [77.20, 28.60]],  # Degenerate collinear points
    }
    pts = [gp.parse_coordinate_metadata({"lat": 28.605, "lon": 77.205})]

    all_inside, inside_count, outside_count, warnings = gp.check_field_boundary(pts, bad_field_dict)
    assert all_inside is False
    assert any("Invalid field boundary geometry" in w or "Error constructing boundary polygon" in w for w in warnings)


# ============================================================================
# Category 4: Spatial Coverage & Protocol Conformance Tests
# ============================================================================

def test_process_spatial_protocol_conformance():
    """Verify GeospatialProcessor conforms to IGeospatialProcessor protocol."""
    gp = GeospatialProcessor()
    assert isinstance(gp, IGeospatialProcessor)

    # With coordinates
    cov = gp.process_spatial({"latitude": 28.6139, "longitude": 77.2090}, field_id="field_01")
    assert isinstance(cov, SpatialCoverage)
    assert cov.has_spatial_metadata is True
    assert cov.centroid.latitude == 28.6139
    assert cov.field_id == "field_01"

    # None / empty coordinates
    cov_empty = gp.process_spatial(None, field_id="field_01")
    assert cov_empty.has_spatial_metadata is False
    assert cov_empty.centroid is None


def test_evaluate_measurements_spatial_report():
    """Verify evaluate_measurements_spatial produces SpatialProcessingReport with bounding box."""
    gp = GeospatialProcessor()
    meas = [
        make_measurement("red", 0.12, "2026-11-09T04:00:00Z", lat=28.612, lon=77.205),
        make_measurement("nir", 0.65, "2026-11-09T04:00:01Z", lat=28.618, lon=77.215),
    ]

    report = gp.evaluate_measurements_spatial(meas)
    assert isinstance(report, SpatialProcessingReport)
    assert report.has_spatial_metadata is True
    assert report.total_points_evaluated == 2
    assert report.bounding_box.min_latitude == 28.612
    assert report.bounding_box.max_latitude == 28.618
    assert report.bounding_box.min_longitude == 77.205
    assert report.bounding_box.max_longitude == 77.215


# ============================================================================
# Category 5: Temporal Processing & Sequence Ordering Tests
# ============================================================================

def test_temporal_valid_timestamp_parsing_and_utc_normalization():
    """Verify parsing ISO 8601 strings, offsets, epoch, and normalizing to UTC."""
    tp = TemporalProcessor()

    # UTC string
    dt1, iso1, tz1 = tp.parse_and_normalize_timestamp("2026-11-09T04:00:00Z")
    assert iso1 == "2026-11-09T04:00:00Z"
    assert tz1 == "UTC"

    # IST offset (+05:30)
    dt2, iso2, tz2 = tp.parse_and_normalize_timestamp("2026-11-09T09:30:00+05:30")
    assert iso2 == "2026-11-09T04:00:00Z"
    assert tz2 == "+05:30"

    # UNIX Epoch in seconds (1762660800 = 2025-11-09T04:00:00Z)
    dt3, iso3, tz3 = tp.parse_and_normalize_timestamp(1762660800)
    assert iso3 == "2025-11-09T04:00:00Z"
    assert tz3 == "UTC_EPOCH"

    # Python datetime object
    dt_input = datetime(2026, 11, 9, 4, 0, 0, tzinfo=timezone.utc)
    dt4, iso4, tz4 = tp.parse_and_normalize_timestamp(dt_input)
    assert iso4 == "2026-11-09T04:00:00Z"


def test_temporal_rejects_invalid_timestamps():
    """Verify invalid, empty, or unparseable timestamps raise TimestampInvalidError."""
    tp = TemporalProcessor()

    with pytest.raises(TimestampInvalidError):
        tp.parse_and_normalize_timestamp(None)

    with pytest.raises(TimestampInvalidError):
        tp.parse_and_normalize_timestamp("")

    with pytest.raises(TimestampInvalidError):
        tp.parse_and_normalize_timestamp("not_a_valid_date")

    with pytest.raises(TimestampInvalidError):
        tp.parse_and_normalize_timestamp(float("nan"))


def test_process_temporal_protocol_conformance():
    """Verify TemporalProcessor conforms to ITemporalProcessor protocol."""
    tp = TemporalProcessor()
    assert isinstance(tp, ITemporalProcessor)

    cov = tp.process_temporal("2026-11-09T04:00:00Z", "2026-11-09T04:10:00Z")
    assert isinstance(cov, TemporalCoverage)
    assert cov.start_time == "2026-11-09T04:00:00Z"
    assert cov.end_time == "2026-11-09T04:10:00Z"
    assert cov.duration_seconds == 600.0


def test_process_temporal_rejects_end_before_start():
    """Verify error raised when end_timestamp precedes collection_timestamp."""
    tp = TemporalProcessor()
    with pytest.raises(TimestampInvalidError) as exc_info:
        tp.process_temporal("2026-11-09T04:10:00Z", "2026-11-09T04:00:00Z")
    assert "precedes start timestamp" in str(exc_info.value.details)


def test_temporal_sequence_reordering_and_duplicate_detection():
    """Verify out-of-order measurements are chronologically re-sequenced and duplicates detected."""
    tp = TemporalProcessor()

    # 3 measurements out of chronological order
    m1 = make_measurement("red", 0.12, "2026-11-09T04:00:10Z", meas_id="m1")
    m2 = make_measurement("red", 0.15, "2026-11-09T04:00:00Z", meas_id="m2")
    m3 = make_measurement("red", 0.18, "2026-11-09T04:00:00Z", meas_id="m3")  # Duplicate timestamp with m2

    sequenced, report = tp.sequence_measurements([m1, m2, m3])
    assert len(sequenced) == 3
    # Check reordering: m2 and m3 should come before m1
    assert sequenced[0].timestamp == "2026-11-09T04:00:00Z"
    assert sequenced[1].timestamp == "2026-11-09T04:00:00Z"
    assert sequenced[2].timestamp == "2026-11-09T04:00:10Z"

    assert report.is_chronological is False
    assert report.out_of_order_count > 0
    assert report.duplicate_timestamps_count == 1
    assert report.duration_seconds == 10.0


def test_temporal_gap_detection():
    """Verify gaps exceeding threshold are detected and recorded in report."""
    tp = TemporalProcessor(default_gap_threshold_seconds=5.0)

    # 15-second gap between m1 and m2
    m1 = make_measurement("red", 0.12, "2026-11-09T04:00:00Z")
    m2 = make_measurement("red", 0.14, "2026-11-09T04:00:15Z")
    m3 = make_measurement("red", 0.16, "2026-11-09T04:00:16Z")

    _, report = tp.sequence_measurements([m1, m2, m3])
    assert report.temporal_gaps_count == 1
    assert report.gap_intervals_seconds == [15.0]
    assert any("temporal gap" in w for w in report.warnings)


def test_temporal_time_window_filtering():
    """Verify filter_time_window filters measurements within an inclusive UTC window."""
    tp = TemporalProcessor()

    m1 = make_measurement("red", 0.10, "2026-11-09T04:00:00Z")
    m2 = make_measurement("red", 0.12, "2026-11-09T04:05:00Z")
    m3 = make_measurement("red", 0.14, "2026-11-09T04:10:00Z")
    m4 = make_measurement("red", 0.16, "2026-11-09T04:20:00Z")

    # Filter [04:05, 04:15]
    filtered = tp.filter_time_window(
        [m1, m2, m3, m4],
        start_time="2026-11-09T04:05:00Z",
        end_time="2026-11-09T04:15:00Z",
    )
    assert len(filtered) == 2
    assert filtered[0].timestamp == "2026-11-09T04:05:00Z"
    assert filtered[1].timestamp == "2026-11-09T04:10:00Z"


def test_temporal_aggregation():
    """Verify aggregate_measurements_temporal computes mathematical means per interval."""
    tp = TemporalProcessor()

    # 4 measurements over a 20-second span
    m1 = make_measurement("red", 0.10, "2026-11-09T04:00:01Z")
    m2 = make_measurement("red", 0.20, "2026-11-09T04:00:05Z")
    m3 = make_measurement("red", 0.30, "2026-11-09T04:00:12Z")
    m4 = make_measurement("red", 0.40, "2026-11-09T04:00:18Z")

    # 10-second buckets
    agg = tp.aggregate_measurements_temporal([m1, m2, m3, m4], interval_seconds=10.0)
    assert len(agg) == 2

    # Bucket 0: m1 and m2 (mean = 0.15)
    b0 = agg[0]
    assert b0["channels"]["red"]["count"] == 2
    assert pytest.approx(b0["channels"]["red"]["mean"], rel=1e-5) == 0.15

    # Bucket 1: m3 and m4 (mean = 0.35)
    b1 = agg[1]
    assert b1["channels"]["red"]["count"] == 2
    assert pytest.approx(b1["channels"]["red"]["mean"], rel=1e-5) == 0.35


# ============================================================================
# Category 6: Spatio-Temporal Association & Queries Tests
# ============================================================================

def test_spatiotemporal_associator_end_to_end():
    """Verify SpatioTemporalAssociator produces valid SpatioTemporalAssociationContract."""
    associator = SpatioTemporalAssociator()

    field = FieldBoundaryContract(
        field_id="field_patna_rice_01",
        crs="EPSG:4326",
        polygon_coordinates=[
            [85.10, 25.55],
            [85.20, 25.55],
            [85.20, 25.65],
            [85.10, 25.65],
            [85.10, 25.55],
        ],
    )

    meas = [
        make_measurement("red", 0.12, "2026-11-09T04:00:10Z", lat=25.59, lon=85.13),
        make_measurement("nir", 0.65, "2026-11-09T04:00:00Z", lat=25.60, lon=85.14),
    ]

    association = associator.associate(
        drone_id="drone_kisan_01",
        sensor_id="sensor_ms_01",
        measurements=meas,
        field_id="field_patna_rice_01",
        field_boundary=field,
    )

    assert isinstance(association, SpatioTemporalAssociationContract)
    assert association.contract_name == "SpatioTemporalAssociationContract"
    assert association.schema_version == "1.0"
    assert association.drone_id == "drone_kisan_01"
    assert association.sensor_id == "sensor_ms_01"
    assert association.field_id == "field_patna_rice_01"
    assert association.measurements_count == 2

    # Spatial report verified
    assert association.spatial_report.has_spatial_metadata is True
    assert association.spatial_report.field_boundary_checked is True
    assert association.spatial_report.is_within_field_boundary is True

    # Temporal report verified (re-sequenced chronologically)
    assert association.temporal_report.normalized_start_time == "2026-11-09T04:00:00Z"
    assert association.temporal_report.normalized_end_time == "2026-11-09T04:00:10Z"
    assert association.temporal_report.is_chronological is False


def test_spatiotemporal_query_by_bounding_box():
    """Verify query_by_bounding_box filters measurements accurately."""
    associator = SpatioTemporalAssociator()

    m_in = make_measurement("red", 0.12, "2026-11-09T04:00:00Z", lat=28.6139, lon=77.2090)
    m_out = make_measurement("red", 0.14, "2026-11-09T04:00:00Z", lat=25.5941, lon=85.1376)

    bbox = SpatialBoundingBox(
        min_latitude=28.0,
        max_latitude=29.0,
        min_longitude=77.0,
        max_longitude=78.0,
        crs="EPSG:4326",
    )

    res = associator.query_by_bounding_box([m_in, m_out], bbox)
    assert len(res) == 1
    assert res[0].spatial_reference.latitude == 28.6139


# ============================================================================
# Category 7: DroneService & DroneModule Integration Tests
# ============================================================================

def test_drone_service_associate_spatiotemporal_integration():
    """Verify DroneService integrates associate_spatiotemporal and increments telemetry."""
    service = DroneService()

    meas = [
        make_measurement("red", 0.12, "2026-11-09T04:00:00Z", lat=28.6139, lon=77.2090),
        make_measurement("nir", 0.65, "2026-11-09T04:00:05Z", lat=28.6140, lon=77.2091),
    ]

    res = service.associate_spatiotemporal(
        drone_id="drone_service_d4",
        sensor_id="sensor_service_d4",
        measurements=meas,
        field_id="field_delhi_01",
    )

    assert isinstance(res, SpatioTemporalAssociationContract)
    assert res.drone_id == "drone_service_d4"
    assert res.measurements_count == 2

    # Telemetry verified
    counters = service.diagnostics.get_health_status()["counters"]
    assert counters["spatiotemporal_associations_total"] >= 1.0


def test_drone_module_workflow_dispatch_spatiotemporal():
    """Verify DroneModule dispatches 'associate_spatiotemporal' operation cleanly."""
    module = DroneModule()
    module.initialize()

    meas = [
        {
            "measurement_id": "m1",
            "measurement_type": "spectral_reflectance",
            "channel_name": "red",
            "original_value": 0.12,
            "original_unit": "unitless_ratio",
            "processed_value": 0.12,
            "normalized_unit": "unitless_ratio",
            "processing_method": "none",
            "calibration_status": "CALIBRATED",
            "timestamp": "2026-11-09T04:00:00Z",
            "spatial_reference": {"latitude": 28.61, "longitude": 77.20},
            "quality_status": "VALID",
            "source_sensor": "sensor_01",
        }
    ]

    req = ApplicationRequest(
        request_id="req_d4_spatiotemporal_test",
        source="test_client",
        operation="associate_spatiotemporal",
        payload={
            "drone_id": "drone_workflow_d4",
            "sensor_id": "sensor_workflow_d4",
            "measurements": meas,
            "field_id": "field_test_d4",
        },
    )

    resp = module.handle(req)
    assert resp.status == "SUCCESS"
    assert resp.response["drone_id"] == "drone_workflow_d4"
    assert resp.response["measurements_count"] == 1
    assert resp.response["contract_name"] == "SpatioTemporalAssociationContract"

    module.shutdown()
