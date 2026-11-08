"""Sensor Registry & Capability Manager for EarthMind Drone Module (Stage D2).

Implements Component 2 (ISensorRegistry) to maintain the logical registry of
supported drone sensors, measurement capabilities, calibration parameters,
and operational profiles.
"""

import threading
from typing import Any, Dict, List, Optional

from core.interfaces.drone import IDroneStorageAdapter, ISensorRegistry
from core.logging.logger import get_logger
from core.schemas.drone import SensorCategory, SensorMetadataContract
from modules.drone.errors import (
    DroneInvalidArgumentError,
    SensorConflictError,
    SensorMetadataMissingError,
    UnsupportedSensorError,
)

logger = get_logger("modules.drone.registry")


class SensorRegistry(ISensorRegistry):
    """Registry maintaining registered drone sensor hardware profiles and capability manifests."""

    def __init__(self, storage_adapter: Optional[IDroneStorageAdapter] = None):
        self._lock = threading.RLock()
        self._sensors: Dict[str, SensorMetadataContract] = {}
        self._storage_adapter = storage_adapter

    def register_sensor(self, metadata: SensorMetadataContract) -> bool:
        """Register or update a sensor hardware capability manifest."""
        if not metadata.sensor_id or not metadata.sensor_id.strip():
            raise DroneInvalidArgumentError(
                details="sensor_id cannot be empty.",
                operation="register_sensor",
            )

        with self._lock:
            # Check for conflict if registering active sensor with duplicate ID but different category
            existing = self._sensors.get(metadata.sensor_id)
            if existing and existing.registration_status == "ACTIVE" and existing.sensor_category != metadata.sensor_category:
                raise SensorConflictError(
                    sensor_a=metadata.sensor_id,
                    sensor_b=existing.sensor_id,
                    details=f"Sensor ID '{metadata.sensor_id}' already registered with incompatible category '{existing.sensor_category.value}'."
                )

            self._sensors[metadata.sensor_id] = metadata.model_copy(deep=True)

            if self._storage_adapter:
                try:
                    self._storage_adapter.store_sensor_profile(metadata)
                except Exception as exc:
                    logger.warning(f"Failed to persist sensor profile to storage adapter: {exc}")

            logger.info(f"Registered sensor profile: {metadata.sensor_id} (category={metadata.sensor_category.value}, status={metadata.registration_status})")
            return True

    def get_sensor(self, sensor_id: str) -> Optional[SensorMetadataContract]:
        """Retrieve sensor capability manifest by sensor ID."""
        with self._lock:
            sensor = self._sensors.get(sensor_id)
            if not sensor and self._storage_adapter:
                try:
                    stored = self._storage_adapter.get_sensor_profile(sensor_id)
                    if stored:
                        self._sensors[sensor_id] = stored.model_copy(deep=True)
                        return stored
                except Exception as exc:
                    logger.warning(f"Error reading sensor profile from storage adapter: {exc}")
            return sensor.model_copy(deep=True) if sensor else None

    def update_sensor(self, sensor_id: str, updates: Dict[str, Any]) -> SensorMetadataContract:
        """Update permitted metadata on an existing sensor profile."""
        with self._lock:
            existing = self.get_sensor(sensor_id)
            if not existing:
                raise UnsupportedSensorError(
                    sensor_id=sensor_id,
                    details=f"Cannot update non-existent sensor '{sensor_id}'."
                )

            existing_dict = existing.model_dump()
            # Do not allow modifying sensor_id
            updates.pop("sensor_id", None)
            existing_dict.update(updates)

            updated = SensorMetadataContract(**existing_dict)
            self._sensors[sensor_id] = updated
            if self._storage_adapter:
                self._storage_adapter.store_sensor_profile(updated)
            return updated

    def unregister_sensor(self, sensor_id: str) -> bool:
        """Deactivate or unregister a sensor."""
        with self._lock:
            if sensor_id in self._sensors:
                # Mark as INACTIVE rather than deleting outright to preserve lineage
                current = self._sensors[sensor_id].model_dump()
                current["registration_status"] = "INACTIVE"
                updated = SensorMetadataContract(**current)
                self._sensors[sensor_id] = updated
                if self._storage_adapter:
                    self._storage_adapter.store_sensor_profile(updated)
                logger.info(f"Deactivated sensor profile: {sensor_id}")
                return True
            return False

    def is_supported(self, sensor_id: str, measurement: str) -> bool:
        """Check if a sensor exists, is ACTIVE, and supports the given measurement channel."""
        sensor = self.get_sensor(sensor_id)
        if not sensor or sensor.registration_status != "ACTIVE":
            return False
        return measurement.lower() in [m.lower() for m in sensor.supported_measurements]

    def is_active(self, sensor_id: str) -> bool:
        """Check if sensor exists and is ACTIVE."""
        sensor = self.get_sensor(sensor_id)
        return bool(sensor and sensor.registration_status == "ACTIVE")

    def list_sensors(
        self,
        category: Optional[SensorCategory] = None,
        only_active: bool = True,
    ) -> List[SensorMetadataContract]:
        """List registered sensor profiles with optional filtering."""
        with self._lock:
            results = []
            for s in self._sensors.values():
                if only_active and s.registration_status != "ACTIVE":
                    continue
                if category and s.sensor_category != category:
                    continue
                results.append(s.model_copy(deep=True))
            return sorted(results, key=lambda x: x.sensor_id)

    def get_sensor_capabilities(self, sensor_id: str) -> Dict[str, Any]:
        """Return capabilities and operational envelope dictionary for a sensor."""
        sensor = self.get_sensor(sensor_id)
        if not sensor:
            raise UnsupportedSensorError(
                sensor_id=sensor_id,
                details=f"Sensor '{sensor_id}' not found in registry."
            )
        return {
            "sensor_id": sensor.sensor_id,
            "sensor_category": sensor.sensor_category.value,
            "status": sensor.registration_status,
            "supported_measurements": sensor.supported_measurements,
            "supported_formats": [f.value for f in sensor.supported_formats],
            "measurement_units": sensor.measurement_units,
            "sampling_characteristics": sensor.sampling_characteristics,
            "calibration_metadata": sensor.calibration_metadata,
            "capability_version": sensor.capability_version,
        }

    def validate_sensor(self, sensor_id: str) -> SensorMetadataContract:
        """Validate that sensor exists and is active, raising specialized exception if not."""
        sensor = self.get_sensor(sensor_id)
        if not sensor:
            raise UnsupportedSensorError(
                sensor_id=sensor_id,
                details=f"Sensor profile '{sensor_id}' is not registered."
            )
        if sensor.registration_status != "ACTIVE":
            raise UnsupportedSensorError(
                sensor_id=sensor_id,
                details=f"Sensor '{sensor_id}' is deactivated (status: {sensor.registration_status})."
            )
        return sensor

    def health_check(self) -> Dict[str, Any]:
        """Return logical health status of the registry."""
        with self._lock:
            active_count = sum(1 for s in self._sensors.values() if s.registration_status == "ACTIVE")
            return {
                "status": "HEALTHY",
                "total_sensors": len(self._sensors),
                "active_sensors": active_count,
                "has_storage_adapter": self._storage_adapter is not None,
            }
