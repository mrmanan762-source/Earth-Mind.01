# EarthMind Satellite Intelligence Module — Provider Registry & Capability Manager

> **Stage:** D2 — Core Foundation, Provider Registry & API Adapter Framework
> **Status:** IMPLEMENTED & VERIFIED
> **Interfaces:** `ISatelliteProviderRegistry` (`core/interfaces/satellite.py`)

---

## 1. Provider Registry Architecture

The `SatelliteProviderRegistry` (`modules/satellite/registry.py`) serves as the single source of truth for all satellite data sources connected to EarthMind.

### 1.1 Registry Operations

```python
registry = SatelliteProviderRegistry(capability_manager=cap_mgr)

# Register provider manifest
registry.register_provider(provider_manifest)

# Lookup
provider = registry.get_provider("copernicus_cdse")
is_avail = registry.is_provider_available("copernicus_cdse")

# Administrative Controls
registry.disable_provider("copernicus_cdse", reason="Maintenance window")
registry.enable_provider("copernicus_cdse")

# Filtering
active_providers = registry.list_providers(status="ACTIVE")
```

### 1.2 Registration Invariants
- **Duplicate Prevention:** Registering an existing `provider_id` raises `SatelliteProviderError` unless explicitly configured with `allow_overwrite=True`.
- **Manifest Completeness:** Every registered provider must declare supported constellations, supported sensor categories, supported formats, and non-empty `attribution_text`.
- **Decoupled API Logic:** The registry stores provider manifests and tracks operational status (`ACTIVE`, `UNAVAILABLE`, `DEGRADED`, etc.); it contains zero provider-specific API implementation details.

---

## 2. Provider Capability Manager

The `ProviderCapabilityManager` (`modules/satellite/capabilities.py`) provides fine-grained discovery and validation of provider capabilities.

### 2.1 Capability Dimensions
The capability profile evaluates:
1. **Sensor Categories:** `OPTICAL_MULTISPECTRAL`, `OPTICAL_HYPERSPECTRAL`, `SYNTHETIC_APERTURE_RADAR`, `THERMAL_INFRARED`, `ALTIMETER`, `ATMOSPHERIC_SOUNDER`.
2. **Constellation Coverage:** Sentinel-1, Sentinel-2, Landsat-8/9, Resourcesat-2A, MODIS, etc.
3. **Packaging Formats:** COG, GeoTIFF, SAFE, NetCDF, HDF5, JSON.
4. **Data Categories:** Optical, SAR, Thermal, Numerical, and Historical observations.

### 2.2 Capability Queries
```python
# Check individual capabilities
cap_mgr.supports_sensor_type("copernicus_cdse", SatelliteSensorType.SYNTHETIC_APERTURE_RADAR)  # True
cap_mgr.supports_constellation("nasa_earthdata", "Landsat-9")                                    # True

# Discover eligible providers for incoming request criteria
eligible = cap_mgr.list_capable_providers(
    sensor_type=SatelliteSensorType.OPTICAL_MULTISPECTRAL,
    constellation="Sentinel-2",
    data_format=SatelliteDataFormat.COG,
)
```
No capability is advertised unless explicitly verified and declared in the provider's registered manifest.
