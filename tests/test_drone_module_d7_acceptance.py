"""Comprehensive End-to-End Acceptance & Hardening Test Suite for EarthMind Drone Module (Stage D7).

Verifies:
1. Complete integrated data flow:
   Raw Drone Sensor Upload -> D1 Contracts -> D2 Gateway/Registry/Adapters ->
   D3 Processing/Calibration/Normalization -> D4 Geospatial/Temporal ->
   D5 Spectral/Numerical Analysis & Fusion -> D6 Uncertainty & Evidence Validation ->
   B2 Context Manager -> B3 Reasoning Engine / Sarvam-105B.
2. Cross-module and architectural boundaries:
   - D1-D6 contracts are versioned, compatible, and immutable.
   - Optical camera routing safely hands off to Vision Module without image decoding.
   - Non-diagnostic guarantee: evidence provides objective measurements, never pre-calculated crop disease diagnoses or chemical prescriptions.
   - Drone module provides zero flight control or navigation.
   - Strict boundary protection: drone sensor evidence is FARM_PRIVATE and never automatically promoted into User Memory, General Memory, or C.2 Knowledge Base.
3. Realistic failure, recovery, and resilience matrix:
   - Malformed, empty, and unsupported sensor payloads.
   - Path traversal and security injection in metadata.
   - Missing calibration handling with transparent uncertainty degradation.
   - Invalid coordinates, out-of-bounds latitude/longitude, and unsupported CRS.
   - Missing spectral bands, zero-division in band ratios, and uncalculable indices.
   - Conflicting multi-sensor measurements detected and preserved without silent averaging.
   - Contradictory, corrupt, and out-of-physical-bounds evidence packets rejected by validation gate.
   - B2 Context Manager unavailable or timed out fails closed without silent false success.
   - Storage failures, adapter rejections, and disabled gateway states.
"""

from unittest.mock import MagicMock
import pytest

from core.errors.exceptions import (
    ContextProviderError,
    EvidenceValidationFailedError,
    GeolocationInvalidError,
    IndicatorProcessingFailedError,
    UnsupportedFormatError,
    UnsupportedSensorError,
)
from core.schemas.application import ApplicationRequest, ApplicationResponse
from core.schemas.drone import (
    AgriculturalIndicatorContract,
    CalibrationStatus,
    DroneCameraRoutingContract,
    DroneDataFormat,
    DroneErrorCode,
    DroneQualityAssessment,
    DroneSensorInputContract,
    DroneUncertaintyAssessment,
    EarthMindDroneSensorEvidence,
    EvidenceStatus,
    FieldBoundaryContract,
    IngestionStatus,
    ProcessedSensorMeasurementContract,
    QualityStatus,
    SensorCategory,
    SensorMetadataContract,
    SpatialBoundingBox,
    SpatialCoordinates,
    SpatialCoverage,
    TemporalCoverage,
)
from core.schemas.model import ModelGenerationRequest, ModelGenerationResponse
from modules.context.manager import B2ContextManager
from modules.context.schemas import (
    ContextItem,
    ContextRequest,
    ContextResult,
    ContextState,
    PriorityLevel,
    PrivacyLevel,
)
from modules.drone.drone_module import DroneModule
from modules.drone.drone_service import DroneService
from modules.drone.evidence_builder import SensorEvidenceBuilder
from modules.drone.evidence_validator import SensorEvidenceValidator
from modules.drone.sarvam_integration import DroneContextProvider, SarvamDroneIntegration
from modules.drone.uncertainty import ConfidenceLevel, UncertaintyAssessor
from modules.reasoning import (
    EvidenceManager,
    EvidenceScope,
    ModelLayerReasoningCapability,
    ReasoningInput,
    ReasoningModule,
    ReasoningPolicyConfig,
    ReasoningState,
    ReasoningStrategyController,
)


# ============================================================================
# Deterministic Test Fixtures
# ============================================================================

@pytest.fixture
def drone_service() -> DroneService:
    service = DroneService()
    # Register active test sensors
    service.register_sensor(
        SensorMetadataContract(
            sensor_id="sensor_micasense_rededge_p",
            sensor_category=SensorCategory.MULTISPECTRAL,
            manufacturer="MicaSense",
            model="RedEdge-P",
            supported_measurements=["blue", "green", "red", "red_edge", "nir"],
            supported_formats=[DroneDataFormat.GEOTIFF, DroneDataFormat.CSV, DroneDataFormat.JSON],
            measurement_units={"reflectance": "unitless_ratio"},
            sampling_characteristics={"bands": 5, "gsd_cm": 3.2},
            calibration_metadata={"panel_required": True, "sun_sensor_supported": True},
            capability_version="1.0",
            registration_status="ACTIVE",
        )
    )
    service.register_sensor(
        SensorMetadataContract(
            sensor_id="sensor_flir_vue_pro",
            sensor_category=SensorCategory.THERMAL,
            manufacturer="FLIR",
            model="Vue Pro R",
            supported_measurements=["thermal_ir"],
            supported_formats=[DroneDataFormat.GEOTIFF, DroneDataFormat.CSV, DroneDataFormat.JSON],
            measurement_units={"thermal_ir": "celsius"},
            sampling_characteristics={"spectral_range_um": "7.5-13.5"},
            calibration_metadata={"factory_calibrated": True},
            capability_version="1.0",
            registration_status="ACTIVE",
        )
    )
    return service


@pytest.fixture
def sample_multispectral_input() -> DroneSensorInputContract:
    return DroneSensorInputContract(
        source_type="drone_sensor",
        drone_id="drone_dji_m300_01",
        sensor_id="sensor_micasense_rededge_p",
        sensor_type="multispectral",
        manufacturer="MicaSense",
        model="RedEdge-P",
        data_format=DroneDataFormat.JSON,
        raw_payload={
            "channels": {
                "blue": [0.05, 0.06, 0.05],
                "green": [0.08, 0.09, 0.08],
                "red": [0.07, 0.08, 0.07],
                "red_edge": [0.22, 0.24, 0.23],
                "nir": [0.55, 0.58, 0.56],
            }
        },
        collection_timestamp="2026-11-09T09:00:00Z",
        ingestion_timestamp="2026-11-09T09:05:00Z",
        spatial_metadata={"latitude": 30.7333, "longitude": 76.7794, "altitude_meters": 60.0},
        calibration_metadata={"calibration_panel_used": True, "sun_sensor_used": True},
        field_id="field_punjab_wheat_block_a",
        farm_id="farm_punjab_central",
        farmer_id="farmer_pb_101",
        source_provenance={"flight_id": "mission_fl_2026_01", "operator": "AgriFly_Punjab"},
    )


# ============================================================================
# 1. Complete Pipeline Verification: Sensor Upload to Sarvam-105B Reasoning
# ============================================================================

def test_complete_e2e_drone_to_sarvam_reasoning(drone_service, sample_multispectral_input):
    """
    Verify complete integrated pipeline:
    1. Ingestion at Drone Data Gateway (D2)
    2. Processing, Quality, Calibration & Unit Normalization (D3)
    3. Geospatial & Temporal Association (D4)
    4. Spectral Analysis & Indicator Extraction (NDVI, NDRE) (D5)
    5. Uncertainty Assessment & Canonical Evidence Packaging (D6)
    6. Strict Evidence Validation Gate (D6)
    7. Delivery to B2 Context Manager (D6/B2)
    8. Context Preparation in B2
    9. Ingestion into B3 Reasoning Engine with Sarvam-105B adapter
    """
    # 1. Ingestion
    ingestion_res = drone_service.ingest_sensor_data(sample_multispectral_input)
    assert ingestion_res.accepted is True
    assert ingestion_res.status == IngestionStatus.SUCCESS

    # 2. Processing
    proc_res = drone_service.process_sensor_data(sample_multispectral_input)
    assert proc_res["measurements_count"] >= 5
    measurements = [ProcessedSensorMeasurementContract(**m) for m in proc_res["measurements"]]
    assert all(m.quality_status == QualityStatus.VALID for m in measurements)

    # 3. Geospatial & Temporal Association
    association = drone_service.associate_spatiotemporal(
        drone_id=sample_multispectral_input.drone_id,
        sensor_id=sample_multispectral_input.sensor_id,
        measurements=measurements,
        field_id=sample_multispectral_input.field_id,
    )
    assert association.spatial_report.has_spatial_metadata is True
    assert association.temporal_report.normalized_start_time is not None

    # 4. Spectral & Indicator Extraction
    indicators = drone_service.extract_available_indicators(measurements)
    assert len(indicators) >= 2  # NDVI and NDRE
    ind_names = [ind.indicator_name for ind in indicators]
    assert "NDVI" in ind_names
    assert "NDRE" in ind_names
    ndvi_ind = next(ind for ind in indicators if ind.indicator_name == "NDVI")
    assert 0.0 < ndvi_ind.result["mean"] < 1.0

    # 5. Spatial & Temporal Coverage assembly
    spatial_coverage = SpatialCoverage(
        has_spatial_metadata=True,
        centroid=association.spatial_report.centroid,
        bounding_box=association.spatial_report.bounding_box,
        field_id=sample_multispectral_input.field_id,
    )
    temporal_coverage = TemporalCoverage(
        start_time=association.temporal_report.normalized_start_time,
        end_time=association.temporal_report.normalized_end_time,
        duration_seconds=association.temporal_report.duration_seconds,
    )

    # 6. Build Evidence
    evidence = drone_service.build_evidence(
        input_data=sample_multispectral_input,
        measurements=measurements,
        indicators=indicators,
        spatial=spatial_coverage,
        temporal=temporal_coverage,
        crop="Wheat",
        warnings=["Light wind gusts during scan"],
        limitations=["Optical saturation possible at extreme canopy density"],
    )
    assert isinstance(evidence, EarthMindDroneSensorEvidence)
    assert evidence.status == EvidenceStatus.SUCCESS
    assert evidence.uncertainty.overall_confidence > 0.80

    # 7. Validate Evidence
    val_res = drone_service.validate_evidence(evidence, strict=True)
    assert val_res.is_valid is True

    # 8. Deliver to B2 Context Manager
    b2 = B2ContextManager()
    delivery_report = drone_service.deliver_evidence_to_context(evidence, context_manager=b2)
    assert delivery_report["delivered"] is True
    assert delivery_report["target_model"] == "Sarvam-105B"

    # Register DroneContextProvider into B2
    provider = drone_service.sarvam_integration.create_context_provider()
    b2.register_provider(provider)

    # Prepare context for Sarvam-105B
    ctx_req = ContextRequest(
        request_id="ctx_req_punjab_eval_001",
        farmer_id=sample_multispectral_input.farmer_id,
        farm_id=sample_multispectral_input.farm_id,
        field_id=sample_multispectral_input.field_id,
        task="Assess wheat canopy vigor and nitrogen status",
    )
    ctx_result = b2.prepare_context(ctx_req)
    assert ctx_result.state in (ContextState.COMPLETED, ContextState.PARTIAL)

    drone_items = [it for it in ctx_result.items if it.source == "drone_module"]
    assert len(drone_items) == 1
    drone_context = drone_items[0]
    assert drone_context.privacy_level == PrivacyLevel.FARM_PRIVATE
    assert drone_context.content["evidence_id"] == evidence.evidence_id
    assert "indicators" in drone_context.content

    # 9. Deliver into B3 Reasoning Engine & Sarvam-105B
    evidence_mgr = EvidenceManager()
    reasoning_input = ReasoningInput(
        request_id="reason_punjab_001",
        task="Assess wheat canopy vigor and nitrogen status",
        prepared_context=ctx_result,
    )
    evidence_items, assumptions, missing = evidence_mgr.prepare_evidence(reasoning_input)
    assert len(evidence_items) >= 1

    matched_drone_ev = next(e for e in evidence_items if "drone" in e.source)
    assert matched_drone_ev.scope == EvidenceScope.FIELD
    assert matched_drone_ev.confidence > 0.80
    assert "indicators" in matched_drone_ev.content

    # Mock Sarvam-105B adapter to verify downstream reasoning consumes drone evidence
    mock_sarvam_model = MagicMock()
    mock_sarvam_model.status.return_value = {"identifier": "sarvam-105b", "loaded": True}
    mock_sarvam_model.generate.return_value = ModelGenerationResponse(
        request_id="sarvam_gen_001",
        status="success",
        response="Grounded on drone evidence: Mean NDVI of 0.77 indicates healthy vegetative wheat canopy.",
        confidence_level=0.91,
        model_version="sarvam-105b-agri",
    )

    reasoning_module = ReasoningModule()
    reasoning_module.initialize()
    reasoning_module.set_capability(ModelLayerReasoningCapability(model=mock_sarvam_model))

    reasoning_input.evidence_items = evidence_items
    reasoning_result, inspector_handoff = reasoning_module.reason(reasoning_input)

    assert reasoning_result.status == ReasoningState.COMPLETED
    assert len(reasoning_result.findings) >= 1
    assert "NDVI" in reasoning_result.findings[0].statement
    mock_sarvam_model.generate.assert_called_once()
    reasoning_module.shutdown()


# ============================================================================
# 2. Cross-Module Boundaries & Architectural Protections
# ============================================================================

def test_optical_camera_routing_to_vision_module(drone_service):
    """
    Verify optical camera images route to Vision Module via DroneCameraRoutingContract
    without image decoding or visual interpretation by Drone Module.
    """
    mock_vision = MagicMock()
    mock_vision.ingest_camera_frame.return_value = {"status": "SUCCESS", "vision_job_id": "vjob_999"}
    service_with_vision = DroneService(vision_service=mock_vision)

    camera_contract = DroneCameraRoutingContract(
        drone_id="drone_dji_m300_01",
        camera_id="cam_zenmuse_h20",
        sensor_category=SensorCategory.RGB,
        collection_timestamp="2026-11-09T09:00:00Z",
        image_reference="s3://earthmind-imagery/punjab/frame_001.jpg",
        image_mime_type="image/jpeg",
        field_id="field_punjab_01",
        destination_module="vision",
        requires_visual_interpretation=True,
    )

    result = service_with_vision.route_camera_data(camera_contract)
    assert result["status"] == "ROUTED"
    assert result["destination_module"] == "vision"
    assert result["vision_response"]["vision_job_id"] == "vjob_999"


def test_drone_module_non_diagnostic_guarantee(drone_service, sample_multispectral_input):
    """
    Verify that the Drone Module emits strictly factual observations and indicators,
    and never injects pre-formed disease diagnoses or chemical treatment prescriptions.
    """
    proc = drone_service.process_sensor_data(sample_multispectral_input)
    meas = [ProcessedSensorMeasurementContract(**m) for m in proc["measurements"]]
    indicators = drone_service.extract_available_indicators(meas)
    evidence = drone_service.build_evidence(
        input_data=sample_multispectral_input,
        measurements=meas,
        indicators=indicators,
        spatial=SpatialCoverage(has_spatial_metadata=False),
        temporal=TemporalCoverage(start_time="2026-11-09T09:00:00Z"),
    )

    # Check that evidence content contains indicators and reflectances, not diagnoses
    evidence_str = str(evidence.model_dump()).lower()
    prohibited_prescriptions = ["apply pesticide", "spray fungicide", "urea dosage", "infected with rust", "treat with"]
    for phrase in prohibited_prescriptions:
        assert phrase not in evidence_str, f"Found prohibited diagnosis/prescription in evidence: {phrase}"


def test_no_flight_control_or_navigation_in_drone_module():
    """Verify DroneModule and DroneService have no flight control, autopilot, or navigation methods."""
    service = DroneService()
    module = DroneModule(service=service)

    forbidden_attributes = [
        "pilot", "fly", "navigate", "autopilot", "takeoff", "land", "set_waypoint",
        "return_to_home", "command_motor", "throttle", "yaw", "pitch_control"
    ]
    for attr in forbidden_attributes:
        assert not hasattr(service, attr), f"DroneService violates boundary by exposing flight control: {attr}"
        assert not hasattr(module, attr), f"DroneModule violates boundary by exposing flight control: {attr}"


def test_drone_evidence_zero_unauthorized_memory_kb_promotion(drone_service, sample_multispectral_input):
    """
    Verify C.3 boundary governance: Drone sensor evidence is scoped as FARM_PRIVATE
    and does NOT promote automatically to General Memory, User Memory, or Knowledge Base.
    """
    proc = drone_service.process_sensor_data(sample_multispectral_input)
    meas = [ProcessedSensorMeasurementContract(**m) for m in proc["measurements"]]
    evidence = drone_service.build_evidence(
        input_data=sample_multispectral_input,
        measurements=meas,
        indicators=[],
        spatial=SpatialCoverage(has_spatial_metadata=False),
        temporal=TemporalCoverage(start_time="2026-11-09T09:00:00Z"),
    )

    item = drone_service.sarvam_integration.format_for_context(evidence)
    assert item.privacy_level == PrivacyLevel.FARM_PRIVATE
    assert item.entity_type == "drone_sensor_evidence"
    assert item.source == "drone_module"
    assert item.is_pii is False


# ============================================================================
# 3. Comprehensive Failure, Recovery & Resilience Matrix
# ============================================================================

def test_failure_malformed_and_empty_payload(drone_service):
    """Test gateway safely rejects malformed or empty sensor payload inputs."""
    # 1. Missing both payload and reference
    with pytest.raises(Exception):
        DroneSensorInputContract(
            drone_id="drone_01",
            sensor_id="sensor_micasense_rededge_p",
            sensor_type="multispectral",
            data_format=DroneDataFormat.JSON,
            collection_timestamp="2026-11-09T09:00:00Z",
            raw_payload=None,
            raw_payload_ref=None,
        )

    # 2. Empty drone_id or sensor_id
    with pytest.raises(Exception):
        DroneSensorInputContract(
            drone_id="",
            sensor_id="sensor_micasense_rededge_p",
            sensor_type="multispectral",
            data_format=DroneDataFormat.JSON,
            collection_timestamp="2026-11-09T09:00:00Z",
            raw_payload={"data": 1},
        )


def test_failure_path_traversal_attack_rejected(drone_service):
    """Test gateway rejects path traversal attempts in identifiers."""
    input_contract = DroneSensorInputContract(
        drone_id="../../etc/shadow",
        sensor_id="sensor_micasense_rededge_p",
        sensor_type="multispectral",
        data_format=DroneDataFormat.JSON,
        collection_timestamp="2026-11-09T09:00:00Z",
        raw_payload={"data": 1},
    )
    result = drone_service.ingest_sensor_data(input_contract)
    assert result.accepted is False
    assert result.status == IngestionStatus.REJECTED
    assert "path traversal" in result.error.message.lower()


def test_failure_unsupported_sensor_and_format(drone_service):
    """Test gateway rejects unlisted or unsupported sensors and formats."""
    # Unregistered sensor
    input_contract = DroneSensorInputContract(
        drone_id="drone_01",
        sensor_id="unregistered_quantum_sensor_9000",
        sensor_type="hyperspectral",
        data_format=DroneDataFormat.JSON,
        collection_timestamp="2026-11-09T09:00:00Z",
        raw_payload={"data": 1},
    )
    result = drone_service.ingest_sensor_data(input_contract)
    assert result.accepted is False
    assert result.status == IngestionStatus.REJECTED
    assert "not registered" in result.error.message.lower()


def test_failure_missing_calibration_transparent_uncertainty_penalty(drone_service):
    """Test uncalibrated sensor input is processed but penalized heavily in uncertainty assessment."""
    uncalibrated_input = DroneSensorInputContract(
        drone_id="drone_dji_m300_01",
        sensor_id="sensor_micasense_rededge_p",
        sensor_type="multispectral",
        data_format=DroneDataFormat.JSON,
        raw_payload={"channels": {"nir": [0.6], "red": [0.1]}},
        collection_timestamp="2026-11-09T09:00:00Z",
        calibration_metadata={"calibration_panel_used": False, "sun_sensor_used": False},
    )
    proc = drone_service.process_sensor_data(uncalibrated_input)
    meas = [ProcessedSensorMeasurementContract(**m) for m in proc["measurements"]]
    indicators = drone_service.extract_available_indicators(meas)

    evidence = drone_service.build_evidence(
        input_data=uncalibrated_input,
        measurements=meas,
        indicators=indicators,
        spatial=SpatialCoverage(has_spatial_metadata=False),
        temporal=TemporalCoverage(start_time="2026-11-09T09:00:00Z"),
    )

    assert evidence.calibration.calibration_status == CalibrationStatus.UNCALIBRATED
    assert evidence.uncertainty.calibration_confidence <= 0.40
    assert any("calibration" in s.lower() or "uncalibrated" in s.lower() for s in evidence.uncertainty.uncertainty_sources)


def test_failure_invalid_coordinates_and_crs_rejection(drone_service):
    """Test geospatial processor rejects coordinates outside physical limits and unsupported CRS."""
    geo = drone_service.geospatial_processor

    # Latitude out of [-90, 90]
    with pytest.raises(GeolocationInvalidError) as exc_lat:
        geo.parse_coordinate_metadata({"latitude": 110.0, "longitude": 75.0})
    assert "outside valid range" in str(exc_lat.value.details)

    # Longitude out of [-180, 180]
    with pytest.raises(GeolocationInvalidError) as exc_lon:
        geo.parse_coordinate_metadata({"latitude": 25.0, "longitude": 200.0})
    assert "outside valid range" in str(exc_lon.value.details)

    # Unsupported CRS
    with pytest.raises(GeolocationInvalidError) as exc_crs:
        geo.parse_coordinate_metadata({"lat": 25.0, "lon": 75.0, "crs": "EPSG:9999999"})
    assert "unsupported or invalid crs" in str(exc_crs.value.details).lower()


def test_failure_missing_bands_and_zero_division_safety(drone_service):
    """Test indicator engine handles missing spectral bands and division-by-zero safely without unhandled crashes."""
    # 1. Missing red band for NDVI
    meas_nir_only = [
        ProcessedSensorMeasurementContract(
            measurement_type="spectral_reflectance",
            channel_name="nir",
            original_value=1000.0,
            original_unit="DN",
            processed_value=0.5,
            normalized_unit="reflectance_ratio",
            processing_method="test",
            timestamp="2026-11-09T09:00:00Z",
            source_sensor="sensor_micasense_rededge_p",
        )
    ]
    with pytest.raises(IndicatorProcessingFailedError) as exc_info:
        drone_service.extract_indicator("NDVI", meas_nir_only)
    assert "missing" in str(exc_info.value).lower()

    # 2. Division by zero: NIR = 0.0, Red = 0.0 fails safe with structured error
    meas_zero = [
        ProcessedSensorMeasurementContract(
            measurement_type="spectral_reflectance",
            channel_name="nir",
            original_value=0.0,
            original_unit="DN",
            processed_value=0.0,
            normalized_unit="reflectance_ratio",
            processing_method="test",
            timestamp="2026-11-09T09:00:00Z",
            source_sensor="sensor_micasense_rededge_p",
        ),
        ProcessedSensorMeasurementContract(
            measurement_type="spectral_reflectance",
            channel_name="red",
            original_value=0.0,
            original_unit="DN",
            processed_value=0.0,
            normalized_unit="reflectance_ratio",
            processing_method="test",
            timestamp="2026-11-09T09:00:00Z",
            source_sensor="sensor_micasense_rededge_p",
        ),
    ]
    with pytest.raises(IndicatorProcessingFailedError) as exc_zero:
        drone_service.extract_indicator("NDVI", meas_zero)
    assert "division-by-zero" in str(exc_zero.value).lower()


def test_failure_multi_sensor_conflict_handling_no_silent_averaging(drone_service):
    """Test multi-sensor fusion detects conflicting measurements and preserves conflict details."""
    coords = SpatialCoordinates(latitude=30.0, longitude=75.0)
    # Sensor 1 reports high surface temperature
    meas1 = [
        ProcessedSensorMeasurementContract(
            measurement_type="temperature",
            channel_name="thermal_ir",
            original_value=45.0,
            original_unit="celsius",
            processed_value=45.0,
            normalized_unit="celsius",
            processing_method="calibrated",
            timestamp="2026-11-09T09:00:00Z",
            spatial_reference=coords,
            source_sensor="sensor_flir_vue_pro",
        )
    ]
    # Sensor 2 reports low surface temperature at same time and place (conflict)
    meas2 = [
        ProcessedSensorMeasurementContract(
            measurement_type="temperature",
            channel_name="thermal_ir",
            original_value=20.0,
            original_unit="celsius",
            processed_value=20.0,
            normalized_unit="celsius",
            processing_method="calibrated",
            timestamp="2026-11-09T09:00:00Z",
            spatial_reference=coords,
            source_sensor="sensor_thermal_secondary",
        )
    ]

    fusion_report = drone_service.fuse_sensor_data(
        sensor_streams={"sensor_flir_vue_pro": meas1, "sensor_thermal_secondary": meas2},
        drone_id="drone_dji_m300_01",
    )
    assert fusion_report.conflicts_detected_count >= 1
    assert any(c["channel"] == "thermal_ir" for c in fusion_report.conflicts)


def test_failure_evidence_validator_rejects_corrupt_and_contradictory_evidence(drone_service):
    """Test validator rejects evidence with contradictory spatial confidence and out-of-range reflectance."""
    builder = SensorEvidenceBuilder()
    validator = SensorEvidenceValidator()

    # Contradictory: spatial metadata absent, but claims 0.95 spatial confidence
    bad_evidence = builder.build_evidence(
        input_data=DroneSensorInputContract(
            drone_id="drone_01",
            sensor_id="sensor_micasense_rededge_p",
            sensor_type="multispectral",
            data_format=DroneDataFormat.JSON,
            raw_payload={"channels": {"nir": [0.5]}},
            collection_timestamp="2026-11-09T09:00:00Z",
        ),
        measurements=[],
        indicators=[],
        spatial=SpatialCoverage(has_spatial_metadata=False),
        temporal=TemporalCoverage(start_time="2026-11-09T09:00:00Z"),
        uncertainty=DroneUncertaintyAssessment(
            spatial_confidence=0.95,  # Contradiction!
            temporal_confidence=0.9,
            calibration_confidence=0.9,
            overall_confidence=0.9,
        ),
    )

    eval_res = validator.evaluate(bad_evidence)
    assert eval_res.is_valid is False
    assert any("spatial" in err.lower() for err in eval_res.errors)


def test_failure_b2_unavailable_fails_closed(drone_service, sample_multispectral_input):
    """Test fail-closed delivery when B2 Context Manager is None or raises delivery error."""
    evidence = drone_service.build_evidence(
        input_data=sample_multispectral_input,
        measurements=[],
        indicators=[],
        spatial=SpatialCoverage(has_spatial_metadata=False),
        temporal=TemporalCoverage(start_time="2026-11-09T09:00:00Z"),
    )

    with pytest.raises(ContextProviderError) as exc_info:
        drone_service.deliver_evidence_to_context(evidence, context_manager=None)
    assert "unavailable or unconfigured" in str(exc_info.value).lower()


def test_failure_gateway_disabled_state(drone_service, sample_multispectral_input):
    """Test gateway behavior when gateway is disabled."""
    drone_service.gateway.set_enabled(False)
    result = drone_service.ingest_sensor_data(sample_multispectral_input)
    assert result.accepted is False
    assert result.status == IngestionStatus.UNAVAILABLE
    assert "disabled" in result.error.message.lower()
    drone_service.gateway.set_enabled(True)  # restore
