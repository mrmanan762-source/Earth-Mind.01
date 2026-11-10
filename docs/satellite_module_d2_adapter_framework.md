# EarthMind Satellite Intelligence Module — API Adapter Framework

> **Stage:** D2 — Core Foundation, Provider Registry & API Adapter Framework
> **Status:** IMPLEMENTED & VERIFIED
> **Interfaces:** `ISatelliteProviderAdapter` (`core/interfaces/satellite.py`)

---

## 1. Adapter Abstraction & Resilience

All satellite data providers interface with EarthMind through the `BaseSatelliteProviderAdapter` abstract class (`modules/satellite/adapters.py`).

### 1.1 Core Responsibilities
- **Standardized Contract:** Exposes `provider_id`, `provider_name`, `timeout`, `search_catalog(request)`, and `acquire_dataset(dataset_id, request)`.
- **Bounded Exponential Backoff Retries:** Automatically handles transient network dropouts and timeouts using `execute_with_retry()` with configurable backoff factor and jitter.
- **Error Normalization:** Translates underlying network and driver exceptions into typed, structured EarthMind exceptions:
  - `TimeoutError` $\rightarrow$ `SatelliteTimeoutError`
  - `ConnectionError` / `OSError` $\rightarrow$ `SatelliteProviderUnavailableError`
  - Unhandled exceptions $\rightarrow$ `SatelliteProviderError`

---

## 2. Implemented Provider Extension Points

### 2.1 NASA Earthdata Adapter (`NasaEarthdataAdapter`)
- **Target Constellations:** Landsat-8, Landsat-9, MODIS-Terra, MODIS-Aqua.
- **Sensor Types:** `OPTICAL_MULTISPECTRAL`, `THERMAL_INFRARED`.
- **Access Protocol:** REST API (CMR Search).
- **Attribution:** NASA EOSDIS / USGS EROS Center.
- **Stage D2 Status:** Extension point established. Ready for live STAC/CMR client integration in Stage D3.

### 2.2 ISRO Bhuvan Adapter (`IsroBhuvanAdapter`)
- **Target Constellations:** Resourcesat-2A, Cartosat-2, RISAT-1A (EOS-04).
- **Sensor Types:** `OPTICAL_MULTISPECTRAL`, `SYNTHETIC_APERTURE_RADAR`.
- **Access Protocol:** REST API.
- **Attribution:** Indian Space Research Organisation (ISRO) / National Remote Sensing Centre (NRSC).
- **Stage D2 Status:** Extension point established. Ready for Bhoonidhi API client integration in Stage D3.

### 2.3 Copernicus CDSE Adapter (`CopernicusCdseAdapter`)
- **Target Constellations:** Sentinel-1, Sentinel-2, Sentinel-3.
- **Sensor Types:** `OPTICAL_MULTISPECTRAL`, `SYNTHETIC_APERTURE_RADAR`, `THERMAL_INFRARED`.
- **Access Protocol:** STAC API / OData.
- **Attribution:** Contains modified Copernicus Sentinel data [2025] processed by EarthMind.
- **Stage D2 Status:** Extension point established. Ready for CDSE STAC client integration in Stage D3.

---

## 3. Deterministic Mock Provider Adapter

`MockSatelliteProviderAdapter` provides a controlled, deterministic simulation environment for test suites and offline local development:
- Clearly flags all generated metadata and acquisition results with `is_mock = True` and attribution `"Mock data for testing only - Not real satellite observations"`.
- Supports simulating provider timeouts, transient errors, and specific sensor categories.
- **Production Guard:** Strictly rejected in production environments (`EARTHMIND_ENV=production`). Attempting to start EarthMind with `mock_provider_enabled = True` in production raises a fatal `ConfigurationError`.
