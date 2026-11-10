# EarthMind Satellite Intelligence Module — Stage D3: Data Acquisition

## 1. Overview
The Data Acquisition subsystem in Stage D3 coordinates the acquisition of satellite assets from remote providers, managing request states, timeouts, bounded retries, and result normalization into standardized `SatelliteAcquisitionResult` contracts.

## 2. Acquisition Engine (`modules/satellite/acquisition.py`)
Conforming to `ISatelliteDataAcquisition` (Component 4), the `SatelliteDataAcquisitionEngine` orchestrates the complete acquisition pipeline:
1. **Cache Pre-Check**: Queries `SatelliteHybridCache` using spatial coordinates, observation date, and constellation constraints. Returns cache hits with `cached=True` immediately.
2. **Catalog Discovery**: Dispatches to `SatelliteDiscoveryEngine` if not cached.
3. **Scene Selection**: Selects the optimal dataset granule from discovered candidates.
4. **Provider Fetch**: Invokes `acquire_dataset` on the responsible `BaseSatelliteProviderAdapter` instance.
5. **Raw Asset Ingestion**: Pipes downloaded raster bytes into `SatelliteIngestionEngine`, persisting payload bytes into storage and generating an immutable `SatelliteRawDataReference`.
6. **Cache & Catalog Update**: Indexes the newly acquired dataset into `SatelliteDataCatalog` and `SatelliteHybridCache`.
7. **Result Assembly**: Emits a standardized `SatelliteAcquisitionResult` with status `ACQUIRED`.

## 3. Request Lifecycle Manager (`modules/satellite/request_manager.py`)
Tracks state transitions for all incoming satellite operations with an explicit transition graph:
- `PENDING -> DISCOVERING -> DISCOVERED -> ACQUIRING -> ACQUIRED -> INGESTING -> COMPLETED`
- Direct transition `PENDING -> COMPLETED` on cache hit.
- Terminal error states: `FAILED` and `CANCELLED`.
- Validates against invalid or illegal state transitions (raising `SatelliteProcessingError`).
- Enforces concurrency throttles (`max_concurrent_requests`) to prevent provider quota exhaustion.
- Preserves tenant isolation via immutable `tenant_id` tracking.
