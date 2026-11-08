# EarthMind Drone Module — Security, Privacy & Data Governance Specification v1.0

> **Status:** Founder-Approved Specification v1.0
> **Stage:** D1 — Architecture & Contract Lock

---

## 1. Security & Untrusted Input Validation

Drone data often originates from third-party hardware, edge devices, pilot laptops, or field gateways. Consequently, all incoming drone payloads are treated as **untrusted user input**.

### 1.1 Ingestion Gate Controls
- **Payload Size Limits:** In-memory uploads are strictly bounded (default maximum: 50 MB). Payloads exceeding limits must use asynchronous pre-signed object storage references (`raw_payload_ref`).
- **File Format & MIME Sniffing:** Payloads must undergo magic byte verification. File extensions alone are never trusted.
- **Decompression Bomb Protection:** Compressed rasters (e.g., GeoTIFFs using DEFLATE or LZW) are validated for decompression ratio limits prior to full memory extraction to prevent denial-of-service.
- **Input Sanitization:** String identifiers (`drone_id`, `sensor_id`, `mission_id`) are sanitized against directory traversal patterns (`../`, `..\\`) and control character injections.

### 1.2 Safe Error Handling & Secret Protection
- Error responses return standardized error contracts (`DroneErrorContract`).
- No raw file paths, internal network topologies, or cloud credentials (e.g. AWS access keys, S3 secret tokens) may appear in error messages or logs.
- Diagnostic logging redacts raw payload bytes and masks API keys or internal database URIs.

---

## 2. Farmer Privacy & Tenant Isolation

Agricultural data (field coordinates, crop yields, flight paths, sensor readings) represents proprietary business data of farmers.

### 2.1 Multi-Tenant Isolation
- Ingestion, processing, and retrieval operations must be strictly scoped by `farmer_id` and `farm_id`.
- Sensor evidence generated for `farm_A` is physically isolated and cannot be retrieved, aggregated, or queried by requests originating from `farm_B`.
- Field boundaries and GPS coordinates are tagged with `PrivacyLevel.FARM_PRIVATE`.

### 2.2 Sensitive Location Data Protection
- High-precision drone flight coordinates (down to centimeter RTK GPS) are considered sensitive spatial data.
- When exporting context items to B2 Context Manager, raw flight trajectories may be summarized into field-level centroids and bounding boxes unless explicit high-precision spatial analysis is authorized.

---

## 3. Storage Boundaries & Memory Governance

The Drone Module complies with EarthMind's global subsystem ownership boundaries:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Data Ownership Boundaries                       │
│                                                                        │
│   ┌─────────────────────┐                 ┌────────────────────────┐   │
│   │    Drone Module     │                 │    Database Module     │   │
│   │  - In-flight data   │ ──persist──────►│  - Physical database   │   │
│   │  - Parsing logic    │    via adapter  │  - Metadata storage    │   │
│   │  - Evidence build   │                 │  - Relational indexes  │   │
│   └─────────────────────┘                 └────────────────────────┘   │
│              │                                                         │
│              ▼                                                         │
│   ┌─────────────────────┐                 ┌────────────────────────┐   │
│   │   B2 Context Mgr    │                 │     Memory Module      │   │
│   │  - Ephemeral context│                 │  - Authorized memories │   │
│   │  - Token budgeting  │                 │  - Farmer preferences  │   │
│   └─────────────────────┘                 └────────────────────────┘   │
│                                                                        │
│   [Strict Governance Rule]                                             │
│   NO automatic promotion of Drone Sensor Evidence into Memory Module   │
│   or C.2 Canonical Knowledge Base.                                     │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Database Module:** All durable records (drone registrations, sensor profiles, flight audit logs) are persisted through the `IDroneStorageAdapter` interface, which is backed by the Database Module. The Drone Module creates no independent database connections.
2. **Memory Module Boundary:** Drone sensor evidence is operational, ephemeral observation data. It is **never** automatically promoted into the Memory Module. Only verified, farmer-approved long-term summaries may be recorded into Memory following explicit human authorization.
3. **C.2 Knowledge Base Boundary:** Drone sensor measurements are time-bound observations, not canonical agronomic facts. They are **never** indexed into C.2 vector collections or Qdrant knowledge bases.
4. **C.3 Cross-Domain Governance:** Any future candidate for cross-domain persistence must traverse C.3 boundary governance policies.

---

## 4. Provenance & Cryptographic Traceability

To maintain end-to-end scientific audibility, every processed measurement and indicator retains a complete provenance chain:

- **Source Payload Hash:** SHA-256 cryptographic digest of the raw ingested file or telemetry stream.
- **Flight & Sensor Identifiers:** Immutable `drone_id`, `sensor_id`, `mission_id`.
- **Temporal Traceability:** Original UTC collection timestamp from sensor clock, ingestion timestamp from gateway, processing timestamp from evidence engine.
- **Processing Lineage:** Version of the processing engine (`engine_version`), pipeline name (`standard_multispectral_v1`), calibration source and date.
- **Parent Measurement References:** Indicators reference the specific `measurement_id`s from which they were calculated.

---

## 5. Retention, Deletion & Lifecycle Management

- **Raw Ingested Artifacts:** Stored in secure object storage with configurable retention policies (e.g., 30–90 days for raw rasters depending on farmer subscription).
- **Processed Evidence Artifacts:** Retained as structured JSON in the database linked to the field's seasonal crop cycle.
- **Right to Erasure:** When a farmer requests deletion of farm data, all associated drone sensor uploads, raw blobs, processed measurements, and evidence artifacts must be systematically purged across storage tiers.
- **Idempotency:** Re-uploading an identical drone payload (matching SHA-256 hash and mission metadata) returns the existing evidence record or safely replaces it without generating duplicate evidence IDs.
