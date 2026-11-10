"""Acceptance Test Suite for EarthMind Satellite Intelligence Module Stage D4: Satellite Data Processing."""

import io
import json
import numpy as np
import pytest
import tifffile

from core.schemas.application import ApplicationRequest
from core.schemas.satellite import (
    SatelliteBandType,
    SatelliteDataFormat,
    SatelliteDataQuality,
    SatelliteDatasetMetadata,
    SatelliteGeospatialMetadata,
    SatelliteProcessedData,
    SatelliteProcessingStatus,
    SatelliteRawDataReference,
    SatelliteSensorType,
    SatelliteSpectralBand,
    SatelliteTemporalMetadata,
)
from modules.satellite.errors import (
    SatelliteInvalidArgumentError,
    SatelliteProcessingError,
)
from modules.satellite.geospatial import SatelliteGeospatialProcessor
from modules.satellite.image_processing import SatelliteImageProcessor
from modules.satellite.processing_pipeline import SatelliteProcessingPipeline
from modules.satellite.quality import SatelliteQualityValidator
from modules.satellite.radar_thermal import (
    SatelliteSARProcessor,
    SatelliteThermalProcessor,
)
from modules.satellite.satellite_module import SatelliteModule
from modules.satellite.satellite_service import SatelliteService
from modules.satellite.spectral import SatelliteSpectralProcessor
from modules.satellite.temporal_numerical import SatelliteTemporalProcessor


@pytest.fixture
def sample_geo():
    return SatelliteGeospatialMetadata(
        latitude=28.6139,
        longitude=77.2090,
        bounding_box=[77.10, 28.50, 77.30, 28.70],
        crs="EPSG:4326",
        spatial_resolution_meters=10.0,
        field_id="field_delhi_001",
        farm_id="farm_north_001",
    )


@pytest.fixture
def sample_temporal():
    return SatelliteTemporalMetadata(
        acquisition_date="2025-03-30T10:30:00Z",
        start_time="2025-03-30T10:00:00Z",
        end_time="2025-03-30T11:00:00Z",
        revisit_interval_days=5.0,
        temporal_coverage_type="SCENE_INSTANTANEOUS",
    )


@pytest.fixture
def sample_metadata(sample_geo, sample_temporal):
    return SatelliteDatasetMetadata(
        dataset_id="S2A_MSIL2A_20250330_TEST_D4",
        provider_id="copernicus_cdse",
        constellation="Sentinel-2",
        platform="Sentinel-2A",
        instrument="MSI",
        sensor_type=SatelliteSensorType.OPTICAL_MULTISPECTRAL,
        processing_level="LEVEL-2A",
        geospatial=sample_geo,
        temporal=sample_temporal,
        cloud_cover_percentage=10.0,
        quality_status=SatelliteDataQuality.GOOD,
        license_attribution="Contains modified Copernicus Sentinel data [2025]",
    )


@pytest.fixture
def sample_optical_matrices():
    return {
        "BLUE": np.array([
            [500, 520, 510, 530],
            [490, 505, 515, 525],
            [480, 495, 500, 510],
            [510, 515, 520, 530],
        ], dtype=np.float32),
        "GREEN": np.array([
            [600, 620, 610, 630],
            [590, 605, 615, 625],
            [580, 595, 600, 610],
            [610, 615, 620, 630],
        ], dtype=np.float32),
        "RED": np.array([
            [400, 420, 410, 430],
            [390, 405, 415, 425],
            [380, 395, 400, 410],
            [410, 415, 420, 430],
        ], dtype=np.float32),
        "NIR": np.array([
            [2500, 2600, 2550, 2650],
            [2400, 2500, 2520, 2580],
            [2350, 2450, 2480, 2500],
            [2550, 2580, 2600, 2650],
        ], dtype=np.float32),
        "SWIR_1": np.array([
            [1200, 1250, 1220, 1280],
            [1180, 1210, 1230, 1260],
            [1150, 1190, 1200, 1220],
            [1220, 1240, 1250, 1280],
        ], dtype=np.float32),
    }


def test_1_image_processor_read_raster_dict():
    proc = SatelliteImageProcessor()
    payload = {"data": [[1.0, 2.0], [3.0, 4.0]]}
    arr = proc.read_raster(payload)
    assert isinstance(arr, np.ndarray)
    assert arr.shape == (2, 2)
    assert arr[0, 0] == 1.0


def test_2_image_processor_read_raster_geotiff_bytes():
    proc = SatelliteImageProcessor()
    buf = io.BytesIO()
    raw = np.array([[10, 20], [30, 40]], dtype=np.uint16)
    tifffile.imwrite(buf, raw)
    data_bytes = buf.getvalue()
    arr = proc.read_raster(data_bytes, data_format=SatelliteDataFormat.GEOTIFF)
    assert isinstance(arr, np.ndarray)
    assert arr.shape == (2, 2)
    assert arr[1, 1] == 40.0


def test_3_image_processor_read_windowed():
    proc = SatelliteImageProcessor()
    full_arr = np.arange(16, dtype=np.float32).reshape((4, 4))
    windowed = proc.read_raster(full_arr, window=(1, 3, 1, 3))
    assert windowed.shape == (2, 2)
    assert windowed[0, 0] == full_arr[1, 1]
    assert windowed[1, 1] == full_arr[2, 2]


def test_4_image_processor_nodata_handling():
    proc = SatelliteImageProcessor(default_nodata_value=-9999.0)
    arr = np.array([[1.0, -9999.0], [np.nan, 5.0]], dtype=np.float32)
    clean, valid_mask = proc.handle_nodata_and_mask(arr)
    assert valid_mask[0, 0] is np.True_
    assert valid_mask[0, 1] is np.False_
    assert np.isnan(clean[0, 1])


def test_5_image_processor_atmospheric_correction(sample_metadata, sample_optical_matrices):
    proc = SatelliteImageProcessor()
    corrected = proc.apply_atmospheric_correction(sample_optical_matrices, sample_metadata)
    assert "NIR" in corrected
    assert np.max(corrected["NIR"]) <= 1.0
    assert np.isclose(corrected["NIR"][0, 0], 0.25)


def test_6_image_processor_cloud_masking(sample_metadata, sample_optical_matrices):
    proc = SatelliteImageProcessor()
    report = proc.generate_cloud_mask(sample_optical_matrices, sample_metadata)
    assert "cloud_mask" in report
    assert "cloud_cover_percentage" in report
    assert "is_usable" in report
    assert isinstance(report["cloud_mask"], np.ndarray)


def test_7_spectral_band_mapping():
    proc = SatelliteSpectralProcessor()
    btype, name, wave, bw, res = proc.map_band_to_canonical("B04", constellation="Sentinel-2")
    assert btype == SatelliteBandType.RED
    assert wave == 665.0
    assert res == 10.0


def test_8_spectral_band_statistics():
    proc = SatelliteSpectralProcessor()
    mat = np.array([[0.2, 0.4], [0.6, np.nan]], dtype=np.float32)
    stats = proc.calculate_band_statistics(mat)
    assert stats["valid_pixel_count"] == 3.0
    assert np.isclose(stats["mean"], 0.4)


def test_9_spectral_processing_success(sample_optical_matrices):
    proc = SatelliteSpectralProcessor()
    bands = proc.process_spectral_bands(
        raw_ref=None,
        target_bands=["RED", "NIR"],
        band_matrices=sample_optical_matrices,
        constellation="Sentinel-2",
    )
    assert "RED" in bands
    assert "NIR" in bands
    assert bands["RED"].band_type == SatelliteBandType.RED


def test_10_spectral_processing_missing_band_error(sample_optical_matrices):
    proc = SatelliteSpectralProcessor()
    with pytest.raises(SatelliteProcessingError):
        proc.process_spectral_bands(
            raw_ref=None,
            target_bands=["RED", "MISSING_BAND_XYZ"],
            band_matrices=sample_optical_matrices,
        )


def test_11_geospatial_crs_validation():
    geo_proc = SatelliteGeospatialProcessor()
    assert geo_proc.validate_crs("EPSG:4326") == "EPSG:4326"
    with pytest.raises(SatelliteInvalidArgumentError):
        geo_proc.validate_crs("EPSG:INVALID_CODE_999999")


def test_12_geospatial_reprojection_utm_to_wgs84():
    geo_proc = SatelliteGeospatialProcessor()
    utm_payload = {
        "x": 716000.0,
        "y": 3167000.0,
        "crs": "EPSG:32643",
        "bounding_box": [715000.0, 3166000.0, 717000.0, 3168000.0],
        "spatial_resolution_meters": 10.0,
        "field_id": "field_utm_001",
    }
    reprojected = geo_proc.process_geospatial(utm_payload, target_crs="EPSG:4326")
    assert reprojected.crs == "EPSG:4326"
    assert 28.0 <= reprojected.latitude <= 29.0
    assert 76.5 <= reprojected.longitude <= 77.5


def test_13_geospatial_invalid_coordinates_rejected():
    geo_proc = SatelliteGeospatialProcessor()
    invalid_payload = {"latitude": 150.0, "longitude": 77.0, "crs": "EPSG:4326"}
    with pytest.raises(SatelliteInvalidArgumentError):
        geo_proc.process_geospatial(invalid_payload)


def test_14_geospatial_field_clipping():
    geo_proc = SatelliteGeospatialProcessor()
    matrix = np.ones((10, 10), dtype=np.float32) * 5.0
    poly = [[2.0, 2.0], [6.0, 2.0], [6.0, 6.0], [2.0, 6.0], [2.0, 2.0]]
    clipped = geo_proc.clip_to_field_boundary(matrix, poly, raster_extent=[0.0, 0.0, 10.0, 10.0])
    assert clipped.shape == (10, 10)
    assert np.isnan(clipped[0, 0])
    assert clipped[5, 4] == 5.0


def test_15_temporal_normalization():
    temp_proc = SatelliteTemporalProcessor()
    norm1 = temp_proc.normalize_timestamp("2025-03-30 10:30:00")
    assert norm1 == "2025-03-30T10:30:00Z"


def test_16_temporal_revisit_interval():
    temp_proc = SatelliteTemporalProcessor()
    meta_s2 = temp_proc.process_temporal("2025-03-30T10:00:00Z", constellation="Sentinel-2")
    assert meta_s2.revisit_interval_days == 5.0


def test_17_temporal_gap_detection():
    temp_proc = SatelliteTemporalProcessor()
    dates = ["2025-01-01T00:00:00Z", "2025-01-06T00:00:00Z", "2025-02-15T00:00:00Z"]
    gaps = temp_proc.detect_observation_gaps(dates, max_allowed_gap_days=10.0)
    assert len(gaps) == 1
    assert gaps[0]["gap_duration_days"] == 40.0


def test_18_numerical_array_validation():
    temp_proc = SatelliteTemporalProcessor()
    valid_arr = np.array([0.1, 0.5, 0.9])
    ok, warnings = temp_proc.validate_numerical_array(valid_arr, expected_range=(0.0, 1.0))
    assert ok is True
    assert len(warnings) == 0


def test_19_sar_processing():
    sar_proc = SatelliteSARProcessor()
    raw_amp = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
    band = sar_proc.process_sar_band(raw_amp, polarization="VV", is_linear_amplitude=True)
    assert band.band_type == SatelliteBandType.SAR_VV
    assert band.measurement_unit == "sigma0_dB"


def test_20_thermal_processing():
    therm_proc = SatelliteThermalProcessor()
    kelvin_matrix = np.array([[298.15, 303.15], [300.0, 305.0]], dtype=np.float32)
    band = therm_proc.process_thermal_band(kelvin_matrix, band_id="TIRS_1")
    assert band.measurement_unit == "celsius"
    assert np.isclose(band.statistics["min_celsius"], 25.0)


def test_21_quality_validator_statuses(sample_geo, sample_temporal):
    qval = SatelliteQualityValidator()
    bands = {"RED": SatelliteSpectralBand(band_id="B04", band_name="Red", band_type=SatelliteBandType.RED, spatial_resolution_meters=10.0)}
    report_valid = qval.validate_processed_dataset(bands, sample_geo, sample_temporal, cloud_cover_over_target=2.0)
    assert report_valid.status == "VALID"


def test_22_pipeline_execution(sample_metadata, sample_optical_matrices):
    pipeline = SatelliteProcessingPipeline()
    proc_data, matrices = pipeline.process(
        raw_ref=None,
        metadata=sample_metadata,
        raw_band_matrices=sample_optical_matrices,
        field_id="field_test_d4",
    )
    assert isinstance(proc_data, SatelliteProcessedData)
    assert proc_data.processing_status == SatelliteProcessingStatus.PROCESSED


def test_23_satellite_service_process_dataset(sample_metadata, sample_optical_matrices):
    service = SatelliteService()
    proc_data, matrices = service.process_dataset(
        metadata=sample_metadata,
        raw_band_matrices=sample_optical_matrices,
        field_id="field_service_001",
    )
    assert proc_data.dataset_id == sample_metadata.dataset_id
    retrieved = service.storage.get_processed_data(proc_data.processed_id)
    assert retrieved is not None


def test_24_satellite_module_workflow_dispatch(sample_metadata, sample_optical_matrices):
    service = SatelliteService()
    module = SatelliteModule(service=service)
    module.initialize()
    matrices_dict = {k: v.tolist() for k, v in sample_optical_matrices.items()}
    req = ApplicationRequest(
        request_id="req_d4_test_001",
        source="test_client",
        target_module="satellite",
        operation="process_dataset",
        payload={
            "metadata": sample_metadata.model_dump(),
            "raw_band_matrices": matrices_dict,
            "field_id": "field_dispatch_001",
        },
    )
    resp = module.handle(req)
    assert resp.status == "SUCCESS"
    assert resp.response["field_id"] == "field_dispatch_001"
    module.shutdown()
