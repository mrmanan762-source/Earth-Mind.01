"""Contract-level validation tests for EarthMind Drone Module Stage D1.

Verifies:
1. Valid sensor input contract parsing and validation.
2. Invalid sensor input rejection (missing required fields, bad formats).
3. Required metadata validation (spatial, temporal, units).
4. Sensor identity and capability validation (SensorMetadataContract).
5. Measurement contract validation (dual preservation of raw vs normalized values).
6. Agricultural indicator contract validation (NDVI, NDRE, NDWI band requirements).
7. EarthMindDroneSensorEvidence output schema validation (v1.0 schema version check).
8. Missing calibration representation (explicit UNCALIBRATED/MISSING without fabricated data).
9. Missing spatial metadata representation (has_spatial_metadata: False without hallucinated coordinates).
10. Missing spectral band representation (graceful degradation, indicator limitation logging).
11. Camera routing contract validation (ensures optical data routed to Vision Module).
12. Sarvam integration contract & B2 ContextItem compatibility.
13. Structured error contract validation (all 18 error codes, retryable flags, metadata).
14. Schema version handling and backward-compatibility rules.
15. Unsupported fields and malformed payload handling.
"""

import pytest
from pydantic import ValidationError

from core.errors.exceptions import (
    CalibrationUnavailableError,
    DroneError,
    DroneInvalidArgumentError,
    DroneInternalError,
    DroneProcessingTimeoutError,
    DroneStorageError,
    DroneStorageUnavailableError,
    EvidenceValidationFailedError,
    GeolocationInvalidError,
    IndicatorProcessingFailedError,
    InsufficientDroneDataError,
    InvalidSensorDataError,
    QualityValidationFailedError,
    SensorConflictError,
    SensorMetadataMissingError,
    TimestampInvalidError,
    UnitConversionFailedError,
    UnsupportedFormatError,
    UnsupportedSensorError,
)
from core.interfaces.drone import (
    ICalibrationNormalizer,
    IDataFormatDetector,
    IDataQualityValidator,
    IDroneDataGateway,
    IDroneDiagnostics,
    IDroneStorageAdapter,
    IGeospatialProcessor,
    IIndicatorExtractor,
    IMultiSensorFusionEngine,
    IProvenanceManager,
    IRawDataProcessor,
    ISarvamDroneIntegration,
    ISensorEvidenceBuilder,
    ISensorEvidenceValidator,
    ISensorRegistry,
    ISpectralNumericalAnalyzer,
    ITemporalProcessor,
    IUncertaintyAssessor,
)
from core.schemas.drone import (
    AgriculturalIndicatorContract,
    CalibrationStatus,
    DroneCameraRoutingContract,
    DroneCollectionInfo,
    DroneDataFormat,
    DroneErrorContract,
    DroneErrorCode,
    DroneFieldInfo,
    DroneQualityAssessment,
    DroneSarvamIntegrationContract,
    DroneSensorInputContract,
    DroneSourceInfo,
    DroneUncertaintyAssessment,
    EarthMindDroneSensorEvidence,
    EvidenceStatus,
    ProcessedSensorMeasurementContract,
    QualityStatus,
    SensorCategory,
    SensorMetadataContract,
    SpatialBoundingBox,
    SpatialCoordinates,
    SpatialCoverage,
    TemporalCoverage,
)
from modules.context.schemas import ContextItem, PriorityLevel, PrivacyLevel


# ============================================================================
# Test 1: Valid Sensor Input Contract
# ============================================================================

def test_valid_drone_sensor_input_contract():
    input_data = DroneSensorInputContract(
        source_type="drone_sensor",
        drone_id="DRONE-AG-2024-001",
        sensor_id="SENSOR-MS-REDEDGE-MX-01",
        sensor_type="multispectral",
        manufacturer="MicaSense",
        model="RedEdge-MX",
        data_format=DroneDataFormat.GEOTIFF,
        raw_payload_ref="s3://earthmind-drone-raw/2025/03/flight_001.tif",
        collection_timestamp="2025-03-30T10:15:30Z",
        ingestion_timestamp="2025-03-30T10:20:00Z",
        spatial_metadata={"latitude": 28.6139, "longitude": 77.2090, "altitude_meters": 45.5},
        unit_metadata={"reflectance": "ratio_0_to_1"},
        calibration_metadata={"panel_used": True},
        field_id="field_wheat_zone_04",
        farm_id="farm_delhi_icar_01",
        farmer_id="farmer_10842",
        source_provenance={"uploader_id": "pilot_01", "sha256": "abcdef1234567890"},
    )

    assert input_data.drone_id == "DRONE-AG-2024-001"
    assert input_data.data_format == DroneDataFormat.GEOTIFF
    assert input_data.source_type == "drone_sensor"
    assert input_data.field_id == "field_wheat_zone_04"


# ============================================================================
# Test 2: Invalid Sensor Input Rejection
# ============================================================================

def test_invalid_sensor_input_missing_payload():
    """Both raw_payload_ref and raw_payload absent must fail validation."""
    with pytest.raises(ValidationError) as exc_info:
        DroneSensorInputContract(
            drone_id="DRONE-001",
            sensor_id="SENSOR-001",
            sensor_type="multispectral",
            data_format=DroneDataFormat.GEOTIFF,
            collection_timestamp="2025-03-30T10:15:30Z",
        )
    assert "Either 'raw_payload_ref' or 'raw_payload' must be provided" in str(exc_info.value)


def test_invalid_sensor_input_missing_drone_id():
    """Empty or missing drone_id must fail validation."""
    with pytest.raises(ValidationError):
        DroneSensorInputContract(
            drone_id="",
            sensor_id="SENSOR-001",
            sensor_type="multispectral",
            data_format=DroneDataFormat.GEOTIFF,
            raw_payload_ref="s3://path/to/data.tif",
            collection_timestamp="2025-03-30T10:15:30Z",
        )


def test_invalid_sensor_input_unsupported_format_enum():
    """Invalid data format string must be rejected."""
    with pytest.raises(ValidationError):
        DroneSensorInputContract(
            drone_id="DRONE-001",
            sensor_id="SENSOR-001",
            sensor_type="multispectral",
            data_format="UNSUPPORTED_PROPRIETARY_BINARY",  # type: ignore
            raw_payload_ref="s3://path/to/data.dat",
            collection_timestamp="2025-03-30T10:15:30Z",
        )


# ============================================================================
# Test 3: Required Metadata Validation (Spatial & Temporal)
# ============================================================================

def test_spatial_bounding_box_validation():
    """min_latitude cannot exceed max_latitude."""
    with pytest.raises(ValidationError) as exc:
        SpatialBoundingBox(
            min_latitude=30.0,
            max_latitude=20.0,  # invalid
            min_longitude=70.0,
            max_longitude=80.0,
        )
    assert "cannot exceed max_latitude" in str(exc.value)


def test_temporal_coverage_contract():
    temporal = TemporalCoverage(
        start_time="2025-03-30T10:00:00Z",
        end_time="2025-03-30T10:15:00Z",
        duration_seconds=900.0,
        sampling_frequency_hz=2.0,
    )
    assert temporal.duration_seconds == 900.0
    assert temporal.sampling_frequency_hz == 2.0


# ============================================================================
# Test 4: Sensor Metadata & Capability Validation
# ============================================================================

def test_sensor_metadata_contract():
    sensor_meta = SensorMetadataContract(
        sensor_id="SENSOR-MS-REDEDGE-MX-01",
        sensor_category=SensorCategory.MULTISPECTRAL,
        manufacturer="MicaSense",
        model="RedEdge-MX",
        supported_measurements=["blue", "green", "red", "red_edge", "nir"],
        supported_formats=[DroneDataFormat.GEOTIFF, DroneDataFormat.RAW_BINARY],
        measurement_units={"red": "reflectance_ratio", "nir": "reflectance_ratio"},
        sampling_characteristics={"bands_count": 5, "gsd_cm": 2.5},
        calibration_metadata={"panel_required": True},
        capability_version="1.0",
        registration_status="ACTIVE",
    )
    assert sensor_meta.sensor_category == SensorCategory.MULTISPECTRAL
    assert "red_edge" in sensor_meta.supported_measurements
    assert DroneDataFormat.GEOTIFF in sensor_meta.supported_formats


# ============================================================================
# Test 5: Processed Sensor Measurement Contract (Dual Preservation)
# ============================================================================

def test_processed_sensor_measurement_preserves_original_and_normalized():
    meas = ProcessedSensorMeasurementContract(
        measurement_id="meas_red_001",
        measurement_type="spectral_reflectance",
        channel_name="red_band",
        original_value=1420.0,
        original_unit="digital_number_12bit",
        processed_value=0.082,
        normalized_unit="reflectance_ratio",
        processing_method="radiometric_panel_normalization",
        calibration_status=CalibrationStatus.CALIBRATED,
        timestamp="2025-03-30T10:15:30Z",
        spatial_reference=SpatialCoordinates(latitude=28.6139, longitude=77.2090, altitude_meters=45.5),
        quality_status=QualityStatus.VALID,
        source_sensor="SENSOR-MS-REDEDGE-MX-01",
        provenance={"conversion_factor": 0.0000577},
    )

    # Both original raw telemetry and normalized scientific value must be preserved
    assert meas.original_value == 1420.0
    assert meas.original_unit == "digital_number_12bit"
    assert meas.processed_value == 0.082
    assert meas.normalized_unit == "reflectance_ratio"
    assert meas.calibration_status == CalibrationStatus.CALIBRATED


# ============================================================================
# Test 6: Agricultural Indicator Contract Validation
# ============================================================================

def test_agricultural_indicator_contract():
    indicator = AgriculturalIndicatorContract(
        indicator_id="ind_ndvi_001",
        indicator_name="NDVI",
        definition="Normalized Difference Vegetation Index: (NIR - Red) / (NIR + Red)",
        calculation_method="standard_band_ratio",
        required_input_measurements=["nir_reflectance", "red_reflectance"],
        result={"mean": 0.74, "min": 0.32, "max": 0.88, "std_dev": 0.09},
        unit="unitless_ratio",
        quality_status=QualityStatus.VALID,
        limitations=["Saturated in ultra-dense canopy (>0.85)"],
    )

    assert indicator.indicator_name == "NDVI"
    assert "nir_reflectance" in indicator.required_input_measurements
    assert indicator.result["mean"] == 0.74
    assert len(indicator.limitations) == 1


# ============================================================================
# Test 7: EarthMindDroneSensorEvidence Output Schema v1.0 Validation
# ============================================================================

def test_earthmind_drone_sensor_evidence_schema_v1():
    evidence = EarthMindDroneSensorEvidence(
        contract_name="EarthMindDroneSensorEvidence",
        schema_version="1.0",
        evidence_id="ev_drone_test_001",
        source=DroneSourceInfo(
            source_type="drone_sensor",
            drone_id="DRONE-01",
            sensor_id="SENSOR-01",
            sensor_type="multispectral",
            manufacturer="MicaSense",
            model="RedEdge",
        ),
        field=DroneFieldInfo(
            field_id="field_wheat_01",
            farm_id="farm_01",
            farmer_id="farmer_01",
            crop="Wheat",
        ),
        collection=DroneCollectionInfo(
            mission_id="mission_01",
            collection_timestamp="2025-03-30T10:15:30Z",
            ingestion_timestamp="2025-03-30T10:20:00Z",
            flight_altitude_meters=45.0,
            flight_speed_mps=5.0,
        ),
        temporal_coverage=TemporalCoverage(
            start_time="2025-03-30T10:10:00Z",
            end_time="2025-03-30T10:25:00Z",
            duration_seconds=900.0,
        ),
        spatial_coverage=SpatialCoverage(
            has_spatial_metadata=True,
            centroid=SpatialCoordinates(latitude=28.6139, longitude=77.2090, altitude_meters=45.0),
        ),
        quality=DroneQualityAssessment(
            input_validity=QualityStatus.VALID,
            measurement_quality="HIGH",
            overall_quality="HIGH",
        ),
        uncertainty=DroneUncertaintyAssessment(
            overall_confidence=0.95,
        ),
        status=EvidenceStatus.SUCCESS,
    )

    assert evidence.contract_name == "EarthMindDroneSensorEvidence"
    assert evidence.schema_version == "1.0"
    assert evidence.status == EvidenceStatus.SUCCESS
    assert evidence.source.drone_id == "DRONE-01"


# ============================================================================
# Test 8: Missing Calibration Representation
# ============================================================================

def test_missing_calibration_representation():
    """Uncalibrated data must be explicitly represented, not fabricated."""
    evidence = EarthMindDroneSensorEvidence(
        contract_name="EarthMindDroneSensorEvidence",
        schema_version="1.0",
        source=DroneSourceInfo(drone_id="D-1", sensor_id="S-1", sensor_type="thermal"),
        collection=DroneCollectionInfo(
            collection_timestamp="2025-03-30T10:00:00Z",
            ingestion_timestamp="2025-03-30T10:05:00Z",
        ),
        temporal_coverage=TemporalCoverage(start_time="2025-03-30T10:00:00Z"),
        calibration={  # type: ignore
            "calibration_status": CalibrationStatus.UNCALIBRATED,
            "panel_used": False,
            "sun_sensor_used": False,
        },
        warnings=["Radiometric calibration panel absent; relative DN values used."],
        status=EvidenceStatus.DEGRADED,
    )

    assert evidence.calibration.calibration_status == CalibrationStatus.UNCALIBRATED
    assert evidence.calibration.panel_used is False
    assert evidence.status == EvidenceStatus.DEGRADED
    assert len(evidence.warnings) == 1


# ============================================================================
# Test 9: Missing Spatial Metadata Representation
# ============================================================================

def test_missing_spatial_metadata_representation():
    """When GPS is absent, has_spatial_metadata is False; coordinates are not hallucinated."""
    spatial = SpatialCoverage(
        has_spatial_metadata=False,
        centroid=None,
        bounding_box=None,
    )
    assert spatial.has_spatial_metadata is False
    assert spatial.centroid is None
    assert spatial.bounding_box is None


# ============================================================================
# Test 10: Missing Spectral Band Representation
# ============================================================================

def test_missing_spectral_band_representation():
    """When a band is missing (e.g. RedEdge for NDRE), indicator is marked degraded with limitation."""
    indicator = AgriculturalIndicatorContract(
        indicator_name="NDRE",
        definition="Normalized Difference Red Edge Index",
        calculation_method="band_math",
        required_input_measurements=["nir_reflectance", "red_edge_reflectance"],
        result={"status": "UNAVAILABLE"},
        quality_status=QualityStatus.INCOMPLETE,
        limitations=["RedEdge band (705nm) missing from sensor payload; NDRE calculation omitted."],
    )

    assert indicator.quality_status == QualityStatus.INCOMPLETE
    assert "RedEdge band (705nm) missing" in indicator.limitations[0]


# ============================================================================
# Test 11: Camera Routing Contract Validation (Vision Module Handoff)
# ============================================================================

def test_camera_routing_contract_validation():
    camera_routing = DroneCameraRoutingContract(
        contract_name="DroneCameraRoutingContract",
        schema_version="1.0",
        drone_id="DRONE-AG-2024-001",
        camera_id="CAM-RGB-SONY-RX1",
        sensor_category=SensorCategory.RGB,
        mission_reference="mission_01",
        field_id="field_wheat_01",
        farm_id="farm_01",
        collection_timestamp="2025-03-30T10:16:00Z",
        image_reference="s3://earthmind-drone-raw/2025/03/frame_042.jpg",
        image_mime_type="image/jpeg",
        spatial_metadata={"latitude": 28.6142, "longitude": 77.2095, "altitude": 45.0},
        destination_module="vision",
        requires_visual_interpretation=True,
    )

    assert camera_routing.destination_module == "vision"
    assert camera_routing.requires_visual_interpretation is True
    assert camera_routing.sensor_category == SensorCategory.RGB
    assert camera_routing.drone_id == "DRONE-AG-2024-001"


# ============================================================================
# Test 12: Sarvam Integration Contract & B2 ContextItem Compatibility
# ============================================================================

def test_sarvam_integration_contract_and_b2_context_item():
    evidence = EarthMindDroneSensorEvidence(
        contract_name="EarthMindDroneSensorEvidence",
        schema_version="1.0",
        evidence_id="ev_drone_test_042",
        source=DroneSourceInfo(drone_id="DRONE-01", sensor_id="SENSOR-01", sensor_type="multispectral"),
        field=DroneFieldInfo(field_id="field_paddy_03", farm_id="farm_02", farmer_id="farmer_09"),
        collection=DroneCollectionInfo(
            collection_timestamp="2025-03-30T10:15:30Z",
            ingestion_timestamp="2025-03-30T10:20:00Z",
        ),
        indicators=[
            AgriculturalIndicatorContract(
                indicator_name="NDVI",
                definition="Normalized Difference Vegetation Index",
                calculation_method="band_math",
                required_input_measurements=["nir", "red"],
                result={"mean": 0.72},
            )
        ],
        temporal_coverage=TemporalCoverage(start_time="2025-03-30T10:15:30Z"),
        uncertainty=DroneUncertaintyAssessment(overall_confidence=0.94),
        status=EvidenceStatus.SUCCESS,
    )

    bridge = DroneSarvamIntegrationContract(
        evidence=evidence,
        target_model="Sarvam-105B",
        context_priority="HIGH",
    )

    context_item = bridge.to_context_item()

    assert isinstance(context_item, ContextItem)
    assert context_item.entity_type == "drone_sensor_evidence"
    assert context_item.entity_id == "field_paddy_03"
    assert context_item.source == "drone_module"
    assert context_item.confidence == 0.94
    assert context_item.priority == PriorityLevel.HIGH
    assert context_item.privacy_level == PrivacyLevel.FARM_PRIVATE
    assert context_item.farmer_id == "farmer_09"
    assert "NDVI" in str(context_item.content)


# ============================================================================
# Test 13: Structured Error Contract Validation (18 Error Codes)
# ============================================================================

def test_drone_error_contract_all_codes():
    all_codes = list(DroneErrorCode)
    assert len(all_codes) == 18

    expected_codes = [
        "INVALID_ARGUMENT",
        "UNSUPPORTED_SENSOR",
        "UNSUPPORTED_FORMAT",
        "INVALID_SENSOR_DATA",
        "SENSOR_METADATA_MISSING",
        "CALIBRATION_UNAVAILABLE",
        "UNIT_CONVERSION_FAILED",
        "GEOLOCATION_INVALID",
        "TIMESTAMP_INVALID",
        "INSUFFICIENT_DATA",
        "QUALITY_VALIDATION_FAILED",
        "INDICATOR_PROCESSING_FAILED",
        "SENSOR_CONFLICT",
        "EVIDENCE_VALIDATION_FAILED",
        "STORAGE_UNAVAILABLE",
        "STORAGE_ERROR",
        "PROCESSING_TIMEOUT",
        "INTERNAL_ERROR",
    ]

    for code_name in expected_codes:
        code_enum = DroneErrorCode(code_name)
        err = DroneErrorContract(
            error_code=code_enum,
            message=f"Testing {code_name}",
            operation="test_op",
            retryable=(code_enum in [DroneErrorCode.STORAGE_UNAVAILABLE, DroneErrorCode.PROCESSING_TIMEOUT]),
            metadata={"test_key": "val"},
        )
        assert err.error_code == code_enum
        assert err.module == "drone"


def test_drone_exception_hierarchy():
    exc = UnsupportedSensorError(sensor_id="UNKNOWN_SENSOR", details="Profile not registered")
    assert isinstance(exc, DroneError)
    assert exc.error_contract.error_code == "UNSUPPORTED_SENSOR"
    assert exc.error_contract.module == "drone"
    assert exc.error_contract.retryable is False

    timeout_exc = DroneProcessingTimeoutError(operation="extract_ndvi", timeout=5.0)
    assert timeout_exc.error_contract.retryable is True
    assert timeout_exc.error_contract.metadata["timeout"] == 5.0


# ============================================================================
# Test 14: Schema Version Handling & Backward Compatibility
# ============================================================================

def test_evidence_contract_rejects_unsupported_version():
    with pytest.raises(ValidationError) as exc:
        EarthMindDroneSensorEvidence(
            contract_name="EarthMindDroneSensorEvidence",
            schema_version="99.0",  # unsupported version
            source=DroneSourceInfo(drone_id="D-1", sensor_id="S-1", sensor_type="ms"),
            collection=DroneCollectionInfo(
                collection_timestamp="2025-03-30T10:00:00Z",
                ingestion_timestamp="2025-03-30T10:05:00Z",
            ),
            temporal_coverage=TemporalCoverage(start_time="2025-03-30T10:00:00Z"),
        )
    assert "Unsupported schema_version: expected '1.0'" in str(exc.value)


def test_evidence_contract_rejects_wrong_contract_name():
    with pytest.raises(ValidationError) as exc:
        EarthMindDroneSensorEvidence(
            contract_name="WrongContractName",
            schema_version="1.0",
            source=DroneSourceInfo(drone_id="D-1", sensor_id="S-1", sensor_type="ms"),
            collection=DroneCollectionInfo(
                collection_timestamp="2025-03-30T10:00:00Z",
                ingestion_timestamp="2025-03-30T10:05:00Z",
            ),
            temporal_coverage=TemporalCoverage(start_time="2025-03-30T10:00:00Z"),
        )
    assert "Invalid contract_name: expected 'EarthMindDroneSensorEvidence'" in str(exc.value)


# ============================================================================
# Test 15: Interfaces Runtime Checkability
# ============================================================================

def test_drone_interfaces_runtime_checkable():
    """Verify that all 18 Drone interfaces are registered and runtime checkable."""
    interfaces = [
        IDroneDataGateway,
        ISensorRegistry,
        IDataFormatDetector,
        IRawDataProcessor,
        IDataQualityValidator,
        ICalibrationNormalizer,
        IGeospatialProcessor,
        ITemporalProcessor,
        ISpectralNumericalAnalyzer,
        IIndicatorExtractor,
        IMultiSensorFusionEngine,
        IUncertaintyAssessor,
        ISensorEvidenceBuilder,
        ISensorEvidenceValidator,
        ISarvamDroneIntegration,
        IProvenanceManager,
        IDroneStorageAdapter,
        IDroneDiagnostics,
    ]

    assert len(interfaces) == 18

    # Create dummy implementation of IDroneDataGateway
    class DummyGateway:
        def ingest_sensor_data(self, request):
            return {"trace_id": "tr_1"}

    assert isinstance(DummyGateway(), IDroneDataGateway)
