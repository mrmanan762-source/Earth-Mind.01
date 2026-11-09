"""DroneService for EarthMind Drone Module (Stage D2: Core Foundation).

Central coordinator and service facade wiring together Gateway, Registry,
Adapters, Formats, Storage, Diagnostics, and Camera Router.
"""

from typing import Any, Dict, List, Optional

from core.config.settings import DroneConfig, settings
from core.interfaces.drone import (
    IDroneDataGateway,
    IDroneDiagnostics,
    IDroneStorageAdapter,
    ISensorRegistry,
)
from core.logging.logger import get_logger
from core.schemas.drone import (
    DroneCameraRoutingContract,
    DroneIngestionResult,
    DroneSensorInputContract,
    SensorCategory,
    SensorMetadataContract,
)
from modules.drone.adapters import SensorAdapterRegistry
from modules.drone.camera_router import CameraDataRouter
from modules.drone.diagnostics import DroneDiagnostics
from modules.drone.formats import DataFormatRegistry
from modules.drone.gateway import DroneDataGateway
from modules.drone.lifecycle import IngestionLifecycleTracker
from modules.drone.processing import DroneProcessingEngine
from modules.drone.registry import SensorRegistry
from modules.drone.storage import InMemoryDroneStorageAdapter

logger = get_logger("modules.drone.service")


class DroneService:
    """Core Drone Service coordinating foundational and processing drone components."""

    def __init__(
        self,
        config: Optional[DroneConfig] = None,
        storage_adapter: Optional[IDroneStorageAdapter] = None,
        vision_service: Optional[Any] = None,
        processing_engine: Optional[DroneProcessingEngine] = None,
    ):
        self._config = config or getattr(settings, "drone", DroneConfig())
        self._storage_adapter = storage_adapter or InMemoryDroneStorageAdapter()
        self._lifecycle_tracker = IngestionLifecycleTracker()
        self._sensor_registry = SensorRegistry(storage_adapter=self._storage_adapter)
        self._format_registry = DataFormatRegistry()
        self._adapter_registry = SensorAdapterRegistry()
        self._diagnostics = DroneDiagnostics()
        self._camera_router = CameraDataRouter(vision_service=vision_service)
        self._processing_engine = processing_engine or DroneProcessingEngine()

        self._gateway = DroneDataGateway(
            sensor_registry=self._sensor_registry,
            format_registry=self._format_registry,
            adapter_registry=self._adapter_registry,
            lifecycle_tracker=self._lifecycle_tracker,
            max_payload_size_bytes=self._config.max_payload_size_bytes,
            gateway_enabled=self._config.gateway_enabled and self._config.enabled,
        )

    # ------------------------------------------------------------------------
    # Properties & Component Access
    # ------------------------------------------------------------------------
    @property
    def config(self) -> DroneConfig:
        return self._config

    @property
    def gateway(self) -> DroneDataGateway:
        return self._gateway

    @property
    def registry(self) -> SensorRegistry:
        return self._sensor_registry

    @property
    def format_registry(self) -> DataFormatRegistry:
        return self._format_registry

    @property
    def adapter_registry(self) -> SensorAdapterRegistry:
        return self._adapter_registry

    @property
    def storage(self) -> IDroneStorageAdapter:
        return self._storage_adapter

    @property
    def diagnostics(self) -> DroneDiagnostics:
        return self._diagnostics

    @property
    def camera_router(self) -> CameraDataRouter:
        return self._camera_router

    @property
    def processing_engine(self) -> DroneProcessingEngine:
        return self._processing_engine

    # ------------------------------------------------------------------------
    # Core Operations
    # ------------------------------------------------------------------------
    def process_sensor_data(
        self, input_data: DroneSensorInputContract
    ) -> Dict[str, Any]:
        """Process raw drone sensor package into normalized ProcessedSensorMeasurementContracts."""
        self._diagnostics.record_metric("processings_total", 1.0)
        sensor_profile = self._sensor_registry.get_sensor(input_data.sensor_id)
        measurements, quality_report, cal_assessment = self._processing_engine.process_sensor_input(
            input_contract=input_data,
            sensor_profile=sensor_profile,
        )
        self._diagnostics.record_metric("measurements_processed", float(len(measurements)))

        return {
            "sensor_id": input_data.sensor_id,
            "drone_id": input_data.drone_id,
            "measurements_count": len(measurements),
            "quality_status": quality_report.overall_status.value,
            "calibration_status": cal_assessment.status.value,
            "measurements": [m.model_dump() for m in measurements],
            "quality_report": quality_report.model_dump(),
            "calibration_assessment": cal_assessment.model_dump(),
        }

    # ------------------------------------------------------------------------
    # Ingestion Operations
    # ------------------------------------------------------------------------
    def ingest_sensor_data(self, input_data: DroneSensorInputContract) -> DroneIngestionResult:
        """Ingest incoming raw drone sensor package."""
        self._diagnostics.record_metric("ingestions_total", 1.0)
        result = self._gateway.process_ingestion(input_data)

        if result.accepted:
            self._diagnostics.record_metric("ingestions_accepted", 1.0)
        else:
            if result.error and result.error.error_code == "INTERNAL_ERROR":
                self._diagnostics.record_metric("ingestions_failed", 1.0)
            else:
                self._diagnostics.record_metric("ingestions_rejected", 1.0)

            if result.error:
                self._diagnostics.record_error(
                    operation="ingest_sensor_data",
                    error_code=result.error.error_code.value if hasattr(result.error.error_code, "value") else str(result.error.error_code),
                    message=result.error.message,
                )

        return result

    def route_camera_data(self, camera_contract: DroneCameraRoutingContract) -> Dict[str, Any]:
        """Route drone camera frame to Vision module."""
        self._diagnostics.record_metric("camera_routes_total", 1.0)
        return self._camera_router.route_camera_data(camera_contract)

    def register_sensor(self, metadata: SensorMetadataContract) -> bool:
        """Register a sensor profile."""
        return self._sensor_registry.register_sensor(metadata)

    def get_sensor(self, sensor_id: str) -> Optional[SensorMetadataContract]:
        """Retrieve sensor profile."""
        return self._sensor_registry.get_sensor(sensor_id)

    def list_sensors(self, category: Optional[SensorCategory] = None) -> List[SensorMetadataContract]:
        """List active sensor profiles."""
        return self._sensor_registry.list_sensors(category=category)

    def check_health(self) -> Dict[str, Any]:
        """Comprehensive composite health check across all D2 components."""
        gw_health = self._gateway.health_check()
        reg_health = self._sensor_registry.health_check()
        adapt_health = self._adapter_registry.health_check()
        diag_health = self._diagnostics.get_health_status()
        storage_health = self._storage_adapter.health_check() if hasattr(self._storage_adapter, "health_check") else {"status": "UNKNOWN"}

        is_healthy = (
            self._config.enabled
            and gw_health.get("status") == "HEALTHY"
            and reg_health.get("status") == "HEALTHY"
            and diag_health.get("status") == "HEALTHY"
        )

        return {
            "status": "HEALTHY" if is_healthy else "DEGRADED",
            "module_enabled": self._config.enabled,
            "gateway": gw_health,
            "registry": reg_health,
            "adapters": adapt_health,
            "storage": storage_health,
            "diagnostics": diag_health,
        }
