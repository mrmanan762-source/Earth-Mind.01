# EarthMind Satellite Intelligence Module — Stage D3: Hybrid Caching & Storage

## 1. Overview
The EarthMind Satellite Module implements a multi-tier hybrid caching and storage strategy:
1. **On-Demand Acquisition**: Queries external satellite provider APIs and fetches scenes dynamically when needed.
2. **Intelligent Caching**: Caches acquired scene metadata and raster pointers with spatial, temporal, and constellation matching.
3. **Historical Data Access**: Enables retrieval and reuse of historical granules from local cache storage without repeating remote network requests.

## 2. Hybrid Acquisition Cache (`modules/satellite/cache.py`)
`SatelliteHybridCache` provides thread-safe in-memory caching of dataset metadata and raw references:
- **Spatial Matching**: Checks whether requested latitude/longitude falls within the cached scene's bounding box, with centroid proximity fallback.
- **Temporal Matching**: Matches requested observation date against cached scene timestamp within a configurable temporal window (default 15 days).
- **Quality & Cloud Matching**: Rejects cached scenes exceeding the caller's `max_cloud_cover_percentage`.
- **Expiration & Eviction**: Enforces configurable TTL (`cache_ttl_seconds`, default 24h). Expired entries are automatically purged upon query. LRU eviction is applied when cache size exceeds `cache_max_entries`.
- **Invalidation**: Supports programmatic invalidation by dataset ID (`invalidate`) and provider ID (`invalidate_provider`).

## 3. Storage Abstraction (`modules/satellite/storage.py`)
Conforming to `ISatelliteCacheStorageAdapter` (Component 8):
- **`InMemorySatelliteStorageAdapter`**: Reference implementation with deep-copy isolation and thread safety. Suitable for testing and development environments.
- **`FilesystemSatelliteStorageAdapter`**: Persistent directory-backed adapter writing raw asset bytes to `raw/`, reference manifests to `metadata/`, and processed containers to `processed/`.
- **Production Safeguards**: `resolve_satellite_storage_adapter` and `Settings.validate_config()` strictly reject in-memory storage in production (`EARTHMIND_ENV=production`), requiring persistent filesystem or external storage.
