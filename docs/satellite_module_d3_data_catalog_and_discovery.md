# EarthMind Satellite Intelligence Module — Stage D3: Data Catalog and Discovery

## 1. Overview
Stage D3 implements the Satellite Data Catalog (`SatelliteDataCatalog`) and the Discovery Engine (`SatelliteDiscoveryEngine`) for the EarthMind Satellite Module. It allows EarthMind to discover, index, and organize satellite imagery across authorized providers (Copernicus CDSE, NASA Earthdata / USGS, and ISRO Bhuvan / Bhoonidhi) without performing premature agricultural reasoning or raster interpretation.

## 2. Satellite Data Catalog (`modules/satellite/catalog.py`)
The `SatelliteDataCatalog` is a thread-safe in-memory and indexed registry of `SatelliteDatasetMetadata` (Contract 3).

### Key Responsibilities
- **Registration**: Registers new dataset metadata records, rejecting duplicates unless `allow_update=True` is explicitly specified.
- **Versioning**: Maintains internal record version numbers that increment upon catalog updates.
- **Spatial & Temporal Querying**: Supports bounding box containment queries (`min_lat <= lat <= max_lat` and `min_lon <= lon <= max_lon`) and observation date lookback window matching.
- **Filtering**: Filters datasets by provider ID, satellite constellation, sensor type, and maximum cloud cover percentage.
- **Attribution & Provenance**: Preserves provider attribution statements and data licensing terms verbatim without synthetic filling.

## 3. Satellite Discovery Engine (`modules/satellite/discovery.py`)
Conforming to protocol `ISatelliteCatalogDiscovery` (Component 3), `SatelliteDiscoveryEngine` queries local catalog indices and active provider adapters to identify available scenes matching a `SatelliteDataRequest`.

### Discovery Workflow
1. **Local Catalog Lookup**: Checks existing catalog records for historical or previously acquired datasets matching the target spatial coordinate and temporal window.
2. **Provider Capability Resolution**: Queries `ProviderCapabilityManager` to filter only providers declaring support for the target constellation and sensor types.
3. **External Adapter Search**: Queries eligible provider adapters (`search_catalog`), catching transient timeouts or errors without failing the overall discovery process.
4. **Cloud Cover Filtering**: Prunes candidate scenes exceeding `max_cloud_cover_percentage`.
5. **Optimal Dataset Selection**: `select_optimal_dataset` deterministically scores candidates based on:
   - Cloud cover percentage (primary factor)
   - Temporal proximity to requested observation timestamp
   - Surface reflectance preference (favoring Level-2A BOA over Level-1C TOA)
   - Spatial resolution fidelity
