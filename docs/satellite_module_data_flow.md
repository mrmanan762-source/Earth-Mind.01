# EarthMind Satellite Intelligence Module — Data Flow Specification v1.0

> **Status:** Authoritative Specification v1.0
> **Stage:** D1 — Architecture & Contract Lock

---

## 1. End-to-End Satellite Data Pipeline

The data flow within the Satellite Module proceeds through an 8-stage pipeline from external catalog discovery to B2 Context integration:

```
[1. Request & Query Generation]
         │ (SatelliteDataRequest with lat/lon, date range, max cloud cover)
         ▼
[2. Catalog Discovery & Selection]
         │ Queries provider STAC/REST APIs -> discovers candidate granules -> selects optimal scene
         ▼
[3. Secure Acquisition & Ingestion]
         │ Downloads raw raster assets -> checks magic bytes -> creates SatelliteRawDataReference
         ▼
[4. Pre-Validation & Quality Gate]
         │ Verifies raster headers, cloud mask layer, solar geometry, and scene integrity
         ▼
[5. Atmospheric & Geospatial Processing]
         │ BOA surface reflectance calibration -> WGS84 EPSG:4326 reprojection -> field polygon clipping
         ▼
[6. Spectral Analysis & Indicator Extraction]
         │ Computes band statistics -> calculates NDVI / NDWI / NDRE -> assesses uncertainty
         ▼
[7. Evidence Packaging & Validation]
         │ Assembles EarthMindSatelliteEvidence v1.0 -> validates schema constraints
         ▼
[8. B2 Context Integration & Sarvam Reasoning]
         │ Encapsulates as ContextItem -> delivers to B2 Context Manager -> consumed by Sarvam-105B
```

---

## 2. Detailed Data Transformation Stages

### Stage 1: Request & Parameter Normalization
- Downstream triggers (e.g. farmer query about field vigor, scheduled weekly scan) emit a `SatelliteDataRequest`.
- Normalizes lat/lon coordinates, lookback window (default 30 days), and maximum allowable cloud cover (default 20%).

### Stage 2: Multi-Provider Catalog Discovery
- `ISatelliteCatalogDiscovery` queries registered provider adapters (`ISatelliteProviderAdapter`).
- Ranks candidate scenes by:
  1. Temporal proximity to target date.
  2. Cloud cover percentage strictly over the target field.
  3. Processing level (L2A BOA preferred over L1C TOA).
- Returns the optimal `SatelliteDatasetMetadata`.

### Stage 3: Acquisition & Ingestion
- `ISatelliteDataAcquisition` fetches designated band assets (e.g. B02, B03, B04, B08, SCL for Sentinel-2).
- Validates data formats (Cloud-Optimized GeoTIFF, SAFE, NetCDF).
- Computes cryptographic SHA-256 hash and creates `SatelliteRawDataReference`.
- Saves raw assets to isolated cache storage (`ISatelliteCacheStorageAdapter`).

### Stage 4: Pre-Validation & Quality Gate
- Evaluates scene-level quality (`ISatellitePreValidator`).
- If target area is completely obscured by clouds (>80%), marks quality as `CLOUD_OBSCURED`.
- If required bands are missing or corrupted, marks status as `DEGRADED` or raises `SatelliteQualityValidationFailedError`.

### Stage 5: Geospatial Alignment & Atmospheric Processing
- `ISatelliteImageryProcessor` applies Scene Classification Layer (SCL) cloud/shadow masking.
- `ISatelliteGeospatialProcessor` reprojects band coordinates from native UTM zones to canonical WGS84 (`EPSG:4326`).
- Crops rasters to target agricultural field boundary without mutating original data.

### Stage 6: Spectral Analysis & Indicator Extraction
- `ISatelliteSpectralProcessor` calculates per-band summary statistics (mean, min, max, std_dev).
- `ISatelliteIndicatorExtractor` verifies required input bands and computes standard indices:
  - $\text{NDVI} = \frac{\text{NIR} - \text{Red}}{\text{NIR} + \text{Red}}$
  - $\text{NDRE} = \frac{\text{NIR} - \text{RedEdge}}{\text{NIR} + \text{RedEdge}}$
  - $\text{NDWI} = \frac{\text{NIR} - \text{SWIR}}{\text{NIR} + \text{SWIR}}$
- Explicitly attaches mathematical limitations (e.g. saturation at high biomass).

### Stage 7: Evidence Assembly & Schema Validation
- `ISatelliteEvidenceBuilder` aggregates source metadata, spatial coverage, temporal window, indicators, quality ratings, and uncertainty metrics into `EarthMindSatelliteEvidence`.
- `ISatelliteEvidenceValidator` verifies schema version `1.0` and required fields.

### Stage 8: B2 Context Integration
- `ISatelliteB2ContextAdapter` transforms `SatelliteIntegrationResponse` into a `ContextItem` via `to_context_item()`.
- B2 Context Manager applies context deduplication, budgeting, and privacy filtering.
- Delivered to **Sarvam-105B** for grounded agricultural reasoning.

---

## 3. Fail-Closed Policies & Degraded Mode Handling

1. **Cloud Obscuration:**
   - If a scene is cloudy, the system does **not** hallucinate or interpolate vegetation indices.
   - It sets `quality.overall_quality = "CLOUD_OBSCURED"`, flags warnings, and searches for an earlier clear acquisition within the lookback window.
2. **Missing Spectral Bands:**
   - If RedEdge is absent (e.g. on Landsat-8), NDRE is omitted rather than approximated with Red.
   - The indicator is marked unavailable with documented limitations.
3. **Provider Outage:**
   - If primary provider fails, falls back to alternative open-access mirrors (e.g. AWS Open Data Sentinel-2 bucket).
   - If all providers are offline, fails closed with `SatelliteProviderUnavailableError` (retryable).
