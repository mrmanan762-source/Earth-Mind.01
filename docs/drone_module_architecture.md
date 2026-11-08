# EarthMind Drone Module — Architecture Specification v1.0

> **Status:** Founder-Approved Architecture v1.0
> **Stage:** D1 — Architecture & Contract Lock
> **Primary Intelligence Model:** Sarvam-105B
> **Context Integration:** B2 Context Manager
> **Visual Interpretation Boundary:** Vision Module

---

## 1. Executive Summary & Purpose

The **EarthMind Drone Module** is a modular sensor-data processing and intelligence layer that transforms raw agricultural drone sensor measurements into validated, structured, spatially and temporally contextualized evidence.

Its purpose is to provide **Sarvam-105B** with the capabilities required to understand and reason over agricultural sensor data collected by drones, without requiring Sarvam-105B or downstream orchestrators to parse heterogeneous proprietary binary formats, manipulate coordinate systems, or perform raw spectral mathematics.

The Drone Module does **not** control physical drone flight, navigate drones autonomously, interpret optical camera imagery, or perform final agronomic diagnosis and treatment decisions.

---

## 2. Primary System Data Paths

Agricultural drones commonly collect two distinct categories of data: sensor measurements (multispectral, hyperspectral, thermal, environmental, soil) and camera imagery (RGB, high-resolution crop photos).

EarthMind enforces strict separation of concerns across these two data flows:

```
[ Sensor Data Path ]
Drone Sensor Data ──► Drone Module ──► Validated Sensor Evidence ──► B2 Context Manager ──► Sarvam-105B
                                                                           ▲
[ Camera Data Path ]                                                       │
Drone Camera Data ──► Vision Module ────────► Visual Evidence ─────────────┘
          │
          └── (Preserves mission/spatial metadata link via Camera Routing Contract)
```

1. **Sensor Data Path:**
   - Raw drone sensor measurements are ingested by the Drone Module.
   - The Drone Module parses, validates, calibrates, georeferences, normalizes, extracts indicators, and bundles measurements into `EarthMindDroneSensorEvidence`.
   - The validated sensor evidence is passed to B2 Context Manager for token budgeting, deduplication, and context aggregation.
   - B2 supplies the structured context to Sarvam-105B for agricultural reasoning.

2. **Camera Data Path:**
   - Optical camera images or video frames collected during drone flights are **not** interpreted by the Drone Module.
   - The Drone Module routes camera payloads to the **Vision Module** via the `DroneCameraRoutingContract`, preserving flight metadata, geolocation, sensor ID, mission reference, and field linkage.
   - The Vision Module processes images into visual evidence, which enters B2 Context Manager independently.

---

## 3. Module Responsibilities & Explicit Non-Responsibilities

### 3.1 Module Responsibilities (19 Core Responsibilities)

1. **Drone sensor data ingestion:** Safely receive sensor payloads from field uploads, gateways, and telemetry endpoints.
2. **Sensor identification and registration:** Validate sensor identity against registered manufacturer, model, and capability profiles.
3. **Data format detection:** Inspect and verify raw payload format (GeoTIFF, NetCDF, HDF5, CSV, JSON, Point Cloud, binary).
4. **Raw data parsing and preprocessing:** Extract raw telemetry streams, band rasters, and tabular measurements.
5. **Data quality validation:** Validate numerical ranges, physical limits, missing bands, noise, and data corruption.
6. **Calibration metadata management:** Track sensor calibration certificates, radiometric targets, and calibration status.
7. **Unit normalization:** Convert heterogeneous measurement units to canonical scientific units (SI / ISO standards).
8. **Geospatial processing:** Parse coordinates, bounding boxes, altitudes, CRS projections (WGS84 / EPSG), and field boundaries.
9. **Temporal processing:** Normalize UTC timestamps, flight durations, collection intervals, and sampling rates.
10. **Spectral and numerical processing:** Process reflectance ratios, radiance values, thermal distributions, and point statistics.
11. **Agricultural indicator extraction:** Calculate indices (e.g., NDVI, NDRE, NDWI) only when required input bands exist.
12. **Multi-sensor data fusion:** Align and fuse readings from complementary onboard sensors (e.g., thermal + multispectral).
13. **Uncertainty and confidence assessment:** Quantify spatial, temporal, calibration, and measurement confidence without inventing probabilities.
14. **Sensor evidence generation:** Assemble structured, validated `EarthMindDroneSensorEvidence` artifacts.
15. **Sensor evidence validation:** Validate schema integrity, boundary constraints, and consistency before distribution.
16. **Sarvam integration interface:** Transform sensor evidence into machine-readable context consumable by B2 and Sarvam-105B.
17. **Provenance and metadata management:** Maintain end-to-end cryptographic and transformation lineage from raw sensor to final evidence.
18. **Storage adapter interfaces:** Provide clean persistence abstractions for sensor metadata and pointers to raw artifacts.
19. **Monitoring and diagnostics:** Emit operational metrics, health checks, error telemetry, and performance tracking.

### 3.2 Explicit Non-Responsibilities (Strict Boundaries)

The Drone Module explicitly does **NOT** own:
- **Physical drone operations:** Motor control, battery management, hardware avionics, or pilot-in-the-loop communication.
- **Flight control:** Real-time autopilot, attitude adjustments, altitude hold, or return-to-home logic.
- **Autonomous flight planning:** Waypoint generation, collision avoidance, obstacle detection, or airspace clearance.
- **Camera-based visual interpretation:** Object detection, visual symptom classification, weed recognition from RGB photos (owned by Vision Module).
- **Final agricultural diagnosis:** Determining disease, pest infestation, or soil pathology (owned by B3 Reasoning / Sarvam-105B).
- **Agricultural treatment recommendations:** Formulating pesticide sprays, fungicide schedules, or intervention advice.
- **Fertilizer or pesticide dosage decisions:** Calculating chemical volumes or prescription maps.
- **Final agricultural planning:** Generating farm management workflows (owned by B4 Planning & Decision Engine).
- **General agricultural knowledge curation:** Authoritative agronomic facts, literature, or crop packages (owned by C.2 Knowledge Base).
- **Satellite imagery processing:** Processing Sentinel/Landsat/Planet satellite rasters (owned by Satellite Intelligence Module).

---

## 4. Component Architecture Specification (18 Logical Components)

The Drone Module is organized into 18 logical components. These represent architectural responsibilities and interface boundaries, not mandatory separate microservices.

### Component 1: Drone Data Gateway
- **Purpose:** Secure entry point for all incoming drone sensor data streams and batch uploads.
- **Responsibilities:** Accept sensor payloads; enforce payload size limits (e.g. 50 MB in-memory); authenticate request tenant context; assign unique ingestion trace IDs.
- **Inputs:** Raw data payload or object reference, upload headers, client credentials, tenant context.
- **Outputs:** Ingested raw payload bundle with assigned ingestion timestamp and tracing ID.
- **Dependencies:** Core logging, tenant authorization context.
- **Non-Responsibilities:** Flight telemetry parsing; binary decoding; user authentication logic.
- **Expected Errors:** `INVALID_ARGUMENT`, `STORAGE_UNAVAILABLE`, `PROCESSING_TIMEOUT`.
- **Integration Boundaries:** Interfaces with edge ingestion APIs, mobile clients, and web portals.
- **Extensibility:** Support for direct streaming telemetry, cloud storage event notifications (S3/GCS bucket triggers).

### Component 2: Sensor Registry & Capability Manager
- **Purpose:** Manage known drone models, sensor hardware specifications, spectral band profiles, and capability manifests.
- **Responsibilities:** Lookup sensor metadata by `sensor_id` or manufacturer/model; verify whether a sensor supports requested processing (e.g. RedEdge band for NDRE); return calibration constraints.
- **Inputs:** Sensor identifier, manufacturer, model, firmware version.
- **Outputs:** `SensorMetadataContract` describing supported measurements, formats, units, and calibration rules.
- **Dependencies:** Storage adapter.
- **Non-Responsibilities:** Live hardware polling; sensor firmware updates.
- **Expected Errors:** `UNSUPPORTED_SENSOR`, `SENSOR_METADATA_MISSING`.
- **Integration Boundaries:** Consulted during ingestion and indicator extraction stages.
- **Extensibility:** Pluggable JSON/DB registry for custom farmer-built or third-party drone sensors.

### Component 3: Data Format Detection Engine
- **Purpose:** Inspect and identify raw sensor file and payload formats.
- **Responsibilities:** Inspect magic bytes, file extensions, MIME types, and schema signatures to reliably classify format (GeoTIFF, NetCDF, HDF5, CSV, JSON, Point Cloud, Binary).
- **Inputs:** Raw payload buffer or file path reference.
- **Outputs:** Detected `DroneDataFormat` enumeration and format metadata.
- **Dependencies:** None.
- **Non-Responsibilities:** Parsing file data; converting data between formats.
- **Expected Errors:** `UNSUPPORTED_FORMAT`, `INVALID_SENSOR_DATA`.
- **Integration Boundaries:** Invoked immediately following Data Gateway ingestion.
- **Extensibility:** Additional proprietary agricultural format sniffers (e.g. DJI multispectral TIFF, Parrot Sequoia RAW).

### Component 4: Raw Data Processing Engine
- **Purpose:** Parse validated formats into structured raw telemetry, tabular points, or raster bands.
- **Responsibilities:** Extract channel arrays, coordinate tags, timestamp headers, and numeric matrices from raw inputs.
- **Inputs:** Raw payload and detected `DroneDataFormat`.
- **Outputs:** Structured raw measurement records and band definitions.
- **Dependencies:** Format detection engine, safe memory bounds.
- **Non-Responsibilities:** Unit normalization; agricultural indicator computation.
- **Expected Errors:** `INVALID_SENSOR_DATA`, `INSUFFICIENT_DATA`, `PROCESSING_TIMEOUT`.
- **Integration Boundaries:** Internal data transformation layer.
- **Extensibility:** C-extension or accelerated raster parsers for large flight datasets.

### Component 5: Data Quality & Validation Engine
- **Purpose:** Perform rigorous data sanity and physical plausibility checks on raw measurements.
- **Responsibilities:** Check for out-of-bounds values (e.g. negative reflectance, surface temps outside -50°C to +80°C); detect corrupted bands; verify minimum required sample points.
- **Inputs:** Structured raw measurement records.
- **Outputs:** Validated measurements and `QualityStatus` classification.
- **Dependencies:** None.
- **Non-Responsibilities:** Estimating missing values or hallucinating repair data.
- **Expected Errors:** `QUALITY_VALIDATION_FAILED`, `INVALID_SENSOR_DATA`, `INSUFFICIENT_DATA`.
- **Integration Boundaries:** Pre-processing gate before calibration and normalization.
- **Extensibility:** Region- and season-specific agronomic sanity threshold profiles.

### Component 6: Calibration & Unit Normalization Engine
- **Purpose:** Apply verified calibration parameters and convert measurements to standard scientific units.
- **Responsibilities:** Resolve sensor calibration certificates or radiometric calibration panel metadata; normalize units to standard SI/ISO units (e.g. Celsius, Kelvin, W/m², %, Pa); flag uncalibrated data explicitly.
- **Inputs:** Validated measurements, calibration metadata, sensor capability profile.
- **Outputs:** Normalized measurements with `CalibrationStatus` and unit metadata.
- **Dependencies:** Sensor Registry.
- **Non-Responsibilities:** Fabricating calibration coefficients when uncalibrated.
- **Expected Errors:** `CALIBRATION_UNAVAILABLE`, `UNIT_CONVERSION_FAILED`.
- **Integration Boundaries:** Normalization pipeline stage.
- **Extensibility:** Dynamic downwelling light sensor (DLS) sun irradiance calibration adapters.

### Component 7: Geospatial Processing Engine
- **Purpose:** Validate, transform, and contextualize drone flight geospatial information.
- **Responsibilities:** Parse GPS coordinates (lat, lon, alt); validate CRS (WGS84 EPSG:4326 default); compute bounding boxes; verify alignment with authorized field polygon boundaries.
- **Inputs:** Geolocation coordinates, altitude, field polygon reference.
- **Outputs:** `SpatialCoverage` model (centroid, bounding box, CRS, elevation, field containment).
- **Dependencies:** None.
- **Non-Responsibilities:** Autonomous drone navigation; path planning; flight corridor clearance.
- **Expected Errors:** `GEOLOCATION_INVALID`, `INVALID_ARGUMENT`.
- **Integration Boundaries:** Feeds spatial context into evidence builder and B2 context filtering.
- **Extensibility:** Multi-CRS reprojector; KML/GeoJSON field boundary intersection engines.

### Component 8: Temporal Processing Engine
- **Purpose:** Validate and normalize collection timeframes and sampling rates.
- **Responsibilities:** Validate ISO 8601 UTC timestamps; calculate flight duration, observation start/end, sampling intervals; detect temporal drift.
- **Inputs:** Raw collection timestamps, ingestion time.
- **Outputs:** `TemporalCoverage` model (start_time, end_time, duration_seconds, sampling_frequency_hz).
- **Dependencies:** System clock.
- **Non-Responsibilities:** Predicting future sensor values; historical trend modeling.
- **Expected Errors:** `TIMESTAMP_INVALID`, `INVALID_ARGUMENT`.
- **Integration Boundaries:** Temporal alignment and B2 temporal context filtering.
- **Extensibility:** Multi-flight temporal stacking and longitudinal time-series alignment.

### Component 9: Spectral & Numerical Analysis Engine
- **Purpose:** Execute numerical, statistical, and band-math operations across processed sensor measurements.
- **Responsibilities:** Calculate band reflectances, thermal means/min/max/percentiles, spatial variance, and sensor histogram statistics.
- **Inputs:** Calibrated measurements and band arrays.
- **Outputs:** Statistical summaries, numerical matrices, and spectral distribution profiles.
- **Dependencies:** Calibration engine.
- **Non-Responsibilities:** Final crop stress diagnosis; disease identification.
- **Expected Errors:** `INDICATOR_PROCESSING_FAILED`, `INSUFFICIENT_DATA`.
- **Integration Boundaries:** Feeds Agricultural Indicator Engine.
- **Extensibility:** Hyperspectral narrow-band continuum removal and derivative spectroscopy.

### Component 10: Agricultural Indicator Extraction Engine
- **Purpose:** Extract standardized vegetation, moisture, and vigor indices from valid spectral and environmental bands.
- **Responsibilities:** Calculate NDVI (NIR-Red)/(NIR+Red), NDRE (NIR-RedEdge)/(NIR+RedEdge), NDWI (NIR-SWIR)/(NIR+SWIR), CWSI (crop water stress index), only when required input bands are present; record limitations when bands are missing.
- **Inputs:** Processed spectral and thermal bands, sensor capability manifest.
- **Outputs:** List of `AgriculturalIndicatorContract` items with spatial coverage, quality status, and explicit limitations.
- **Dependencies:** Spectral & Numerical Analysis Engine, Sensor Registry.
- **Non-Responsibilities:** Prescribing fertilizer dosage or recommending pesticide intervention based on indices.
- **Expected Errors:** `INDICATOR_PROCESSING_FAILED`, `INSUFFICIENT_DATA`.
- **Integration Boundaries:** Primary evidence extraction layer.
- **Extensibility:** Support for custom agricultural indices (SAVI, EVI, GNDVI, PRI, VARI).

### Component 11: Multi-Sensor Fusion Engine
- **Purpose:** Spatially and temporally align measurements from multiple concurrent sensors on the same flight.
- **Responsibilities:** Align multispectral, thermal, and environmental sensor readings collected over the same field within the same mission timeframe; detect inter-sensor conflicts.
- **Inputs:** Multiple processed sensor measurement streams from the same drone/mission.
- **Outputs:** Co-registered composite sensor observation package.
- **Dependencies:** Geospatial Engine, Temporal Engine.
- **Non-Responsibilities:** Merging drone data with satellite imagery (owned by Satellite Intelligence Module).
- **Expected Errors:** `SENSOR_CONFLICT`, `INSUFFICIENT_DATA`.
- **Integration Boundaries:** Aggregates multi-sensor payloads before evidence assembly.
- **Extensibility:** Sensor fusion algorithms (Kalman filtering, spatial nearest-neighbor interpolation).

### Component 12: Uncertainty & Confidence Assessment Engine
- **Purpose:** Quantify quality, calibration, spatial, and temporal uncertainty across processed observations.
- **Responsibilities:** Calculate separate, transparent confidence dimensions (input validity, measurement quality, processing quality, calibration status, spatial confidence, temporal confidence, evidence completeness, overall evidence quality); never conflate confidence with correctness.
- **Inputs:** Quality flags, calibration status, spatial resolution, temporal age, sensor conflict signals.
- **Outputs:** `DroneUncertainty` and `DroneQuality` assessment structures.
- **Dependencies:** Quality, Calibration, Geospatial, and Temporal engines.
- **Non-Responsibilities:** Inventing arbitrary numerical probabilities without a documented, verified methodology.
- **Expected Errors:** `QUALITY_VALIDATION_FAILED`.
- **Integration Boundaries:** Embedded directly in `EarthMindDroneSensorEvidence`.
- **Extensibility:** Bayesian uncertainty propagation models for multi-sensor composites.

### Component 13: Sensor Evidence Builder
- **Purpose:** Synthesize processed measurements, extracted indicators, spatial/temporal metadata, uncertainty, and provenance into a unified evidence container.
- **Responsibilities:** Assemble the canonical `EarthMindDroneSensorEvidence` artifact conforming to schema version 1.0; attach explicit limitations and warnings; maintain audit traceability.
- **Inputs:** Processed measurements, agricultural indicators, spatial/temporal metadata, quality/uncertainty assessments, provenance history.
- **Outputs:** Complete `EarthMindDroneSensorEvidence` instance.
- **Dependencies:** Components 4 through 12, Provenance Manager.
- **Non-Responsibilities:** Agricultural diagnosis; LLM prompt generation.
- **Expected Errors:** `EVIDENCE_VALIDATION_FAILED`, `INSUFFICIENT_DATA`.
- **Integration Boundaries:** Outputs to Sensor Evidence Validator.
- **Extensibility:** Evidence packaging profiles for specialized agricultural domains (orchards, row crops, paddy).

### Component 14: Sensor Evidence Validator
- **Purpose:** Final validation gate ensuring produced evidence conforms strictly to contract v1.0.
- **Responsibilities:** Verify all mandatory fields; check for unvalidated NaN/Inf values; ensure status is explicitly SUCCESS, PARTIAL, DEGRADED, REJECTED, or FAILED; reject silent incomplete data.
- **Inputs:** `EarthMindDroneSensorEvidence` candidate instance.
- **Outputs:** Validated evidence artifact or validation error with structured failure details.
- **Dependencies:** Schema contract definitions.
- **Non-Responsibilities:** Correcting invalid data; generating mock data.
- **Expected Errors:** `EVIDENCE_VALIDATION_FAILED`.
- **Integration Boundaries:** Gatekeeper between Drone Module and Sarvam Integration Interface.
- **Extensibility:** Contract version migration validators.

### Component 15: Sarvam Integration Interface
- **Purpose:** Bridge validated drone sensor evidence to EarthMind's central intelligence orchestration pipeline.
- **Responsibilities:** Provide a versioned, machine-readable adapter converting `EarthMindDroneSensorEvidence` into B2-compatible `ContextItem` representations; ensure token boundedness; preserve provenance, indicators, and limitations.
- **Inputs:** Validated `EarthMindDroneSensorEvidence`.
- **Outputs:** `ContextItem` ready for B2 Context Manager consumption.
- **Dependencies:** B2 Context Manager contracts, Core Schemas.
- **Non-Responsibilities:** Directly invoking Sarvam-105B LLM; overriding B2 token budgets or prioritization rules.
- **Expected Errors:** `INVALID_ARGUMENT`, `EVIDENCE_VALIDATION_FAILED`.
- **Integration Boundaries:** Interface with B2 Context Manager.
- **Extensibility:** Custom serialization adapters for conversational vs analytical reasoning workflows.

### Component 16: Provenance & Metadata Manager
- **Purpose:** Ensure end-to-end traceability of every processed measurement and indicator back to raw sensor data.
- **Responsibilities:** Track drone ID, sensor ID, collection timestamp, ingestion timestamp, transformation steps, calibration source, and evidence ID; generate cryptographic hash signatures of source payloads.
- **Inputs:** Pipeline execution context, transformation events, raw payload references.
- **Outputs:** Comprehensive `ProvenanceMetadata` object.
- **Dependencies:** Core hashing utilities.
- **Non-Responsibilities:** Long-term raw binary storage management.
- **Expected Errors:** `INTERNAL_ERROR`.
- **Integration Boundaries:** Embedded in every measurement, indicator, and evidence contract.
- **Extensibility:** Blockchain or immutable audit ledger export adapters.

### Component 17: Storage Adapter Interface
- **Purpose:** Provider-independent abstraction for reading and writing drone metadata, registered sensor profiles, and references to raw artifacts.
- **Responsibilities:** Define contracts for storing/retrieving drone session metadata, sensor capabilities, and evidence records; support blob/file pointer references for large rasters.
- **Inputs:** Entity records, query filters, storage keys.
- **Outputs:** Stored records, persistence confirmations, file stream handles.
- **Dependencies:** Core interfaces.
- **Non-Responsibilities:** Direct physical database connection pooling (owned by Database Module); vector indexing (owned by Qdrant/Index layer).
- **Expected Errors:** `STORAGE_UNAVAILABLE`, `STORAGE_ERROR`.
- **Integration Boundaries:** Interface with Database Module and object storage (S3/local disk).
- **Extensibility:** Adapters for SQLite, PostgreSQL, S3, MinIO, Azure Blob.

### Component 18: Monitoring & Diagnostics
- **Purpose:** Operational telemetry, health inspection, and processing metrics.
- **Responsibilities:** Track ingestion rates, parsing latencies, validation failure counts, sensor error distributions, memory consumption; provide component health checks.
- **Inputs:** Pipeline telemetry events, system resource metrics.
- **Outputs:** Structured diagnostic metrics, health status reports (`HEALTHY`, `DEGRADED`, `UNHEALTHY`).
- **Dependencies:** Core logging and metrics infrastructure.
- **Non-Responsibilities:** System alerting notification delivery (PagerDuty/Slack).
- **Expected Errors:** None (fail-safe in-memory metrics).
- **Integration Boundaries:** Consumed by system lifecycle manager, health probes, and admin dashboards.
- **Extensibility:** Prometheus/OpenTelemetry exporter integration.

---

## 5. Architectural Boundaries & Cross-Module Protection

```
┌────────────────────────────────────────────────────────────────────────┐
│                        EarthMind System Architecture                   │
│                                                                        │
│   ┌─────────────────────┐                 ┌────────────────────────┐   │
│   │    Drone Module     │                 │     Vision Module      │   │
│   │  (Sensors & Data)   │                 │   (Optical Imagery)    │   │
│   └──────────┬──────────┘                 └───────────┬────────────┘   │
│              │ Validated Evidence                     │ Visual Evidence│
│              ▼                                        ▼                │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │                     B2 Context Manager                         │   │
│   │       (Deduplication, Budgeting, Privacy, Prioritization)      │   │
│   └────────────────────────────────┬───────────────────────────────┘   │
│                                    │ Controlled Context Package        │
│                                    ▼                                   │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │                 B3 Reasoning / Sarvam-105B                     │   │
│   │         (Agricultural Diagnosis & Cognitive Reasoning)         │   │
│   └────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

The Drone Module strictly adheres to EarthMind's existing module boundaries:

1. **B2 Context Manager:** The Drone Module never bypasses B2 to communicate directly with Sarvam-105B. Validated evidence is delivered to B2 as structured context items.
2. **B3 Reasoning Engine:** Agricultural diagnosis, pest identification, and treatment recommendations remain exclusive responsibilities of B3 and Sarvam-105B. The Drone Module produces factual, validated sensor evidence only.
3. **B4 Planning & Decision Engine:** Drone evidence serves as input context; flight plans or agricultural interventions are planned by B4, never by the Drone Module.
4. **Vision Module:** Camera imagery collected during drone missions is routed directly to the Vision Module. The Drone Module never attempts visual object detection or leaf symptom segmentation.
5. **Memory Module & C.2 Knowledge Base:** Drone sensor readings are transient operational data. They are **never** automatically promoted into General Memory or C.2 canonical knowledge without explicit C.3 boundary governance.
6. **Database Module:** All persistent storage operations flow through standard storage adapter interfaces. The Drone Module does not create independent physical database connections.
