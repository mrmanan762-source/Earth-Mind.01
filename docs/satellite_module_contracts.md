# EarthMind Satellite Intelligence Module — Data Contracts Specification v1.0

> **Status:** Founder-Approved Contract Specification v1.0
> **Schema Version:** 1.0
> **Stage:** D1 — Architecture & Contract Lock

---

## 1. Overview & Core Contract Principles

The EarthMind Satellite Intelligence Module operates on formally specified, versioned, machine-readable data contracts defined in `core/schemas/satellite.py`.

Key design principles:
- **Immutability and Provenance:** Source dataset IDs, provider identity, collection timestamps, and processing steps are permanently recorded.
- **Fail-Closed Processing:** Uncalibrated bands, excessive cloud obscuration, or missing coordinates result in explicit status flags (`DEGRADED`, `CLOUD_OBSCURED`, `INCOMPLETE`) rather than hallucinated or silently interpolated values.
- **Strict B2 Context Decoupling:** Output artifacts cleanly convert into standard `ContextItem` representations without requiring direct knowledge of Sarvam-105B prompt templates.

---

## 2. Core Enumerations

| Enumeration | Allowed Values | Description |
| :--- | :--- | :--- |
| `SatelliteProviderStatus` | `ACTIVE`, `DEGRADED`, `MAINTENANCE`, `UNAVAILABLE`, `DEPRECATED` | Operational health of data providers. |
| `SatelliteAcquisitionStatus` | `PENDING`, `SEARCHING`, `FOUND`, `DOWNLOADING`, `ACQUIRED`, `NOT_FOUND`, `FAILED`, `CANCELLED` | Lifecycle state of image acquisition. |
| `SatelliteProcessingStatus` | `PENDING`, `PREPROCESSING`, `PROCESSED`, `CALIBRATED`, `FAILED`, `SKIPPED` | Status of data processing pipeline. |
| `SatelliteDataQuality` | `EXCELLENT`, `GOOD`, `ACCEPTABLE`, `DEGRADED`, `CLOUD_OBSCURED`, `INCOMPLETE`, `INVALID` | Quality classification of observations. |
| `SatelliteEvidenceStatus` | `SUCCESS`, `PARTIAL`, `DEGRADED`, `REJECTED`, `FAILED` | Final status of generated evidence artifact. |
| `SatelliteSensorType` | `OPTICAL_MULTISPECTRAL`, `OPTICAL_HYPERSPECTRAL`, `SYNTHETIC_APERTURE_RADAR`, `THERMAL_INFRARED`, `ALTIMETER`, `RADIOMETER`, `ATMOSPHERIC_SOUNDER`, `OTHER` | Earth observation sensor taxonomy. |
| `SatelliteBandType` | `COASTAL_AEROSOL`, `BLUE`, `GREEN`, `RED`, `RED_EDGE_1`, `RED_EDGE_2`, `RED_EDGE_3`, `NIR`, `NIR_NARROW`, `WATER_VAPOUR`, `SWIR_1`, `SWIR_2`, `THERMAL_1`, `THERMAL_2`, `SAR_VV`, `SAR_VH`, `SAR_HH`, `SAR_HV`, `OTHER` | Standardized spectral band classifications. |
| `SatelliteDataFormat` | `GEOTIFF`, `COG`, `NETCDF`, `HDF5`, `SAFE`, `ZARR`, `JSON`, `GEOJSON`, `CSV`, `RAW_BINARY` | Supported raster and tabular formats. |
| `SatelliteErrorCode` | 18 standardized error codes (see Section 6) | Module-specific error classification. |

---

## 3. Core Versioned Contracts

### 3.1 Contract 1: `SatelliteDataRequest`
Specifies criteria for finding and acquiring satellite observations:
- `request_id`: Unique request identifier.
- `tenant_id`, `farmer_id`, `farm_id`, `field_id`: Scoping identifiers.
- `geospatial`: Target centroid, optional bounding box, and CRS.
- `temporal_window`: Target acquisition date, start/end range, and revisit expectations.
- `target_constellations`: Preferred satellite systems (e.g. `["Sentinel-2", "Landsat-8/9"]`).
- `sensor_types`: Sensor categories required.
- `requested_bands` & `requested_indicators`: Explicit spectral bands or indices desired.
- `max_cloud_cover_percentage`: Filtering threshold for acceptable cloud cover (default 20%).
- `prefer_calibrated`: Preference for surface reflectance (L2A) vs top-of-atmosphere (L1C).

### 3.2 Contract 2: `SatelliteProvider`
Hardware and API capabilities of registered satellite data providers:
- `provider_id`, `provider_name`, `status`: Identity and operational state.
- `supported_constellations`, `supported_sensor_types`, `supported_formats`: Technical coverage.
- `access_protocol`: Access mechanism (`STAC_API`, `REST_API`, `AWS_S3_BUCKET`).
- `requires_authentication` & `credential_key_env_var`: Backend-only credential management.
- `rate_limit_requests_per_minute`: Provider API rate limit.
- `license_type` & `attribution_text`: Licensing classification and mandatory attribution string.

### 3.3 Contract 3: `SatelliteDatasetMetadata`
Catalog metadata for a discovered or acquired scene/granule:
- `dataset_id`, `provider_id`, `constellation`, `platform`, `instrument`, `sensor_type`, `processing_level`.
- `geospatial`: Centroid, bounding box, spatial resolution in meters.
- `temporal`: Acquisition date/time, revisit interval.
- `cloud_cover_percentage`, `snow_ice_percentage`, `sun_elevation_degrees`, `sun_azimuth_degrees`.
- `available_bands`: List of `SatelliteSpectralBand` metadata descriptors.
- `data_format`, `quality_status`, `license_attribution`, `raw_reference_uri`.

### 3.4 Contract 4: `SatelliteAcquisitionResult`
Result of catalog search and asset download:
- `acquisition_id`, `request_id`, `status`, `provider_id`.
- `dataset_metadata`: Discovered/acquired scene metadata.
- `acquired_at`, `download_size_bytes`, `cached`, `warnings`, `error_message`.

### 3.5 Contract 5: `SatelliteRawDataReference`
Pointer to stored raw satellite assets:
- `reference_id`, `dataset_id`, `provider_id`, `storage_uri`, `data_format`, `size_bytes`, `sha256_hash`, `retention_expires_at`, `created_at`.

### 3.6 Contract 6: `SatelliteProcessedData`
Calibrated and georeferenced raster band arrays:
- `processed_id`, `dataset_id`, `field_id`, `processing_status`, `processing_pipeline`, `engine_version`.
- `processed_bands`: Calibrated bands indexed by band name.
- `geospatial`, `temporal`, `quality_status`.
- `atmospheric_correction_applied`, `cloud_mask_applied`, `cloud_coverage_over_target`.
- `provenance`, `warnings`.

### 3.7 Contract 7: `SatelliteIndicator`
Calculated agricultural vegetation or moisture index:
- `indicator_id`, `indicator_name` (e.g. `NDVI`, `NDRE`, `NDWI`).
- `definition`: Formal agronomic definition.
- `calculation_method`: Formula used (e.g. `(NIR - Red) / (NIR + Red)`).
- `required_bands`: Band names required for valid calculation.
- `source_dataset_id`: Lineage link.
- `result_statistics`: Summary statistics (`mean`, `min`, `max`, `std_dev`, `median`, `p25`, `p75`).
- `unit`: Measurement unit (default `unitless_ratio`).
- `quality_status`, `limitations`, `warnings`.

---

## 4. Primary Output Contract v1.0: `EarthMindSatelliteEvidence`

The authoritative output contract consumed by downstream reasoning and context systems:

```json
{
  "contract_name": "EarthMindSatelliteEvidence",
  "schema_version": "1.0",
  "evidence_id": "ev_sat_4f7e2a91b3c0",
  "source": {
    "provider_id": "copernicus_cdse",
    "constellation": "Sentinel-2",
    "platform": "Sentinel-2B",
    "instrument": "MSI",
    "sensor_type": "OPTICAL_MULTISPECTRAL",
    "dataset_id": "S2B_MSIL2A_20250328T051649_N0511_R062_T43REQ_20250328T073610",
    "processing_level": "LEVEL-2A"
  },
  "scope": {
    "tenant_id": "tenant_icar_01",
    "farmer_id": "farmer_10842",
    "farm_id": "farm_karnal_01",
    "field_id": "field_wheat_zone_02",
    "crop": "Wheat"
  },
  "geospatial": {
    "latitude": 29.6857,
    "longitude": 76.9905,
    "bounding_box": [76.9850, 29.6800, 76.9960, 29.6910],
    "crs": "EPSG:4326",
    "spatial_resolution_meters": 10.0,
    "coverage_area_hectares": 12.4
  },
  "temporal": {
    "acquisition_date": "2025-03-28T05:16:49Z",
    "revisit_interval_days": 5.0,
    "temporal_coverage_type": "SCENE_INSTANTANEOUS"
  },
  "indicators": [
    {
      "indicator_id": "sat_ind_01a",
      "indicator_name": "NDVI",
      "definition": "Normalized Difference Vegetation Index: (NIR - Red) / (NIR + Red)",
      "calculation_method": "standard_band_ratio",
      "required_bands": ["RED", "NIR"],
      "source_dataset_id": "S2B_MSIL2A_20250328T051649_N0511_R062_T43REQ_20250328T073610",
      "result_statistics": {
        "mean": 0.76,
        "min": 0.42,
        "max": 0.86,
        "std_dev": 0.08,
        "median": 0.77
      },
      "unit": "unitless_ratio",
      "quality_status": "EXCELLENT",
      "limitations": [
        "Saturates at high biomass (LAI > 4)"
      ]
    }
  ],
  "band_summaries": {
    "RED": {"mean": 0.065, "min": 0.032, "max": 0.145},
    "NIR": {"mean": 0.485, "min": 0.220, "max": 0.590}
  },
  "quality": {
    "overall_quality": "EXCELLENT",
    "cloud_cover_percentage": 1.2,
    "is_atmospheric_corrected": true,
    "resolution_fidelity": "NATIVE",
    "evidence_completeness": "COMPLETE"
  },
  "uncertainty": {
    "spatial_confidence": 0.98,
    "temporal_confidence": 0.95,
    "spectral_confidence": 0.96,
    "overall_confidence": 0.96,
    "uncertainty_sources": []
  },
  "license_attribution": "Contains modified Copernicus Sentinel data (2025), processed by EarthMind",
  "provenance": {
    "granule_sha256": "8f3b2...a9c",
    "pipeline": "standard_satellite_pipeline_v1"
  },
  "warnings": [],
  "limitations": [
    "Macro 10m resolution cannot detect individual leaf symptoms; indicates aggregate canopy vigor"
  ],
  "status": "SUCCESS"
}
```

---

## 5. Integration Contracts (B2 / Sarvam Bridge)

`SatelliteIntegrationResponse` wraps `EarthMindSatelliteEvidence` and provides the canonical `to_context_item()` method:
- Maps evidence into standard `ContextItem`.
- `entity_type`: `"satellite_evidence"`.
- `entity_id`: Field ID or evidence ID.
- `data_type`: `"satellite_observation"`.
- `privacy_level`: `PrivacyLevel.FARM_PRIVATE`.
- `bounded_token_estimate`: 350 tokens.
- `confidence`: Matched to `uncertainty.overall_confidence`.

---

## 6. Structured Error Contract (`SatelliteErrorContract`)

18 standardized error codes conforming to `ErrorContract`:
`INVALID_ARGUMENT`, `PROVIDER_ERROR`, `PROVIDER_UNAVAILABLE`, `DATASET_UNAVAILABLE`, `DATASET_NOT_FOUND`, `UNSUPPORTED_FORMAT`, `INGESTION_FAILED`, `INVALID_METADATA`, `PROCESSING_FAILED`, `INSUFFICIENT_DATA`, `QUALITY_VALIDATION_FAILED`, `INDICATOR_PROCESSING_FAILED`, `EVIDENCE_VALIDATION_FAILED`, `STORAGE_UNAVAILABLE`, `STORAGE_ERROR`, `TIMEOUT`, `INTEGRATION_ERROR`, `INTERNAL_ERROR`.
