"""Satellite Data Catalog for EarthMind Satellite Module (Stage D3).

Maintains normalized metadata for discoverable and acquired satellite datasets.
Tracks:
- Granule / scene identity (`dataset_id`)
- Provider identity (`provider_id`)
- Geographic coverage (`SatelliteGeospatialMetadata`)
- Temporal coverage (`SatelliteTemporalMetadata`)
- Sensor types, constellations, and platforms
- Available spectral bands and data formats
- Cloud cover and preliminary data quality
- Licensing and mandatory attribution
- Metadata versioning and provenance
"""

import threading
import time
from typing import Any, Dict, List, Optional

from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteDatasetMetadata,
    SatelliteGeospatialMetadata,
    SatelliteSensorType,
    SatelliteTemporalMetadata,
)
from modules.satellite.errors import (
    SatelliteDatasetNotFoundError,
    SatelliteInvalidArgumentError,
)

logger = get_logger("modules.satellite.catalog")


class CatalogRecord:
    """Internal container for catalog entry with versioning and registration lineage."""

    def __init__(self, metadata: SatelliteDatasetMetadata, version: int = 1):
        self.metadata = metadata
        self.version = version
        self.registered_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.updated_at = self.registered_at


class SatelliteDataCatalog:
    """
    Thread-safe catalog for discovering, indexing, and retrieving
    normalized satellite dataset metadata records.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._records: Dict[str, CatalogRecord] = {}

    def register_dataset(
        self,
        metadata: SatelliteDatasetMetadata,
        allow_update: bool = False,
    ) -> bool:
        """
        Register a new dataset metadata record in the catalog.

        Args:
            metadata: SatelliteDatasetMetadata contract.
            allow_update: If True, increments version on collision; if False, rejects duplicate.

        Returns:
            bool indicating whether registration or update was successful.
        """
        if not metadata or not metadata.dataset_id or not metadata.dataset_id.strip():
            raise SatelliteInvalidArgumentError(
                details="Cannot register dataset with empty or invalid dataset_id.",
                operation="register_dataset",
            )

        with self._lock:
            did = metadata.dataset_id.strip()
            if did in self._records:
                if not allow_update:
                    logger.warning(f"Dataset '{did}' is already registered in catalog; duplicate rejected.")
                    return False

                # Update existing record and increment version
                current = self._records[did]
                new_version = current.version + 1
                rec = CatalogRecord(metadata=metadata.model_copy(deep=True), version=new_version)
                rec.registered_at = current.registered_at
                self._records[did] = rec
                logger.info(f"Updated dataset '{did}' in catalog to version {new_version}.")
                return True

            # Register fresh record
            self._records[did] = CatalogRecord(metadata=metadata.model_copy(deep=True), version=1)
            logger.info(f"Registered new dataset '{did}' in satellite catalog.")
            return True

    def get_dataset(self, dataset_id: str) -> Optional[SatelliteDatasetMetadata]:
        """Retrieve dataset metadata by unique granule/scene ID."""
        if not dataset_id or not dataset_id.strip():
            return None
        with self._lock:
            rec = self._records.get(dataset_id.strip())
            return rec.metadata.model_copy(deep=True) if rec else None

    def get_dataset_version(self, dataset_id: str) -> Optional[int]:
        """Retrieve the catalog version number of a registered dataset."""
        if not dataset_id or not dataset_id.strip():
            return None
        with self._lock:
            rec = self._records.get(dataset_id.strip())
            return rec.version if rec else None

    def list_datasets(
        self,
        provider_id: Optional[str] = None,
        constellation: Optional[str] = None,
        sensor_type: Optional[SatelliteSensorType] = None,
        max_cloud_cover: Optional[float] = None,
    ) -> List[SatelliteDatasetMetadata]:
        """List registered datasets matching optional filters."""
        with self._lock:
            results = []
            for rec in self._records.values():
                meta = rec.metadata
                if provider_id and meta.provider_id != provider_id:
                    continue
                if constellation and meta.constellation != constellation:
                    continue
                if sensor_type and meta.sensor_type != sensor_type:
                    continue
                if max_cloud_cover is not None and meta.cloud_cover_percentage > max_cloud_cover:
                    continue
                results.append(meta.model_copy(deep=True))
            return results

    def search_spatial_temporal(
        self,
        latitude: float,
        longitude: float,
        target_date: Optional[str] = None,
        lookback_days: int = 30,
        max_cloud_cover: float = 20.0,
        constellations: Optional[List[str]] = None,
    ) -> List[SatelliteDatasetMetadata]:
        """
        Search catalog for datasets covering a geographic point and temporal window.
        """
        with self._lock:
            matches: List[SatelliteDatasetMetadata] = []
            target_ts = None
            if target_date:
                try:
                    # Parse target date timestamp
                    target_ts = time.mktime(time.strptime(target_date.split("T")[0], "%Y-%m-%d"))
                except Exception:
                    pass

            for rec in self._records.values():
                meta = rec.metadata

                # 1. Cloud cover check
                if meta.cloud_cover_percentage > max_cloud_cover:
                    continue

                # 2. Constellation filter
                if constellations and meta.constellation not in constellations:
                    continue

                # 3. Spatial check: point in scene bounding box or within approximate distance
                geo = meta.geospatial
                if geo.bounding_box:
                    min_lon, min_lat, max_lon, max_lat = geo.bounding_box
                    if not (min_lat <= latitude <= max_lat and min_lon <= longitude <= max_lon):
                        continue
                else:
                    # Centroid proximity fallback (~0.5 degrees roughly 55km)
                    if abs(geo.latitude - latitude) > 0.5 or abs(geo.longitude - longitude) > 0.5:
                        continue

                # 4. Temporal check
                if target_ts is not None:
                    try:
                        acq_date_str = meta.temporal.acquisition_date.split("T")[0]
                        acq_ts = time.mktime(time.strptime(acq_date_str, "%Y-%m-%d"))
                        diff_days = abs(target_ts - acq_ts) / 86400.0
                        if diff_days > lookback_days:
                            continue
                    except Exception:
                        pass

                matches.append(meta.model_copy(deep=True))

            # Sort matches: lowest cloud cover first, then closest temporally
            matches.sort(key=lambda m: m.cloud_cover_percentage)
            return matches

    def unregister_dataset(self, dataset_id: str) -> bool:
        """Remove a dataset from the catalog."""
        with self._lock:
            did = dataset_id.strip()
            if did in self._records:
                del self._records[did]
                logger.info(f"Unregistered dataset '{did}' from catalog.")
                return True
            return False

    def count(self) -> int:
        """Return total number of registered datasets."""
        with self._lock:
            return len(self._records)

    def clear(self) -> None:
        """Clear all registered catalog records."""
        with self._lock:
            self._records.clear()
