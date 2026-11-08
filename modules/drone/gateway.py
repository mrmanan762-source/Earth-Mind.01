"""Drone Data Gateway for EarthMind Drone Module (Stage D2).

Implements Component 1 (IDroneDataGateway).
Acts as the standardized, secure, untrusted entry point for incoming drone
sensor packages. Validates outer structure, tenant scope, size limits,
verifies formats and registered sensor capabilities, detects duplicates,
and returns structured Ingestion Results.
"""

import hashlib
import time
from typing import Any, Dict, Optional

from core.interfaces.drone import IDroneDataGateway
from core.logging.logger import get_logger
from core.schemas.drone import (
    DroneDataFormat,
    DroneErrorContract,
    DroneErrorCode,
    DroneIngestionResult,
    DroneSensorInputContract,
    IngestionStatus,
)
from modules.drone.adapters import SensorAdapterRegistry
from modules.drone.errors import (
    DroneError,
    DroneInvalidArgumentError,
    InsufficientDroneDataError,
    SensorMetadataMissingError,
    UnsupportedFormatError,
    UnsupportedSensorError,
)
from modules.drone.formats import DataFormatRegistry
from modules.drone.lifecycle import IngestionLifecycleTracker
from modules.drone.registry import SensorRegistry

logger = get_logger("modules.drone.gateway")


class DroneDataGateway(IDroneDataGateway):
    """Component 1: Standardized entry point for incoming drone sensor data."""

    def __init__(
        self,
        sensor_registry: SensorRegistry,
        format_registry: DataFormatRegistry,
        adapter_registry: SensorAdapterRegistry,
        lifecycle_tracker: Optional[IngestionLifecycleTracker] = None,
        max_payload_size_bytes: int = 50 * 1024 * 1024,  # 50 MB
        gateway_enabled: bool = True,
    ):
        self._sensor_registry = sensor_registry
        self._format_registry = format_registry
        self._adapter_registry = adapter_registry
        self._lifecycle_tracker = lifecycle_tracker or IngestionLifecycleTracker()
        self._max_payload_size_bytes = max_payload_size_bytes
        self._gateway_enabled = gateway_enabled

    @property
    def is_enabled(self) -> bool:
        return self._gateway_enabled

    def set_enabled(self, enabled: bool) -> None:
        self._gateway_enabled = enabled

    def _compute_payload_hash(self, request: DroneSensorInputContract) -> str:
        """Compute deterministic payload fingerprint for duplicate/idempotency detection."""
        hasher = hashlib.sha256()
        hasher.update(request.drone_id.encode("utf-8"))
        hasher.update(request.sensor_id.encode("utf-8"))
        hasher.update(request.data_format.value.encode("utf-8"))
        hasher.update(request.collection_timestamp.encode("utf-8"))

        if request.raw_payload_ref:
            hasher.update(request.raw_payload_ref.encode("utf-8"))
        if request.raw_payload is not None:
            if isinstance(request.raw_payload, bytes):
                hasher.update(request.raw_payload)
            else:
                hasher.update(str(request.raw_payload).encode("utf-8"))

        # Include declared sha256 from provenance if available
        if request.source_provenance and "payload_sha256" in request.source_provenance:
            hasher.update(str(request.source_provenance["payload_sha256"]).encode("utf-8"))

        return hasher.hexdigest()

    def ingest_sensor_data(self, request: DroneSensorInputContract) -> Dict[str, Any]:
        """Ingest incoming raw sensor payload and return structured ingestion result dictionary."""
        result = self.process_ingestion(request)
        return result.to_dict()

    def process_ingestion(self, request: DroneSensorInputContract) -> DroneIngestionResult:
        """Process incoming sensor package through gateway validation gates."""
        received_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # 0. Check gateway availability
        if not self._gateway_enabled:
            err = DroneErrorContract(
                error_code=DroneErrorCode.STORAGE_UNAVAILABLE,
                message="Drone Data Gateway is currently disabled or unavailable.",
                operation="ingest_sensor_data",
                retryable=True,
                metadata={"gateway_enabled": False},
            )
            return DroneIngestionResult(
                drone_id=request.drone_id or "UNKNOWN",
                sensor_id=request.sensor_id or "UNKNOWN",
                status=IngestionStatus.UNAVAILABLE,
                accepted=False,
                received_timestamp=received_time,
                error=err,
            )

        # 1. Structural input sanity checks
        if not request.drone_id or not request.drone_id.strip():
            err = DroneErrorContract(
                error_code=DroneErrorCode.INVALID_ARGUMENT,
                message="Missing required drone hardware identifier 'drone_id'.",
                operation="ingest_sensor_data",
                retryable=False,
                metadata={"argument": "drone_id"},
            )
            return DroneIngestionResult(
                drone_id="MISSING",
                sensor_id=request.sensor_id or "UNKNOWN",
                status=IngestionStatus.REJECTED,
                accepted=False,
                received_timestamp=received_time,
                error=err,
            )

        if not request.sensor_id or not request.sensor_id.strip():
            err = DroneErrorContract(
                error_code=DroneErrorCode.INVALID_ARGUMENT,
                message="Missing required sensor identifier 'sensor_id'.",
                operation="ingest_sensor_data",
                retryable=False,
                metadata={"argument": "sensor_id"},
            )
            return DroneIngestionResult(
                drone_id=request.drone_id,
                sensor_id="MISSING",
                status=IngestionStatus.REJECTED,
                accepted=False,
                received_timestamp=received_time,
                error=err,
            )

        # Path traversal checks on string identifiers
        for field_name, val in [("drone_id", request.drone_id), ("sensor_id", request.sensor_id), ("raw_payload_ref", request.raw_payload_ref)]:
            if val and ("../" in val or "..\\" in val):
                err = DroneErrorContract(
                    error_code=DroneErrorCode.INVALID_ARGUMENT,
                    message=f"Path traversal characters detected in '{field_name}'.",
                    operation="ingest_sensor_data",
                    retryable=False,
                    metadata={"argument": field_name},
                )
                return DroneIngestionResult(
                    drone_id=request.drone_id,
                    sensor_id=request.sensor_id,
                    status=IngestionStatus.REJECTED,
                    accepted=False,
                    received_timestamp=received_time,
                    error=err,
                )

        # 2. Payload size validation
        payload_size = 0
        if request.raw_payload is not None:
            if isinstance(request.raw_payload, (bytes, bytearray)):
                payload_size = len(request.raw_payload)
            elif isinstance(request.raw_payload, str):
                payload_size = len(request.raw_payload.encode("utf-8"))
            elif isinstance(request.raw_payload, (dict, list)):
                payload_size = len(str(request.raw_payload).encode("utf-8"))

        if payload_size > self._max_payload_size_bytes:
            err = DroneErrorContract(
                error_code=DroneErrorCode.INVALID_ARGUMENT,
                message=f"Payload size ({payload_size} bytes) exceeds configured gateway maximum limit ({self._max_payload_size_bytes} bytes).",
                operation="ingest_sensor_data",
                retryable=False,
                metadata={"payload_size": payload_size, "max_limit": self._max_payload_size_bytes},
            )
            return DroneIngestionResult(
                drone_id=request.drone_id,
                sensor_id=request.sensor_id,
                status=IngestionStatus.REJECTED,
                accepted=False,
                received_timestamp=received_time,
                error=err,
            )

        # 3. Duplicate Ingestion / Idempotency Check
        payload_hash = self._compute_payload_hash(request)
        tracked = self._lifecycle_tracker.check_duplicate(payload_hash)
        if tracked:
            logger.info(f"Duplicate sensor data ingestion detected for hash {payload_hash}. Returning existing ingestion {tracked.ingestion_id}.")
            return tracked

        # Start lifecycle in PENDING
        initial_record = self._lifecycle_tracker.register_start(
            drone_id=request.drone_id,
            sensor_id=request.sensor_id,
            idempotency_key=payload_hash,
            metadata={
                "data_format": request.data_format.value,
                "collection_timestamp": request.collection_timestamp,
                "payload_size_bytes": payload_size,
                "field_id": request.field_id,
                "farm_id": request.farm_id,
                "farmer_id": request.farmer_id,
            }
        )
        ing_id = initial_record.ingestion_id

        # Transition to RUNNING
        self._lifecycle_tracker.transition_to(ing_id, IngestionStatus.RUNNING)

        warnings = []

        try:
            # 4. Check sensor registration in Sensor Registry
            sensor_meta = self._sensor_registry.get_sensor(request.sensor_id)
            if not sensor_meta:
                raise UnsupportedSensorError(
                    sensor_id=request.sensor_id,
                    details=f"Sensor '{request.sensor_id}' is not registered in the Sensor Registry."
                )

            if sensor_meta.registration_status != "ACTIVE":
                raise UnsupportedSensorError(
                    sensor_id=request.sensor_id,
                    details=f"Sensor '{request.sensor_id}' is deactivated (status: {sensor_meta.registration_status})."
                )

            # 5. Format Capability Check
            if not self._format_registry.is_supported(request.data_format):
                raise UnsupportedFormatError(
                    data_format=request.data_format.value,
                    details=f"Declared format '{request.data_format.value}' is not supported."
                )

            # Validate byte signature if inline bytes provided
            if isinstance(request.raw_payload, (bytes, bytearray)):
                self._format_registry.validate_payload_format(request.data_format, bytes(request.raw_payload[:16]))

            # 6. Adapter compatibility check
            adapter = self._adapter_registry.find_adapter(request, sensor_meta)

            # 7. Check calibration representation
            if not request.calibration_metadata:
                warnings.append("No calibration metadata supplied with raw ingestion package.")

            # Ingestion accepted successfully
            meta_update = {
                "matched_adapter": adapter.adapter_id,
                "adapter_version": adapter.adapter_version,
                "sensor_category": sensor_meta.sensor_category.value,
                "payload_hash": payload_hash,
            }

            final_record = self._lifecycle_tracker.transition_to(
                ingestion_id=ing_id,
                target_status=IngestionStatus.SUCCESS,
                warnings=warnings,
                metadata_update=meta_update,
            )

            logger.info(
                f"Accepted drone sensor package: ingestion_id={ing_id}, drone={request.drone_id}, "
                f"sensor={request.sensor_id}, format={request.data_format.value}"
            )
            return final_record

        except DroneError as de:
            logger.warning(f"Drone ingestion validation rejected: {de.error_contract.message}")
            return self._lifecycle_tracker.transition_to(
                ingestion_id=ing_id,
                target_status=IngestionStatus.REJECTED,
                error=de.error_contract,
            )
        except Exception as exc:
            logger.error(f"Unexpected error during drone ingestion: {exc}")
            err = DroneErrorContract(
                error_code=DroneErrorCode.INTERNAL_ERROR,
                message="An internal error occurred during drone ingestion processing.",
                operation="ingest_sensor_data",
                retryable=False,
                metadata={"details": str(exc)},
            )
            return self._lifecycle_tracker.transition_to(
                ingestion_id=ing_id,
                target_status=IngestionStatus.FAILED,
                error=err,
            )

    def health_check(self) -> Dict[str, Any]:
        """Report Gateway health status."""
        return {
            "gateway_enabled": self._gateway_enabled,
            "max_payload_size_bytes": self._max_payload_size_bytes,
            "status": "HEALTHY" if self._gateway_enabled else "DEGRADED",
        }
