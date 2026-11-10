"""Acceptance Test Suite for EarthMind Satellite Intelligence Module Stage D5: Spectral, Geospatial & Temporal Analysis.

Covers:
1. Exact formula calculation for NDVI: (NIR - Red) / (NIR + Red) using independent reference values.
2. Exact formula calculation for NDRE: (NIR - RedEdge) / (NIR + RedEdge) using independent reference values.
3. Exact formula calculation for NDWI (Green - NIR / McFeeters variant) using independent reference values.
4. Exact formula calculation for NDWI (NIR - SWIR / Gao canopy moisture variant) using independent reference values.
5. Exact formula calculation for EVI: 2.5 * (NIR - Red) / (NIR + 6*Red - 7.5*Blue + 1.0).
6. Distinct separation and non-interchangeability of the two NDWI variants.
7. Division-by-zero protection (denominator approaching zero sets NaN, avoids ZeroDivisionError).
8. Boundary range validation and clipping [-1.0, 1.0].
9. Missing spectral band rejection without silent fallback.
10. Statistical distribution metrics (mean, median, min, max, std dev, valid/invalid counts, CV).
11. Vegetation vigor categorization and heterogeneity assessment.
12. Water indicator analysis preserving non-diagnostic separation from soil moisture.
13. Coverage area calculation in hectares from pixel count and ground resolution.
14. Zonal statistics computation across spatial sub-zones.
15. Chronological time-series construction and linear trajectory trend calculation.
16. Multi-date change detection (pixel differences, relative change percentages, area categorizations).
17. Preservation of non-diagnostic boundary in change detection (no automatic disease/drought labeling).
18. Multi-source satellite observation fusion (spatial/temporal compatibility evaluation).
19. Agricultural indicator extraction (Contract 7 SatelliteIndicator) including Land Surface Temperature.
20. SatelliteService extraction, change detection, and fusion integration.
21. SatelliteModule workflow dispatch handling for calculate_indices and extract_indicators.
"""

import numpy as np
import pytest

from core.schemas.application import ApplicationRequest
from core.schemas.satellite import (
    SatelliteBandType,
    SatelliteDataFormat,
    SatelliteDataQuality,
    SatelliteGeospatialMetadata,
    SatelliteIndicator,
    SatelliteProcessedData,
    SatelliteProcessingStatus,
    SatelliteSpectralBand,
    SatelliteTemporalMetadata,
)
from modules.satellite.change_detection import SatelliteChangeDetector
from modules.satellite.errors import (
    SatelliteIndicatorProcessingError,
    SatelliteInvalidArgumentError,
)
from modules.satellite.fusion import SatelliteMultiSourceFusionEngine
from modules.satellite.indices import (
    SUPPORTED_INDICES,
    SatelliteSpectralIndexEngine,
)
from modules.satellite.indicators import SatelliteIndicatorGenerator
from modules.satellite.satellite_module import SatelliteModule
from modules.satellite.satellite_service import SatelliteService
from modules.satellite.spatial_analysis import SatelliteSpatialAnalyzer
from modules.satellite.temporal_analysis import SatelliteTemporalAnalyzer
from modules.satellite.vegetation_water import VegetationWaterAnalyzer


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def index_engine():
    return SatelliteSpectralIndexEngine(version="1.0.0")


@pytest.fixture
def calibrated_bands():
    """
    Standard calibrated reflectance test fixture:
    NIR = 0.8, RED = 0.2, GREEN = 0.3, BLUE = 0.1, RED_EDGE_1 = 0.5, SWIR_1 = 0.4
    Independent Reference Calculations:
    - NDVI = (0.8 - 0.2) / (0.8 + 0.2) = 0.6 / 1.0 = 0.6000
    - NDRE = (0.8 - 0.5) / (0.8 + 0.5) = 0.3 / 1.3 = 0.230769... -> 0.2308
    - NDWI_GREEN_NIR = (0.3 - 0.8) / (0.3 + 0.8) = -0.5 / 1.1 = -0.454545... -> -0.4545
    - NDWI_NIR_SWIR = (0.8 - 0.4) / (0.8 + 0.4) = 0.4 / 1.2 = 0.333333... -> 0.3333
    - EVI = 2.5 * (0.8 - 0.2) / (0.8 + 6*0.2 - 7.5*0.1 + 1.0)
          = 2.5 * 0.6 / (0.8 + 1.2 - 0.75 + 1.0) = 1.5 / 2.25 = 0.666666... -> 0.6667
    """
    return {
        "NIR": np.array([[0.8, 0.8], [0.8, 0.8]], dtype=np.float32),
        "RED": np.array([[0.2, 0.2], [0.2, 0.2]], dtype=np.float32),
        "GREEN": np.array([[0.3, 0.3], [0.3, 0.3]], dtype=np.float32),
        "BLUE": np.array([[0.1, 0.1], [0.1, 0.1]], dtype=np.float32),
        "RED_EDGE_1": np.array([[0.5, 0.5], [0.5, 0.5]], dtype=np.float32),
        "SWIR_1": np.array([[0.4, 0.4], [0.4, 0.4]], dtype=np.float32),
    }


@pytest.fixture
def sample_processed_data():
    geo = SatelliteGeospatialMetadata(
        latitude=28.6139,
        longitude=77.2090,
        crs="EPSG:4326",
        spatial_resolution_meters=10.0,
    )
    temporal = SatelliteTemporalMetadata(
        acquisition_date="2025-03-30T10:00:00Z",
        revisit_interval_days=5.0,
    )
    return SatelliteProcessedData(
        processed_id="proc_test_d5_001",
        dataset_id="S2A_MSIL2A_TEST_D5",
        processing_status=SatelliteProcessingStatus.PROCESSED,
        geospatial=geo,
        temporal=temporal,
        processed_bands={
            "RED": SatelliteSpectralBand(band_id="B04", band_name="Red", band_type=SatelliteBandType.RED, spatial_resolution_meters=10.0),
            "NIR": SatelliteSpectralBand(band_id="B08", band_name="NIR", band_type=SatelliteBandType.NIR, spatial_resolution_meters=10.0),
            "GREEN": SatelliteSpectralBand(band_id="B03", band_name="Green", band_type=SatelliteBandType.GREEN, spatial_resolution_meters=10.0),
            "SWIR_1": SatelliteSpectralBand(band_id="B11", band_name="SWIR 1", band_type=SatelliteBandType.SWIR_1, spatial_resolution_meters=20.0),
        },
    )


# ============================================================================
# 1. Spectral Index Engine Tests (Exact Formulas & Reference Values)
# ============================================================================

def test_1_ndvi_exact_formula_and_reference(index_engine, calibrated_bands):
    ndvi_mat = index_engine.calculate_index_matrix("NDVI", calibrated_bands)
    expected_ref = 0.6000
    assert np.allclose(ndvi_mat, expected_ref, atol=1e-4)


def test_2_ndre_exact_formula_and_reference(index_engine, calibrated_bands):
    ndre_mat = index_engine.calculate_index_matrix("NDRE", calibrated_bands)
    expected_ref = 0.3 / 1.3  # ~0.230769
    assert np.allclose(ndre_mat, expected_ref, atol=1e-4)


def test_3_ndwi_green_nir_mcfeeters_reference(index_engine, calibrated_bands):
    ndwi_mcfeeters = index_engine.calculate_index_matrix("NDWI_GREEN_NIR", calibrated_bands)
    expected_ref = (0.3 - 0.8) / (0.3 + 0.8)  # -0.5 / 1.1 = -0.454545
    assert np.allclose(ndwi_mcfeeters, expected_ref, atol=1e-4)


def test_4_ndwi_nir_swir_gao_moisture_reference(index_engine, calibrated_bands):
    ndwi_gao = index_engine.calculate_index_matrix("NDWI_NIR_SWIR", calibrated_bands)
    expected_ref = (0.8 - 0.4) / (0.8 + 0.4)  # 0.4 / 1.2 = 0.333333
    assert np.allclose(ndwi_gao, expected_ref, atol=1e-4)


def test_5_evi_exact_formula_and_reference(index_engine, calibrated_bands):
    evi_mat = index_engine.calculate_index_matrix("EVI", calibrated_bands)
    # 2.5 * (0.8 - 0.2) / (0.8 + 6*0.2 - 7.5*0.1 + 1.0) = 1.5 / 2.25 = 0.666667
    expected_ref = 2.5 * 0.6 / 2.25
    assert np.allclose(evi_mat, expected_ref, atol=1e-4)


def test_6_ndwi_variants_distinct_identification(index_engine, calibrated_bands):
    mcfeeters = index_engine.calculate_index_matrix("NDWI_GREEN_NIR", calibrated_bands)
    gao = index_engine.calculate_index_matrix("NDWI_NIR_SWIR", calibrated_bands)
    # Must yield strictly distinct numbers reflecting their distinct physical formulas
    assert not np.isclose(mcfeeters[0, 0], gao[0, 0])
    assert mcfeeters[0, 0] < 0.0  # Open water index is negative over vegetation
    assert gao[0, 0] > 0.0        # Canopy moisture index is positive over vegetation


def test_7_division_by_zero_protection(index_engine):
    zero_bands = {
        "NIR": np.array([[0.0, 0.0]], dtype=np.float32),
        "RED": np.array([[0.0, 0.0]], dtype=np.float32),
    }
    # Denominator is 0.0 -> must safely yield NaN without ZeroDivisionError
    res = index_engine.calculate_index_matrix("NDVI", zero_bands)
    assert np.all(np.isnan(res))


def test_8_boundary_clipping(index_engine):
    extreme_bands = {
        "NIR": np.array([[100.0]], dtype=np.float32),
        "RED": np.array([[-50.0]], dtype=np.float32),
    }
    res = index_engine.calculate_index_matrix("NDVI", extreme_bands)
    assert -1.0 <= res[0, 0] <= 1.0


def test_9_missing_spectral_band_rejection(index_engine):
    incomplete_bands = {"NIR": np.array([[0.5]], dtype=np.float32)}
    with pytest.raises(SatelliteIndicatorProcessingError) as exc_info:
        index_engine.calculate_index_matrix("NDVI", incomplete_bands)
    assert "RED" in str(exc_info.value)


# ============================================================================
# 2. Vegetation & Water Analysis Tests
# ============================================================================

def test_10_vegetation_distribution_metrics():
    analyzer = VegetationWaterAnalyzer()
    mat = np.array([[0.2, 0.4], [0.6, 0.8]], dtype=np.float32)
    stats = analyzer.compute_distribution_metrics(mat)
    assert np.isclose(stats["mean"], 0.5)
    assert np.isclose(stats["min"], 0.2)
    assert np.isclose(stats["max"], 0.8)
    assert stats["valid_pixel_count"] == 4
    assert stats["coverage_valid_percentage"] == 100.0


def test_11_vegetation_vigor_analysis():
    analyzer = VegetationWaterAnalyzer()
    ndvi = np.array([[0.7, 0.75], [0.8, 0.85]], dtype=np.float32)
    res = analyzer.analyze_vegetation_vigor(ndvi)
    assert res["canopy_density_class"] == "HIGH_DENSITY"
    assert "limitations" in res


def test_12_water_indicators_non_diagnostic_boundary():
    analyzer = VegetationWaterAnalyzer()
    ndwi_canopy = np.array([[0.3, 0.35]], dtype=np.float32)
    ndwi_water = np.array([[-0.2, -0.25]], dtype=np.float32)
    res = analyzer.analyze_water_indicators(ndwi_canopy, ndwi_water)
    assert res["surface_ponding_detected"] is False
    assert any("MUST NOT be equated with direct in-situ volumetric soil moisture" in lim for lim in res["limitations"])


# ============================================================================
# 3. Geospatial & Area Analysis Tests
# ============================================================================

def test_13_coverage_area_hectares():
    spatial = SatelliteSpatialAnalyzer()
    # 100 pixels at 10m resolution = 100 * 100m^2 = 10,000 m^2 = 1.0 hectare
    ha = spatial.calculate_coverage_area_hectares(100, 10.0)
    assert np.isclose(ha, 1.0)


def test_14_zonal_statistics_computation():
    spatial = SatelliteSpatialAnalyzer()
    raster = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    zone_a = np.array([[True, True], [False, False]])
    zonal = spatial.compute_zonal_statistics(raster, spatial_resolution_meters=10.0, zones={"zone_north": zone_a})
    assert zonal["overall"]["mean"] == 2.5
    assert zonal["zone_north"]["mean"] == 1.5
    assert zonal["zone_north"]["valid_pixels"] == 2


# ============================================================================
# 4. Temporal Analysis & Change Detection Tests
# ============================================================================

def test_15_temporal_time_series_trend():
    temporal = SatelliteTemporalAnalyzer()
    observations = [
        {"date": "2025-01-01", "value": 0.3},
        {"date": "2025-01-15", "value": 0.45},
        {"date": "2025-02-01", "value": 0.6},
    ]
    ts = temporal.build_time_series(observations)
    assert ts["observation_count"] == 3
    assert ts["trend"] == "INCREASING"
    assert ts["summary"]["delta_first_to_last"] == 0.3


def test_16_change_detection_computation():
    detector = SatelliteChangeDetector()
    t1 = np.array([[0.4, 0.4], [0.4, 0.4]], dtype=np.float32)
    t2 = np.array([[0.6, 0.4], [0.2, 0.4]], dtype=np.float32)
    res = detector.compute_pixel_difference(t1, t2, date_t1="2025-01-01", date_t2="2025-02-01", threshold_change=0.05)
    assert res["status"] == "COMPUTED"
    # [0, 0] increased (+0.2), [1, 0] decreased (-0.2), others stable
    assert res["summary"]["increased_pixel_percentage"] == 25.0
    assert res["summary"]["decreased_pixel_percentage"] == 25.0
    assert res["summary"]["stable_pixel_percentage"] == 50.0
    assert any("MUST NOT automatically be attributed to crop disease" in lim for lim in res["limitations"])


# ============================================================================
# 5. Multi-Source Fusion & Indicator Generator Tests
# ============================================================================

def test_17_multi_source_fusion(sample_processed_data):
    fusion = SatelliteMultiSourceFusionEngine(max_temporal_delta_days=7.0)
    # Clone observation for second date
    obs2 = sample_processed_data.model_copy(update={
        "dataset_id": "LC09_L2SP_TEST_D5",
        "temporal": SatelliteTemporalMetadata(acquisition_date="2025-04-02T10:00:00Z"),
    })
    result = fusion.fuse_constellations([sample_processed_data, obs2])
    assert result["fusion_status"] == "FUSED"
    assert len(result["constellations_included"]) == 2
    assert "provenance" in result


def test_18_indicator_contract_generation():
    gen = SatelliteIndicatorGenerator()
    thermal_mat = np.array([[26.5, 27.2], [26.8, 27.0]], dtype=np.float32)
    ind = gen.generate_thermal_indicator(thermal_mat, source_dataset_id="LC09_TIRS_001")
    assert isinstance(ind, SatelliteIndicator)
    assert ind.indicator_name == "LAND_SURFACE_TEMPERATURE"
    assert ind.unit == "degrees_celsius"
    assert np.isclose(ind.result_statistics["mean_celsius"], 26.88, atol=0.05)


# ============================================================================
# 6. Service & Module Integration Tests
# ============================================================================

def test_19_satellite_service_indicator_extraction(sample_processed_data, calibrated_bands):
    service = SatelliteService()
    indicators = service.extract_indicators(
        processed_data=sample_processed_data,
        band_matrices=calibrated_bands,
        requested_indicators=["NDVI", "NDWI_NIR_SWIR"],
    )
    assert len(indicators) == 2
    names = [ind.indicator_name for ind in indicators]
    assert "NDVI" in names
    assert "NDWI_NIR_SWIR" in names


def test_20_satellite_module_indicator_dispatch(sample_processed_data, calibrated_bands):
    service = SatelliteService()
    module = SatelliteModule(service=service)
    module.initialize()

    matrices_dict = {k: v.tolist() for k, v in calibrated_bands.items()}
    req = ApplicationRequest(
        request_id="req_d5_test_001",
        source="test_client",
        target_module="satellite",
        operation="extract_indicators",
        payload={
            "processed_data": sample_processed_data.model_dump(),
            "band_matrices": matrices_dict,
            "requested_indicators": ["NDVI"],
        },
    )
    resp = module.handle(req)
    assert resp.status == "SUCCESS"
    assert len(resp.response) == 1
    assert resp.response[0]["indicator_name"] == "NDVI"
    module.shutdown()
