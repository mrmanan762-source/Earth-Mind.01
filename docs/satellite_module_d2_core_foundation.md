# EarthMind Satellite Intelligence Module — Stage D2 Core Foundation

> **Stage:** D2 — Core Foundation, Provider Registry & API Adapter Framework
> **Status:** IMPLEMENTED & VERIFIED
> **Primary Intelligence Model:** Sarvam-105B
> **Layer:** Layer 1 (Satellite Data Access) & Layer 2 (Ingestion & Management Foundations)

---

## 1. Overview & Objectives

Stage D2 establishes the operational, testable software foundation for the EarthMind Satellite Intelligence Module, converting the architecture locked in Stage D1 into functional services without prematurely implementing later-stage processing or making live third-party network downloads.

Key responsibilities delivered in D2:
1. **Centralized Configuration:** Managed through `SatelliteConfig` in `core/config/settings.py` with environment variable bindings, positive timeout/retry validation, and secret masking in `to_safe_dict()`.
2. **Deterministic Lifecycle Management:** `SatelliteLifecycleTracker` and `SatelliteLifecycleManager` in `modules/satellite/lifecycle.py` enforcing clean state transitions (`INITIALIZED`, `STARTING`, `RUNNING`, `STOPPING`, `STOPPED`, `FAILED`), startup/shutdown hooks, and failure isolation.
3. **Provider Registry:** `SatelliteProviderRegistry` in `modules/satellite/registry.py` conforming to `ISatelliteProviderRegistry`, preventing duplicate provider IDs and controlling availability statuses (`ACTIVE`, `UNAVAILABLE`).
4. **Provider Capability Management:** `ProviderCapabilityManager` in `modules/satellite/capabilities.py` evaluating optical, multispectral, SAR/radar, thermal, numerical, geospatial, and temporal dataset coverage without fabricating capabilities.
5. **Provider Adapter Framework:** `BaseSatelliteProviderAdapter` in `modules/satellite/adapters.py` conforming to `ISatelliteProviderAdapter`, featuring bounded retries with exponential backoff and error normalization into specialized `SatelliteError` subclasses.
6. **Provider Extension Points:** Stubs for NASA (`NasaEarthdataAdapter`), ISRO/NRSC (`IsroBhuvanAdapter`), and Copernicus CDSE (`CopernicusCdseAdapter`), plus a deterministic `MockSatelliteProviderAdapter` for local testing.
7. **Request Validation:** `SatelliteRequestValidator` in `modules/satellite/request_validator.py` executing defensive checks across geospatial coordinates, bounding boxes, temporal windows, and sensor categories.
8. **Foundational Diagnostics:** `SatelliteDiagnostics` in `modules/satellite/diagnostics.py` conforming to `ISatelliteDiagnostics` with sanitized error histories and operational metrics.
9. **Service & Module Wiring:** `SatelliteService` and `SatelliteModule` integrated into `app/main.py` lifecycle bootstrap.

---

## 2. Core Components

| Component | File | Interface / Protocol | Responsibilities |
|---|---|---|---|
| `SatelliteConfig` | `core/config/settings.py` | Pydantic `BaseModel` | Central configuration, timeout, retry policy, secret masking |
| `SatelliteLifecycleManager` | `modules/satellite/lifecycle.py` | Internal Manager | Lifecycle state transitions, hooks, duplicate init prevention |
| `SatelliteProviderRegistry` | `modules/satellite/registry.py` | `ISatelliteProviderRegistry` | Central provider registry, enable/disable toggling, duplicate check |
| `ProviderCapabilityManager` | `modules/satellite/capabilities.py` | Internal Manager | Granular capability profiling and filter resolution |
| `BaseSatelliteProviderAdapter` | `modules/satellite/adapters.py` | `ISatelliteProviderAdapter` | Standard adapter base with retry and error normalization |
| `SatelliteRequestValidator` | `modules/satellite/request_validator.py` | Internal Validator | Validates `SatelliteDataRequest` bounds, timestamps, and parameters |
| `SatelliteDiagnostics` | `modules/satellite/diagnostics.py` | `ISatelliteDiagnostics` | Health reporting, operational counters, secret-sanitized logs |
| `SatelliteService` | `modules/satellite/satellite_service.py` | Internal Service | Orchestrates validation, discovery, and adapter dispatch |
| `SatelliteModule` | `modules/satellite/satellite_module.py` | `ModuleInterface` | Lifecycle hooks and application workflow dispatch |
