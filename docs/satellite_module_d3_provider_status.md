# EarthMind Satellite Intelligence Module — Stage D3: Provider Status & Verification

## 1. Provider Ecosystem Overview
EarthMind integrates with three approved primary Earth observation providers, alongside a deterministic mock adapter for testing.

| Provider | Provider ID | Protocol | Supported Constellations | Supported Sensor Types | Formats | Auth Requirements | Live Verification Status |
|---|---|---|---|---|---|---|---|
| **Copernicus CDSE** | `copernicus_cdse` | STAC API / OData | Sentinel-1, Sentinel-2, Sentinel-3 | Multispectral, SAR, Thermal | SAFE, COG, GeoTIFF | Client ID & Client Secret | Adapter Ready (Live calls require CDSE credentials) |
| **NASA Earthdata** | `nasa_earthdata` | CMR / REST | Landsat-8, Landsat-9, MODIS | Multispectral, Thermal | GeoTIFF, COG, HDF5 | API Bearer Token | Adapter Ready (Live calls require NASA API key) |
| **ISRO Bhuvan / Bhoonidhi** | `isro_bhuvan` | REST API | Resourcesat-2A, Cartosat-2, RISAT-1A | Multispectral, SAR | GeoTIFF, Raw Binary | API Token | Adapter Ready (Live calls require ISRO API key) |
| **Deterministic Mock** | `mock_satellite_provider` | In-Memory | Mock-Sentinel, Mock-Sat-1 | Multispectral, Thermal | COG, GeoTIFF, JSON | None | **VERIFIED** (Active for unit tests & offline development; blocked in production) |

## 2. Authentication and Security Governance
- All credentials are read strictly from backend environment variables:
  - `EARTHMIND_SATELLITE_COPERNICUS_CLIENT_ID`
  - `EARTHMIND_SATELLITE_COPERNICUS_CLIENT_SECRET`
  - `EARTHMIND_SATELLITE_NASA_API_KEY`
  - `EARTHMIND_SATELLITE_ISRO_API_KEY`
- Credentials are masked with `***` in `Settings.to_safe_dict()` and in all diagnostics logs.
- In production, `mock_provider_enabled = True` is rejected by `Settings.validate_config()`.

## 3. Mandatory Attribution Statements
- **Copernicus CDSE**: `"Contains modified Copernicus Sentinel data [2025] processed by EarthMind"`
- **NASA / USGS**: `"NASA EOSDIS / USGS Earth Resources Observation and Science (EROS) Center"`
- **ISRO / NRSC**: `"Indian Space Research Organisation (ISRO) / National Remote Sensing Centre (NRSC)"`
