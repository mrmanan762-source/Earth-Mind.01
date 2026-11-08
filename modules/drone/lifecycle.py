"""Ingestion Lifecycle & Status Management for EarthMind Drone Module (Stage D2).

Manages state machine transitions, ingestion idempotency, and execution tracking
for incoming drone sensor packages.
"""

import threading
import time
from typing import Any, Dict, List, Optional

from core.logging.logger import get_logger
from core.schemas.drone import (
    DroneErrorContract,
    DroneIngestionResult,
    IngestionStatus,
)
from modules.drone.errors import DroneInvalidArgumentError

logger = get_logger("modules.drone.lifecycle")


# Valid lifecycle state transitions
VALID_TRANSITIONS: Dict[IngestionStatus, List[IngestionStatus]] = {
    IngestionStatus.PENDING: [
        IngestionStatus.RUNNING,
        IngestionStatus.REJECTED,
        IngestionStatus.FAILED,
        IngestionStatus.UNAVAILABLE,
    ],
    IngestionStatus.RUNNING: [
        IngestionStatus.SUCCESS,
        IngestionStatus.REJECTED,
        IngestionStatus.FAILED,
        IngestionStatus.UNAVAILABLE,
    ],
    IngestionStatus.SUCCESS: [],
    IngestionStatus.REJECTED: [],
    IngestionStatus.FAILED: [],
    IngestionStatus.UNAVAILABLE: [],
}


class IngestionLifecycleTracker:
    """Thread-safe tracker managing state transitions, history, and duplicate detection."""

    def __init__(self, max_history: int = 1000):
        self._lock = threading.RLock()
        self._records: Dict[str, DroneIngestionResult] = {}
        self._idempotency_map: Dict[str, str] = {}  # idempotency_key -> ingestion_id
        self._max_history = max_history

    def register_start(
        self,
        drone_id: str,
        sensor_id: str,
        idempotency_key: Optional[str] = None,
        ingestion_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DroneIngestionResult:
        """Start tracking a new ingestion request in PENDING state."""
        with self._lock:
            # Check idempotency
            if idempotency_key and idempotency_key in self._idempotency_map:
                existing_id = self._idempotency_map[idempotency_key]
                if existing_id in self._records:
                    logger.info(f"Duplicate ingestion detected for idempotency key '{idempotency_key}'. Returning existing record {existing_id}.")
                    return self._records[existing_id]

            init_kwargs = {
                "drone_id": drone_id,
                "sensor_id": sensor_id,
                "status": IngestionStatus.PENDING,
                "accepted": False,
                "metadata": metadata or {},
            }
            if ingestion_id:
                init_kwargs["ingestion_id"] = ingestion_id

            result = DroneIngestionResult(**init_kwargs)
            self._records[result.ingestion_id] = result

            if idempotency_key:
                self._idempotency_map[idempotency_key] = result.ingestion_id

            # Maintain history size bounds
            if len(self._records) > self._max_history:
                oldest_id = next(iter(self._records))
                del self._records[oldest_id]
                # Cleanup reverse mapping if any
                keys_to_del = [k for k, v in self._idempotency_map.items() if v == oldest_id]
                for k in keys_to_del:
                    del self._idempotency_map[k]

            return result

    def transition_to(
        self,
        ingestion_id: str,
        target_status: IngestionStatus,
        warnings: Optional[List[str]] = None,
        error: Optional[Any] = None,
        metadata_update: Optional[Dict[str, Any]] = None,
    ) -> DroneIngestionResult:
        """Perform a validated lifecycle state transition."""
        with self._lock:
            if ingestion_id not in self._records:
                raise DroneInvalidArgumentError(
                    details=f"Ingestion ID '{ingestion_id}' not found in active lifecycle tracker.",
                    operation="transition_to",
                )

            current = self._records[ingestion_id]
            allowed = VALID_TRANSITIONS.get(current.status, [])

            if target_status not in allowed:
                raise DroneInvalidArgumentError(
                    details=f"Invalid state transition from '{current.status.value}' to '{target_status.value}' for ingestion '{ingestion_id}'.",
                    operation="transition_to",
                )

            current_dict = current.model_dump()
            current_dict["status"] = target_status

            if target_status == IngestionStatus.SUCCESS:
                current_dict["accepted"] = True
            elif target_status in (IngestionStatus.REJECTED, IngestionStatus.FAILED, IngestionStatus.UNAVAILABLE):
                current_dict["accepted"] = False

            if warnings:
                current_dict["warnings"] = list(set(current_dict.get("warnings", []) + warnings))

            if error:
                current_dict["error"] = error

            if metadata_update:
                current_dict["metadata"] = {**current_dict.get("metadata", {}), **metadata_update}

            updated = DroneIngestionResult(**current_dict)
            self._records[ingestion_id] = updated
            return updated

    def get_record(self, ingestion_id: str) -> Optional[DroneIngestionResult]:
        """Retrieve an ingestion result by ingestion_id."""
        with self._lock:
            return self._records.get(ingestion_id)

    def check_duplicate(self, idempotency_key: str) -> Optional[DroneIngestionResult]:
        """Check if an idempotency key has already been tracked."""
        with self._lock:
            if idempotency_key in self._idempotency_map:
                ing_id = self._idempotency_map[idempotency_key]
                return self._records.get(ing_id)
            return None

    def clear(self) -> None:
        """Clear all tracking state (used in testing)."""
        with self._lock:
            self._records.clear()
            self._idempotency_map.clear()
