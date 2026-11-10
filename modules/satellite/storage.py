"""Satellite Storage Adapters for EarthMind Satellite Module (Stage D3).

Implements Component 8 (ISatelliteCacheStorageAdapter) with:
- `InMemorySatelliteStorageAdapter` (Thread-safe reference adapter for testing and dev)
- `FilesystemSatelliteStorageAdapter` (Local persistent directory storage)
- Storage adapter factory respecting environment safeguards (blocking in-memory in production)
"""

import os
import shutil
import threading
import time
from typing import Any, Dict, List, Optional

from core.errors.exceptions import ConfigurationError
from core.interfaces.satellite import ISatelliteCacheStorageAdapter
from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteProcessedData,
    SatelliteRawDataReference,
)
from modules.satellite.errors import (
    SatelliteStorageError,
    SatelliteStorageUnavailableError,
)

logger = get_logger("modules.satellite.storage")


class InMemorySatelliteStorageAdapter(ISatelliteCacheStorageAdapter):
    """
    In-memory reference storage adapter conforming to ISatelliteCacheStorageAdapter.
    Suitable for development, testing, and isolated staging environments.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._raw_references: Dict[str, SatelliteRawDataReference] = {}
        self._raw_payloads: Dict[str, bytes] = {}
        self._processed_data: Dict[str, SatelliteProcessedData] = {}
        self._healthy = True

    def set_healthy(self, healthy: bool) -> None:
        """Simulate storage health status for testing."""
        self._healthy = healthy

    def store_raw_reference(self, reference: SatelliteRawDataReference) -> bool:
        """Persist a raw data reference pointer."""
        if not self._healthy:
            raise SatelliteStorageUnavailableError(
                details="In-memory satellite storage adapter is currently marked unhealthy.",
                operation="store_raw_reference",
            )
        with self._lock:
            self._raw_references[reference.reference_id] = reference.model_copy(deep=True)
            return True

    def get_raw_reference(self, reference_id: str) -> Optional[SatelliteRawDataReference]:
        """Retrieve raw data reference by ID."""
        if not self._healthy:
            raise SatelliteStorageUnavailableError(
                details="In-memory satellite storage adapter is currently marked unhealthy.",
                operation="get_raw_reference",
            )
        with self._lock:
            ref = self._raw_references.get(reference_id)
            return ref.model_copy(deep=True) if ref else None

    def store_raw_payload(self, reference_id: str, payload_bytes: bytes) -> bool:
        """Store raw asset bytes associated with reference ID."""
        if not self._healthy:
            raise SatelliteStorageUnavailableError(
                details="In-memory satellite storage adapter is currently marked unhealthy.",
                operation="store_raw_payload",
            )
        with self._lock:
            self._raw_payloads[reference_id] = bytes(payload_bytes)
            return True

    def get_raw_payload(self, reference_id: str) -> Optional[bytes]:
        """Retrieve raw asset bytes by reference ID."""
        if not self._healthy:
            raise SatelliteStorageUnavailableError(
                details="In-memory satellite storage adapter is currently marked unhealthy.",
                operation="get_raw_payload",
            )
        with self._lock:
            return self._raw_payloads.get(reference_id)

    def store_processed_data(self, data: SatelliteProcessedData) -> str:
        """Persist processed satellite band data and return storage identifier."""
        if not self._healthy:
            raise SatelliteStorageUnavailableError(
                details="In-memory satellite storage adapter is currently marked unhealthy.",
                operation="store_processed_data",
            )
        with self._lock:
            pid = data.processed_id
            self._processed_data[pid] = data.model_copy(deep=True)
            return pid

    def get_processed_data(self, processed_id: str) -> Optional[SatelliteProcessedData]:
        """Retrieve processed satellite data by ID."""
        if not self._healthy:
            raise SatelliteStorageUnavailableError(
                details="In-memory satellite storage adapter is currently marked unhealthy.",
                operation="get_processed_data",
            )
        with self._lock:
            data = self._processed_data.get(processed_id)
            return data.model_copy(deep=True) if data else None

    def purge_expired(self, current_time_utc: str) -> int:
        """Purge expired cache entries according to retention policy."""
        with self._lock:
            purged = 0
            to_remove = []
            for ref_id, ref in self._raw_references.items():
                if ref.retention_expires_at and ref.retention_expires_at <= current_time_utc:
                    to_remove.append(ref_id)

            for ref_id in to_remove:
                del self._raw_references[ref_id]
                self._raw_payloads.pop(ref_id, None)
                purged += 1

            return purged

    def clear(self) -> None:
        """Clear all stored data (used in test teardown)."""
        with self._lock:
            self._raw_references.clear()
            self._raw_payloads.clear()
            self._processed_data.clear()


class FilesystemSatelliteStorageAdapter(ISatelliteCacheStorageAdapter):
    """
    Filesystem-backed persistent storage adapter for satellite assets and metadata.
    """

    def __init__(self, base_dir: str = "/tmp/earthmind_satellite_storage"):
        self._base_dir = os.path.abspath(base_dir)
        self._raw_dir = os.path.join(self._base_dir, "raw")
        self._meta_dir = os.path.join(self._base_dir, "metadata")
        self._proc_dir = os.path.join(self._base_dir, "processed")
        os.makedirs(self._raw_dir, exist_ok=True)
        os.makedirs(self._meta_dir, exist_ok=True)
        os.makedirs(self._proc_dir, exist_ok=True)
        self._lock = threading.RLock()
        self._healthy = True

    def set_healthy(self, healthy: bool) -> None:
        self._healthy = healthy

    def store_raw_reference(self, reference: SatelliteRawDataReference) -> bool:
        if not self._healthy:
            raise SatelliteStorageUnavailableError(
                details="Filesystem storage adapter is currently marked unhealthy.",
                operation="store_raw_reference",
            )
        with self._lock:
            meta_path = os.path.join(self._meta_dir, f"{reference.reference_id}.json")
            try:
                with open(meta_path, "w", encoding="utf-8") as f:
                    f.write(reference.model_dump_json(indent=2))
                return True
            except Exception as exc:
                raise SatelliteStorageError(
                    details=f"Failed to persist raw reference to {meta_path}: {exc}",
                    operation="store_raw_reference",
                ) from exc

    def get_raw_reference(self, reference_id: str) -> Optional[SatelliteRawDataReference]:
        if not self._healthy:
            raise SatelliteStorageUnavailableError(
                details="Filesystem storage adapter is currently marked unhealthy.",
                operation="get_raw_reference",
            )
        with self._lock:
            meta_path = os.path.join(self._meta_dir, f"{reference_id}.json")
            if not os.path.exists(meta_path):
                return None
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    return SatelliteRawDataReference.model_validate_json(f.read())
            except Exception as exc:
                raise SatelliteStorageError(
                    details=f"Failed to read raw reference {meta_path}: {exc}",
                    operation="get_raw_reference",
                ) from exc

    def store_raw_payload(self, reference_id: str, payload_bytes: bytes) -> bool:
        if not self._healthy:
            raise SatelliteStorageUnavailableError(
                details="Filesystem storage adapter is currently marked unhealthy.",
                operation="store_raw_payload",
            )
        with self._lock:
            raw_path = os.path.join(self._raw_dir, f"{reference_id}.bin")
            try:
                with open(raw_path, "wb") as f:
                    f.write(payload_bytes)
                return True
            except Exception as exc:
                raise SatelliteStorageError(
                    details=f"Failed to write raw bytes to {raw_path}: {exc}",
                    operation="store_raw_payload",
                ) from exc

    def get_raw_payload(self, reference_id: str) -> Optional[bytes]:
        if not self._healthy:
            raise SatelliteStorageUnavailableError(
                details="Filesystem storage adapter is currently marked unhealthy.",
                operation="get_raw_payload",
            )
        with self._lock:
            raw_path = os.path.join(self._raw_dir, f"{reference_id}.bin")
            if not os.path.exists(raw_path):
                return None
            try:
                with open(raw_path, "rb") as f:
                    return f.read()
            except Exception as exc:
                raise SatelliteStorageError(
                    details=f"Failed to read raw bytes from {raw_path}: {exc}",
                    operation="get_raw_payload",
                ) from exc

    def store_processed_data(self, data: SatelliteProcessedData) -> str:
        if not self._healthy:
            raise SatelliteStorageUnavailableError(
                details="Filesystem storage adapter is currently marked unhealthy.",
                operation="store_processed_data",
            )
        with self._lock:
            pid = data.processed_id
            proc_path = os.path.join(self._proc_dir, f"{pid}.json")
            try:
                with open(proc_path, "w", encoding="utf-8") as f:
                    f.write(data.model_dump_json(indent=2))
                return pid
            except Exception as exc:
                raise SatelliteStorageError(
                    details=f"Failed to persist processed data to {proc_path}: {exc}",
                    operation="store_processed_data",
                ) from exc

    def get_processed_data(self, processed_id: str) -> Optional[SatelliteProcessedData]:
        if not self._healthy:
            raise SatelliteStorageUnavailableError(
                details="Filesystem storage adapter is currently marked unhealthy.",
                operation="get_processed_data",
            )
        with self._lock:
            proc_path = os.path.join(self._proc_dir, f"{processed_id}.json")
            if not os.path.exists(proc_path):
                return None
            try:
                with open(proc_path, "r", encoding="utf-8") as f:
                    return SatelliteProcessedData.model_validate_json(f.read())
            except Exception as exc:
                raise SatelliteStorageError(
                    details=f"Failed to read processed data from {proc_path}: {exc}",
                    operation="get_processed_data",
                ) from exc

    def purge_expired(self, current_time_utc: str) -> int:
        with self._lock:
            purged = 0
            if not os.path.exists(self._meta_dir):
                return 0
            for fname in os.listdir(self._meta_dir):
                if not fname.endswith(".json"):
                    continue
                meta_path = os.path.join(self._meta_dir, fname)
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        ref = SatelliteRawDataReference.model_validate_json(f.read())
                    if ref.retention_expires_at and ref.retention_expires_at <= current_time_utc:
                        os.remove(meta_path)
                        raw_path = os.path.join(self._raw_dir, f"{ref.reference_id}.bin")
                        if os.path.exists(raw_path):
                            os.remove(raw_path)
                        purged += 1
                except Exception as exc:
                    logger.warning(f"Error purging file {meta_path}: {exc}")
            return purged

    def clear(self) -> None:
        """Clear filesystem storage."""
        with self._lock:
            if os.path.exists(self._base_dir):
                shutil.rmtree(self._base_dir)
                os.makedirs(self._raw_dir, exist_ok=True)
                os.makedirs(self._meta_dir, exist_ok=True)
                os.makedirs(self._proc_dir, exist_ok=True)


def resolve_satellite_storage_adapter(
    adapter_type: str = "in_memory",
    base_dir: Optional[str] = None,
    is_production: bool = False,
) -> ISatelliteCacheStorageAdapter:
    """Factory resolving satellite storage adapter with production safeguards."""
    norm = adapter_type.strip().lower()
    if is_production and norm in ("in_memory", "memory"):
        raise ConfigurationError(
            "Production mode violation: In-memory satellite storage adapter is prohibited in production mode. "
            "Configure EARTHMIND_SATELLITE_STORAGE_ADAPTER to 'filesystem' or an external database/cloud adapter.",
            details={"setting": "satellite.storage_adapter", "value": adapter_type},
        )

    if norm in ("in_memory", "memory"):
        return InMemorySatelliteStorageAdapter()
    elif norm in ("filesystem", "file", "disk"):
        return FilesystemSatelliteStorageAdapter(base_dir=base_dir or "/tmp/earthmind_satellite_storage")
    else:
        logger.warning(f"Unrecognized satellite storage adapter '{adapter_type}', defaulting to in_memory.")
        return InMemorySatelliteStorageAdapter()
