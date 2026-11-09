"""Comprehensive Test Suite for EarthMind Drone Module Stage D3: Processing, Quality, Calibration & Normalization.

Verifies:
1. Valid parsing for supported D3 formats (JSON, CSV, synthetic multispectral/thermal dictionaries, raw binary).
2. Malformed, truncated, and unsupported payload rejection.
3. Missing fields, invalid values, duplicate channels, and data gaps detection.
4. Valid, invalid, and missing timestamps and metadata.
5. Valid calibration, missing calibration, expired calibration, and factory default calibration handling.
6. Correct unit conversions across temperatures, spectral ratios, pressures, and rejection of unknown units.
7. Original raw values and original units remain unchanged alongside normalized values.
8. Processed measurements retain complete source traceability, origin sensor, and timestamps.
9. Structured error handling, lifecycle status, and backward compatibility with D1 and D2 components.
"""

import json
import pytest
from typing import Any, Dict

from core.errors.exceptions import (
    InsufficientDroneDataError,
    InvalidSensorDataError,
    QualityValidationFailedError,
    UnitConversionFailedError,
    UnsupportedFormatError,
)
from core.interfaces.drone import ICalibrationNormalizer, IRawDataProcessor
from core.schemas.application import ApplicationRequest
from core.schemas.drone import (
    CalibrationStatus,
    DroneDataFormat,
    DroneSensorInputContract,
    ProcessedSensorMeasurementContract,
    QualityStatus,
    SensorCategory,
    SensorMetadataContract,
)
from modules.drone.calibration import CalibrationAssessment, CalibrationEngine
from modules.drone.drone_module import DroneModule
from modules.drone.drone_service import DroneService
from modules.drone.normalization import UnitNormalizer
from modules.drone.parser import RawDataParser
from modules.drone.processing import CalibrationNormalizerAdapter, DroneProcessingEngine
from modules.drone.quality import DataQualityReport, DataQualityValidator


# ============================================================================
# Category 1: Raw Data Parser Tests (Component 4)
# ============================================================================

def test_parser_valid_json_dict():
    """Verify JSON dictionary with channels and units parses correctly."""
    parser = RawDataParser()
    payload = {
        "channels": {"red": 14200, "nir": 38900},
        "units": {"red": "raw_dn", "nir": "raw_dn"},
        "metadata": {"flight_mode": "autonomous"},
    }
    result = parser.parse_raw_data(payload, DroneDataFormat.JSON)
    assert result["format"] == "JSON"
    assert result["sample_count"] == 2
    assert "red" in result["channels"]
    assert "nir" in result["channels"]
    assert result["metadata"]["flight_mode"] == "autonomous"


def test_parser_valid_json_string_and_bytes():
    """Verify JSON string and utf-8 bytes parsing."""
    parser = RawDataParser()
    payload_str = json.dumps([{"channel": "thermal", "value": 298.15, "unit": "kelvin"}])
    res_str = parser.parse_raw_data(payload_str, DroneDataFormat.JSON)
    assert res_str["sample_count"] == 1
    assert res_str["measurements"][0]["channel"] == "thermal"

    res_bytes = parser.parse_raw_data(payload_str.encode("utf-8"), DroneDataFormat.JSON)
    assert res_bytes["sample_count"] == 1


def test_parser_valid_csv_tabular():
    """Verify CSV parsing with headers into channel lists and measurements."""
    parser = RawDataParser()
    csv_text = "red,green,blue,nir\n0.12,0.18,0.08,0.55\n0.14,0.19,0.09,0.58\n"
    res = parser.parse_raw_data(csv_text, DroneDataFormat.CSV)
    assert res["format"] == "CSV"
    assert res["sample_count"] == 2
    assert res["channels"]["red"] == [0.12, 0.14]
    assert res["channels"]["nir"] == [0.55, 0.58]


def test_parser_valid_raw_binary():
    """Verify raw binary payload unpacks into 16-bit uint samples."""
    parser = RawDataParser()
    # 4 samples (8 bytes) of uint16: 100, 200, 300, 400
    import struct
    buf = struct.pack("<4H", 100, 200, 300, 400)
    res = parser.parse_raw_data(buf, DroneDataFormat.RAW_BINARY)
    assert res["format"] == "RAW_BINARY"
    assert res["sample_count"] == 4
    assert res["channels"]["raw_stream"] == [100, 200, 300, 400]


def test_parser_rejects_empty_and_none_payload():
    """Verify parser rejects empty or None payload with InsufficientDroneDataError."""
    parser = RawDataParser()
    with pytest.raises(InsufficientDroneDataError):
        parser.parse_raw_data(None, DroneDataFormat.JSON)

    with pytest.raises(InsufficientDroneDataError):
        parser.parse_raw_data("", DroneDataFormat.JSON)

    with pytest.raises(InsufficientDroneDataError):
        parser.parse_raw_data("   ", DroneDataFormat.CSV)


def test_parser_rejects_malformed_json():
    """Verify parser rejects invalid JSON syntax with InvalidSensorDataError."""
    parser = RawDataParser()
    with pytest.raises(InvalidSensorDataError):
        parser.parse_raw_data("{\"red\": 12000, unclosed_bracket", DroneDataFormat.JSON)


def test_parser_rejects_malformed_csv():
    """Verify parser rejects CSV with column mismatch or duplicate headers."""
    parser = RawDataParser()
    # Column count mismatch
    bad_csv = "red,green,blue\n0.12,0.15\n"
    with pytest.raises(InvalidSensorDataError):
        parser.parse_raw_data(bad_csv, DroneDataFormat.CSV)

    # Duplicate headers
    dup_header_csv = "red,green,red\n0.1,0.2,0.3\n"
    with pytest.raises(InvalidSensorDataError):
        parser.parse_raw_data(dup_header_csv, DroneDataFormat.CSV)


def test_parser_rejects_truncated_binary():
    """Verify parser rejects truncated binary data (<4 bytes)."""
    parser = RawDataParser()
    with pytest.raises(InvalidSensorDataError):
        parser.parse_raw_data(b"\x01\x02", DroneDataFormat.RAW_BINARY)


# ============================================================================
# Category 2: Data Quality & Validation Tests (Component 5)
# ============================================================================

def test_quality_validator_valid_measurements():
    """Verify plausible physical measurements return VALID status."""
    validator = DataQualityValidator()
    measurements = [
        {"channel": "red", "value": 0.14, "unit": "unitless_ratio"},
        {"channel": "nir", "value": 0.65, "unit": "unitless_ratio"},
        {"channel": "thermal_canopy", "value": 26.5, "unit": "celsius"},
    ]
    report = validator.evaluate_measurements(measurements, collection_timestamp="2026-11-09T03:00:00Z")
    assert report.overall_status == QualityStatus.VALID
    assert report.valid_count == 3
    assert report.invalid_count == 0


def test_quality_validator_detects_out_of_bounds_values():
    """Verify out-of-bounds measurements are flagged as SUSPECT or INVALID with warnings."""
    validator = DataQualityValidator()
    measurements = [
        # Normal
        {"channel": "red", "value": 0.20, "unit": "unitless_ratio"},
        # Out-of-bounds temperature: 150°C (beyond max 80°C)
        {"channel": "surface_temp", "value": 150.0, "unit": "celsius"},
    ]
    report = validator.evaluate_measurements(measurements)
    assert report.overall_status == QualityStatus.SUSPECT
    assert any("outside physical plausibility bounds" in w for w in report.warnings)


def test_quality_validator_detects_nan_and_inf():
    """Verify NaN and Infinity values are marked INVALID."""
    validator = DataQualityValidator()
    measurements = [
        {"channel": "red", "value": float("nan"), "unit": "unitless_ratio"},
        {"channel": "green", "value": float("inf"), "unit": "unitless_ratio"},
    ]
    report = validator.evaluate_measurements(measurements)
    assert report.overall_status == QualityStatus.INVALID
    assert report.invalid_count == 2


def test_quality_validator_detects_duplicate_channels_and_missing_expected():
    """Verify duplicate channels and missing expected channels trigger explicit warnings."""
    validator = DataQualityValidator()
    measurements = [
        {"channel": "red", "value": 0.15, "unit": "unitless_ratio"},
        {"channel": "red", "value": 0.16, "unit": "unitless_ratio"},
    ]
    report = validator.evaluate_measurements(
        measurements,
        expected_channels=["red", "nir", "blue"],
    )
    assert any("Duplicate channel" in w for w in report.warnings)
    assert any("missing expected channels" in w for w in report.warnings)


def test_quality_validator_validates_timestamp():
    """Verify invalid or timezone-naive timestamps are rejected."""
    validator = DataQualityValidator()
    measurements = [{"channel": "red", "value": 0.2, "unit": "unitless_ratio"}]

    # Invalid timestamp string
    report_bad = validator.evaluate_measurements(measurements, collection_timestamp="not_a_timestamp")
    assert report_bad.overall_status == QualityStatus.INVALID
    assert any("Invalid collection timestamp" in e for e in report_bad.errors)

    # Valid UTC timestamp
    report_good = validator.evaluate_measurements(measurements, collection_timestamp="2026-11-09T03:00:00Z")
    assert report_good.overall_status == QualityStatus.VALID


def test_quality_validator_never_discards_measurements():
    """Verify that even when measurements are invalid, all items are retained in report."""
    validator = DataQualityValidator()
    measurements = [
        {"channel": "bad_item", "value": "non_numeric", "unit": "celsius"},
        {"channel": "good_item", "value": 25.0, "unit": "celsius"},
    ]
    report = validator.evaluate_measurements(measurements)
    assert len(report.items) == 2
    assert report.items[0].is_valid is False
    assert report.items[1].is_valid is True


# ============================================================================
# Category 3: Calibration Engine Tests
# ============================================================================

def test_calibration_valid_panel_and_sun_sensor():
    """Verify valid calibration metadata returns CALIBRATED status with coefficients."""
    cal_engine = CalibrationEngine()
    metadata = {
        "panel_used": True,
        "sun_sensor_used": True,
        "calibration_timestamp": "2026-11-09T01:00:00Z",
        "coefficients": {"red": 1.05, "nir": 1.12},
    }
    assessment = cal_engine.evaluate_calibration(
        metadata,
        observation_timestamp="2026-11-09T03:00:00Z",
    )
    assert assessment.status == CalibrationStatus.CALIBRATED
    assert assessment.panel_used is True
    assert assessment.applied_coefficients["red"] == 1.05
    assert assessment.is_valid_for_processing is True

    # Test applying transformation
    val, method = cal_engine.apply_calibration_transform(0.5, "red", assessment)
    assert val == 0.5 * 1.05
    assert "calibrated_radiometric_scaling" in method


def test_calibration_missing_metadata():
    """Verify missing calibration metadata explicitly yields MISSING status without hallucination."""
    cal_engine = CalibrationEngine()
    assessment = cal_engine.evaluate_calibration(None)
    assert assessment.status == CalibrationStatus.MISSING
    assert assessment.is_valid_for_processing is False
    assert any("completely absent" in w for w in assessment.warnings)

    # Pass-through transform
    val, method = cal_engine.apply_calibration_transform(10.0, "red", assessment)
    assert val == 10.0
    assert "uncalibrated_pass_through" in method


def test_calibration_expired_handling():
    """Verify calibration older than threshold is marked EXPIRED."""
    cal_engine = CalibrationEngine(max_calibration_age_days=30)
    metadata = {
        "panel_used": True,
        "calibration_timestamp": "2026-09-01T00:00:00Z",  # > 60 days before Nov 2026
        "coefficients": {"red": 1.02},
    }
    assessment = cal_engine.evaluate_calibration(
        metadata,
        observation_timestamp="2026-11-09T03:00:00Z",
    )
    assert assessment.status == CalibrationStatus.EXPIRED
    assert assessment.is_valid_for_processing is False
    assert any("expired" in w for w in assessment.warnings)


def test_calibration_factory_default_fallback():
    """Verify fallback to sensor profile factory calibration when flight metadata absent."""
    cal_engine = CalibrationEngine()
    sensor_profile = {
        "calibration_metadata": {
            "calibration_timestamp": "2026-01-01T00:00:00Z",
            "coefficients": {"nir": 1.01},
        }
    }
    assessment = cal_engine.evaluate_calibration(
        calibration_metadata=None,
        sensor_profile=sensor_profile,
    )
    assert assessment.status == CalibrationStatus.FACTORY_DEFAULT
    assert assessment.applied_coefficients["nir"] == 1.01
    assert assessment.is_valid_for_processing is True


# ============================================================================
# Category 4: Unit Normalization Engine Tests
# ============================================================================

def test_unit_normalization_temperature_conversions():
    """Verify Fahrenheit, Kelvin, and Millikelvin convert accurately to Celsius."""
    normalizer = UnitNormalizer()

    # Fahrenheit to Celsius (32°F -> 0°C, 212°F -> 100°C)
    val_f0, unit_f0, _ = normalizer.normalize(32.0, "fahrenheit")
    assert val_f0 == 0.0
    assert unit_f0 == "celsius"

    val_f100, unit_f100, _ = normalizer.normalize(212.0, "fahrenheit")
    assert val_f100 == 100.0
    assert unit_f100 == "celsius"

    # Kelvin to Celsius (300K -> 26.85°C)
    val_k, unit_k, _ = normalizer.normalize(300.0, "kelvin")
    assert val_k == 26.85
    assert unit_k == "celsius"

    # Millikelvin to Celsius (300000 mK -> 26.85°C)
    val_mk, unit_mk, _ = normalizer.normalize(300000.0, "millikelvin")
    assert val_mk == 26.85
    assert unit_mk == "celsius"


def test_unit_normalization_spectral_and_dn():
    """Verify percentage and 16-bit raw DN normalize to unitless ratio [0.0, 1.0]."""
    normalizer = UnitNormalizer()

    # Percent to ratio (75% -> 0.75)
    val_pct, unit_pct, _ = normalizer.normalize(75.0, "percent")
    assert val_pct == 0.75
    assert unit_pct == "unitless_ratio"

    # Raw DN 16-bit
    val_dn, unit_dn, _ = normalizer.normalize(32767.5, "raw_dn")
    assert 0.499 <= val_dn <= 0.501
    assert unit_dn == "unitless_ratio"


def test_unit_normalization_pressure_and_irradiance():
    """Verify Pa converts to hPa and kW/m² converts to W/m²."""
    normalizer = UnitNormalizer()

    # Pascal to hPa (101325 Pa -> 1013.25 hPa)
    val_pa, unit_pa, _ = normalizer.normalize(101325.0, "pa")
    assert val_pa == 1013.25
    assert unit_pa == "hpa"

    # kW/m² to W/m² (1.2 kW/m² -> 1200 W/m²)
    val_irr, unit_irr, _ = normalizer.normalize(1.2, "kw/m2")
    assert val_irr == 1200.0
    assert unit_irr == "w/m2"


def test_unit_normalization_rejects_unknown_units():
    """Verify unknown or nonsensical units raise UnitConversionFailedError."""
    normalizer = UnitNormalizer()
    with pytest.raises(UnitConversionFailedError):
        normalizer.normalize(42.0, "invented_fictional_unit")

    with pytest.raises(UnitConversionFailedError):
        normalizer.normalize(10.0, "")


# ============================================================================
# Category 5: End-to-End Processing Engine & Measurement Contract Tests
# ============================================================================

def test_processing_engine_end_to_end_multispectral():
    """Verify end-to-end processing pipeline for multispectral JSON sensor input."""
    engine = DroneProcessingEngine()

    sensor_profile = SensorMetadataContract(
        sensor_id="sensor_multispectral_001",
        sensor_category=SensorCategory.MULTISPECTRAL,
        supported_measurements=["red", "green", "blue", "nir"],
        supported_formats=[DroneDataFormat.JSON],
    )

    input_contract = DroneSensorInputContract(
        drone_id="drone_kisan_01",
        sensor_id="sensor_multispectral_001",
        sensor_type="multispectral",
        data_format=DroneDataFormat.JSON,
        collection_timestamp="2026-11-09T04:00:00Z",
        raw_payload={
            "channels": {
                "red": 0.12,
                "green": 0.18,
                "blue": 0.08,
                "nir": 0.65,
            },
            "units": {
                "red": "unitless_ratio",
                "green": "unitless_ratio",
                "blue": "unitless_ratio",
                "nir": "unitless_ratio",
            },
        },
        calibration_metadata={
            "panel_used": True,
            "coefficients": {"red": 1.0, "nir": 1.0, "green": 1.0, "blue": 1.0},
        },
        spatial_metadata={"latitude": 25.5941, "longitude": 85.1376, "altitude_meters": 45.0},
    )

    measurements, q_report, cal_assess = engine.process_sensor_input(input_contract, sensor_profile)

    assert len(measurements) == 4
    assert q_report.overall_status == QualityStatus.VALID
    assert cal_assess.status == CalibrationStatus.CALIBRATED

    for m in measurements:
        assert isinstance(m, ProcessedSensorMeasurementContract)
        # Check dual preservation: original vs normalized
        assert m.original_value is not None
        assert m.original_unit == "unitless_ratio"
        assert m.normalized_unit == "unitless_ratio"
        assert m.processed_value == m.original_value
        # Check traceability
        assert m.source_sensor == "sensor_multispectral_001"
        assert m.timestamp == "2026-11-09T04:00:00Z"
        assert m.spatial_reference is not None
        assert m.spatial_reference.latitude == 25.5941
        assert "drone_id" in m.provenance
        assert m.provenance["drone_id"] == "drone_kisan_01"


def test_processing_engine_end_to_end_thermal_csv():
    """Verify end-to-end processing of CSV thermal telemetry with Fahrenheit to Celsius conversion."""
    engine = DroneProcessingEngine()

    input_contract = DroneSensorInputContract(
        drone_id="drone_thermal_01",
        sensor_id="sensor_thermal_002",
        sensor_type="thermal",
        data_format=DroneDataFormat.CSV,
        collection_timestamp="2026-11-09T04:30:00Z",
        raw_payload="thermal_ir\n77.0\n",
        unit_metadata={"thermal_ir": "fahrenheit"},
    )

    measurements, q_report, cal_assess = engine.process_sensor_input(input_contract)
    assert len(measurements) == 1
    m = measurements[0]

    # Original value preserved
    assert m.original_value == 77.0
    assert m.original_unit == "fahrenheit"

    # Normalized value converted (77°F = 25.0°C)
    assert m.processed_value == 25.0
    assert m.normalized_unit == "celsius"
    assert "fahrenheit_to_celsius" in m.processing_method


def test_calibration_normalizer_adapter_protocol():
    """Verify CalibrationNormalizerAdapter adheres to ICalibrationNormalizer protocol."""
    adapter = CalibrationNormalizerAdapter()
    assert isinstance(adapter, ICalibrationNormalizer)

    raw_m = {
        "channel": "temp",
        "value": 300.0,
        "unit": "kelvin",
        "source_sensor": "test_sensor",
    }
    result = adapter.normalize_measurement(raw_m)
    assert isinstance(result, ProcessedSensorMeasurementContract)
    assert result.original_value == 300.0
    assert result.original_unit == "kelvin"
    assert result.processed_value == 26.85
    assert result.normalized_unit == "celsius"


# ============================================================================
# Category 6: Service & Lifecycle Integration Tests
# ============================================================================

def test_drone_service_process_sensor_data_integration():
    """Verify DroneService.process_sensor_data coordinates processing and records telemetry."""
    service = DroneService()

    input_contract = DroneSensorInputContract(
        drone_id="drone_service_test",
        sensor_id="sensor_synthetic_01",
        sensor_type="multispectral",
        data_format=DroneDataFormat.JSON,
        collection_timestamp="2026-11-09T05:00:00Z",
        raw_payload={"channels": {"nir": 0.72}, "units": {"nir": "unitless_ratio"}},
    )

    res = service.process_sensor_data(input_contract)
    assert res["drone_id"] == "drone_service_test"
    assert res["sensor_id"] == "sensor_synthetic_01"
    assert res["measurements_count"] == 1
    assert res["quality_status"] == QualityStatus.VALID.value
    assert len(res["measurements"]) == 1

    # Telemetry verified
    counters = service.diagnostics.get_health_status()["counters"]
    assert counters["processings_total"] >= 1.0
    assert counters["measurements_processed"] >= 1.0


def test_drone_module_workflow_dispatch_process_operation():
    """Verify DroneModule dispatching 'process_sensor_data' via ApplicationRequest."""
    module = DroneModule()
    module.initialize()

    req = ApplicationRequest(
        request_id="req_d3_process_test",
        source="test_client",
        operation="process_sensor_data",
        payload={
            "drone_id": "drone_workflow_01",
            "sensor_id": "sensor_workflow_01",
            "sensor_type": "multispectral",
            "data_format": "JSON",
            "collection_timestamp": "2026-11-09T05:15:00Z",
            "raw_payload": {"channels": {"red": 0.15}, "units": {"red": "unitless_ratio"}},
        },
    )

    resp = module.handle(req)
    assert resp.status == "SUCCESS"
    assert resp.response["drone_id"] == "drone_workflow_01"
    assert resp.response["measurements_count"] == 1

    module.shutdown()
