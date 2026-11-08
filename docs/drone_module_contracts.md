# EarthMind Drone Module — Data Contracts Specification v1.0

> **Status:** Founder-Approved Contract Specification v1.0
> **Schema Version:** 1.0
> **Stage:** D1 — Architecture & Contract Lock

---

## 1. Overview & Contract Principles

The EarthMind Drone Module operates on formally specified, versioned, machine-readable data contracts. These contracts guarantee:

- **Immutability of Raw Identity:** Original sensor measurement values and units are permanently preserved alongside normalized representations.
- **Fail-Closed Validation:** Incomplete, corrupted, or uncalibrated data is explicitly flagged and never silently converted into trusted evidence.
- **Unambiguous Provenance:** Every measurement, indicator, and evidence item is traceable to source sensor, drone, timestamp, and processing version.
- **Strict Boundary Separation:** Optical camera data routes exclusively to the Vision Module; validated sensor evidence routes exclusively through B2 Context Manager to Sarvam-105B.

---

## 2. Core Enumerations

All contracts utilize centralized string-based enumerations to prevent ambiguity:

| Enumeration | Allowed Values | Description |
| :--- | :--- | :--- |
| `SensorCategory` | `MULTISPECTRAL`, `HYPERSPECTRAL`, `THERMAL`, `RGB`, `ENVIRONMENTAL`, `SOIL`, `LIDAR`, `OTHER` | Hardware taxonomy of sensor types. |
| `DroneDataFormat` | `GEOTIFF`, `NETCDF`, `HDF5`, `CSV`, `JSON`, `LAS`, `POINT_CLOUD`, `RAW_BINARY`, `JPEG_METADATA` | Supported raw file and payload formats. |
| `QualityStatus` | `VALID`, `SUSPECT`, `DEGRADED`, `CALIBRATION_MISSING`, `GEOLOCATION_DEGRADED`, `INCOMPLETE`, `INVALID` | Quality rating of measurement or data stream. |
| `CalibrationStatus`| `CALIBRATED`, `UNCALIBRATED`, `FACTORY_DEFAULT`, `EXPIRED`, `MISSING` | Radiometric/sensor calibration state. |
| `EvidenceStatus` | `SUCCESS`, `PARTIAL`, `DEGRADED`, `REJECTED`, `FAILED` | Overall status of generated sensor evidence artifact. |
| `DroneErrorCode` | 18 approved codes (see Section 9) | Standardized error taxonomy. |

---

## 3. Contract 1: Drone Sensor Input Contract (`DroneSensorInputContract`)

Describes incoming raw sensor data ingested through the Drone Data Gateway:

```json
{
  "source_type": "drone_sensor",
  "drone_id": "DRONE-AG-2024-001",
  "sensor_id": "SENSOR-MS-REDEDGE-MX-01",
  "sensor_type": "multispectral",
  "manufacturer": "MicaSense",
  "model": "RedEdge-MX",
  "data_format": "GEOTIFF",
  "raw_payload_ref": "s3://earthmind-drone-raw/2025/03/flight_001.tif",
  "raw_payload": null,
  "collection_timestamp": "2025-03-30T10:15:30Z",
  "ingestion_timestamp": "2025-03-30T10:20:00Z",
  "spatial_metadata": {
    "latitude": 28.6139,
    "longitude": 77.2090,
    "altitude_meters": 45.5,
    "crs": "EPSG:4326"
  },
  "unit_metadata": {
    "reflectance": "ratio_0_to_1",
    "temperature": "celsius"
  },
  "calibration_metadata": {
    "calibration_panel_used": true,
    "panel_albedo_factor": 0.67,
    "last_factory_calibration": "2024-11-15T00:00:00Z"
  },
  "field_id": "field_wheat_zone_04",
  "farm_id": "farm_delhi_icar_01",
  "farmer_id": "farmer_10842",
  "source_provenance": {
    "uploader_id": "pilot_user_44",
    "device_firmware": "v2.4.1",
    "payload_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }
}
```

### Required vs. Optional Fields:
- **Required:** `source_type`, `drone_id`, `sensor_id`, `sensor_type`, `data_format`, `collection_timestamp`, `ingestion_timestamp`, `source_provenance`.
- **Conditionally Required:** At least one of `raw_payload_ref` (URI/path) or `raw_payload` (base64/binary bytes) must be provided.
- **Optional:** `manufacturer`, `model`, `spatial_metadata`, `unit_metadata`, `calibration_metadata`, `field_id`, `farm_id`, `farmer_id`.

---

## 4. Contract 2: Sensor Metadata Contract (`SensorMetadataContract`)

Defines sensor hardware specifications, capabilities, and registered operational envelopes:

```json
{
  "sensor_id": "SENSOR-MS-REDEDGE-MX-01",
  "sensor_category": "MULTISPECTRAL",
  "manufacturer": "MicaSense",
  "model": "RedEdge-MX",
  "supported_measurements": ["blue_reflectance", "green_reflectance", "red_reflectance", "red_edge_reflectance", "nir_reflectance"],
  "supported_formats": ["GEOTIFF", "RAW_BINARY"],
  "measurement_units": {
    "blue_reflectance": "ratio",
    "green_reflectance": "ratio",
    "red_reflectance": "ratio",
    "red_edge_reflectance": "ratio",
    "nir_reflectance": "ratio"
  },
  "sampling_characteristics": {
    "bands_count": 5,
    "ground_sampling_distance_cm": 2.5,
    "spectral_range_nm": [475, 840],
    "sampling_rate_hz": 1.0
  },
  "calibration_metadata": {
    "requires_radiometric_panel": true,
    "requires_sun_sensor": true,
    "calibration_interval_days": 180
  },
  "capability_version": "1.0",
  "registration_status": "ACTIVE"
}
```

---

## 5. Contract 3: Processed Sensor Measurement Contract (`ProcessedSensorMeasurementContract`)

Guarantees dual preservation of original and normalized values:

```json
{
  "measurement_id": "meas_ms_red_001",
  "measurement_type": "spectral_reflectance",
  "channel_name": "red_band",
  "original_value": 1420.0,
  "original_unit": "digital_number_12bit",
  "processed_value": 0.082,
  "normalized_unit": "reflectance_ratio",
  "processing_method": "radiometric_calibration_panel_normalization",
  "calibration_status": "CALIBRATED",
  "timestamp": "2025-03-30T10:15:30Z",
  "spatial_reference": {
    "latitude": 28.6139,
    "longitude": 77.2090,
    "altitude_meters": 45.5,
    "crs": "EPSG:4326"
  },
  "quality_status": "VALID",
  "source_sensor": "SENSOR-MS-REDEDGE-MX-01",
  "provenance": {
    "source_file": "flight_001.tif",
    "panel_reflectance": 0.67,
    "conversion_factor": 0.0000577,
    "applied_pipeline": "modules.drone.processing.radiometric"
  }
}
```

---

## 6. Contract 4: Agricultural Indicator Contract (`AgriculturalIndicatorContract`)

Standardizes extracted vegetation, moisture, and vigor indices. Requires input bands to be verified before calculation:

```json
{
  "indicator_id": "ind_ndvi_field_zone_04",
  "indicator_name": "NDVI",
  "definition": "Normalized Difference Vegetation Index: (NIR - Red) / (NIR + Red)",
  "calculation_method": "standard_band_ratio",
  "required_input_measurements": ["nir_reflectance", "red_reflectance"],
  "result": {
    "mean": 0.74,
    "min": 0.32,
    "max": 0.88,
    "standard_deviation": 0.09,
    "histogram_distribution": [0.05, 0.12, 0.45, 0.38]
  },
  "unit": "unitless_ratio",
  "spatial_coverage": {
    "centroid": {"latitude": 28.6139, "longitude": 77.2090},
    "bounding_box": {
      "min_latitude": 28.6120,
      "max_latitude": 28.6150,
      "min_longitude": 77.2070,
      "max_longitude": 77.2110
    },
    "area_hectares": 3.8,
    "crs": "EPSG:4326"
  },
  "temporal_coverage": {
    "start_time": "2025-03-30T10:10:00Z",
    "end_time": "2025-03-30T10:25:00Z",
    "duration_seconds": 900
  },
  "processing_version": "1.0",
  "quality_status": "VALID",
  "limitations": [
    "Saturated in ultra-dense canopy (>0.85)",
    "Calculated at 10:15 UTC under clear sky conditions"
  ]
}
```

---

## 7. Contract 5: Sensor Evidence Output Contract (`EarthMindDroneSensorEvidence`)

The primary output contract of the Drone Module. Conforms to version 1.0:

```json
{
  "contract_name": "EarthMindDroneSensorEvidence",
  "schema_version": "1.0",
  "evidence_id": "ev_drone_20250330_001",
  "source": {
    "source_type": "drone_sensor",
    "drone_id": "DRONE-AG-2024-001",
    "sensor_id": "SENSOR-MS-REDEDGE-MX-01",
    "sensor_type": "multispectral",
    "manufacturer": "MicaSense",
    "model": "RedEdge-MX"
  },
  "field": {
    "field_id": "field_wheat_zone_04",
    "farm_id": "farm_delhi_icar_01",
    "farmer_id": "farmer_10842",
    "crop": "Wheat (Triticum aestivum L.)"
  },
  "collection": {
    "mission_id": "mission_wheat_scan_03",
    "collection_timestamp": "2025-03-30T10:15:30Z",
    "ingestion_timestamp": "2025-03-30T10:20:00Z",
    "flight_altitude_meters": 45.5,
    "flight_speed_mps": 5.0
  },
  "measurements": [
    {
      "measurement_id": "meas_ms_red_001",
      "measurement_type": "spectral_reflectance",
      "channel_name": "red_band",
      "original_value": 1420.0,
      "original_unit": "digital_number_12bit",
      "processed_value": 0.082,
      "normalized_unit": "reflectance_ratio",
      "processing_method": "radiometric_calibration_panel_normalization",
      "calibration_status": "CALIBRATED",
      "timestamp": "2025-03-30T10:15:30Z",
      "quality_status": "VALID"
    }
  ],
  "indicators": [
    {
      "indicator_id": "ind_ndvi_001",
      "indicator_name": "NDVI",
      "result": {"mean": 0.74, "min": 0.32, "max": 0.88},
      "unit": "unitless_ratio",
      "quality_status": "VALID",
      "limitations": []
    }
  ],
  "spatial_coverage": {
    "has_spatial_metadata": true,
    "centroid": {"latitude": 28.6139, "longitude": 77.2090, "altitude_meters": 45.5},
    "bounding_box": {
      "min_latitude": 28.6120,
      "max_latitude": 28.6150,
      "min_longitude": 77.2070,
      "max_longitude": 77.2110
    },
    "crs": "EPSG:4326"
  },
  "temporal_coverage": {
    "start_time": "2025-03-30T10:10:00Z",
    "end_time": "2025-03-30T10:25:00Z",
    "duration_seconds": 900
  },
  "quality": {
    "input_validity": "VALID",
    "measurement_quality": "HIGH",
    "processing_quality": "NORMALIZED",
    "evidence_completeness": "COMPLETE",
    "overall_quality": "HIGH"
  },
  "uncertainty": {
    "spatial_confidence": 0.95,
    "temporal_confidence": 0.98,
    "calibration_confidence": 0.92,
    "overall_confidence": 0.94,
    "uncertainty_sources": ["minor_wind_buffeting_2mps"]
  },
  "calibration": {
    "calibration_status": "CALIBRATED",
    "panel_used": true,
    "sun_sensor_used": true,
    "calibration_timestamp": "2025-03-30T10:05:00Z"
  },
  "processing": {
    "engine_version": "1.0.0",
    "pipeline": "standard_multispectral_v1",
    "processing_timestamp": "2025-03-30T10:22:15Z"
  },
  "provenance": {
    "source_file": "s3://earthmind-drone-raw/2025/03/flight_001.tif",
    "source_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "trace_id": "tr_scan_wheat_44"
  },
  "warnings": [],
  "limitations": [
    "Evidence covers vegetative canopy reflectance; does not directly measure sub-surface soil moisture"
  ],
  "status": "SUCCESS"
}
```

---

## 8. Contract 6: Camera Routing Contract (`DroneCameraRoutingContract`)

Ensures optical RGB camera imagery is handed off cleanly to the Vision Module without visual interpretation by the Drone Module:

```json
{
  "contract_name": "DroneCameraRoutingContract",
  "routing_id": "route_cam_20250330_001",
  "drone_id": "DRONE-AG-2024-001",
  "camera_id": "CAM-RGB-SONY-RX1",
  "sensor_category": "RGB",
  "mission_reference": "mission_wheat_scan_03",
  "field_id": "field_wheat_zone_04",
  "farm_id": "farm_delhi_icar_01",
  "collection_timestamp": "2025-03-30T10:16:00Z",
  "image_reference": "s3://earthmind-drone-raw/2025/03/cam_frame_042.jpg",
  "image_mime_type": "image/jpeg",
  "spatial_metadata": {
    "latitude": 28.6142,
    "longitude": 77.2095,
    "altitude_meters": 45.0,
    "heading_degrees": 180.0,
    "gimbal_pitch_degrees": -90.0,
    "crs": "EPSG:4326"
  },
  "source_provenance": {
    "flight_controller": "PX4_v1.14",
    "frame_number": 42
  },
  "destination_module": "vision",
  "requires_visual_interpretation": true
}
```

---

## 9. Contract 7: Sarvam Integration Contract & B2 Translation

Defines how validated sensor evidence maps into B2 Context Manager without bypassing B2:

```python
class DroneSarvamIntegrationContract(BaseModel):
    """Bridge contract providing validated sensor evidence to B2 Context Manager."""
    evidence: EarthMindDroneSensorEvidence
    target_model: str = "Sarvam-105B"
    context_priority: str = "HIGH"

    def to_context_item(self) -> ContextItem:
        """Converts drone evidence into a B2-compliant ContextItem."""
        ...
```

The resulting `ContextItem` features:
- `entity_type`: `"drone_sensor_evidence"`
- `entity_id`: `evidence.field.field_id` or `evidence.evidence_id`
- `data_type`: `"sensor_evidence"`
- `content`: JSON-serializable evidence package summary (indicators, measurements, uncertainty, warnings, limitations)
- `confidence`: `evidence.uncertainty.overall_confidence`
- `privacy_level`: `PrivacyLevel.FARM_PRIVATE`
- `source`: `"drone_module"`
- `source_id`: `evidence.evidence_id`

---

## 10. Contract 8: Structured Error Contract (`DroneErrorContract`)

Standardized error reporting adhering to EarthMind framework specifications:

| Error Code | Meaning | Default Retryable |
| :--- | :--- | :--- |
| `INVALID_ARGUMENT` | Payload validation failure, missing required field, bad types | False |
| `UNSUPPORTED_SENSOR` | Sensor hardware profile not registered or recognized | False |
| `UNSUPPORTED_FORMAT` | File/data format cannot be decoded or is not supported | False |
| `INVALID_SENSOR_DATA` | Payload corrupted, unreadable bytes, or nonsensical data | False |
| `SENSOR_METADATA_MISSING` | Required sensor capability manifest not found | False |
| `CALIBRATION_UNAVAILABLE` | Calibration certificate/panel missing when strictly required | False |
| `UNIT_CONVERSION_FAILED` | Measurement unit unrecognized or conversion math failed | False |
| `GEOLOCATION_INVALID` | Coordinates missing, out of range, or unparseable | False |
| `TIMESTAMP_INVALID` | Collection timestamp invalid, in the future, or unparseable | False |
| `INSUFFICIENT_DATA` | Not enough data points to compute indicators or fusion | False |
| `QUALITY_VALIDATION_FAILED`| Data failed physical quality limits (e.g. negative reflectance) | False |
| `INDICATOR_PROCESSING_FAILED`| Required bands missing for requested indicator | False |
| `SENSOR_CONFLICT` | Contradictory readings across concurrent sensors on same flight | False |
| `EVIDENCE_VALIDATION_FAILED`| Assembled evidence fails final schema validation gate | False |
| `STORAGE_UNAVAILABLE` | External blob/metadata storage unreachable | True |
| `STORAGE_ERROR` | Error reading or writing persistence storage | False |
| `PROCESSING_TIMEOUT` | Processing exceeded configured time budget | True |
| `INTERNAL_ERROR` | Unexpected unhandled exception in processing engine | False |

Every error payload includes:
- `error_code`: One of the 18 approved codes above.
- `message`: Clear, sanitized error description.
- `module`: `"drone"`.
- `operation`: Specific component operation name (e.g., `"parse_raw_payload"`, `"calculate_indicator"`).
- `retryable`: Boolean indicating transient vs deterministic failure.
- `metadata`: Contextual key-value pairs (e.g., `{"sensor_id": "...", "format": "..."}`).
