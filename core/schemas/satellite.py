"""Data Contracts for EarthMind Satellite Intelligence Module (Stage D1).

Defines formally specified, versioned Pydantic models and enumerations for:
- SatelliteProviderStatus, SatelliteAcquisitionStatus, SatelliteProcessingStatus,
  SatelliteDataQuality, SatelliteEvidenceStatus, SatelliteErrorCode,
  SatelliteBandType, SatelliteSensorType, SatelliteDataFormat
- SatelliteGeospatialMetadata and SatelliteTemporalMetadata
- SatelliteSpectralBand (Contract for spectral channels/bands)
- SatelliteDataRequest (Contract 1)
- SatelliteProvider (Contract 2)
- SatelliteDatasetMetadata (Contract 3)
- SatelliteAcquisitionResult (Contract 4)
- SatelliteRawDataReference (Contract 5)
- SatelliteProcessedData (Contract 6)
- SatelliteIndicator (Contract 7)
- EarthMindSatelliteEvidence (Contract 8 - Primary Output Contract v1.0)
- SatelliteIntegrationRequest and SatelliteIntegrationResponse (Contract 9 - B2/Sarvam Integration)
- SatelliteErrorContract (Contract 10 - Standardized Errors)
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

class SatelliteProviderStatus(str, Enum):
    """Operational status of a satellite data provider."""
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    MAINTENANCE = "MAINTENANCE"
    UNAVAILABLE = "UNAVAILABLE"
    DEPRECATED = "DEPRECATED"


class SatelliteAcquisitionStatus(str, Enum):
    """Lifecycle status of satellite imagery acquisition."""
    PENDING = "PENDING"
    SEARCHING = "SEARCHING"
    FOUND = "FOUND"
    DOWNLOADING = "DOWNLOADING"
    ACQUIRED = "ACQUIRED"
    NOT_FOUND = "NOT_FOUND"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SatelliteProcessingStatus(str, Enum):
    """Processing stage status for satellite data."""
    PENDING = "PENDING"
    PREPROCESSING = "PREPROCESSING"
    PROCESSED = "PROCESSED"
    CALIBRATED = "CALIBRATED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class SatelliteDataQuality(str, Enum):
    """Quality classification of satellite observations."""
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    ACCEPTABLE = "ACCEPTABLE"
    DEGRADED = "DEGRADED"
    CLOUD_OBSCURED = "CLOUD_OBSCURED"
    INCOMPLETE = "INCOMPLETE"
    INVALID = "INVALID"


class SatelliteEvidenceStatus(str, Enum):
    """Overall status of generated EarthMindSatelliteEvidence artifact."""
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class SatelliteSensorType(str, Enum):
    """Category of Earth observation satellite sensor."""
    OPTICAL_MULTISPECTRAL = "OPTICAL_MULTISPECTRAL"
    OPTICAL_HYPERSPECTRAL = "OPTICAL_HYPERSPECTRAL"
    SYNTHETIC_APERTURE_RADAR = "SYNTHETIC_APERTURE_RADAR"
    THERMAL_INFRARED = "THERMAL_INFRARED"
    ALTIMETER = "ALTIMETER"
    RADIOMETER = "RADIOMETER"
    ATMOSPHERIC_SOUNDER = "ATMOSPHERIC_SOUNDER"
    OTHER = "OTHER"


class SatelliteBandType(str, Enum):
    """Standardized spectral and radar band classifications."""
    COASTAL_AEROSOL = "COASTAL_AEROSOL"
    BLUE = "BLUE"
    GREEN = "GREEN"
    RED = "RED"
    RED_EDGE_1 = "RED_EDGE_1"
    RED_EDGE_2 = "RED_EDGE_2"
    RED_EDGE_3 = "RED_EDGE_3"
    NIR = "NIR"
    NIR_NARROW = "NIR_NARROW"
    WATER_VAPOUR = "WATER_VAPOUR"
    SWIR_1 = "SWIR_1"
    SWIR_2 = "SWIR_2"
    THERMAL_1 = "THERMAL_1"
    THERMAL_2 = "THERMAL_2"
    SAR_VV = "SAR_VV"
    SAR_VH = "SAR_VH"
    SAR_HH = "SAR_HH"
    SAR_HV = "SAR_HV"
    OTHER = "OTHER"


class SatelliteDataFormat(str, Enum):
    """Supported satellite file and data formats."""
    GEOTIFF = "GEOTIFF"
    COG = "COG"  # Cloud-Optimized GeoTIFF
    NETCDF = "NETCDF"
    HDF5 = "HDF5"
    SAFE = "SAFE"  # Sentinel Standard Archive Format for Europe
    ZARR = "ZARR"
    JSON = "JSON"
    GEOJSON = "GEOJSON"
    CSV = "CSV"
    RAW_BINARY = "RAW_BINARY"


class SatelliteErrorCode(str, Enum):
    """Approved error code taxonomy for Satellite Module errors."""
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    DATASET_UNAVAILABLE = "DATASET_UNAVAILABLE"
    DATASET_NOT_FOUND = "DATASET_NOT_FOUND"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    INGESTION_FAILED = "INGESTION_FAILED"
    INVALID_METADATA = "INVALID_METADATA"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    QUALITY_VALIDATION_FAILED = "QUALITY_VALIDATION_FAILED"
    INDICATOR_PROCESSING_FAILED = "INDICATOR_PROCESSING_FAILED"
    EVIDENCE_VALIDATION_FAILED = "EVIDENCE_VALIDATION_FAILED"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    STORAGE_ERROR = "STORAGE_ERROR"
    TIMEOUT = "TIMEOUT"
    INTEGRATION_ERROR = "INTEGRATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ============================================================================
# Shared Geospatial and Temporal Models
# ============================================================================

class SatelliteGeospatialMetadata(BaseModel):
    """Geospatial spatial context for satellite data and requests."""
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Centroid latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Centroid longitude in decimal degrees")
    bounding_box: Optional[List[float]] = Field(
        None,
        min_length=4,
        max_length=4,
        description="Bounding box [min_lon, min_lat, max_lon, max_lat] in decimal degrees"
    )
    crs: str = Field("EPSG:4326", description="Coordinate Reference System identifier (default WGS84)")
    spatial_resolution_meters: Optional[float] = Field(None, gt=0.0, description="Nominal pixel ground resolution in meters")
    field_id: Optional[str] = Field(None, description="Associated agricultural field ID")
    farm_id: Optional[str] = Field(None, description="Associated farm ID")
    coverage_area_hectares: Optional[float] = Field(None, ge=0.0, description="Estimated coverage area in hectares")

    @model_validator(mode="after")
    def validate_bounding_box(self) -> "SatelliteGeospatialMetadata":
        if self.bounding_box is not None:
            min_lon, min_lat, max_lon, max_lat = self.bounding_box
            if min_lat > max_lat:
                raise ValueError(f"min_lat ({min_lat}) cannot exceed max_lat ({max_lat})")
            if min_lon > max_lon:
                raise ValueError(f"min_lon ({min_lon}) cannot exceed max_lon ({max_lon})")
            if not (-90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0):
                raise ValueError("Bounding box latitude values must be between -90.0 and 90.0")
            if not (-180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0):
                raise ValueError("Bounding box longitude values must be between -180.0 and 180.0")
        return self


class SatelliteTemporalMetadata(BaseModel):
    """Temporal coverage and acquisition timing for satellite observations."""
    acquisition_date: str = Field(..., description="ISO 8601 UTC date or timestamp of observation")
    start_time: Optional[str] = Field(None, description="ISO 8601 UTC start of observation window")
    end_time: Optional[str] = Field(None, description="ISO 8601 UTC end of observation window")
    revisit_interval_days: Optional[float] = Field(None, gt=0.0, description="Sensor constellation revisit interval in days")
    temporal_coverage_type: str = Field("SCENE_INSTANTANEOUS", description="Temporal nature (e.g. SCENE_INSTANTANEOUS, COMPOSITE_10DAY)")


# ============================================================================
# Spectral Band Model
# ============================================================================

class SatelliteSpectralBand(BaseModel):
    """Spectral or radar channel band specification with calibration and statistics."""
    band_id: str = Field(..., min_length=1, description="Band identifier (e.g. 'B04', 'B08', 'VV')")
    band_name: str = Field(..., min_length=1, description="Descriptive band name (e.g. 'RED', 'NIR', 'SAR_VV')")
    band_type: SatelliteBandType = Field(..., description="Standardized band category")
    central_wavelength_nm: Optional[float] = Field(None, gt=0.0, description="Central wavelength in nanometers")
    bandwidth_nm: Optional[float] = Field(None, gt=0.0, description="Bandwidth (FWHM) in nanometers")
    spatial_resolution_meters: float = Field(..., gt=0.0, description="Pixel resolution in meters")
    measurement_unit: str = Field("reflectance", description="Scientific unit (e.g. 'reflectance', 'radiance_W_m2_sr_um', 'sigma0_dB')")
    is_calibrated: bool = Field(True, description="Whether radiometric/sensor calibration has been applied")
    data_format: SatelliteDataFormat = Field(SatelliteDataFormat.COG, description="Storage format of the band raster")
    band_raster_ref: Optional[str] = Field(None, description="URI or path reference to band raster artifact")
    statistics: Dict[str, float] = Field(default_factory=dict, description="Summary statistics (mean, min, max, std_dev)")


# ============================================================================
# Contract 1: Satellite Data Request
# ============================================================================

class SatelliteDataRequest(BaseModel):
    """
    Contract 1: User or system request for satellite observations over a target area and timeframe.
    """
    request_id: str = Field(default_factory=lambda: f"sat_req_{uuid.uuid4().hex[:12]}", description="Unique request identifier")
    tenant_id: str = Field("default", min_length=1, description="Tenant / farmer identifier for data isolation")
    farmer_id: Optional[str] = Field(None, description="Authorized farmer ID")
    farm_id: Optional[str] = Field(None, description="Target farm ID")
    field_id: Optional[str] = Field(None, description="Target agricultural field ID")

    geospatial: SatelliteGeospatialMetadata = Field(..., description="Target geographic coordinates and extent")
    temporal_window: SatelliteTemporalMetadata = Field(..., description="Target observation date or time window")

    target_constellations: List[str] = Field(
        default_factory=lambda: ["Sentinel-2", "Landsat-8/9"],
        description="Preferred satellite missions/constellations"
    )
    sensor_types: List[SatelliteSensorType] = Field(
        default_factory=lambda: [SatelliteSensorType.OPTICAL_MULTISPECTRAL],
        description="Required sensor categories"
    )
    requested_bands: List[str] = Field(
        default_factory=list,
        description="Specific band IDs requested (e.g. ['RED', 'NIR'])"
    )
    requested_indicators: List[str] = Field(
        default_factory=list,
        description="Specific agricultural indicators requested (e.g. ['NDVI', 'NDWI', 'NDRE'])"
    )

    max_cloud_cover_percentage: float = Field(20.0, ge=0.0, le=100.0, description="Maximum acceptable cloud cover percentage")
    prefer_calibrated: bool = Field(True, description="Prefer surface reflectance (BOA/L2A) over top-of-atmosphere (TOA/L1C)")
    created_at: str = Field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        description="ISO 8601 UTC creation timestamp"
    )


# ============================================================================
# Contract 2: Satellite Provider
# ============================================================================

class SatelliteProvider(BaseModel):
    """
    Contract 2: Registered satellite data provider capability manifest.
    """
    provider_id: str = Field(..., min_length=1, description="Unique provider identifier (e.g. 'copernicus_scihub', 'usgs_eros', 'isro_bhuvan')")
    provider_name: str = Field(..., min_length=1, description="Human-readable provider name")
    status: SatelliteProviderStatus = Field(SatelliteProviderStatus.ACTIVE, description="Current operational status")
    supported_constellations: List[str] = Field(..., min_length=1, description="Missions supported (e.g. ['Sentinel-2A', 'Sentinel-2B'])")
    supported_sensor_types: List[SatelliteSensorType] = Field(..., min_length=1, description="Supported sensor types")
    supported_formats: List[SatelliteDataFormat] = Field(..., min_length=1, description="Supported data formats")
    access_protocol: str = Field("REST_API", description="Protocol type (e.g. 'STAC_API', 'REST_API', 'AWS_S3_BUCKET')")
    requires_authentication: bool = Field(True, description="Whether API credentials are required")
    credential_key_env_var: Optional[str] = Field(None, description="Environment variable name for provider credentials")
    rate_limit_requests_per_minute: int = Field(60, gt=0, description="Configured rate limit")
    terms_of_service_url: Optional[str] = Field(None, description="URL to data provider terms and licensing")
    license_type: str = Field("OPEN_ACCESS", description="License classification (e.g. 'OPEN_ACCESS', 'RESTRICTED', 'COMMERCIAL')")
    attribution_text: str = Field(..., description="Mandatory attribution statement")


# ============================================================================
# Contract 3: Satellite Dataset Metadata
# ============================================================================

class SatelliteDatasetMetadata(BaseModel):
    """
    Contract 3: Comprehensive catalog metadata for an acquired or discoverable satellite scene/granule.
    """
    dataset_id: str = Field(..., min_length=1, description="Granule or scene identifier (e.g. 'S2A_MSIL2A_20250330T051651_N0511_R062_T43REQ_20250330T073612')")
    provider_id: str = Field(..., min_length=1, description="Provider identifier")
    constellation: str = Field(..., min_length=1, description="Satellite constellation/mission")
    platform: str = Field(..., min_length=1, description="Spacecraft platform identifier (e.g. 'Sentinel-2A')")
    instrument: str = Field(..., min_length=1, description="Instrument name (e.g. 'MSI', 'OLI-2', 'TIRS-2')")
    sensor_type: SatelliteSensorType = Field(..., description="Sensor category")
    processing_level: str = Field(..., description="Data processing level (e.g. 'LEVEL-2A', 'LEVEL-1C')")

    geospatial: SatelliteGeospatialMetadata = Field(..., description="Scene geospatial coverage and resolution")
    temporal: SatelliteTemporalMetadata = Field(..., description="Scene acquisition timestamp and timing")

    cloud_cover_percentage: float = Field(0.0, ge=0.0, le=100.0, description="Scene cloud cover percentage")
    snow_ice_percentage: Optional[float] = Field(None, ge=0.0, le=100.0, description="Snow or ice percentage")
    sun_elevation_degrees: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Sun elevation angle at scene center")
    sun_azimuth_degrees: Optional[float] = Field(None, ge=0.0, le=360.0, description="Sun azimuth angle at scene center")

    available_bands: List[SatelliteSpectralBand] = Field(default_factory=list, description="Metadata of spectral bands in dataset")
    data_format: SatelliteDataFormat = Field(SatelliteDataFormat.COG, description="Data packaging format")
    quality_status: SatelliteDataQuality = Field(SatelliteDataQuality.GOOD, description="Quality rating")
    license_attribution: str = Field(..., description="Attribution text required by provider")
    raw_reference_uri: Optional[str] = Field(None, description="URI or path reference to raw dataset granule")


# ============================================================================
# Contract 4: Satellite Acquisition Result
# ============================================================================

class SatelliteAcquisitionResult(BaseModel):
    """
    Contract 4: Output of satellite catalog discovery and data acquisition operation.
    """
    acquisition_id: str = Field(default_factory=lambda: f"acq_{uuid.uuid4().hex[:12]}", description="Acquisition execution ID")
    request_id: str = Field(..., min_length=1, description="Associated request ID")
    status: SatelliteAcquisitionStatus = Field(..., description="Acquisition lifecycle status")
    provider_id: str = Field(..., min_length=1, description="Provider used for acquisition")
    dataset_metadata: Optional[SatelliteDatasetMetadata] = Field(None, description="Acquired dataset metadata if found")
    acquired_at: str = Field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        description="ISO 8601 UTC timestamp of acquisition completion"
    )
    download_size_bytes: Optional[int] = Field(None, ge=0, description="Total size in bytes of acquired assets")
    cached: bool = Field(False, description="Whether data was served from cache")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings during acquisition")
    error_message: Optional[str] = Field(None, description="Error explanation if status is FAILED or NOT_FOUND")


# ============================================================================
# Contract 5: Satellite Raw Data Reference
# ============================================================================

class SatelliteRawDataReference(BaseModel):
    """
    Contract 5: Immutable reference pointer to stored raw satellite imagery artifact.
    Prevents holding massive multi-gigabyte rasters in Python memory.
    """
    reference_id: str = Field(default_factory=lambda: f"ref_{uuid.uuid4().hex[:12]}", description="Unique reference ID")
    dataset_id: str = Field(..., min_length=1, description="Dataset/granule identifier")
    provider_id: str = Field(..., min_length=1, description="Source provider identifier")
    storage_uri: str = Field(..., min_length=1, description="URI or filesystem path where raw data is stored")
    data_format: SatelliteDataFormat = Field(..., description="Data format of stored artifact")
    size_bytes: int = Field(..., ge=0, description="Size of artifact in bytes")
    sha256_hash: Optional[str] = Field(None, description="Cryptographic SHA-256 hash of raw data for audit integrity")
    retention_expires_at: Optional[str] = Field(None, description="ISO 8601 UTC timestamp when raw cache expires")
    created_at: str = Field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        description="ISO 8601 UTC creation timestamp"
    )


# ============================================================================
# Contract 6: Satellite Processed Data
# ============================================================================

class SatelliteProcessedData(BaseModel):
    """
    Contract 6: Standardized container for calibrated, georeferenced, processed satellite band matrices.
    Preserves original vs processed values and normalization lineage.
    """
    processed_id: str = Field(default_factory=lambda: f"proc_{uuid.uuid4().hex[:12]}", description="Unique processed data ID")
    dataset_id: str = Field(..., min_length=1, description="Source dataset identifier")
    field_id: Optional[str] = Field(None, description="Associated agricultural field ID")
    processing_status: SatelliteProcessingStatus = Field(SatelliteProcessingStatus.PROCESSED, description="Processing status")
    processing_pipeline: str = Field("standard_satellite_pipeline_v1", description="Applied pipeline identifier")
    engine_version: str = Field("1.0.0", description="Processing engine version")

    processed_bands: Dict[str, SatelliteSpectralBand] = Field(
        default_factory=dict,
        description="Dictionary of calibrated processed bands indexed by band name"
    )
    geospatial: SatelliteGeospatialMetadata = Field(..., description="Validated geospatial bounding and resolution")
    temporal: SatelliteTemporalMetadata = Field(..., description="Observation timing")
    quality_status: SatelliteDataQuality = Field(SatelliteDataQuality.GOOD, description="Processing quality assessment")

    atmospheric_correction_applied: bool = Field(True, description="Whether atmospheric correction (BOA) was verified/applied")
    cloud_mask_applied: bool = Field(False, description="Whether cloud and shadow masking was applied to exclude pixels")
    cloud_coverage_over_target: float = Field(0.0, ge=0.0, le=100.0, description="Cloud cover percentage strictly over target field")

    provenance: Dict[str, Any] = Field(default_factory=dict, description="Detailed processing lineage and transform steps")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal processing warnings")


# ============================================================================
# Contract 7: Satellite Indicator
# ============================================================================

class SatelliteIndicator(BaseModel):
    """
    Contract 7: Standardized agricultural indicator extracted from satellite bands (e.g. NDVI, NDWI, NDRE, EVI).
    Calculated strictly when required spectral bands are physically present and calibrated.
    """
    indicator_id: str = Field(default_factory=lambda: f"sat_ind_{uuid.uuid4().hex[:12]}", description="Unique indicator ID")
    indicator_name: str = Field(..., min_length=1, description="Canonical indicator name (e.g. 'NDVI', 'NDRE', 'NDWI')")
    definition: str = Field(..., description="Agronomic and mathematical definition of indicator")
    calculation_method: str = Field(..., description="Algorithm or formula applied")
    required_bands: List[str] = Field(..., min_length=1, description="List of required spectral band names")
    source_dataset_id: str = Field(..., min_length=1, description="Origin satellite dataset ID")

    result_statistics: Dict[str, Any] = Field(
        ...,
        description="Statistical summary over target area (mean, min, max, std_dev, median, p25, p75, or status if degraded)"
    )
    unit: str = Field("unitless_ratio", description="Scientific unit of the calculated indicator")
    quality_status: SatelliteDataQuality = Field(SatelliteDataQuality.GOOD, description="Indicator quality classification")
    limitations: List[str] = Field(default_factory=list, description="Known agronomic or physical limitations")
    warnings: List[str] = Field(default_factory=list, description="Processing or cloud-interference warnings")


# ============================================================================
# Contract 8: EarthMind Satellite Evidence (Primary Output Contract v1.0)
# ============================================================================

class SatelliteSourceInfo(BaseModel):
    """Source satellite constellation, instrument, and provider details."""
    provider_id: str = Field(..., description="Satellite data provider identifier")
    constellation: str = Field(..., description="Constellation name (e.g. 'Sentinel-2')")
    platform: str = Field(..., description="Spacecraft platform (e.g. 'Sentinel-2B')")
    instrument: str = Field(..., description="Sensor/instrument name (e.g. 'MSI')")
    sensor_type: SatelliteSensorType = Field(..., description="Category of sensor")
    dataset_id: str = Field(..., description="Granule or scene identifier")
    processing_level: str = Field(..., description="Processing level (e.g. 'LEVEL-2A')")


class SatelliteScopeInfo(BaseModel):
    """Target agricultural scope."""
    tenant_id: str = Field("default", description="Tenant identifier")
    farmer_id: Optional[str] = Field(None, description="Authorized farmer identifier")
    farm_id: Optional[str] = Field(None, description="Farm identifier")
    field_id: Optional[str] = Field(None, description="Agricultural field identifier")
    crop: Optional[str] = Field(None, description="Target crop if specified")


class SatelliteQualityAssessment(BaseModel):
    """Multi-dimensional quality indicators for satellite evidence."""
    overall_quality: SatelliteDataQuality = Field(SatelliteDataQuality.GOOD, description="Composite quality rating")
    cloud_cover_percentage: float = Field(0.0, ge=0.0, le=100.0, description="Cloud cover percentage over target")
    is_atmospheric_corrected: bool = Field(True, description="Confirms surface reflectance / atmospheric correction")
    resolution_fidelity: str = Field("NATIVE", description="Resolution quality (NATIVE, RESAMPLED, DEGRADED)")
    evidence_completeness: str = Field("COMPLETE", description="Completeness of requested observations")


class SatelliteUncertaintyAssessment(BaseModel):
    """Transparent uncertainty and confidence breakdown without invented probabilities."""
    spatial_confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence in geospatial alignment")
    temporal_confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence in observation timeliness")
    spectral_confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence in spectral radiometric quality")
    overall_confidence: float = Field(1.0, ge=0.0, le=1.0, description="Composite confidence rating")
    uncertainty_sources: List[str] = Field(default_factory=list, description="Documented sources of uncertainty")


class EarthMindSatelliteEvidence(BaseModel):
    """
    Contract 8: Formal Output Contract v1.0 of the EarthMind Satellite Intelligence Module.
    Encapsulates validated, structured satellite observations for B2 Context Manager and Sarvam-105B.
    """
    contract_name: str = Field("EarthMindSatelliteEvidence", description="Approved contract identifier")
    schema_version: str = Field("1.0", description="Contract schema version")
    evidence_id: str = Field(default_factory=lambda: f"ev_sat_{uuid.uuid4().hex[:12]}", description="Unique evidence ID")

    source: SatelliteSourceInfo = Field(..., description="Origin satellite mission and sensor identity")
    scope: SatelliteScopeInfo = Field(default_factory=SatelliteScopeInfo, description="Agricultural scope")

    geospatial: SatelliteGeospatialMetadata = Field(..., description="Geospatial coverage and resolution")
    temporal: SatelliteTemporalMetadata = Field(..., description="Observation timing and revisit window")

    indicators: List[SatelliteIndicator] = Field(default_factory=list, description="Extracted agricultural indicators")
    band_summaries: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="Summary statistics of key spectral bands over target area"
    )

    quality: SatelliteQualityAssessment = Field(default_factory=SatelliteQualityAssessment, description="Quality assessment")
    uncertainty: SatelliteUncertaintyAssessment = Field(default_factory=SatelliteUncertaintyAssessment, description="Uncertainty metrics")

    license_attribution: str = Field(..., description="Mandatory attribution statement for data provider")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Cryptographic hashes and processing lineage")

    warnings: List[str] = Field(default_factory=list, description="Non-fatal operational warnings")
    limitations: List[str] = Field(default_factory=list, description="Agronomic or physical limitations")
    status: SatelliteEvidenceStatus = Field(SatelliteEvidenceStatus.SUCCESS, description="Execution status")

    @model_validator(mode="after")
    def validate_contract_integrity(self) -> "EarthMindSatelliteEvidence":
        if self.contract_name != "EarthMindSatelliteEvidence":
            raise ValueError(f"Invalid contract_name: expected 'EarthMindSatelliteEvidence', got '{self.contract_name}'")
        if self.schema_version != "1.0":
            raise ValueError(f"Unsupported schema_version: expected '1.0', got '{self.schema_version}'")
        return self


# ============================================================================
# Contract 9: Satellite Integration Request & Response (B2 Context Manager Bridge)
# ============================================================================

class SatelliteIntegrationRequest(BaseModel):
    """
    Contract 9A: Request from B2 Context Manager or Orchestrator requesting satellite evidence.
    """
    request_id: str = Field(default_factory=lambda: f"sat_int_req_{uuid.uuid4().hex[:12]}", description="Integration request ID")
    tenant_id: str = Field("default", description="Tenant identifier")
    farmer_id: Optional[str] = Field(None, description="Farmer identifier")
    farm_id: Optional[str] = Field(None, description="Farm identifier")
    field_id: Optional[str] = Field(None, description="Field identifier")

    latitude: float = Field(..., ge=-90.0, le=90.0, description="Target centroid latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Target centroid longitude")
    target_date: Optional[str] = Field(None, description="Desired observation date (ISO 8601 UTC)")
    lookback_days: int = Field(30, ge=1, le=365, description="Maximum days to look back for cloud-free observations")
    requested_indicators: List[str] = Field(default_factory=lambda: ["NDVI"], description="Requested indicators")
    target_model: str = Field("Sarvam-105B", description="Target reasoning model")
    context_priority: str = Field("HIGH", description="Priority level for B2 context budgeting")


class SatelliteIntegrationResponse(BaseModel):
    """
    Contract 9B: Bridge providing validated satellite evidence to EarthMind's B2 Context Manager.
    Sarvam-105B consumes context via B2; the Satellite Module does not bypass B2.
    """
    contract_name: str = Field("SatelliteIntegrationResponse", description="Bridge contract identifier")
    schema_version: str = Field("1.0", description="Bridge schema version")
    request_id: str = Field(..., min_length=1, description="Origin integration request ID")
    evidence: EarthMindSatelliteEvidence = Field(..., description="Validated satellite evidence payload")
    target_model: str = Field("Sarvam-105B", description="Target reasoning model")
    context_priority: str = Field("HIGH", description="Context priority level for B2 budgeting")
    bounded_token_estimate: int = Field(350, ge=1, description="Estimated token footprint of structured summary")

    def to_context_item(self) -> "ContextItem":
        """
        Converts validated satellite evidence into a B2-compliant ContextItem.
        Enforces loose coupling without bypassing B2 Context Manager.
        """
        from modules.context.schemas import ContextItem, PriorityLevel, PrivacyLevel

        indicators_summary = [
            {"indicator": ind.indicator_name, "value": ind.result_statistics, "quality": ind.quality_status.value}
            for ind in self.evidence.indicators
        ]

        content_payload = {
            "evidence_id": self.evidence.evidence_id,
            "provider_id": self.evidence.source.provider_id,
            "constellation": self.evidence.source.constellation,
            "platform": self.evidence.source.platform,
            "instrument": self.evidence.source.instrument,
            "dataset_id": self.evidence.source.dataset_id,
            "acquisition_date": self.evidence.temporal.acquisition_date,
            "indicators": indicators_summary,
            "band_summaries": self.evidence.band_summaries,
            "cloud_cover_percentage": self.evidence.quality.cloud_cover_percentage,
            "overall_quality": self.evidence.quality.overall_quality.value,
            "overall_confidence": self.evidence.uncertainty.overall_confidence,
            "license_attribution": self.evidence.license_attribution,
            "warnings": self.evidence.warnings,
            "limitations": self.evidence.limitations,
            "status": self.evidence.status.value,
        }

        priority_enum = PriorityLevel.HIGH if self.context_priority.upper() == "HIGH" else PriorityLevel.MEDIUM

        return ContextItem(
            context_id=f"ctx_sat_{self.evidence.evidence_id}",
            entity_type="satellite_evidence",
            entity_id=self.evidence.scope.field_id or self.evidence.evidence_id,
            data_type="satellite_observation",
            content=content_payload,
            farmer_id=self.evidence.scope.farmer_id,
            farm_id=self.evidence.scope.farm_id,
            field_id=self.evidence.scope.field_id,
            event_time=self.evidence.temporal.acquisition_date,
            source="satellite_module",
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
                "geospatial": self.evidence.geospatial.model_dump(),
                "license_attribution": self.evidence.license_attribution,
            }
        )


# ============================================================================
# Contract 10: Structured Error Contract
# ============================================================================

class SatelliteErrorContract(BaseModel):
    """
    Contract 10: Standardized structured error contract conforming to EarthMind ErrorContract standards.
    """
    error_code: SatelliteErrorCode = Field(..., description="Standardized Satellite error code")
    message: str = Field(..., description="Sanitized, human-readable error explanation")
    module: str = Field("satellite", description="Origin module name")
    operation: str = Field(..., description="Specific operation during which error occurred")
    retryable: bool = Field(False, description="Whether caller should retry operation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Structured contextual diagnostics")
