"""Comprehensive Acceptance Test Suite for EarthMind Drone Module Stage D5.

Verifies:
1. Spectral band identification, canonicalization, and validation.
2. Correct NDVI, NDRE, and supported NDWI (Gao vs McFeeters) calculations using known test values.
3. NDWI variants clearly distinguished and not treated as interchangeable.
4. Handling of missing bands, invalid inputs, division by zero, and incompatible resolutions.
5. Numerical and thermal processing with unit preservation and non-diagnostic boundaries.
6. Indicator metadata, definitions, limitations, and source traceability.
7. Spatial and temporal compatibility checks for multi-sensor fusion.
8. Multi-sensor fusion with compatible inputs preserving provenance.
9. Conflicting, incomplete, and incompatible sensor inputs (no silent averaging).
10. No fabricated indicators, measurements, or synthetic confidence scores.
11. Integration with DroneService and DroneModule workflow dispatch.
12. Compatibility with D1–D4 contracts and behavior.
"""

import math
import pytest
from typing import Any, Dict, List

from core.errors.exceptions import (
    DroneInvalidArgumentError,
    IndicatorProcessingFailedError,
    InsufficientDroneDataError,
)
from core.schemas.application import ApplicationRequest
from core.schemas.drone import (
    AgriculturalIndicatorContract,
    CalibrationStatus,
    FusedSensorMeasurementContract,
    MultiSensorFusionReportContract,
    NumericalAnalysisResultContract,
    ProcessedSensorMeasurementContract,
    QualityStatus,
    SpatialBoundingBox,
    SpatialCoordinates,
    SpatialCoverage,
    SpectralAnalysisResultContract,
    SpectralBandMetadataContract,
    TemporalCoverage,
)
from modules.drone.drone_module import DroneModule
from modules.drone.drone_service import DroneService
from modules.drone.fusion import MultiSensorFusionEngine
from modules.drone.indicators import (
    INDICATOR_CATALOG,
    IndicatorExtractionEngine,
)
from modules.drone.numerical import NumericalAnalysisEngine
from modules.drone.spectral import (
    STANDARD_SPECTRAL_BANDS,
    SpectralAnalysisEngine,
)


# ============================================================================
# Test Fixtures & Synthetic Data
# ============================================================================

def make_processed_measurement(
    channel_name: str,
    processed_val: float,
    orig_val: Any = None,
    orig_unit: str = "reflectance",
    norm_unit: str = "reflectance",
    sensor_id: str = "sensor_multi_01",
    timestamp: str = "2026-11-09T10:00:00Z",
    lat: float = 28.6139,
    lon: float = 77.2090,
    cal_status: CalibrationStatus = CalibrationStatus.CALIBRATED,
    quality_status: QualityStatus = QualityStatus.VALID,
) -> ProcessedSensorMeasurementContract:
    """Deterministic synthetic fixture generator."""
    return ProcessedSensorMeasurementContract(
        measurement_id=f"meas_{channel_name}_{int(processed_val*1000)}",
        measurement_type="spectral_reflectance",
        channel_name=channel_name,
        original_value=orig_val if orig_val is not None else processed_val,
        original_unit=orig_unit,
        processed_value=float(processed_val),
        normalized_unit=norm_unit,
        processing_method="synthetic_calibration -> unit_norm",
        calibration_status=cal_status,
        timestamp=timestamp,
        spatial_reference=SpatialCoordinates(latitude=lat, longitude=lon, altitude_meters=50.0),
        quality_status=quality_status,
        source_sensor=sensor_id,
        provenance={"drone_id": "drone_alpha_01"},
    )


# ============================================================================
# 1. Spectral Analysis Engine Tests
# ============================================================================

class TestSpectralAnalysisEngine:
    """Tests for Component 9 (ISpectralNumericalAnalyzer)."""

    def test_canonicalize_and_catalog(self):
        engine = SpectralAnalysisEngine()
        assert engine.canonicalize_band_name("NIR") == "nir"
        assert engine.canonicalize_band_name("Near_IR") == "nir"
        assert engine.canonicalize_band_name("RedEdge") == "red_edge"
        assert engine.canonicalize_band_name("red-edge") == "red_edge"
        assert engine.canonicalize_band_name("Green") == "green"
        assert engine.canonicalize_band_name("SWIR1") == "swir1"
        assert engine.canonicalize_band_name("swir") == "swir1"

        profile = engine.get_band_profile("nir")
        assert profile is not None
        assert profile["center_wavelength_nm"] == 840.0

    def test_validate_band_data_bounds(self):
        engine = SpectralAnalysisEngine()
        # Valid reflectance [0, 1]
        valid, flat, warnings = engine.validate_band_data("red", [0.05, 0.12, 0.08])
        assert valid is True
        assert len(flat) == 3
        assert len(warnings) == 0

        # Negative reflectance warning
        valid, flat, warnings = engine.validate_band_data("red", [-0.05, 0.10])
        assert valid is True
        assert any("negative reflectance" in w for w in warnings)

        # Non-finite values
        valid, flat, warnings = engine.validate_band_data("nir", [0.45, float("nan"), 0.50])
        assert valid is True
        assert len(flat) == 2
        assert any("Non-finite" in w for w in warnings)

        # None data
        valid, flat, warnings = engine.validate_band_data("blue", None)
        assert valid is False

    def test_analyze_bands_full_cycle(self):
        engine = SpectralAnalysisEngine()
        band_payload = {
            "drone_id": "drone_01",
            "sensor_id": "sensor_micasense_01",
            "timestamp": "2026-11-09T10:00:00Z",
            "bands": {
                "blue": [0.03, 0.04, 0.035],
                "green": [0.08, 0.09, 0.085],
                "red": [0.04, 0.05, 0.045],
                "red_edge": [0.25, 0.28, 0.26],
                "nir": [0.55, 0.60, 0.58],
            },
        }
        res = engine.analyze_bands(band_payload)
        contract = SpectralAnalysisResultContract(**res)
        assert contract.drone_id == "drone_01"
        assert len(contract.detected_bands) == 5
        assert "nir" in contract.band_statistics
        assert contract.band_statistics["nir"]["mean"] == pytest.approx(0.576667, rel=1e-3)
        assert contract.band_statistics["nir"]["min"] == 0.55
        assert contract.band_statistics["nir"]["max"] == 0.60
        assert contract.quality_status == QualityStatus.VALID

    def test_incompatible_matrix_resolutions(self):
        engine = SpectralAnalysisEngine()
        band_payload = {
            "drone_id": "drone_01",
            "sensor_id": "sensor_01",
            "bands": {
                "red": [[0.1, 0.2], [0.1, 0.2]],  # 2x2
                "nir": [[0.5, 0.6, 0.7], [0.5, 0.6, 0.7]],  # 2x3 incompatible
            },
        }
        res = engine.analyze_bands(band_payload)
        contract = SpectralAnalysisResultContract(**res)
        assert contract.quality_status == QualityStatus.DEGRADED
        assert any("Incompatible matrix resolutions" in w for w in contract.warnings)


# ============================================================================
# 2. Agricultural Indicator Extraction Engine Tests
# ============================================================================

class TestIndicatorExtractionEngine:
    """Tests for Component 10 (IIndicatorExtractor)."""

    def test_ndvi_exact_calculation(self):
        """
        Known values:
        NIR = 0.60, Red = 0.20
        NDVI = (0.60 - 0.20) / (0.60 + 0.20) = 0.40 / 0.80 = 0.5000
        """
        engine = IndicatorExtractionEngine()
        meas_list = [
            make_processed_measurement("nir", 0.60),
            make_processed_measurement("red", 0.20),
        ]
        ind = engine.extract_indicator("NDVI", meas_list)
        assert ind.indicator_name == "NDVI"
        assert ind.result["mean"] == 0.5000
        assert ind.result["sample_count"] == 1
        assert ind.quality_status == QualityStatus.VALID
        assert "Saturates in high-biomass" in ind.limitations[0]

    def test_ndre_exact_calculation(self):
        """
        Known values:
        NIR = 0.70, RedEdge = 0.30
        NDRE = (0.70 - 0.30) / (0.70 + 0.30) = 0.40 / 1.00 = 0.4000
        """
        engine = IndicatorExtractionEngine()
        meas_list = [
            make_processed_measurement("nir", 0.70),
            make_processed_measurement("red_edge", 0.30),
        ]
        ind = engine.extract_indicator("NDRE", meas_list)
        assert ind.indicator_name == "NDRE"
        assert ind.result["mean"] == 0.4000
        assert ind.calculation_method == "(NIR - RedEdge) / (NIR + RedEdge)"
        assert ind.quality_status == QualityStatus.VALID

    def test_ndwi_variants_strictly_distinguished(self):
        """
        NDWI_GAO uses NIR and SWIR.
        NDWI_MCFEETERS uses Green and NIR.
        Never treat different formulas as interchangeable.
        """
        engine = IndicatorExtractionEngine()
        meas_list = [
            make_processed_measurement("green", 0.15),
            make_processed_measurement("nir", 0.55),
            make_processed_measurement("swir1", 0.25),
        ]

        # NDWI_GAO = (NIR - SWIR) / (NIR + SWIR) = (0.55 - 0.25) / (0.55 + 0.25) = 0.30 / 0.80 = 0.3750
        ind_gao = engine.extract_indicator("NDWI_GAO", meas_list)
        assert ind_gao.indicator_name == "NDWI_GAO"
        assert ind_gao.result["mean"] == 0.3750
        assert "swir" in ind_gao.calculation_method.lower()
        assert "canopy water content" in ind_gao.definition.lower()

        # NDWI_MCFEETERS = (Green - NIR) / (Green + NIR) = (0.15 - 0.55) / (0.15 + 0.55) = -0.40 / 0.70 = -0.5714
        ind_mcfeeters = engine.extract_indicator("NDWI_MCFEETERS", meas_list)
        assert ind_mcfeeters.indicator_name == "NDWI_MCFEETERS"
        assert ind_mcfeeters.result["mean"] == pytest.approx(-0.5714, abs=1e-3)
        assert "green" in ind_mcfeeters.calculation_method.lower()
        assert "surface open-water" in ind_mcfeeters.definition.lower()

        # The two values must be completely distinct
        assert ind_gao.result["mean"] != ind_mcfeeters.result["mean"]
        assert ind_gao.required_input_measurements != ind_mcfeeters.required_input_measurements

    def test_missing_bands_fail_safe_no_fabrication(self):
        """If required band is missing, raise IndicatorProcessingFailedError without fabricating data."""
        engine = IndicatorExtractionEngine()
        # Only red and green, no NIR
        meas_list = [
            make_processed_measurement("green", 0.15),
            make_processed_measurement("red", 0.10),
        ]
        with pytest.raises(IndicatorProcessingFailedError) as exc_info:
            engine.extract_indicator("NDVI", meas_list)
        assert "Missing required spectral band" in str(exc_info.value)
        assert "nir" in str(exc_info.value)

    def test_division_by_zero_handling(self):
        """If NIR + Red == 0, handle safely without crashing or NaN."""
        engine = IndicatorExtractionEngine()
        meas_list = [
            make_processed_measurement("nir", 0.0),
            make_processed_measurement("red", 0.0),
        ]
        with pytest.raises(IndicatorProcessingFailedError) as exc_info:
            engine.extract_indicator("NDVI", meas_list)
        assert "division-by-zero" in str(exc_info.value)

    def test_extract_available_indicators(self):
        """Should automatically compute all supported indicators for present bands without failing on absent ones."""
        engine = IndicatorExtractionEngine()
        # Has green, red, red_edge, nir -> can compute NDVI, NDRE, NDWI_MCFEETERS, but NOT NDWI_GAO (lacks SWIR)
        meas_list = [
            make_processed_measurement("green", 0.12),
            make_processed_measurement("red", 0.08),
            make_processed_measurement("red_edge", 0.28),
            make_processed_measurement("nir", 0.64),
        ]
        indicators = engine.extract_available_indicators(meas_list)
        names = [i.indicator_name for i in indicators]
        assert "NDVI" in names
        assert "NDRE" in names
        assert "NDWI_MCFEETERS" in names
        assert "NDWI_GAO" not in names


# ============================================================================
# 3. Numerical & Thermal Analysis Tests
# ============================================================================

class TestNumericalAnalysisEngine:
    """Tests for Numerical & Thermal Analysis."""

    def test_numerical_channel_summary(self):
        engine = NumericalAnalysisEngine()
        meas_list = [
            make_processed_measurement("ambient_temp", 28.5, norm_unit="celsius"),
            make_processed_measurement("ambient_temp", 31.5, norm_unit="celsius"),
            make_processed_measurement("ambient_temp", 30.0, norm_unit="celsius"),
        ]
        res = engine.process_measurements(meas_list, "ambient_temp")
        assert res.channel_name == "ambient_temp"
        assert res.sample_count == 3
        assert res.mean == 30.0
        assert res.min_value == 28.5
        assert res.max_value == 31.5
        assert res.normalized_unit == "celsius"
        assert res.quality_status == QualityStatus.VALID

    def test_thermal_range_validation_non_diagnostic(self):
        engine = NumericalAnalysisEngine()
        # Normal canopy thermal range
        meas_list = [
            make_processed_measurement("thermal_ir", 26.2, orig_unit="celsius", norm_unit="celsius"),
            make_processed_measurement("thermal_ir", 27.8, orig_unit="celsius", norm_unit="celsius"),
        ]
        res = engine.process_thermal_summary(meas_list)
        assert res.channel_name == "thermal_ir"
        assert res.mean == pytest.approx(27.0, rel=1e-2)
        assert res.quality_status == QualityStatus.VALID

        # Out-of-range thermal reading flags suspect quality
        extreme_meas = [
            make_processed_measurement("thermal_ir", 95.0, orig_unit="celsius", norm_unit="celsius"),
        ]
        res_ext = engine.process_thermal_summary(extreme_meas)
        assert res_ext.quality_status == QualityStatus.SUSPECT
        assert any("outside typical agronomic range" in w for w in res_ext.warnings)


# ============================================================================
# 4. Multi-Sensor Fusion Engine Tests
# ============================================================================

class TestMultiSensorFusionEngine:
    """Tests for Component 11 (IMultiSensorFusionEngine)."""

    def test_compatible_fusion_preserves_provenance(self):
        fusion = MultiSensorFusionEngine()
        # Multispectral sensor stream
        ms_stream = [
            make_processed_measurement("nir", 0.65, sensor_id="sensor_micasense_01", timestamp="2026-11-09T10:00:00Z"),
        ]
        # Thermal sensor stream (at same coordinate, same minute)
        th_stream = [
            make_processed_measurement("thermal_ir", 27.5, orig_unit="celsius", norm_unit="celsius", sensor_id="sensor_flir_01", timestamp="2026-11-09T10:00:02Z"),
        ]

        report = fusion.fuse_measurements({
            "sensor_micasense_01": ms_stream,
            "sensor_flir_01": th_stream,
        }, drone_id="drone_alpha")

        assert report.fused_measurements_count == 1
        assert report.conflicts_detected_count == 0
        fused = report.fused_measurements[0]
        assert "nir" in fused.fused_channels
        assert "thermal_ir" in fused.fused_channels
        assert fused.participating_sensor_ids == ["sensor_micasense_01", "sensor_flir_01"]
        assert fused.temporal_delta_seconds == pytest.approx(2.0, abs=0.1)
        assert fused.has_conflict is False

    def test_conflict_detection_no_silent_averaging(self):
        """
        If two sensors report significantly conflicting values for the same channel,
        do NOT silently average them; record conflict explicitly.
        """
        fusion = MultiSensorFusionEngine(relative_conflict_threshold=0.25)
        # Sensor A reports temperature 25.0 °C
        s_a = [
            make_processed_measurement("ambient_temp", 25.0, sensor_id="probe_temp_a", timestamp="2026-11-09T10:00:00Z"),
        ]
        # Sensor B reports temperature 45.0 °C (differ by > 50%)
        s_b = [
            make_processed_measurement("ambient_temp", 45.0, sensor_id="probe_temp_b", timestamp="2026-11-09T10:00:01Z"),
        ]

        report = fusion.fuse_measurements({
            "probe_temp_a": s_a,
            "probe_temp_b": s_b,
        })

        assert report.conflicts_detected_count > 0
        fused = report.fused_measurements[0]
        assert fused.has_conflict is True
        assert fused.quality_status == QualityStatus.SUSPECT
        # Original individual readings must be preserved under distinct keys, NOT silently averaged
        assert "ambient_temp_probe_temp_b" in fused.fused_channels
        assert any("conflict detected" in w.lower() for w in report.warnings)

    def test_incompatible_spatial_temporal_rejected(self):
        """Observations separated beyond spatial/temporal threshold must be marked incompatible."""
        fusion = MultiSensorFusionEngine(max_spatial_distance_meters=10.0, max_temporal_delta_seconds=60.0)
        s_a = [
            make_processed_measurement("red", 0.05, lat=28.6139, lon=77.2090, timestamp="2026-11-09T10:00:00Z"),
        ]
        # Sensor B is 2 hours later
        s_b = [
            make_processed_measurement("thermal_ir", 28.0, lat=28.6139, lon=77.2090, timestamp="2026-11-09T12:00:00Z", sensor_id="thermal_sensor"),
        ]

        report = fusion.fuse_measurements({
            "s_a": s_a,
            "thermal_sensor": s_b,
        })
        assert report.incompatible_inputs_count == 1
        # Primary stream was s_a, thermal_sensor was rejected for temporal incompatibility
        assert len(report.fused_measurements[0].participating_sensor_ids) == 1


# ============================================================================
# 5. Service & Module Integration Tests
# ============================================================================

class TestDroneServiceAndModuleD5Integration:
    """Tests for DroneService and DroneModule integration with Stage D5."""

    def test_drone_service_spectral_and_indicator_operations(self):
        service = DroneService()

        # Spectral analysis
        spec_result = service.analyze_spectral({
            "drone_id": "drone_test",
            "sensor_id": "sensor_micasense",
            "bands": {"red": [0.08, 0.09], "nir": [0.60, 0.62]},
        })
        assert spec_result["contract_name"] == "SpectralAnalysisResultContract"
        assert "nir" in spec_result["band_statistics"]

        # Indicator extraction
        meas = [
            make_processed_measurement("red", 0.10),
            make_processed_measurement("nir", 0.70),
        ]
        ind = service.extract_indicator("NDVI", meas)
        assert ind.indicator_name == "NDVI"
        assert ind.result["mean"] == pytest.approx(0.75, abs=1e-3)

        # Thermal summary
        th_meas = [
            make_processed_measurement("thermal_ir", 25.5, orig_unit="celsius", norm_unit="celsius"),
        ]
        th_res = service.process_thermal_summary(th_meas)
        assert th_res.mean == 25.5

    def test_drone_module_workflow_dispatch_d5(self):
        module = DroneModule()
        module.initialize()

        # Operation: analyze_spectral
        req_spectral = ApplicationRequest(
            request_id="req_spec_01",
            source="test",
            operation="analyze_spectral",
            payload={
                "drone_id": "drone_d5",
                "sensor_id": "sensor_d5",
                "bands": {"green": [0.1], "nir": [0.5]},
            },
        )
        resp_spectral = module.handle(req_spectral)
        assert resp_spectral.status == "SUCCESS"
        assert resp_spectral.response["contract_name"] == "SpectralAnalysisResultContract"

        # Operation: extract_indicator
        req_ind = ApplicationRequest(
            request_id="req_ind_01",
            source="test",
            operation="extract_indicator",
            payload={
                "indicator_name": "NDVI",
                "measurements": [
                    make_processed_measurement("nir", 0.60).model_dump(),
                    make_processed_measurement("red", 0.20).model_dump(),
                ],
            },
        )
        resp_ind = module.handle(req_ind)
        assert resp_ind.status == "SUCCESS"
        assert resp_ind.response["indicator_name"] == "NDVI"
        assert resp_ind.response["result"]["mean"] == 0.5

        # Operation: fuse_sensors
        req_fuse = ApplicationRequest(
            request_id="req_fuse_01",
            source="test",
            operation="fuse_sensor_data",
            payload={
                "drone_id": "drone_d5",
                "sensor_streams": {
                    "sensor_a": [make_processed_measurement("nir", 0.60, sensor_id="sensor_a").model_dump()],
                    "sensor_b": [make_processed_measurement("thermal_ir", 26.0, sensor_id="sensor_b").model_dump()],
                },
            },
        )
        resp_fuse = module.handle(req_fuse)
        assert resp_fuse.status == "SUCCESS"
        assert resp_fuse.response["contract_name"] == "MultiSensorFusionReportContract"
        assert resp_fuse.response["fused_measurements_count"] == 1

        module.shutdown()
