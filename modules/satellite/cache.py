"""Hybrid Satellite Acquisition Cache for EarthMind Satellite Module (Stage D3).

Coordinates on-demand acquisition, intelligent caching, and historical data access.
Features:
- Geospatial matching (exact coordinates or point within scene bounding box)
- Temporal matching (observation date within requested lookback window)
- Constellation & Sensor Type filtering
- Cloud cover threshold filtering
- TTL expiration & eviction
- Preserves provider identity, license attribution, and provenance
- Returns cached acquisition results with `cached=True`
"""

import threading
import time
from typing import Any, Dict, List, Optional

from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteAcquisitionResult,
    SatelliteAcquisitionStatus,
    SatelliteDataRequest,
    SatelliteDatasetMetadata,
    SatelliteRawDataReference,
)
from modules.satellite.catalog import SatelliteDataCatalog
from modules.satellite.storage import InMemorySatelliteStorageAdapter

logger = get_logger("modules.satellite.cache")


class CachedSceneEntry:
    """Internal cache entry wrapper with access statistics and timestamps."""

    def __init__(
        self,
        metadata: SatelliteDatasetMetadata,
        raw_reference: Optional[SatelliteRawDataReference] = None,
        ttl_seconds: int = 86400,
    ):
        self.metadata = metadata
        self.raw_reference = raw_reference
        self.created_at_ts = time.time()
        self.last_accessed_ts = self.created_at_ts
        self.ttl_seconds = ttl_seconds
        self.access_count = 0

    @property
    def is_expired(self) -> bool:
        if self.ttl_seconds <= 0:
            return False
        return (time.time() - self.created_at_ts) > self.ttl_seconds

    def touch(self) -> None:
        self.last_accessed_ts = time.time()
        self.access_count += 1


class SatelliteHybridCache:
    """
    Hybrid cache managing satellite dataset metadata and raw asset references.
    Supports spatial, temporal, and metadata matching without re-fetching from providers.
    """

    def __init__(
        self,
        catalog: Optional[SatelliteDataCatalog] = None,
        default_ttl_seconds: int = 86400,
        max_entries: int = 1000,
    ):
        self._catalog = catalog or SatelliteDataCatalog()
        self._default_ttl_seconds = default_ttl_seconds
        self._max_entries = max_entries
        self._lock = threading.RLock()
        self._entries: Dict[str, CachedSceneEntry] = {}  # indexed by dataset_id

    @property
    def catalog(self) -> SatelliteDataCatalog:
        return self._catalog

    def put(
        self,
        metadata: SatelliteDatasetMetadata,
        raw_reference: Optional[SatelliteRawDataReference] = None,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Cache an acquired dataset and its raw reference."""
        if not metadata or not metadata.dataset_id:
            return

        with self._lock:
            did = metadata.dataset_id
            ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
            entry = CachedSceneEntry(metadata=metadata.model_copy(deep=True), raw_reference=raw_reference, ttl_seconds=ttl)
            self._entries[did] = entry

            # Also register in catalog for catalog discovery
            self._catalog.register_dataset(metadata, allow_update=True)
            logger.debug(f"Cached satellite dataset '{did}' (TTL={ttl}s).")

            # Prune if exceeded max entries
            if len(self._entries) > self._max_entries:
                self._evict_lru()

    def get_by_id(self, dataset_id: str) -> Optional[SatelliteDatasetMetadata]:
        """Retrieve cached dataset by exact dataset ID, verifying expiration."""
        if not dataset_id:
            return None
        with self._lock:
            entry = self._entries.get(dataset_id.strip())
            if not entry:
                return None
            if entry.is_expired:
                logger.info(f"Cached dataset '{dataset_id}' has expired; evicting.")
                self.invalidate(dataset_id)
                return None
            entry.touch()
            return entry.metadata.model_copy(deep=True)

    def get_raw_reference_by_id(self, dataset_id: str) -> Optional[SatelliteRawDataReference]:
        """Retrieve stored raw reference for a cached dataset ID."""
        if not dataset_id:
            return None
        with self._lock:
            entry = self._entries.get(dataset_id.strip())
            if not entry or entry.is_expired:
                return None
            entry.touch()
            return entry.raw_reference.model_copy(deep=True) if entry.raw_reference else None

    def match_request(
        self,
        request: SatelliteDataRequest,
    ) -> Optional[SatelliteAcquisitionResult]:
        """
        Check cache for an existing dataset meeting the geospatial, temporal,
        and sensor requirements of a SatelliteDataRequest.
        """
        with self._lock:
            req_lat = request.geospatial.latitude
            req_lon = request.geospatial.longitude
            req_date_str = request.temporal_window.acquisition_date.split("T")[0]
            max_cloud = request.max_cloud_cover_percentage
            target_constellations = request.target_constellations

            try:
                target_ts = time.mktime(time.strptime(req_date_str, "%Y-%m-%d"))
            except Exception:
                target_ts = time.time()

            candidates: List[CachedSceneEntry] = []

            for did, entry in list(self._entries.items()):
                if entry.is_expired:
                    self.invalidate(did)
                    continue

                meta = entry.metadata

                # 1. Cloud cover check
                if meta.cloud_cover_percentage > max_cloud:
                    continue

                # 2. Constellation check
                if target_constellations and meta.constellation not in target_constellations:
                    continue

                # 3. Sensor type check
                if request.sensor_types and meta.sensor_type not in request.sensor_types:
                    continue

                # 4. Spatial matching: point inside bounding box or proximity
                geo = meta.geospatial
                if geo.bounding_box:
                    min_lon, min_lat, max_lon, max_lat = geo.bounding_box
                    if not (min_lat <= req_lat <= max_lat and min_lon <= req_lon <= max_lon):
                        continue
                else:
                    if abs(geo.latitude - req_lat) > 0.5 or abs(geo.longitude - req_lon) > 0.5:
                        continue

                # 5. Temporal matching: within 15 days window of requested observation
                try:
                    scene_date_str = meta.temporal.acquisition_date.split("T")[0]
                    scene_ts = time.mktime(time.strptime(scene_date_str, "%Y-%m-%d"))
                    diff_days = abs(target_ts - scene_ts) / 86400.0
                    if diff_days > 15.0:
                        continue
                except Exception:
                    pass

                candidates.append(entry)

            if not candidates:
                return None

            # Sort candidate entries: lowest cloud cover first
            candidates.sort(key=lambda e: e.metadata.cloud_cover_percentage)
            best_entry = candidates[0]
            best_entry.touch()
            best_meta = best_entry.metadata.model_copy(deep=True)

            logger.info(f"Hybrid cache hit for request '{request.request_id}': dataset '{best_meta.dataset_id}'.")
            return SatelliteAcquisitionResult(
                request_id=request.request_id,
                status=SatelliteAcquisitionStatus.ACQUIRED,
                provider_id=best_meta.provider_id,
                dataset_metadata=best_meta,
                download_size_bytes=best_entry.raw_reference.size_bytes if best_entry.raw_reference else None,
                cached=True,
                warnings=["Served from EarthMind Satellite Hybrid Acquisition Cache"],
            )

    def invalidate(self, dataset_id: str) -> bool:
        """Evict a specific dataset entry from cache and catalog."""
        with self._lock:
            did = dataset_id.strip()
            if did in self._entries:
                del self._entries[did]
                self._catalog.unregister_dataset(did)
                logger.info(f"Invalidated cache entry for dataset '{did}'.")
                return True
            return False

    def invalidate_provider(self, provider_id: str) -> int:
        """Evict all cached entries belonging to a specific provider."""
        with self._lock:
            to_remove = [did for did, entry in self._entries.items() if entry.metadata.provider_id == provider_id]
            for did in to_remove:
                self.invalidate(did)
            return len(to_remove)

    def purge_expired(self) -> int:
        """Purge all expired cache entries."""
        with self._lock:
            expired = [did for did, entry in self._entries.items() if entry.is_expired]
            for did in expired:
                self.invalidate(did)
            return len(expired)

    def _evict_lru(self) -> None:
        """Evict least recently accessed entries when cache exceeds capacity."""
        if not self._entries:
            return
        sorted_entries = sorted(self._entries.items(), key=lambda item: item[1].last_accessed_ts)
        evict_count = max(1, len(self._entries) - self._max_entries + 10)
        for did, _ in sorted_entries[:evict_count]:
            self.invalidate(did)

    def size(self) -> int:
        """Return number of cached entries."""
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._entries.clear()
            self._catalog.clear()
