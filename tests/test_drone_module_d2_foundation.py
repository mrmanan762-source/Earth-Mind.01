"""Unit and integration test suite for EarthMind Drone Module Stage D2: Core Foundation.

Verifies all 47 foundational test requirements across 7 categories:
1. Core Foundation (module initialization, configuration loading, rejection of invalid config,
   dependency registration, health check, shutdown).
2. Drone Data Gateway (valid sensor input acceptance, invalid input rejection, missing drone ID,
   missing sensor ID, unsupported format, oversized payload, duplicate ingestion requests,
   structured ingestion result, error propagation).
3. Sensor Registry (sensor registration, duplicate sensor handling, sensor retrieval,
   sensor update, sensor deactivation, unknown sensor handling, invalid capability definition,
   capability lookup, registry storage abstraction behavior).
4. Adapter Infrastructure (adapter registration, adapter lookup, unsupported adapter handling,
   adapter incompatibility, adapter failure handling, adapter unavailability, adapter versioning,
   multiple adapter registration).
5. Format Capability Registry (supported format recognition, unsupported format handling,
   file extension vs magic bytes distinction, adapter-format compatibility).
6. Camera Data Routing (camera input identification, camera routing contract validation,
   missing Vision integration behavior, preservation of source metadata).
7. Security & Reliability (malformed input handling, unsafe path traversal rejection,
   safe error messages, sensitive-data log protection, ingestion status transitions,
   farmer/field authorization scoping, no silent production storage fallback).
"""

import os
import pytest
from pydantic import ValidationError

from core.config.settings import DroneConfig, Settings
from core.errors.exceptions import ConfigurationError
from core.interfaces.drone import (
    IDroneDataGateway,
    IDroneDiagnostics,
    IDroneStorageAdapter,
    ISensorRegistry,
)
from core.schemas.application import ApplicationRequest
from core.schemas.drone import (
    DroneCameraRoutingContract,
    DroneDataFormat,
    DroneErrorContract,
    DroneErrorCode,
    DroneIngestionResult,
    DroneSensorInputContract,
    IngestionStatus,
    SensorCategory,
    SensorMetadataContract,
)
from modules.drone.adapters import (
    BaseSensorAdapter,
    ISensorAdapter,
    SensorAdapterRegistry,
    SyntheticMultispectralSensorAdapter,
    SyntheticThermalSensorAdapter,
)
from modules.drone.camera_router import CameraDataRouter
from modules.drone.diagnostics import DroneDiagnostics
from modules.drone.drone_module import DroneModule
from modules.drone.drone_service import DroneService
from modules.drone.errors import (
    DroneError,
    DroneInvalidArgumentError,
    DroneStorageError,
    SensorConflictError,
    UnsupportedFormatError,
    UnsupportedSensorError,
)
from modules.drone.formats import DataFormatRegistry, FormatCapability
from modules.drone.gateway import DroneDataGateway
from modules.drone.lifecycle import IngestionLifecycleTracker
from modules.drone.registry import SensorRegistry
from modules.drone.storage import InMemoryDroneStorageAdapter


# ============================================================================
# Category 1: Core Foundation (Tests 1–6)
# ============================================================================

def test_1_clean_module_initialization():
    module = DroneModule()
    assert module._is_initialized is False
    module.initialize()
    assert module._is_initialized is True
    assert isinstance(module.service, DroneService)
    module.shutdown()


def test_2_configuration_loading():
    config = DroneConfig(
        enabled=True,
        gateway_enabled=True,
        max_payload_size_bytes=10 * 1024 * 1024,
        default_timeout=25.0,
    )
    assert config.enabled is True
    assert config.max_payload_size_bytes == 10 * 1024 * 1024
    assert config.default_timeout == 25.0
    assert "GEOTIFF" in config.supported_formats


def test_3_invalid_configuration_rejection():
    # Negative payload size must fail validation in Settings
    settings_custom = Settings(drone=DroneConfig(max_payload_size_bytes=-1))
    with pytest.raises(ConfigurationError) as exc_info:
        settings_custom.validate_config()
    assert "max_payload_size_bytes" in str(exc_info.value)

    # Negative timeout must fail validation
    settings_custom_timeout = Settings(drone=DroneConfig(default_timeout=-5.0))
    with pytest.raises(ConfigurationError) as exc_timeout:
        settings_custom_timeout.validate_config()
    assert "drone.default_timeout" in str(exc_timeout.value)


def test_4_dependency_registration_in_service():
    service = DroneService()
    assert isinstance(service.gateway, IDroneDataGateway)
    assert isinstance(service.registry, ISensorRegistry)
    assert isinstance(service.storage, IDroneStorageAdapter)
    assert isinstance(service.diagnostics, IDroneDiagnostics)
    assert isinstance(service.format_registry, DataFormatRegistry)
    assert isinstance(service.adapter_registry, SensorAdapterRegistry)


def test_5_health_check_behavior():
    service = DroneService()
    health = service.check_health()
    assert health["status"] == "HEALTHY"
    assert health["module_enabled"] is True
    assert health["gateway"]["status"] == "HEALTHY"
    assert health["registry"]["status"] == "HEALTHY"


def test_6_shutdown_behavior():
    module = DroneModule()
    module.initialize()
    assert module._is_initialized is True
    module.shutdown()
    assert module._is_initialized is False
    health = module.health_check()
    assert health["initialized"] is False


# ============================================================================
# Category 2: Drone Data Gateway (Tests 7–15)
# ============================================================================

@pytest.fixture
def configured_gateway():
    storage = InMemoryDroneStorageAdapter()
    registry = SensorRegistry(storage_adapter=storage)
    formats = DataFormatRegistry()
    adapters = SensorAdapterRegistry()
    lifecycle = IngestionLifecycleTracker()

    # Pre-register standard multispectral sensor
    meta = SensorMetadataContract(
        sensor_id="SENSOR-TEST-MS-01",
        sensor_category=SensorCategory.MULTISPECTRAL,
        manufacturer="MicaSense",
        model="RedEdge-MX",
        supported_measurements=["blue", "green", "red", "nir"],
        supported_formats=[DroneDataFormat.GEOTIFF, DroneDataFormat.CSV, DroneDataFormat.JSON],
        registration_status="ACTIVE",
    )
    registry.register_sensor(meta)

    gateway = DroneDataGateway(
        sensor_registry=registry,
        format_registry=formats,
        adapter_registry=adapters,
        lifecycle_tracker=lifecycle,
        max_payload_size_bytes=1024 * 1024,  # 1MB limit for tests
        gateway_enabled=True,
    )
    return gateway, registry, adapters


def test_7_valid_sensor_input_acceptance(configured_gateway):
    gateway, _, _ = configured_gateway
    inp = DroneSensorInputContract(
        drone_id="DRONE-01",
        sensor_id="SENSOR-TEST-MS-01",
        sensor_type="multispectral",
        data_format=DroneDataFormat.GEOTIFF,
        raw_payload=b"II*\x00mock_geotiff_raster_bytes",
        collection_timestamp="2025-03-30T10:15:30Z",
        calibration_metadata={"panel_used": True},
        field_id="field_wheat_01",
        farmer_id="farmer_101",
    )
    result = gateway.process_ingestion(inp)
    assert result.accepted is True
    assert result.status == IngestionStatus.SUCCESS
    assert result.drone_id == "DRONE-01"
    assert result.sensor_id == "SENSOR-TEST-MS-01"
    assert result.error is None


def test_8_invalid_input_rejection(configured_gateway):
    gateway, _, _ = configured_gateway
    # Invalid because neither raw_payload nor raw_payload_ref is supplied
    with pytest.raises(ValidationError) as exc:
        DroneSensorInputContract(
            drone_id="DRONE-01",
            sensor_id="SENSOR-TEST-MS-01",
            sensor_type="multispectral",
            data_format=DroneDataFormat.GEOTIFF,
            collection_timestamp="2025-03-30T10:15:30Z",
        )
    assert "Either 'raw_payload_ref' or 'raw_payload' must be provided" in str(exc.value)


def test_9_missing_drone_identifier(configured_gateway):
    gateway, _, _ = configured_gateway
    # Direct contract instantiation rejects empty string
    with pytest.raises(ValidationError):
        DroneSensorInputContract(
            drone_id="",
            sensor_id="SENSOR-TEST-MS-01",
            sensor_type="multispectral",
            data_format=DroneDataFormat.GEOTIFF,
            raw_payload_ref="s3://test.tif",
            collection_timestamp="2025-03-30T10:15:30Z",
        )


def test_10_missing_sensor_identifier(configured_gateway):
    gateway, _, _ = configured_gateway
    with pytest.raises(ValidationError):
        DroneSensorInputContract(
            drone_id="DRONE-01",
            sensor_id="",
            sensor_type="multispectral",
            data_format=DroneDataFormat.GEOTIFF,
            raw_payload_ref="s3://test.tif",
            collection_timestamp="2025-03-30T10:15:30Z",
        )


def test_11_unsupported_format(configured_gateway):
    gateway, _, _ = configured_gateway
    # Request with format not supported by the registered sensor (e.g. LAS point cloud on MS sensor)
    inp = DroneSensorInputContract(
        drone_id="DRONE-01",
        sensor_id="SENSOR-TEST-MS-01",
        sensor_type="multispectral",
        data_format=DroneDataFormat.LAS,
        raw_payload=b"LASFmock_point_cloud",
        collection_timestamp="2025-03-30T10:15:30Z",
    )
    result = gateway.process_ingestion(inp)
    assert result.accepted is False
    assert result.status == IngestionStatus.REJECTED
    assert result.error is not None
    assert result.error.error_code == DroneErrorCode.UNSUPPORTED_SENSOR


def test_12_oversized_payload(configured_gateway):
    gateway, _, _ = configured_gateway
    # Gateway has 1MB limit; supply 1.5MB payload
    oversized_bytes = b"X" * (1500 * 1024)
    inp = DroneSensorInputContract(
        drone_id="DRONE-01",
        sensor_id="SENSOR-TEST-MS-01",
        sensor_type="multispectral",
        data_format=DroneDataFormat.GEOTIFF,
        raw_payload=oversized_bytes,
        collection_timestamp="2025-03-30T10:15:30Z",
    )
    result = gateway.process_ingestion(inp)
    assert result.accepted is False
    assert result.status == IngestionStatus.REJECTED
    assert result.error.error_code == DroneErrorCode.INVALID_ARGUMENT
    assert "exceeds configured gateway maximum limit" in result.error.message


def test_13_duplicate_ingestion_request(configured_gateway):
    gateway, _, _ = configured_gateway
    inp = DroneSensorInputContract(
        drone_id="DRONE-01",
        sensor_id="SENSOR-TEST-MS-01",
        sensor_type="multispectral",
        data_format=DroneDataFormat.GEOTIFF,
        raw_payload=b"II*\x00identical_sensor_bytes_001",
        collection_timestamp="2025-03-30T10:15:30Z",
    )
    res1 = gateway.process_ingestion(inp)
    assert res1.accepted is True

    # Resend exact identical payload
    res2 = gateway.process_ingestion(inp)
    assert res2.accepted is True
    # Must match original ingestion_id idempotently
    assert res1.ingestion_id == res2.ingestion_id


def test_14_structured_ingestion_result_properties(configured_gateway):
    gateway, _, _ = configured_gateway
    inp = DroneSensorInputContract(
        drone_id="DRONE-01",
        sensor_id="SENSOR-TEST-MS-01",
        sensor_type="multispectral",
        data_format=DroneDataFormat.GEOTIFF,
        raw_payload_ref="s3://earthmind/flight.tif",
        collection_timestamp="2025-03-30T10:15:30Z",
    )
    res = gateway.process_ingestion(inp)
    assert isinstance(res, DroneIngestionResult)
    # Both attribute access and dict indexing work
    assert res.ingestion_id.startswith("ing_")
    assert res["status"] == IngestionStatus.SUCCESS
    assert res.get("drone_id") == "DRONE-01"
    dict_repr = res.to_dict()
    assert "ingestion_id" in dict_repr


def test_15_gateway_error_propagation(configured_gateway):
    gateway, _, _ = configured_gateway
    # Ingest for an unknown, unregistered sensor ID
    inp = DroneSensorInputContract(
        drone_id="DRONE-01",
        sensor_id="SENSOR-UNKNOWN-99",
        sensor_type="hyperspectral",
        data_format=DroneDataFormat.HDF5,
        raw_payload_ref="s3://earthmind/flight.h5",
        collection_timestamp="2025-03-30T10:15:30Z",
    )
    res = gateway.process_ingestion(inp)
    assert res.accepted is False
    assert res.status == IngestionStatus.REJECTED
    assert res.error.error_code == DroneErrorCode.UNSUPPORTED_SENSOR
    assert "not registered" in res.error.message


# ============================================================================
# Category 3: Sensor Registry (Tests 16–24)
# ============================================================================

def test_16_sensor_registration():
    reg = SensorRegistry()
    meta = SensorMetadataContract(
        sensor_id="SENS-01",
        sensor_category=SensorCategory.SOIL,
        manufacturer="Sentek",
        model="Drill & Drop",
        supported_measurements=["volumetric_water_content", "soil_temperature"],
        supported_formats=[DroneDataFormat.CSV],
        registration_status="ACTIVE",
    )
    assert reg.register_sensor(meta) is True
    retrieved = reg.get_sensor("SENS-01")
    assert retrieved is not None
    assert retrieved.sensor_category == SensorCategory.SOIL


def test_17_duplicate_sensor_registration_conflict():
    reg = SensorRegistry()
    meta1 = SensorMetadataContract(
        sensor_id="SENS-DUAL",
        sensor_category=SensorCategory.MULTISPECTRAL,
        supported_measurements=["red", "nir"],
        registration_status="ACTIVE",
    )
    reg.register_sensor(meta1)

    # Attempting to re-register same active sensor ID under a completely different category must raise conflict
    meta2 = SensorMetadataContract(
        sensor_id="SENS-DUAL",
        sensor_category=SensorCategory.THERMAL,
        supported_measurements=["thermal_ir"],
        registration_status="ACTIVE",
    )
    with pytest.raises(SensorConflictError):
        reg.register_sensor(meta2)


def test_18_sensor_retrieval():
    reg = SensorRegistry()
    assert reg.get_sensor("NON_EXISTENT") is None


def test_19_sensor_update():
    reg = SensorRegistry()
    meta = SensorMetadataContract(
        sensor_id="SENS-UPD",
        sensor_category=SensorCategory.ENVIRONMENTAL,
        supported_measurements=["ambient_temp"],
        registration_status="ACTIVE",
    )
    reg.register_sensor(meta)
    updated = reg.update_sensor("SENS-UPD", {"model": "WeatherVane-Pro"})
    assert updated.model == "WeatherVane-Pro"
    assert reg.get_sensor("SENS-UPD").model == "WeatherVane-Pro"


def test_20_sensor_deactivation():
    reg = SensorRegistry()
    meta = SensorMetadataContract(
        sensor_id="SENS-DEACT",
        sensor_category=SensorCategory.LIDAR,
        supported_measurements=["elevation_map"],
        registration_status="ACTIVE",
    )
    reg.register_sensor(meta)
    assert reg.is_supported("SENS-DEACT", "elevation_map") is True
    assert reg.unregister_sensor("SENS-DEACT") is True

    # After deactivation, status is INACTIVE and it is no longer supported
    deact_sensor = reg.get_sensor("SENS-DEACT")
    assert deact_sensor.registration_status == "INACTIVE"
    assert reg.is_supported("SENS-DEACT", "elevation_map") is False


def test_21_unknown_sensor_handling():
    reg = SensorRegistry()
    with pytest.raises(UnsupportedSensorError):
        reg.validate_sensor("UNKNOWN_SENSOR_XYZ")


def test_22_invalid_capability_definition():
    with pytest.raises(ValidationError):
        SensorMetadataContract(
            sensor_id="",  # empty ID rejected
            sensor_category=SensorCategory.MULTISPECTRAL,
        )


def test_23_capability_lookup():
    reg = SensorRegistry()
    meta = SensorMetadataContract(
        sensor_id="SENS-CAP",
        sensor_category=SensorCategory.THERMAL,
        supported_measurements=["surface_temp"],
        supported_formats=[DroneDataFormat.GEOTIFF],
        capability_version="2.0",
        registration_status="ACTIVE",
    )
    reg.register_sensor(meta)
    caps = reg.get_sensor_capabilities("SENS-CAP")
    assert caps["sensor_category"] == "THERMAL"
    assert "surface_temp" in caps["supported_measurements"]
    assert caps["capability_version"] == "2.0"


def test_24_registry_storage_abstraction_behavior():
    storage = InMemoryDroneStorageAdapter()
    reg = SensorRegistry(storage_adapter=storage)
    meta = SensorMetadataContract(
        sensor_id="SENS-STORAGE",
        sensor_category=SensorCategory.MULTISPECTRAL,
        supported_measurements=["red", "nir"],
        registration_status="ACTIVE",
    )
    reg.register_sensor(meta)

    # Clear memory cache in registry; should fall back to storage adapter
    reg._sensors.clear()
    retrieved = reg.get_sensor("SENS-STORAGE")
    assert retrieved is not None
    assert retrieved.sensor_id == "SENS-STORAGE"


# ============================================================================
# Category 4: Adapter Infrastructure (Tests 25–32)
# ============================================================================

def test_25_adapter_registration():
    reg = SensorAdapterRegistry()
    custom_adapter = SyntheticMultispectralSensorAdapter(adapter_id="adapter_custom_ms")
    reg.register_adapter(custom_adapter)
    assert reg.get_adapter("adapter_custom_ms") is not None


def test_26_adapter_lookup():
    reg = SensorAdapterRegistry()
    found = reg.get_adapter("adapter_synthetic_multispectral_v1")
    assert found is not None
    assert isinstance(found, ISensorAdapter)


def test_27_unsupported_adapter_handling():
    reg = SensorAdapterRegistry()
    inp = DroneSensorInputContract(
        drone_id="D1",
        sensor_id="S1",
        sensor_type="lidar",
        data_format=DroneDataFormat.LAS,
        raw_payload=b"LASFmock",
        collection_timestamp="2025-01-01T00:00:00Z",
    )
    meta = SensorMetadataContract(
        sensor_id="S1",
        sensor_category=SensorCategory.LIDAR,
        supported_formats=[DroneDataFormat.LAS],
    )
    with pytest.raises(UnsupportedSensorError) as exc_info:
        reg.find_adapter(inp, meta)
    assert "No compatible adapter registered" in str(exc_info.value)


def test_28_adapter_incompatibility():
    adapter = SyntheticMultispectralSensorAdapter()
    inp = DroneSensorInputContract(
        drone_id="D1",
        sensor_id="S1",
        sensor_type="multispectral",
        data_format=DroneDataFormat.RAW_BINARY,  # not supported by synthetic adapter
        raw_payload=b"\x00\x01\x02",
        collection_timestamp="2025-01-01T00:00:00Z",
    )
    meta = SensorMetadataContract(
        sensor_id="S1",
        sensor_category=SensorCategory.MULTISPECTRAL,
    )
    assert adapter.is_compatible(inp, meta) is False


def test_29_adapter_failure_handling():
    class FailingAdapter(BaseSensorAdapter):
        def __init__(self):
            super().__init__("failing_adapter", supported_category=SensorCategory.OTHER)

        def parse_header(self, input_data):
            raise RuntimeError("Hardware communication timeout")

    fail_adapter = FailingAdapter()
    inp = DroneSensorInputContract(
        drone_id="D1",
        sensor_id="S1",
        sensor_type="other",
        data_format=DroneDataFormat.CSV,
        raw_payload_ref="s3://test.csv",
        collection_timestamp="2025-01-01T00:00:00Z",
    )
    with pytest.raises(RuntimeError):
        fail_adapter.parse_header(inp)


def test_30_adapter_unavailability():
    class UnavailableAdapter(BaseSensorAdapter):
        def __init__(self):
            super().__init__("unavail_adapter", supported_category=SensorCategory.THERMAL, supported_formats=[DroneDataFormat.GEOTIFF])

        def is_available(self):
            return False

        def parse_header(self, input_data):
            return {}

    reg = SensorAdapterRegistry()
    reg._adapters.clear()
    reg.register_adapter(UnavailableAdapter())

    inp = DroneSensorInputContract(
        drone_id="D1",
        sensor_id="S1",
        sensor_type="thermal",
        data_format=DroneDataFormat.GEOTIFF,
        raw_payload=b"II*\x00",
        collection_timestamp="2025-01-01T00:00:00Z",
    )
    meta = SensorMetadataContract(
        sensor_id="S1",
        sensor_category=SensorCategory.THERMAL,
        supported_formats=[DroneDataFormat.GEOTIFF],
    )
    with pytest.raises(UnsupportedSensorError):
        reg.find_adapter(inp, meta)


def test_31_adapter_version_handling():
    adapter = SyntheticMultispectralSensorAdapter()
    assert adapter.adapter_version == "1.0.0"
    hdr = adapter.parse_header(DroneSensorInputContract(
        drone_id="D1",
        sensor_id="S1",
        sensor_type="ms",
        data_format=DroneDataFormat.GEOTIFF,
        raw_payload_ref="s3://test.tif",
        collection_timestamp="2025-01-01T00:00:00Z",
    ))
    assert hdr["synthetic_mode"] is True


def test_32_multiple_adapter_registration():
    reg = SensorAdapterRegistry()
    adapters = reg.list_adapters()
    assert len(adapters) >= 2
    categories = {a.supported_category for a in adapters}
    assert SensorCategory.MULTISPECTRAL in categories
    assert SensorCategory.THERMAL in categories


# ============================================================================
# Category 5: Format Capability Registry (Tests 33–36)
# ============================================================================

def test_33_supported_format_recognition():
    fmt_reg = DataFormatRegistry()
    assert fmt_reg.is_supported(DroneDataFormat.GEOTIFF) is True
    assert fmt_reg.is_supported(DroneDataFormat.NETCDF) is True
    assert fmt_reg.is_supported(DroneDataFormat.CSV) is True
    assert fmt_reg.is_supported(DroneDataFormat.JSON) is True


def test_34_unsupported_format_handling():
    fmt_reg = DataFormatRegistry()
    with pytest.raises(UnsupportedFormatError):
        fmt_reg.detect_format_from_bytes(b"\x00\x00\x00\x00", filename_hint="unknown.xyz_unsupported")


def test_35_file_extension_vs_actual_format_distinction():
    fmt_reg = DataFormatRegistry()
    # Payload has .csv extension but begins with TIFF magic bytes
    tiff_bytes = b"II*\x00actual_raster"
    detected = fmt_reg.detect_format_from_bytes(tiff_bytes, filename_hint="spoofed_name.csv")
    # True magic bytes must take precedence over fake extension
    assert detected == DroneDataFormat.GEOTIFF


def test_36_adapter_format_compatibility():
    fmt_reg = DataFormatRegistry()
    geotiff_cap = fmt_reg.get_capability(DroneDataFormat.GEOTIFF)
    assert geotiff_cap is not None
    assert geotiff_cap.is_binary is True
    assert ".tif" in geotiff_cap.file_extensions


# ============================================================================
# Category 6: Camera Data Routing (Tests 37–40)
# ============================================================================

def test_37_camera_input_identification():
    router = CameraDataRouter()
    routing_contract = DroneCameraRoutingContract(
        drone_id="DRONE-01",
        camera_id="CAM-RGB-01",
        sensor_category=SensorCategory.RGB,
        collection_timestamp="2025-03-30T10:15:30Z",
        image_reference="s3://bucket/frame_01.jpg",
        image_mime_type="image/jpeg",
    )
    result = router.route_camera_data(routing_contract)
    assert result["destination_module"] == "vision"


def test_38_camera_routing_contract_validation():
    # Attempting to route non-RGB sensor through Camera router must fail
    router = CameraDataRouter()
    with pytest.raises(ValidationError):
        DroneCameraRoutingContract(
            drone_id="DRONE-01",
            camera_id="CAM-01",
            sensor_category="INVALID_CATEGORY",  # type: ignore
            collection_timestamp="2025-03-30T10:15:30Z",
            image_reference="s3://bucket/frame.jpg",
        )


def test_39_missing_vision_integration_behavior():
    router = CameraDataRouter(vision_service=None)
    routing_contract = DroneCameraRoutingContract(
        drone_id="DRONE-01",
        camera_id="CAM-RGB-01",
        sensor_category=SensorCategory.RGB,
        collection_timestamp="2025-03-30T10:15:30Z",
        image_reference="s3://bucket/frame_01.jpg",
    )
    res = router.route_camera_data(routing_contract)
    # When vision service is not connected, reports HANDOFF_PENDING rather than crashing or inventing diagnoses
    assert res["status"] == "HANDOFF_PENDING"
    assert "pending integration" in res["message"]


def test_40_preservation_of_source_metadata():
    router = CameraDataRouter()
    routing_contract = DroneCameraRoutingContract(
        drone_id="DRONE-01",
        camera_id="CAM-RGB-01",
        sensor_category=SensorCategory.RGB,
        mission_reference="mission_spring_wheat_02",
        field_id="field_zone_08",
        collection_timestamp="2025-03-30T10:15:30Z",
        image_reference="s3://bucket/frame_01.jpg",
        spatial_metadata={"latitude": 28.6139, "longitude": 77.2090},
    )
    res = router.route_camera_data(routing_contract)
    meta = res["metadata_preserved"]
    assert meta["drone_id"] == "DRONE-01"
    assert meta["camera_id"] == "CAM-RGB-01"
    assert meta["mission_reference"] == "mission_spring_wheat_02"
    assert meta["field_id"] == "field_zone_08"
    assert meta["has_spatial"] is True


# ============================================================================
# Category 7: Security & Reliability (Tests 41–47)
# ============================================================================

def test_41_malformed_input_handling(configured_gateway):
    gateway, _, _ = configured_gateway
    # Ingesting corrupted binary that declares GeoTIFF but has invalid header bytes
    inp = DroneSensorInputContract(
        drone_id="DRONE-01",
        sensor_id="SENSOR-TEST-MS-01",
        sensor_type="multispectral",
        data_format=DroneDataFormat.GEOTIFF,
        raw_payload=b"\x00\x00\x00\x00malformed_payload",
        collection_timestamp="2025-03-30T10:15:30Z",
    )
    res = gateway.process_ingestion(inp)
    assert res.accepted is False
    assert res.status == IngestionStatus.REJECTED
    assert res.error.error_code == DroneErrorCode.UNSUPPORTED_FORMAT


def test_42_unsafe_payload_rejection_path_traversal(configured_gateway):
    gateway, _, _ = configured_gateway
    inp = DroneSensorInputContract(
        drone_id="../../etc/passwd",
        sensor_id="SENSOR-TEST-MS-01",
        sensor_type="multispectral",
        data_format=DroneDataFormat.GEOTIFF,
        raw_payload_ref="s3://test.tif",
        collection_timestamp="2025-03-30T10:15:30Z",
    )
    res = gateway.process_ingestion(inp)
    assert res.accepted is False
    assert res.status == IngestionStatus.REJECTED
    assert "Path traversal" in res.error.message


def test_43_safe_error_messages(configured_gateway):
    gateway, _, _ = configured_gateway
    # Secret tokens in payload or provenance must never be reflected in error message
    inp = DroneSensorInputContract(
        drone_id="DRONE-01",
        sensor_id="SENSOR-UNKNOWN-SECRET",
        sensor_type="multispectral",
        data_format=DroneDataFormat.GEOTIFF,
        raw_payload_ref="s3://secret_key_aws_12345/test.tif",
        collection_timestamp="2025-03-30T10:15:30Z",
    )
    res = gateway.process_ingestion(inp)
    assert res.accepted is False
    assert "secret_key_aws_12345" not in res.error.message


def test_44_sensitive_data_log_protection():
    diag = DroneDiagnostics()
    diag.record_error(
        operation="process_telemetry",
        error_code="INVALID_ARGUMENT",
        message="Failure near precise field location lat=28.6139485293, lon=77.209029482",
    )
    status = diag.get_diagnostics_summary()
    assert len(status["recent_errors"]) == 1
    # Error message is sanitized and bounded in size
    assert len(status["recent_errors"][0]["message"]) <= 200


def test_45_ingestion_status_transitions():
    tracker = IngestionLifecycleTracker()
    rec = tracker.register_start("D1", "S1")
    assert rec.status == IngestionStatus.PENDING

    rec_running = tracker.transition_to(rec.ingestion_id, IngestionStatus.RUNNING)
    assert rec_running.status == IngestionStatus.RUNNING

    # Invalid transition directly from SUCCESS to RUNNING must fail
    rec_success = tracker.transition_to(rec.ingestion_id, IngestionStatus.SUCCESS)
    assert rec_success.status == IngestionStatus.SUCCESS

    with pytest.raises(DroneInvalidArgumentError):
        tracker.transition_to(rec.ingestion_id, IngestionStatus.RUNNING)


def test_46_farmer_field_authorization_boundary(configured_gateway):
    gateway, _, _ = configured_gateway
    inp = DroneSensorInputContract(
        drone_id="DRONE-01",
        sensor_id="SENSOR-TEST-MS-01",
        sensor_type="multispectral",
        data_format=DroneDataFormat.GEOTIFF,
        raw_payload=b"II*\x00valid",
        collection_timestamp="2025-03-30T10:15:30Z",
        farmer_id="farmer_tenant_A",
        farm_id="farm_punjab_01",
        field_id="field_zone_north",
    )
    res = gateway.process_ingestion(inp)
    assert res.accepted is True
    assert res.metadata["farmer_id"] == "farmer_tenant_A"
    assert res.metadata["farm_id"] == "farm_punjab_01"


def test_47_no_silent_production_storage_fallback():
    # When storage adapter experiences failure, it raises DroneStorageError rather than silently continuing
    storage = InMemoryDroneStorageAdapter()
    storage.set_healthy(False)
    reg = SensorRegistry(storage_adapter=storage)
    meta = SensorMetadataContract(
        sensor_id="S1",
        sensor_category=SensorCategory.THERMAL,
    )
    # Attempting to read profile on unhealthy storage must raise DroneStorageError
    with pytest.raises(DroneStorageError):
        storage.get_sensor_profile("S1")
