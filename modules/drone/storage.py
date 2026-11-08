"""Drone Storage Adapter Implementation for EarthMind Drone Module (Stage D2).

Implements Component 17 (IDroneStorageAdapter) with thread safety, deep copy
isolation, and clean boundary separation. Does not couple directly to database
SDKs or trigger unauthorized memory promotion.
"""

import threading
from typing import Any, Dict, List, Optional

from core.interfaces.drone import IDroneStorageAdapter
from core.logging.logger import get_logger
from core.schemas.drone import EarthMindDroneSensorEvidence, SensorMetadataContract
from modules.drone.errors import DroneStorageError

logger = get_logger("modules.drone.storage")


class InMemoryDroneStorageAdapter(IDroneStorageAdapter):
    """
    In-memory reference storage adapter conforming to IDroneStorageAdapter.
    Suitable for development, testing, and isolated staging environments.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._evidence_store: Dict[str, EarthMindDroneSensorEvidence] = {}
        self._sensor_store: Dict[str, SensorMetadataContract] = {}
        self._healthy = True

    def set_healthy(self, healthy: bool) -> None:
        """Simulate storage health status for testing."""
        self._healthy = healthy

    def store_evidence(self, evidence: EarthMindDroneSensorEvidence) -> str:
        """Persist validated evidence and return storage identifier."""
        if not self._healthy:
            raise DroneStorageError(
                details="Storage adapter is currently marked unhealthy.",
                operation="store_evidence",
            )
        with self._lock:
            ev_id = evidence.evidence_id
            self._evidence_store[ev_id] = evidence.model_copy(deep=True)
            logger.debug(f"Stored evidence record: {ev_id}")
            return ev_id

    def get_evidence(self, evidence_id: str) -> Optional[EarthMindDroneSensorEvidence]:
        """Retrieve stored evidence by ID."""
        if not self._healthy:
            raise DroneStorageError(
                details="Storage adapter is currently marked unhealthy.",
                operation="get_evidence",
            )
        with self._lock:
            record = self._evidence_store.get(evidence_id)
            return record.model_copy(deep=True) if record else None

    def store_sensor_profile(self, profile: SensorMetadataContract) -> bool:
        """Persist a sensor hardware capability manifest."""
        if not self._healthy:
            raise DroneStorageError(
                details="Storage adapter is currently marked unhealthy.",
                operation="store_sensor_profile",
            )
        with self._lock:
            self._sensor_store[profile.sensor_id] = profile.model_copy(deep=True)
            logger.debug(f"Stored sensor profile: {profile.sensor_id}")
            return True

    def get_sensor_profile(self, sensor_id: str) -> Optional[SensorMetadataContract]:
        """Retrieve a sensor profile by ID."""
        if not self._healthy:
            raise DroneStorageError(
                details="Storage adapter is currently marked unhealthy.",
                operation="get_sensor_profile",
            )
        with self._lock:
            record = self._sensor_store.get(sensor_id)
            return record.model_copy(deep=True) if record else None

    def list_sensor_profiles(self) -> List[SensorMetadataContract]:
        """List all stored sensor profiles."""
        with self._lock:
            return [p.model_copy(deep=True) for p in self._sensor_store.values()]

    def health_check(self) -> Dict[str, Any]:
        """Report storage adapter health."""
        with self._lock:
            return {
                "adapter": "in_memory",
                "status": "HEALTHY" if self._healthy else "UNHEALTHY",
                "evidence_count": len(self._evidence_store),
                "sensor_profiles_count": len(self._sensor_store),
            }

    def clear(self) -> None:
        """Clear all stores (used in test teardown)."""
        with self._lock:
            self._evidence_store.clear()
            self._sensor_store.clear()
