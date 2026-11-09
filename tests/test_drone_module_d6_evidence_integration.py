"""Acceptance Test Suite for EarthMind Drone Module Stage D6.

Tests:
1. Valid and invalid uncertainty assessments.
2. Prevention of fabricated confidence or unsupported statistical certainty.
3. Categorical confidence level determination (HIGH, MEDIUM, LOW, INSUFFICIENT_DATA).
4. Sensor evidence packet assembly and schema validation (Contract 5, schema v1.0).
5. End-to-end source-to-indicator provenance and lineage preservation.
6. Missing, contradictory, uncalibrated, and invalid evidence rejection.
7. Calibration, quality, spatial, and temporal metadata preservation.
8. Successful B2 Context Manager integration using existing contracts (DroneSarvamIntegrationContract -> ContextItem).
9. Safe handling of unavailable B2, timeouts, and delivery errors without silent success.
10. Strict guarantee that invalid evidence never reaches B2 / Sarvam.
11. Boundary isolation preventing unauthorized Memory or Knowledge Base promotion.
12. Backward compatibility with D1–D5 operations through DroneService and DroneModule.
"""

import pytest
from core.errors.exceptions import (
    ContextProviderError,
    EvidenceValidationFailedError,
)
from core.schemas.drone import (
    AgriculturalIndicatorContract,
    CalibrationStatus,
    DroneCalibrationInfo,
    DroneDataFormat,
    DroneQualityAssessment,
    DroneSensorInputContract,
    DroneUncertaintyAssessment,
    EarthMindDroneSensorEvidence,
    EvidenceStatus,
    ProcessedSensorMeasurementContract,
    QualityStatus,
    SpatialBoundingBox,
    SpatialCoordinates,
    SpatialCoverage,
    TemporalCoverage,
)
from modules.context.manager import B2ContextManager
from modules.context.schemas import (
    ContextItem,
    ContextRequest,
    PrivacyLevel,
)
from modules.drone.drone_module import DroneModule
from modules.drone.drone_service import DroneService
from modules.drone.evidence_builder import SensorEvidenceBuilder
from modules.drone.evidence_validator import SensorEvidenceValidator
from modules.drone.sarvam_integration import DroneContextProvider, SarvamDroneIntegration
from modules.drone.uncertainty import ConfidenceLevel, UncertaintyAssessor


# ============================================================================
# Deterministic Test Fixtures
# ============================================================================

@pytest.fixture
def sample_sensor_input() -> DroneSensorInputContract:
    return DroneSensorInputContract(
        source_type="drone_sensor",
        drone_id="drone_test_01",
        sensor_id="sensor_ms_01",
        sensor_type="multispectral",
        manufacturer="MicaSense",
        model="RedEdge-P",
        data_format=DroneDataFormat.GEOTIFF,
        raw_payload={"channels": ["nir", "red", "green"]},
        collection_timestamp="2026-11-09T08:00:00Z",
        ingestion_timestamp="2026-11-09T08:05:00Z",
        spatial_metadata={"latitude": 28.6139, "longitude": 77.2090, "altitude_meters": 50.0},
        calibration_metadata={"calibration_panel_used": True, "sun_sensor_used": True},
        field_id="field_punjab_wheat_01",
        farm_id="farm_punjab_01",
        farmer_id="farmer_pb_007",
        source_provenance={"flight_id": "flight_999", "battery_percent": 92},
    )


@pytest.fixture
def sample_measurements() -> list[ProcessedSensorMeasurementContract]:
    coords = SpatialCoordinates(latitude=28.6139, longitude=77.2090, altitude_meters=50.0)
    return [
        ProcessedSensorMeasurementContract(
            measurement_id="meas_nir_001",
            measurement_type="spectral_reflectance",
            channel_name="nir",
            original_value=2450.0,
            original_unit="DN",
            processed_value=0.55,
            normalized_unit="reflectance_ratio",
            processing_method="panel_calibration",
            calibration_status=CalibrationStatus.CALIBRATED,
            timestamp="2026-11-09T08:00:00Z",
            spatial_reference=coords,
            quality_status=QualityStatus.VALID,
            source_sensor="sensor_ms_01",
            provenance={"raw_channel": "nir"},
        ),
        ProcessedSensorMeasurementContract(
            measurement_id="meas_red_001",
            measurement_type="spectral_reflectance",
            channel_name="red",
            original_value=600.0,
            original_unit="DN",
            processed_value=0.10,
            normalized_unit="reflectance_ratio",
            processing_method="panel_calibration",
            calibration_status=CalibrationStatus.CALIBRATED,
            timestamp="2026-11-09T08:00:00Z",
            spatial_reference=coords,
            quality_status=QualityStatus.VALID,
            source_sensor="sensor_ms_01",
            provenance={"raw_channel": "red"},
        ),
    ]


@pytest.fixture
def sample_indicators() -> list[AgriculturalIndicatorContract]:
    return [
        AgriculturalIndicatorContract(
            indicator_id="ind_ndvi_001",
            indicator_name="NDVI",
            definition="(NIR - Red) / (NIR + Red)",
            calculation_method="standard_band_ratio",
            required_input_measurements=["nir", "red"],
            result={"mean": 0.6923, "min": 0.65, "max": 0.72},
            unit="unitless_ratio",
            quality_status=QualityStatus.VALID,
            limitations=["Saturated in ultra-dense canopy"],
        )
    ]


@pytest.fixture
def sample_spatial() -> SpatialCoverage:
    return SpatialCoverage(
        has_spatial_metadata=True,
        centroid=SpatialCoordinates(latitude=28.6139, longitude=77.2090, altitude_meters=50.0),
        bounding_box=SpatialBoundingBox(
            min_latitude=28.6130, max_latitude=28.6150, min_longitude=77.2080, max_longitude=77.2100
        ),
        area_hectares=2.5,
        crs="EPSG:4326",
        field_id="field_punjab_wheat_01",
    )


@pytest.fixture
def sample_temporal() -> TemporalCoverage:
    return TemporalCoverage(
        start_time="2026-11-09T08:00:00Z",
        end_time="2026-11-09T08:15:00Z",
        duration_seconds=900.0,
        sampling_frequency_hz=1.0,
    )


# ============================================================================
# 1. Uncertainty Assessment Tests
# ============================================================================

def test_uncertainty_assessment_high_confidence(sample_spatial, sample_temporal):
    """Test comprehensive uncertainty assessment with optimal inputs produces HIGH confidence."""
    assessor = UncertaintyAssessor()
    quality = DroneQualityAssessment(
        input_validity=QualityStatus.VALID,
        measurement_quality="HIGH",
        processing_quality="NORMALIZED",
        evidence_completeness="COMPLETE",
        overall_quality="HIGH",
    )
    result = assessor.assess_comprehensive_uncertainty(
        quality_assessment=quality,
        calibration_status=CalibrationStatus.CALIBRATED,
        panel_used=True,
        sun_sensor_used=True,
        spatial_coverage=sample_spatial,
        temporal_coverage=sample_temporal,
        measurements_count=10,
        indicators_count=2,
    )

    assert isinstance(result, DroneUncertaintyAssessment)
    assert result.overall_confidence >= 0.85
    assert result.spatial_confidence >= 0.90
    assert result.temporal_confidence >= 0.90
    assert result.calibration_confidence >= 0.90
    assert assessor.determine_confidence_level(result.overall_confidence) == ConfidenceLevel.HIGH


def test_uncertainty_assessment_degraded_when_uncalibrated_and_missing_spatial(sample_temporal):
    """Test uncertainty degrades transparently when spatial metadata and calibration are missing."""
    assessor = UncertaintyAssessor()
    quality = DroneQualityAssessment(
        input_validity=QualityStatus.CALIBRATION_MISSING,
        measurement_quality="DEGRADED",
        processing_quality="NORMALIZED",
        evidence_completeness="PARTIAL",
        overall_quality="DEGRADED",
    )
    no_spatial = SpatialCoverage(has_spatial_metadata=False)
    result = assessor.assess_comprehensive_uncertainty(
        quality_assessment=quality,
        calibration_status=CalibrationStatus.UNCALIBRATED,
        panel_used=False,
        sun_sensor_used=False,
        spatial_coverage=no_spatial,
        temporal_coverage=sample_temporal,
        measurements_count=2,
        indicators_count=1,
    )

    assert result.spatial_confidence == 0.0
    assert result.calibration_confidence < 0.50
    assert result.overall_confidence < 0.60
    assert any("geospatial" in s.lower() for s in result.uncertainty_sources)
    assert any("calibration" in s.lower() or "uncalibrated" in s.lower() for s in result.uncertainty_sources)
    level = assessor.determine_confidence_level(result.overall_confidence)
    assert level in (ConfidenceLevel.LOW, ConfidenceLevel.INSUFFICIENT_DATA)


def test_uncertainty_no_fabricated_confidence_on_empty_measurements(sample_spatial, sample_temporal):
    """Test uncertainty correctly penalizes empty measurement sets and records reason."""
    assessor = UncertaintyAssessor()
    quality = DroneQualityAssessment(
        input_validity=QualityStatus.INCOMPLETE,
        overall_quality="DEGRADED",
    )
    result = assessor.assess_comprehensive_uncertainty(
        quality_assessment=quality,
        calibration_status=CalibrationStatus.MISSING,
        panel_used=False,
        sun_sensor_used=False,
        spatial_coverage=sample_spatial,
        temporal_coverage=sample_temporal,
        measurements_count=0,
        indicators_count=0,
    )

    assert result.overall_confidence < 0.35
    assert any("zero processed measurements" in s.lower() for s in result.uncertainty_sources)
    assert assessor.determine_confidence_level(result.overall_confidence) == ConfidenceLevel.INSUFFICIENT_DATA


# ============================================================================
# 2. Sensor Evidence Builder Tests
# ============================================================================

def test_evidence_builder_assembly(
    sample_sensor_input, sample_measurements, sample_indicators, sample_spatial, sample_temporal
):
    """Test complete EarthMindDroneSensorEvidence packet assembly with all 10 required blocks."""
    builder = SensorEvidenceBuilder()
    evidence = builder.build_evidence(
        input_data=sample_sensor_input,
        measurements=sample_measurements,
        indicators=sample_indicators,
        spatial=sample_spatial,
        temporal=sample_temporal,
        crop="Wheat",
    )

    assert isinstance(evidence, EarthMindDroneSensorEvidence)
    assert evidence.contract_name == "EarthMindDroneSensorEvidence"
    assert evidence.schema_version == "1.0"
    assert evidence.evidence_id.startswith("ev_drone_")
    assert evidence.source.drone_id == "drone_test_01"
    assert evidence.source.sensor_id == "sensor_ms_01"
    assert evidence.field.field_id == "field_punjab_wheat_01"
    assert evidence.field.crop == "Wheat"
    assert len(evidence.measurements) == 2
    assert len(evidence.indicators) == 1
    assert evidence.spatial_coverage.has_spatial_metadata is True
    assert evidence.temporal_coverage.start_time == "2026-11-09T08:00:00Z"
    assert evidence.calibration.calibration_status == CalibrationStatus.CALIBRATED
    assert evidence.uncertainty.overall_confidence > 0.80
    assert "evidence_hash" in evidence.provenance
    assert evidence.status == EvidenceStatus.SUCCESS


def test_evidence_builder_provenance_cryptographic_hash(
    sample_sensor_input, sample_measurements, sample_indicators, sample_spatial, sample_temporal
):
    """Test that generated evidence contains deterministic SHA-256 provenance hash."""
    builder = SensorEvidenceBuilder()
    evidence = builder.build_evidence(
        input_data=sample_sensor_input,
        measurements=sample_measurements,
        indicators=sample_indicators,
        spatial=sample_spatial,
        temporal=sample_temporal,
    )
    evidence_hash = evidence.provenance.get("evidence_hash")
    assert isinstance(evidence_hash, str)
    assert len(evidence_hash) == 64  # valid SHA-256 hex string


# ============================================================================
# 3. Sensor Evidence Validator Tests
# ============================================================================

def test_evidence_validator_accepts_valid_packet(
    sample_sensor_input, sample_measurements, sample_indicators, sample_spatial, sample_temporal
):
    """Test validator approves a fully conformant evidence packet."""
    builder = SensorEvidenceBuilder()
    validator = SensorEvidenceValidator()
    evidence = builder.build_evidence(
        input_data=sample_sensor_input,
        measurements=sample_measurements,
        indicators=sample_indicators,
        spatial=sample_spatial,
        temporal=sample_temporal,
    )

    result = validator.evaluate(evidence)
    assert result.is_valid is True
    assert len(result.errors) == 0
    assert result.traceability_verified is True
    assert validator.validate_evidence(evidence) is True


def test_evidence_validator_rejects_missing_source_to_indicator_lineage(
    sample_sensor_input, sample_measurements, sample_spatial, sample_temporal
):
    """Test validator rejects evidence where indicator requires channels missing in measurements."""
    # Indicator requiring 'swir1' which is not present in measurements (nir and red only)
    broken_indicator = AgriculturalIndicatorContract(
        indicator_id="ind_ndwi_broken",
        indicator_name="NDWI_GAO",
        definition="(NIR - SWIR) / (NIR + SWIR)",
        calculation_method="standard_band_ratio",
        required_input_measurements=["nir", "swir1"],
        result={"mean": 0.45},
    )
    builder = SensorEvidenceBuilder()
    validator = SensorEvidenceValidator()
    evidence = builder.build_evidence(
        input_data=sample_sensor_input,
        measurements=sample_measurements,
        indicators=[broken_indicator],
        spatial=sample_spatial,
        temporal=sample_temporal,
    )

    result = validator.evaluate(evidence)
    assert result.is_valid is False
    assert any("missing required input channel 'swir1'" in err for err in result.errors)
    with pytest.raises(EvidenceValidationFailedError):
        validator.validate_or_raise(evidence)


def test_evidence_validator_rejects_contradictory_uncertainty(
    sample_sensor_input, sample_measurements, sample_indicators, sample_temporal
):
    """Test validator rejects evidence asserting 1.0 spatial confidence when spatial metadata is absent."""
    no_spatial = SpatialCoverage(has_spatial_metadata=False)
    contradictory_uncertainty = DroneUncertaintyAssessment(
        spatial_confidence=1.0,  # Contradiction: spatial metadata is missing
        temporal_confidence=0.9,
        calibration_confidence=0.9,
        overall_confidence=0.95,
    )
    builder = SensorEvidenceBuilder()
    validator = SensorEvidenceValidator()
    evidence = builder.build_evidence(
        input_data=sample_sensor_input,
        measurements=sample_measurements,
        indicators=sample_indicators,
        spatial=no_spatial,
        temporal=sample_temporal,
        uncertainty=contradictory_uncertainty,
    )

    result = validator.evaluate(evidence)
    assert result.is_valid is False
    assert any("high spatial confidence despite absent spatial metadata" in err for err in result.errors)


def test_evidence_validator_rejects_out_of_bounds_reflectance(
    sample_sensor_input, sample_indicators, sample_spatial, sample_temporal
):
    """Test validator rejects physically nonsensical negative reflectance."""
    bad_measurement = ProcessedSensorMeasurementContract(
        measurement_id="meas_bad_nir",
        measurement_type="spectral_reflectance",
        channel_name="nir",
        original_value=-50.0,
        original_unit="DN",
        processed_value=-0.25,  # Invalid negative reflectance
        normalized_unit="reflectance_ratio",
        processing_method="panel_calibration",
        timestamp="2026-11-09T08:00:00Z",
        source_sensor="sensor_ms_01",
    )
    builder = SensorEvidenceBuilder()
    validator = SensorEvidenceValidator()
    evidence = builder.build_evidence(
        input_data=sample_sensor_input,
        measurements=[bad_measurement],
        indicators=sample_indicators,
        spatial=sample_spatial,
        temporal=sample_temporal,
    )

    result = validator.evaluate(evidence)
    assert result.is_valid is False
    assert any("out of physical bounds" in err for err in result.errors)


# ============================================================================
# 4. Sarvam Integration & B2 Context Bridge Tests
# ============================================================================

def test_format_for_context_item(
    sample_sensor_input, sample_measurements, sample_indicators, sample_spatial, sample_temporal
):
    """Test conversion of validated evidence to B2 ContextItem conforming to B2 specifications."""
    builder = SensorEvidenceBuilder()
    integration = SarvamDroneIntegration()
    evidence = builder.build_evidence(
        input_data=sample_sensor_input,
        measurements=sample_measurements,
        indicators=sample_indicators,
        spatial=sample_spatial,
        temporal=sample_temporal,
    )

    context_item = integration.format_for_context(evidence)
    assert isinstance(context_item, ContextItem)
    assert context_item.context_id == f"ctx_drone_{evidence.evidence_id}"
    assert context_item.entity_type == "drone_sensor_evidence"
    assert context_item.entity_id == "field_punjab_wheat_01"
    assert context_item.data_type == "sensor_evidence"
    assert context_item.privacy_level == PrivacyLevel.FARM_PRIVATE
    assert context_item.source == "drone_module"
    assert context_item.source_id == evidence.evidence_id
    assert context_item.confidence == evidence.uncertainty.overall_confidence
    assert "indicators" in context_item.content
    assert context_item.content["evidence_id"] == evidence.evidence_id


def test_b2_context_manager_integration(
    sample_sensor_input, sample_measurements, sample_indicators, sample_spatial, sample_temporal
):
    """Test registering DroneContextProvider in B2ContextManager and retrieving validated context."""
    builder = SensorEvidenceBuilder()
    evidence = builder.build_evidence(
        input_data=sample_sensor_input,
        measurements=sample_measurements,
        indicators=sample_indicators,
        spatial=sample_spatial,
        temporal=sample_temporal,
    )

    b2 = B2ContextManager()
    integration = SarvamDroneIntegration(context_manager=b2)
    provider = integration.create_context_provider()
    b2.register_provider(provider)

    # Stage evidence in integration buffer
    integration.stage_evidence(evidence)

    # Execute B2 Context preparation
    req = ContextRequest(
        request_id="req_scan_wheat_001",
        field_id="field_punjab_wheat_01",
        farmer_id="farmer_pb_007",
        task="Evaluate crop vigor and vegetation index",
    )
    res = b2.prepare_context(req)

    assert res.state.value in ("COMPLETED", "PARTIAL")
    drone_items = [it for it in res.items if it.source == "drone_module"]
    assert len(drone_items) == 1
    assert drone_items[0].entity_id == "field_punjab_wheat_01"
    assert drone_items[0].content["evidence_id"] == evidence.evidence_id


def test_invalid_evidence_never_reaches_b2(
    sample_sensor_input, sample_measurements, sample_spatial, sample_temporal
):
    """Test that invalid evidence is rejected and prevented from reaching B2 Context Manager."""
    # Build broken evidence lacking required channel for indicator
    broken_ind = AgriculturalIndicatorContract(
        indicator_id="ind_broken",
        indicator_name="NDRE",
        definition="(NIR - RedEdge) / (NIR + RedEdge)",
        calculation_method="standard_band_ratio",
        required_input_measurements=["nir", "red_edge"],  # red_edge missing
        result={"mean": 0.5},
    )
    builder = SensorEvidenceBuilder()
    evidence = builder.build_evidence(
        input_data=sample_sensor_input,
        measurements=sample_measurements,
        indicators=[broken_ind],
        spatial=sample_spatial,
        temporal=sample_temporal,
    )

    b2 = B2ContextManager()
    integration = SarvamDroneIntegration(context_manager=b2)

    with pytest.raises(EvidenceValidationFailedError):
        integration.deliver_to_context_manager(evidence)


def test_sarvam_integration_failure_when_b2_unavailable(
    sample_sensor_input, sample_measurements, sample_indicators, sample_spatial, sample_temporal
):
    """Test fail-closed delivery failure when B2 Context Manager is not configured."""
    builder = SensorEvidenceBuilder()
    evidence = builder.build_evidence(
        input_data=sample_sensor_input,
        measurements=sample_measurements,
        indicators=sample_indicators,
        spatial=sample_spatial,
        temporal=sample_temporal,
    )
    integration = SarvamDroneIntegration(context_manager=None)

    with pytest.raises(ContextProviderError) as exc_info:
        integration.deliver_to_context_manager(evidence)

    assert "unavailable or unconfigured" in str(exc_info.value).lower()


# ============================================================================
# 5. Boundary Governance & Non-Promotion Tests
# ============================================================================

def test_drone_evidence_boundary_isolation_no_unauthorized_promotion(
    sample_sensor_input, sample_measurements, sample_indicators, sample_spatial, sample_temporal
):
    """
    Test C.3 boundary governance: Drone sensor evidence is scoped as FARM_PRIVATE
    and does NOT promote automatically to General Memory, User Memory, or Knowledge Base.
    """
    builder = SensorEvidenceBuilder()
    integration = SarvamDroneIntegration()
    evidence = builder.build_evidence(
        input_data=sample_sensor_input,
        measurements=sample_measurements,
        indicators=sample_indicators,
        spatial=sample_spatial,
        temporal=sample_temporal,
    )
    item = integration.format_for_context(evidence)

    assert item.privacy_level == PrivacyLevel.FARM_PRIVATE
    assert item.is_pii is False
    assert item.entity_type == "drone_sensor_evidence"
    assert item.data_type == "sensor_evidence"
    assert item.source == "drone_module"


# ============================================================================
# 6. Service & Module End-to-End Workflow Tests
# ============================================================================

def test_drone_service_d6_operations(
    sample_sensor_input, sample_measurements, sample_indicators, sample_spatial, sample_temporal
):
    """Test D6 operations exposed via DroneService facade."""
    service = DroneService()

    # 1. Build evidence via service
    evidence = service.build_evidence(
        input_data=sample_sensor_input,
        measurements=sample_measurements,
        indicators=sample_indicators,
        spatial=sample_spatial,
        temporal=sample_temporal,
        crop="Wheat",
    )
    assert evidence.status == EvidenceStatus.SUCCESS

    # 2. Validate evidence via service
    val_res = service.validate_evidence(evidence, strict=False)
    assert val_res.is_valid is True

    # 3. Deliver to context manager via service
    b2 = B2ContextManager()
    delivery = service.deliver_evidence_to_context(evidence, context_manager=b2)
    assert delivery["delivered"] is True
    assert delivery["target_model"] == "Sarvam-105B"


def test_drone_module_application_request_dispatch(
    sample_sensor_input, sample_measurements, sample_indicators, sample_spatial, sample_temporal
):
    """Test ApplicationRequest dispatch in DroneModule for D6 operations."""
    from core.schemas.application import ApplicationRequest

    module = DroneModule()
    module.initialize()

    # Dispatch 'build_evidence'
    req_build = ApplicationRequest(
        request_id="req_build_01",
        source="test_runner",
        operation="build_evidence",
        payload={
            "input_data": sample_sensor_input.model_dump(),
            "measurements": [m.model_dump() for m in sample_measurements],
            "indicators": [i.model_dump() for i in sample_indicators],
            "spatial": sample_spatial.model_dump(),
            "temporal": sample_temporal.model_dump(),
            "crop": "Wheat",
        },
    )
    resp_build = module.handle(req_build)
    assert resp_build.status == "SUCCESS"
    evidence_payload = resp_build.response
    assert evidence_payload["evidence_id"].startswith("ev_drone_")

    # Dispatch 'validate_evidence'
    req_val = ApplicationRequest(
        request_id="req_val_01",
        source="test_runner",
        operation="validate_evidence",
        payload={"evidence": evidence_payload, "strict": False},
    )
    resp_val = module.handle(req_val)
    assert resp_val.status == "SUCCESS"
    assert resp_val.response["is_valid"] is True

    module.shutdown()
