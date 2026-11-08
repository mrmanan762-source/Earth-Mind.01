# EarthMind Drone Module — Data Flow & Pipeline Specification v1.0

> **Status:** Founder-Approved Specification v1.0
> **Stage:** D1 — Architecture & Contract Lock

---

## 1. Primary Data Flow Overview

The EarthMind Drone Module processes agricultural drone missions through two distinct architectural pathways:

1. **Sensor Intelligence Pathway:** Ingestion → Preprocessing → Validation → Normalization → Extraction → Fusion → Evidence Construction → B2 Context Manager → Sarvam-105B.
2. **Camera Routing Pathway:** Ingestion → Format/Metadata Extraction → Vision Module Handoff (Optical interpretation strictly delegated).

```
                      ┌────────────────────────────┐
                      │    Drone Mission Upload    │
                      └─────────────┬──────────────┘
                                    │
                                    ▼
                      ┌────────────────────────────┐
                      │    Drone Data Gateway      │
                      └───────┬────────────┬───────┘
                              │            │
            [Camera Imagery]  │            │  [Sensor Telemetry / Rasters]
                              ▼            ▼
                 ┌────────────────┐    ┌───────────────────────────┐
                 │ Camera Routing │    │ 16-Stage Processing Pipe  │
                 │    Contract    │    │ (Quality, Normalization,  │
                 └───────┬────────┘    │  Indicators, Fusion)      │
                         │             └─────────────┬─────────────┘
                         ▼                           │
                 ┌────────────────┐                  ▼
                 │ Vision Module  │    ┌───────────────────────────┐
                 │ (Deep Visual   │    │  EarthMindDroneSensor-    │
                 │  Analysis)     │    │       Evidence v1.0       │
                 └───────┬────────┘    └─────────────┬─────────────┘
                         │                           │
                         │   Visual Evidence         │ Sensor Evidence
                         ▼                           ▼
                 ┌─────────────────────────────────────────────────┐
                 │               B2 Context Manager                │
                 │   (Deduplication, Token Budgeting, Policy)      │
                 └─────────────────────────┬───────────────────────┘
                                           │
                                           ▼
                 ┌─────────────────────────────────────────────────┐
                 │           B3 Reasoning / Sarvam-105B            │
                 │       (Holistic Agricultural Reasoning)         │
                 └─────────────────────────────────────────────────┘
```

---

## 2. 16-Stage Logical Processing Pipeline

The sensor data pathway executes through 16 sequential, deterministic stages. Incomplete, corrupted, or uncalibrated data is never silently converted into trusted evidence.

```
Stage 1:  Receive drone sensor data
Stage 2:  Identify source drone and sensor
Stage 3:  Detect and validate data format
Stage 4:  Parse supported raw data
Stage 5:  Perform initial quality checks
Stage 6:  Resolve calibration metadata
Stage 7:  Normalize supported units
Stage 8:  Process spatial information
Stage 9:  Normalize timestamps
Stage 10: Process numerical and spectral measurements
Stage 11: Extract supported agricultural indicators
Stage 12: Align and fuse compatible sensor data
Stage 13: Assess uncertainty and data quality
Stage 14: Build sensor evidence
Stage 15: Validate evidence
Stage 16: Forward validated evidence through Sarvam integration interface
```

### Detailed Stage Breakdown:

| Stage | Operation | Component | Input | Output | Failure Action |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Receive Data** | Ingest payload & enforce size limits | Data Gateway | Upload request / blob | Ingested bundle + trace_id | Raise `INVALID_ARGUMENT` or `STORAGE_UNAVAILABLE` |
| **2. Identify Sensor** | Match `drone_id` & `sensor_id` | Sensor Registry | Ingestion bundle | Registered Sensor Profile | Raise `UNSUPPORTED_SENSOR` |
| **3. Detect Format** | Inspect magic bytes / headers | Format Detector | Raw payload | `DroneDataFormat` enum | Raise `UNSUPPORTED_FORMAT` |
| **4. Parse Raw Data** | Extract channels / matrices | Raw Processor | Raw buffer + format | Structured raw records | Raise `INVALID_SENSOR_DATA` |
| **5. Quality Checks** | Check physical plausible bounds | Quality Validator | Raw records | Quality-checked records | Raise `QUALITY_VALIDATION_FAILED` |
| **6. Resolve Calibration** | Read panel / sun sensor / certs | Calibration Engine | Quality records + certs | Calibrated records + status | Set `UNCALIBRATED`; log warning |
| **7. Normalize Units** | Convert to SI / standard units | Unit Normalizer | Calibrated records | Normalized records + units | Raise `UNIT_CONVERSION_FAILED` |
| **8. Spatial Processing** | Validate GPS, CRS, bounding box | Geospatial Engine | Raw spatial coords | `SpatialCoverage` model | Set `has_spatial_metadata: false` or raise `GEOLOCATION_INVALID` |
| **9. Temporal Normalization** | Validate UTC ISO timestamps | Temporal Engine | Raw time headers | `TemporalCoverage` model | Raise `TIMESTAMP_INVALID` |
| **10. Numerical Processing** | Compute band statistics & rasters | Spectral/Numerical Engine | Normalized records | Band summaries / matrices | Raise `INSUFFICIENT_DATA` |
| **11. Indicator Extraction** | Compute NDVI, NDRE, NDWI etc. | Indicator Engine | Processed bands + profile | `AgriculturalIndicator` list | Degrade indicators missing bands; log limitations |
| **12. Multi-Sensor Fusion** | Co-register multi-sensor streams | Multi-Sensor Fusion | Concurrent sensor streams | Aligned composite records | Flag `SENSOR_CONFLICT`; continue with single sensor |
| **13. Uncertainty Assessment** | Quantify 8 quality dimensions | Uncertainty Engine | Quality, calibration, spatial signals | `DroneUncertainty` model | Fail-safe default confidence; document limits |
| **14. Build Evidence** | Assemble canonical evidence struct | Evidence Builder | All processed stages | Candidate `EarthMindDroneSensorEvidence` | Raise `INSUFFICIENT_DATA` |
| **15. Validate Evidence** | Schema gate & range verification | Evidence Validator | Candidate evidence | Validated evidence | Raise `EVIDENCE_VALIDATION_FAILED` |
| **16. Forward to B2** | Convert to `ContextItem` | Sarvam Integration | Validated evidence | B2 ContextItem container | Raise `INVALID_ARGUMENT` |

---

## 3. Failure Behavior & Partial-Evidence Policies

### 3.1 Strict Fail-Closed Rule
Under no circumstances may incomplete, fabricated, or corrupted sensor data silently masquerade as trusted agricultural evidence.

### 3.2 Evidence Status Classification
Every produced `EarthMindDroneSensorEvidence` artifact contains an explicit `status` field:
- `SUCCESS`: All requested sensor channels, calibration parameters, spatial metadata, and agricultural indicators were processed and validated cleanly.
- `PARTIAL`: Core measurements are valid, but optional indicators or non-critical secondary sensors could not be computed (e.g. RedEdge band missing for NDRE; thermal camera stream unavailable). Limitations are explicitly attached.
- `DEGRADED`: Data is valid for qualitative review, but operational conditions degrade precision (e.g. uncalibrated reflectance lacking radiometric panel; GPS precision degraded). Warnings are explicitly attached.
- `REJECTED`: Quality checks failed (e.g. negative reflectance values, corrupt headers, invalid timestamp). Artifact is not forwarded to B2.
- `FAILED`: Terminal processing exception occurred. Structured `DroneErrorContract` is returned.

### 3.3 Explicit Condition Handling Matrix

| Condition | Module Action | Resulting Evidence Status | Warnings / Limitations Added |
| :--- | :--- | :--- | :--- |
| **Missing Calibration Panel** | Process with factory default or uncalibrated flag; do not fabricate panel coefficients | `DEGRADED` | "Calibration panel absent; reflectance is relative, not surface-calibrated" |
| **Missing Spatial Metadata (No GPS)** | Mark `has_spatial_metadata: false`; do not hallucinate coordinates | `PARTIAL` | "Geolocation unavailable; measurements cannot be localized to field polygon" |
| **Missing Spectral Band (e.g. RedEdge)** | Skip NDRE calculation; compute NDVI if Red/NIR present | `PARTIAL` | "NDRE unavailable: RedEdge band (705nm) missing from sensor payload" |
| **Sensor Disagreement during Fusion** | Preserve both measurements; flag `SENSOR_CONFLICT` | `DEGRADED` | "Sensor conflict detected: Thermal IR reads 34°C, Contact Thermistor reads 27°C" |
| **Corrupted Payload / Truncated File** | Halt processing immediately | `REJECTED` | Raise `INVALID_SENSOR_DATA` |
| **Out-of-Bounds Physical Value** | Reject measurement; do not clamp silently | `REJECTED` | Raise `QUALITY_VALIDATION_FAILED` |

---

## 4. Camera Routing Pathway Specification

When raw mission packages include optical imagery (RGB photos, orthomosaics, video frames):

1. The **Data Format Detection Engine** identifies image MIME types (`image/jpeg`, `image/png`, `image/tiff`).
2. The **Drone Module** extracts mission and spatial telemetry tags without decoding or analyzing image pixels.
3. The Drone Module constructs a `DroneCameraRoutingContract`:
   - Drone ID, Camera ID, Mission Reference, Field ID.
   - Image URI/storage reference and MIME type.
   - Geolocation (lat/lon/alt), gimbal pitch, heading, collection UTC timestamp.
4. The payload is dispatched to the **Vision Module**:
   - The Vision Module owns all optical feature extraction, symptom detection, weed counting, and visual classification.
   - The Vision Module outputs `VisualEvidence` to B2 Context Manager.
5. In B2 Context Manager, sensor evidence and visual evidence are co-referenced via common `mission_id` and `field_id`.
