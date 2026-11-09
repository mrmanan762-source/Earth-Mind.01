# EarthMind Satellite Intelligence Module — Security, Privacy & Data Governance

> **Status:** Authoritative Specification v1.0
> **Stage:** D1 — Architecture & Contract Lock

---

## 1. Threat Model & Security Principles

The Satellite Intelligence Module handles untrusted external network responses, large raster binaries, and farmer geospatial location metadata. It adheres to EarthMind's core security rules:

1. **Backend-Only Credential Isolation:**
   - Satellite provider credentials (e.g., Copernicus Data Space API secrets, NASA Earthdata tokens) are managed strictly via environment variables (e.g. `EARTHMIND_SATELLITE_COPERNICUS_SECRET`).
   - Credentials are never logged, returned in API responses, or exposed to the frontend or mobile clients.
   - `Settings.to_safe_dict()` masks all satellite credentials.

2. **Tenant Isolation & Multi-Farmer Privacy:**
   - Every satellite request and evidence payload carries `tenant_id` and optional `farmer_id`/`field_id`.
   - Field coordinates and bounding boxes are classified as `PrivacyLevel.FARM_PRIVATE`.
   - Data belonging to one farmer is never exposed or shared with another farmer.

3. **Untrusted Data Sanitization:**
   - External provider manifests and raster bytes are treated as untrusted inputs.
   - Bounding boxes, coordinates, and pixel matrices are validated against strict physical limits (-90 to +90 lat, -180 to +180 lon, reflectance 0.0 to 1.0).
   - Decompression bombing and oversized raster payload protections are enforced during ingestion.

---

## 2. Licensing & Provider Attribution Governance

Satellite data comes from government space agencies with strict open-access licensing terms:

| Constellation | Provider / Agency | License Classification | Mandatory Attribution |
| :--- | :--- | :--- | :--- |
| **Sentinel-1 / Sentinel-2** | ESA / Copernicus CDSE | Free, full and open license | *"Contains modified Copernicus Sentinel data ([Year]), processed by EarthMind"* |
| **Landsat-8 / Landsat-9** | USGS / NASA | Public Domain | *"USGS/NASA Landsat data courtesy of the U.S. Geological Survey"* |
| **MODIS** | NASA LP DAAC | NASA Open Access | *"NASA LP DAAC, processed by EarthMind"* |
| **Resourcesat / Cartosat** | ISRO / NRSC | National Open Access | *"Data courtesy National Remote Sensing Centre (NRSC), ISRO"* |

Every `EarthMindSatelliteEvidence` artifact explicitly retains `license_attribution`. This attribution is propagated into the B2 `ContextItem` so Sarvam-105B cites the data source accurately.

---

## 3. Data Governance & Memory/KB Isolation Boundaries

1. **Zero Automatic Promotion into Memory:**
   - Satellite observations are ephemeral environmental telemetry.
   - They are **never** automatically promoted into User Memory or General Memory.
   - Any long-term farm profile updates (e.g., historical vigor trends) must pass through explicit C.3 RAG-Memory boundary governance.

2. **Zero Permanent Writes to C.2 Knowledge Base or Vector DB:**
   - Raw satellite rasters and computed indicators are **not** vectorized or indexed into Qdrant (`earthmind_knowledge`).
   - C.2 canonical knowledge is reserved for authoritative agricultural literature, crop packages, and extension guides.

3. **No Hallucinated or Interpolated Science Data:**
   - The module never fabricates reflectance values or invents cloud-free pixels.
   - Missing or corrupted values are labeled explicitly as `INCOMPLETE`, `SUSPECT`, or `CLOUD_OBSCURED`.

---

## 4. Cache Lifecycle & Data Retention Policy

- **Raw Data Cache:** Large raw raster tiles (GeoTIFFs) have a default Time-To-Live (TTL) of 7 days in scratch storage, after which they are purged by `purge_expired()`.
- **Processed Band Summaries & Indicators:** Lightweight JSON summaries and bounding statistics are retained in operational storage for the duration of the current crop cycle (e.g. 180 days).
- **Tenant Deletion:** When a farmer requests data erasure, all associated satellite requests, field bounding references, and evidence records are physically purged.
