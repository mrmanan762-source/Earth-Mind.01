# EarthMind Satellite Intelligence Module — Configuration & Security

> **Stage:** D2 — Core Foundation, Provider Registry & API Adapter Framework
> **Status:** IMPLEMENTED & VERIFIED
> **Settings Model:** `SatelliteConfig` (`core/config/settings.py`)

---

## 1. Centralized Configuration Reference

The Satellite Module configuration is managed via `SatelliteConfig` in `core/config/settings.py`:

| Parameter | Environment Variable | Default | Description |
|---|---|---|---|
| `enabled` | `EARTHMIND_SATELLITE_ENABLED` | `true` | Master enable toggle for the Satellite module |
| `default_timeout` | `EARTHMIND_SATELLITE_DEFAULT_TIMEOUT` | `30.0` | Default timeout in seconds for provider operations |
| `max_retries` | `EARTHMIND_SATELLITE_MAX_RETRIES` | `3` | Maximum retry attempts for transient errors |
| `initial_retry_backoff` | `EARTHMIND_SATELLITE_INITIAL_BACKOFF` | `0.5` | Initial exponential backoff delay in seconds |
| `max_retry_backoff` | `EARTHMIND_SATELLITE_MAX_BACKOFF` | `5.0` | Ceiling delay for backoff retries |
| `max_concurrent_requests` | `EARTHMIND_SATELLITE_MAX_CONCURRENCY` | `5` | Maximum concurrent provider calls |
| `max_cloud_cover_percentage` | `EARTHMIND_SATELLITE_MAX_CLOUD_COVER` | `20.0` | Default cloud cover cutoff threshold |
| `strict_validation` | `EARTHMIND_SATELLITE_STRICT_VALIDATION` | `true` | Enforce strict request schema and boundary checks |
| `nasa_enabled` | `EARTHMIND_SATELLITE_NASA_ENABLED` | `true` | Enable NASA Earthdata provider |
| `isro_enabled` | `EARTHMIND_SATELLITE_ISRO_ENABLED` | `true` | Enable ISRO Bhuvan provider |
| `copernicus_enabled` | `EARTHMIND_SATELLITE_COPERNICUS_ENABLED` | `true` | Enable Copernicus CDSE provider |
| `mock_provider_enabled` | `EARTHMIND_SATELLITE_MOCK_ENABLED` | `false` | Enable deterministic mock provider (dev/test only) |
| `nasa_api_key` | `EARTHMIND_SATELLITE_NASA_API_KEY` | `None` | NASA Earthdata token |
| `isro_api_key` | `EARTHMIND_SATELLITE_ISRO_API_KEY` | `None` | ISRO Bhuvan token |
| `copernicus_client_id` | `EARTHMIND_SATELLITE_COPERNICUS_CLIENT_ID` | `None` | Copernicus CDSE Client ID |
| `copernicus_client_secret` | `EARTHMIND_SATELLITE_COPERNICUS_CLIENT_SECRET` | `None` | Copernicus CDSE Client Secret |

---

## 2. Security Safeguards

### 2.1 Backend-Only Credential Handling
All credentials and tokens are retrieved via backend environment variables and injected into server-side adapters. Credentials are never sent to the client, frontend, or stored in persistent user records.

### 2.2 Secret Masking
`Settings.to_safe_dict()` automatically redacts all Satellite credentials (`nasa_api_key`, `isro_api_key`, `copernicus_client_id`, `copernicus_client_secret`), formatting them as `***` or masked substrings (e.g. `sec***789`). Furthermore, `SatelliteDiagnostics._sanitize_message()` scrubs any token or secret strings from diagnostic logs and exception traces.

### 2.3 Production Environment Safeguards
When `EARTHMIND_ENV=production`, `Settings.validate_config()` enforces:
1. `mock_provider_enabled` must be `False`.
2. Timeouts, retries, and cloud cover bounds must be positive and physically valid.
3. No silent fallback to mock data or test providers is allowed.

### 2.4 Tenant Isolation & Request Boundaries
`SatelliteRequestValidator` verifies `tenant_id` on every request, ensures latitude/longitude lie strictly within physical planetary bounds, verifies bounding box coordinates, and rejects dangerous path traversal sequences (`../`, `..\`) in field, farm, and request identifiers.
