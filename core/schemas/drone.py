"""Data Contracts for EarthMind Drone Module (Stage D1).

Defines formally specified, versioned Pydantic models for:
- SensorCategory, DroneDataFormat, QualityStatus, CalibrationStatus, EvidenceStatus, DroneErrorCode
- Geospatial and Temporal models (SpatialCoordinates, SpatialBoundingBox, SpatialCoverage, TemporalCoverage)
- DroneSensorInputContract (Contract 1)
- SensorMetadataContract (Contract 2)
- ProcessedSensorMeasurementContract (Contract 3)
- AgriculturalIndicatorContract (Contract 4)
- EarthMindDroneSensorEvidence (Contract 5 - Output Contract v1.0)
- DroneCameraRoutingContract (Contract 6 - Vision Handoff)
- DroneSarvamIntegrationContract (Contract 7 - B2/Sarvam Bridge)
- DroneErrorContract (Contract 8 - Standardized Errors)
"""

from enum import Enum
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from modules.context.schemas import ContextItem


# ============================================================================
# Core Enumerations
# ============================================================================

class SensorCategory(str, Enum):
    """Hardware categories for drone-mounted sensors."""
    MULTISPECTRAL = "MULTISPECTRAL"
    HYPERSPECTRAL = "HYPERSPECTRAL"
    THERMAL = "THERMAL"
    RGB = "RGB"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    SOIL = "SOIL"
    LIDAR = "LIDAR"
    OTHER = "OTHER"


class DroneDataFormat(str, Enum):
    """Supported raw sensor data file and stream formats."""
    GEOTIFF = "GEOTIFF"
    NETCDF = "NETCDF"
    HDF5 = "HDF5"
    CSV = "CSV"
    JSON = "JSON"
    LAS = "LAS"
    POINT_CLOUD = "POINT_CLOUD"
    RAW_BINARY = "RAW_BINARY"
    JPEG_METADATA = "JPEG_METADATA"


class QualityStatus(str, Enum):
    """Quality rating of processed sensor measurement or stream."""
    VALID = "VALID"
    SUSPECT = "SUSPECT"
    DEGRADED = "DEGRADED"
    CALIBRATION_MISSING = "CALIBRATION_MISSING"
    GEOLOCATION_DEGRADED = "GEOLOCATION_DEGRADED"
    INCOMPLETE = "INCOMPLETE"
    INVALID = "INVALID"


class CalibrationStatus(str, Enum):
    """Calibration state of drone sensor observations."""
    CALIBRATED = "CALIBRATED"
    UNCALIBRATED = "UNCALIBRATED"
    FACTORY_DEFAULT = "FACTORY_DEFAULT"
    EXPIRED = "EXPIRED"
    MISSING = "MISSING"


class EvidenceStatus(str, Enum):
    """Overall status of generated EarthMindDroneSensorEvidence artifact."""
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class DroneErrorCode(str, Enum):
    """Approved error code taxonomy for Drone Module errors."""
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    UNSUPPORTED_SENSOR = "UNSUPPORTED_SENSOR"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    INVALID_SENSOR_DATA = "INVALID_SENSOR_DATA"
    SENSOR_METADATA_MISSING = "SENSOR_METADATA_MISSING"
    CALIBRATION_UNAVAILABLE = "CALIBRATION_UNAVAILABLE"
    UNIT_CONVERSION_FAILED = "UNIT_CONVERSION_FAILED"
    GEOLOCATION_INVALID = "GEOLOCATION_INVALID"
    TIMESTAMP_INVALID = "TIMESTAMP_INVALID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    QUALITY_VALIDATION_FAILED = "QUALITY_VALIDATION_FAILED"
    INDICATOR_PROCESSING_FAILED = "INDICATOR_PROCESSING_FAILED"
    SENSOR_CONFLICT = "SENSOR_CONFLICT"
    EVIDENCE_VALIDATION_FAILED = "EVIDENCE_VALIDATION_FAILED"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    STORAGE_ERROR = "STORAGE_ERROR"
    PROCESSING_TIMEOUT = "PROCESSING_TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ============================================================================
# Geospatial and Temporal Shared Models
# ============================================================================

class SpatialCoordinates(BaseModel):
    """Geographic point coordinates."""
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees")
    altitude_meters: Optional[float] = Field(None, description="Altitude in meters above ground or sea level")
    crs: str = Field("EPSG:4326", description="Coordinate Reference System identifier (default WGS84)")


class SpatialBoundingBox(BaseModel):
    """Geographic bounding box."""
    min_latitude: float = Field(..., ge=-90.0, le=90.0)
    max_latitude: float = Field(..., ge=-90.0, le=90.0)
    min_longitude: float = Field(..., ge=-180.0, le=180.0)
    max_longitude: float = Field(..., ge=-180.0, le=180.0)
    crs: str = Field("EPSG:4326", description="CRS of the bounding box")

    @model_validator(mode="after")
    def validate_bounds(self) -> "SpatialBoundingBox":
        if self.min_latitude > self.max_latitude:
            raise ValueError(f"min_latitude ({self.min_latitude}) cannot exceed max_latitude ({self.max_latitude})")
        if self.min_longitude > self.max_longitude:
            raise ValueError(f"min_longitude ({self.min_longitude}) cannot exceed max_longitude ({self.max_longitude})")
        return self


class SpatialCoverage(BaseModel):
    """Complete spatial context for drone observations."""
    has_spatial_metadata: bool = Field(True, description="False if geolocation is absent (prevents hallucination)")
    centroid: Optional[SpatialCoordinates] = Field(None, description="Center coordinate of the mission or observation")
    bounding_box: Optional[SpatialBoundingBox] = Field(None, description="Bounding box encompassing observations")
    area_hectares: Optional[float] = Field(None, ge=0.0, description="Estimated coverage area in hectares")
    crs: str = Field("EPSG:4326", description="Coordinate Reference System")
    field_id: Optional[str] = Field(None, description="Referenced agricultural field ID")


class TemporalCoverage(BaseModel):
    """Temporal range and sampling rate of drone mission observations."""
    start_time: str = Field(..., description="ISO 8601 UTC timestamp of observation start")
    end_time: Optional[str] = Field(None, description="ISO 8601 UTC timestamp of observation end")
    duration_seconds: Optional[float] = Field(None, ge=0.0, description="Mission duration in seconds")
    sampling_frequency_hz: Optional[float] = Field(None, gt=0.0, description="Sensor sampling frequency in Hz")


# ============================================================================
# 6.1 Drone Sensor Input Contract
# ============================================================================

class DroneSensorInputContract(BaseModel):
    """
    Contract 1: Ingested raw sensor data entering the Drone Module via the Data Gateway.
    Untrusted input with strict field validations.
    """
    source_type: str = Field("drone_sensor", description="Source category identifier")
    drone_id: str = Field(..., min_length=1, description="Registered drone hardware identifier")
    sensor_id: str = Field(..., min_length=1, description="Registered sensor identifier")
    sensor_type: str = Field(..., min_length=1, description="Sensor category or model descriptor")
    manufacturer: Optional[str] = Field(None, description="Hardware manufacturer")
    model: Optional[str] = Field(None, description="Hardware model name")
    data_format: DroneDataFormat = Field(..., description="Format of the sensor data")

    # Data payload references
    raw_payload_ref: Optional[str] = Field(None, description="URI or path reference to raw data artifact")
    raw_payload: Optional[Any] = Field(None, description="Inline raw payload buffer or parsed dictionary")

    # Timestamps
    collection_timestamp: str = Field(..., description="ISO 8601 UTC timestamp when sensor recorded data")
    ingestion_timestamp: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                     description="ISO 8601 UTC timestamp of gateway ingestion")

    # Spatial and unit metadata
    spatial_metadata: Optional[Dict[str, Any]] = Field(None, description="Raw spatial tags or coordinates")
    unit_metadata: Optional[Dict[str, str]] = Field(default_factory=dict, description="Declared measurement units")
    calibration_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Calibration panel/sun sensor info")

    # Scoping
    field_id: Optional[str] = Field(None, description="Authorized target field ID")
    farm_id: Optional[str] = Field(None, description="Authorized target farm ID")
    farmer_id: Optional[str] = Field(None, description="Authorized tenant farmer ID")

    # Provenance
    source_provenance: Dict[str, Any] = Field(default_factory=dict, description="Origin upload details and file hashes")

    @model_validator(mode="after")
    def validate_payload_presence(self) -> "DroneSensorInputContract":
        if self.raw_payload_ref is None and self.raw_payload is None:
            raise ValueError("Either 'raw_payload_ref' or 'raw_payload' must be provided.")
        return self


# ============================================================================
# 6.2 Sensor Metadata Contract
# ============================================================================

class SensorMetadataContract(BaseModel):
    """
    Contract 2: Hardware profile and capability manifest of registered drone sensors.
    """
    sensor_id: str = Field(..., min_length=1, description="Unique registered sensor identifier")
    sensor_category: SensorCategory = Field(..., description="Hardware sensor category")
    manufacturer: Optional[str] = Field(None, description="Manufacturer name")
    model: Optional[str] = Field(None, description="Sensor model name")
    supported_measurements: List[str] = Field(default_factory=list, description="Supported measurement channel names")
    supported_formats: List[DroneDataFormat] = Field(default_factory=list, description="Supported file/stream formats")
    measurement_units: Dict[str, str] = Field(default_factory=dict, description="Standard units for measurements")
    sampling_characteristics: Dict[str, Any] = Field(default_factory=dict, description="Band count, GSD, wavelength range")
    calibration_metadata: Dict[str, Any] = Field(default_factory=dict, description="Calibration requirements and intervals")
    capability_version: str = Field("1.0", description="Schema or capability manifest version")
    registration_status: str = Field("ACTIVE", description="Registration status (ACTIVE, DEPRECATED, INACTIVE)")


# ============================================================================
# 6.3 Processed Sensor Measurement Contract
# ============================================================================

class ProcessedSensorMeasurementContract(BaseModel):
    """
    Contract 3: Individual processed sensor measurement.
    Preserves original vs processed values and units to prevent loss of raw telemetry.
    """
    measurement_id: str = Field(default_factory=lambda: f"meas_{uuid.uuid4().hex[:12]}", description="Unique measurement ID")
    measurement_type: str = Field(..., description="Measurement type (e.g. 'spectral_reflectance', 'temperature')")
    channel_name: str = Field(..., description="Specific channel or band (e.g. 'red', 'nir', 'lwir')")

    original_value: Any = Field(..., description="Unmodified original sensor reading (DN, raw volts, etc.)")
    original_unit: str = Field(..., description="Original raw unit")
    processed_value: float = Field(..., description="Calibrated, normalized numerical value")
    normalized_unit: str = Field(..., description="Standardized SI/scientific unit")

    processing_method: str = Field(..., description="Name of normalization/calibration algorithm applied")
    calibration_status: CalibrationStatus = Field(CalibrationStatus.CALIBRATED, description="Calibration status")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp of measurement")
    spatial_reference: Optional[SpatialCoordinates] = Field(None, description="Georeferenced coordinate of measurement")
    quality_status: QualityStatus = Field(QualityStatus.VALID, description="Measurement quality status")
    source_sensor: str = Field(..., description="Origin sensor ID")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Transformation history and source references")


# ============================================================================
# 6.4 Agricultural Indicator Contract
# ============================================================================

class AgriculturalIndicatorContract(BaseModel):
    """
    Contract 4: Standardized agricultural indicator extracted from sensor measurements.
    Strictly records definitions, input measurements, and limitations.
    """
    indicator_id: str = Field(default_factory=lambda: f"ind_{uuid.uuid4().hex[:12]}", description="Unique indicator ID")
    indicator_name: str = Field(..., description="Standardized indicator name (e.g. 'NDVI', 'NDRE', 'CWSI')")
    definition: str = Field(..., description="Mathematical or agronomic definition of indicator")
    calculation_method: str = Field(..., description="Calculation algorithm identifier")
    required_input_measurements: List[str] = Field(..., description="Required input channel/measurement names")
    result: Dict[str, Any] = Field(..., description="Statistical summary or matrix (mean, min, max, std_dev, raster_ref)")
    unit: str = Field("unitless_ratio", description="Unit of the indicator")
    spatial_coverage: Optional[SpatialCoverage] = Field(None, description="Spatial extent of the calculated indicator")
    temporal_coverage: Optional[TemporalCoverage] = Field(None, description="Temporal window of calculation")
    processing_version: str = Field("1.0", description="Engine version used for calculation")
    quality_status: QualityStatus = Field(QualityStatus.VALID, description="Quality classification of indicator")
    limitations: List[str] = Field(default_factory=list, description="Known agronomic or physical limitations of result")


# ============================================================================
# 6.5 Sensor Evidence Contract (EarthMindDroneSensorEvidence v1.0)
# ============================================================================

class DroneSourceInfo(BaseModel):
    """Origin hardware identity in sensor evidence."""
    source_type: str = Field("drone_sensor", description="Source category")
    drone_id: str = Field(..., description="Drone identifier")
    sensor_id: str = Field(..., description="Primary sensor identifier")
    sensor_type: str = Field(..., description="Sensor category or model descriptor")
    manufacturer: Optional[str] = Field(None, description="Manufacturer")
    model: Optional[str] = Field(None, description="Model")


class DroneFieldInfo(BaseModel):
    """Target agricultural field scope in sensor evidence."""
    field_id: Optional[str] = Field(None, description="Field identifier")
    farm_id: Optional[str] = Field(None, description="Farm identifier")
    farmer_id: Optional[str] = Field(None, description="Farmer identifier")
    crop: Optional[str] = Field(None, description="Crop name if specified")


class DroneCollectionInfo(BaseModel):
    """Mission and collection execution metadata in sensor evidence."""
    mission_id: Optional[str] = Field(None, description="Mission or flight identifier")
    collection_timestamp: str = Field(..., description="ISO 8601 UTC timestamp of collection")
    ingestion_timestamp: str = Field(..., description="ISO 8601 UTC timestamp of ingestion")
    flight_altitude_meters: Optional[float] = Field(None, description="Nominal flight altitude in meters")
    flight_speed_mps: Optional[float] = Field(None, description="Nominal flight speed in m/s")


class DroneQualityAssessment(BaseModel):
    """Multi-dimensional quality indicators for sensor evidence."""
    input_validity: QualityStatus = Field(QualityStatus.VALID, description="Input data validity status")
    measurement_quality: str = Field("NORMAL", description="Overall measurement fidelity (HIGH, NORMAL, DEGRADED)")
    processing_quality: str = Field("NORMALIZED", description="Processing pipeline state")
    evidence_completeness: str = Field("COMPLETE", description="Completeness of requested channels/indicators")
    overall_quality: str = Field("HIGH", description="Composite quality summary")


class DroneUncertaintyAssessment(BaseModel):
    """Transparent uncertainty and confidence breakdown without invented probabilities."""
    spatial_confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence in geospatial positioning")
    temporal_confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence in timestamp accuracy")
    calibration_confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence in radiometric calibration")
    overall_confidence: float = Field(1.0, ge=0.0, le=1.0, description="Composite confidence rating")
    uncertainty_sources: List[str] = Field(default_factory=list, description="Documented physical sources of uncertainty")


class DroneCalibrationInfo(BaseModel):
    """Calibration parameters applied during evidence processing."""
    calibration_status: CalibrationStatus = Field(CalibrationStatus.CALIBRATED, description="Calibration state")
    panel_used: bool = Field(False, description="Whether radiometric calibration panel was used")
    sun_sensor_used: bool = Field(False, description="Whether incident light / DLS sensor was used")
    calibration_timestamp: Optional[str] = Field(None, description="Timestamp of calibration execution or cert")


class DroneProcessingInfo(BaseModel):
    """Processing engine metadata."""
    engine_version: str = Field("1.0.0", description="Drone module processing engine version")
    pipeline: str = Field("standard_drone_pipeline_v1", description="Applied processing pipeline")
    processing_timestamp: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                      description="ISO 8601 UTC processing timestamp")


class EarthMindDroneSensorEvidence(BaseModel):
    """
    Contract 5: Formal Output Contract v1.0 of the EarthMind Drone Module.
    Encapsulates validated, structured sensor observations for B2 Context Manager and Sarvam-105B.
    """
    contract_name: str = Field("EarthMindDroneSensorEvidence", description="Approved contract identifier")
    schema_version: str = Field("1.0", description="Contract schema version")
    evidence_id: str = Field(default_factory=lambda: f"ev_drone_{uuid.uuid4().hex[:12]}", description="Unique evidence ID")

    source: DroneSourceInfo = Field(..., description="Origin drone and sensor information")
    field: DroneFieldInfo = Field(default_factory=DroneFieldInfo, description="Field and farm scoping")
    collection: DroneCollectionInfo = Field(..., description="Collection and flight parameters")

    measurements: List[ProcessedSensorMeasurementContract] = Field(default_factory=list, description="Validated measurements")
    indicators: List[AgriculturalIndicatorContract] = Field(default_factory=list, description="Extracted agricultural indicators")

    spatial_coverage: SpatialCoverage = Field(default_factory=SpatialCoverage, description="Spatial boundaries and centroid")
    temporal_coverage: TemporalCoverage = Field(..., description="Temporal coverage of observations")

    quality: DroneQualityAssessment = Field(default_factory=DroneQualityAssessment, description="Quality assessment")
    uncertainty: DroneUncertaintyAssessment = Field(default_factory=DroneUncertaintyAssessment, description="Uncertainty metrics")
    calibration: DroneCalibrationInfo = Field(default_factory=DroneCalibrationInfo, description="Calibration metadata")
    processing: DroneProcessingInfo = Field(default_factory=DroneProcessingInfo, description="Processing engine lineage")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Cryptographic hashes and source lineage")

    warnings: List[str] = Field(default_factory=list, description="Non-fatal operational warnings")
    limitations: List[str] = Field(default_factory=list, description="Agronomic or physical limitations")
    status: EvidenceStatus = Field(EvidenceStatus.SUCCESS, description="Execution status")

    @model_validator(mode="after")
    def validate_contract_integrity(self) -> "EarthMindDroneSensorEvidence":
        if self.contract_name != "EarthMindDroneSensorEvidence":
            raise ValueError(f"Invalid contract_name: expected 'EarthMindDroneSensorEvidence', got '{self.contract_name}'")
        if self.schema_version != "1.0":
            raise ValueError(f"Unsupported schema_version: expected '1.0', got '{self.schema_version}'")
        return self


# ============================================================================
# 6.6 Camera Routing Contract
# ============================================================================

class DroneCameraRoutingContract(BaseModel):
    """
    Contract 6: Optical camera imagery handoff contract.
    Routes raw camera frames/imagery to the Vision Module without visual interpretation by Drone Module.
    """
    contract_name: str = Field("DroneCameraRoutingContract", description="Contract identifier")
    schema_version: str = Field("1.0", description="Schema version")
    routing_id: str = Field(default_factory=lambda: f"route_cam_{uuid.uuid4().hex[:12]}", description="Unique routing ID")

    drone_id: str = Field(..., min_length=1, description="Drone hardware identifier")
    camera_id: str = Field(..., min_length=1, description="Camera sensor identifier")
    sensor_category: SensorCategory = Field(SensorCategory.RGB, description="Optical sensor category (RGB)")

    mission_reference: Optional[str] = Field(None, description="Mission or flight reference ID")
    field_id: Optional[str] = Field(None, description="Associated agricultural field ID")
    farm_id: Optional[str] = Field(None, description="Associated agricultural farm ID")
    farmer_id: Optional[str] = Field(None, description="Associated farmer ID")

    collection_timestamp: str = Field(..., description="ISO 8601 UTC timestamp of image capture")
    image_reference: str = Field(..., description="URI or path reference to image file (S3, local disk)")
    image_mime_type: str = Field("image/jpeg", description="MIME type of the image")

    spatial_metadata: Optional[Dict[str, Any]] = Field(None, description="GPS coordinates, gimbal pitch, heading")
    source_provenance: Dict[str, Any] = Field(default_factory=dict, description="Flight controller and frame metadata")

    destination_module: str = Field("vision", description="Target module for visual interpretation")
    requires_visual_interpretation: bool = Field(True, description="Explicit marker indicating optical interpretation is required")


# ============================================================================
# 6.7 Sarvam Integration Contract & B2 Bridge
# ============================================================================

class DroneSarvamIntegrationContract(BaseModel):
    """
    Contract 7: Bridge providing validated sensor evidence to EarthMind's B2 Context Manager.
    Sarvam-105B consumes context via B2; the Drone Module does not bypass B2.
    """
    contract_name: str = Field("DroneSarvamIntegrationContract", description="Bridge contract identifier")
    schema_version: str = Field("1.0", description="Bridge schema version")
    evidence: EarthMindDroneSensorEvidence = Field(..., description="Validated sensor evidence payload")
    target_model: str = Field("Sarvam-105B", description="Target reasoning model")
    context_priority: str = Field("HIGH", description="Context priority level for B2 budgeting")
    bounded_token_estimate: int = Field(350, ge=1, description="Estimated token footprint of structured summary")

    def to_context_item(self) -> "ContextItem":
        """
        Converts validated drone evidence into a B2-compliant ContextItem.
        Enforces loose coupling without bypassing B2 Context Manager.
        """
        from modules.context.schemas import ContextItem, PriorityLevel, PrivacyLevel

        indicators_summary = [
            {"indicator": ind.indicator_name, "value": ind.result, "quality": ind.quality_status.value}
            for ind in self.evidence.indicators
        ]

        content_payload = {
            "evidence_id": self.evidence.evidence_id,
            "drone_id": self.evidence.source.drone_id,
            "sensor_id": self.evidence.source.sensor_id,
            "sensor_type": self.evidence.source.sensor_type,
            "collection_time": self.evidence.collection.collection_timestamp,
            "indicators": indicators_summary,
            "measurements_count": len(self.evidence.measurements),
            "calibration_status": self.evidence.calibration.calibration_status.value,
            "overall_quality": self.evidence.quality.overall_quality,
            "overall_confidence": self.evidence.uncertainty.overall_confidence,
            "warnings": self.evidence.warnings,
            "limitations": self.evidence.limitations,
            "status": self.evidence.status.value,
        }

        priority_enum = PriorityLevel.HIGH if self.context_priority.upper() == "HIGH" else PriorityLevel.MEDIUM

        return ContextItem(
            context_id=f"ctx_drone_{self.evidence.evidence_id}",
            entity_type="drone_sensor_evidence",
            entity_id=self.evidence.field.field_id or self.evidence.evidence_id,
            data_type="sensor_evidence",
            content=content_payload,
            farmer_id=self.evidence.field.farmer_id,
            farm_id=self.evidence.field.farm_id,
            field_id=self.evidence.field.field_id,
            event_time=self.evidence.collection.collection_timestamp,
            source="drone_module",
            source_id=self.evidence.evidence_id,
            confidence=self.evidence.uncertainty.overall_confidence,
            privacy_level=PrivacyLevel.FARM_PRIVATE,
            is_pii=False,
            relevance_score=1.0,
            priority=priority_enum,
            token_count=self.bounded_token_estimate,
            version=self.schema_version,
            metadata={
                "contract_name": self.contract_name,
                "evidence_status": self.evidence.status.value,
                "spatial_coverage": self.evidence.spatial_coverage.model_dump(),
            }
        )


# ============================================================================
# 6.8 Structured Error Contract
# ============================================================================

class DroneErrorContract(BaseModel):
    """
    Contract 8: Standardized structured error contract conforming to EarthMind ErrorContract standards.
    """
    error_code: DroneErrorCode = Field(..., description="Standardized Drone error code")
    message: str = Field(..., description="Sanitized, human-readable error explanation")
    module: str = Field("drone", description="Origin module name")
    operation: str = Field(..., description="Specific operation during which error occurred")
    retryable: bool = Field(False, description="Whether client/caller should retry operation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Structured contextual diagnostics")
