"""Interface definitions for EarthMind Satellite Intelligence Module (Stage D1).

Defines protocol interfaces for all 24 logical components across 6 layers:

Layer 1: Satellite Data Access
1. ISatelliteProviderRegistry
2. ISatelliteProviderAdapter
3. ISatelliteCatalogDiscovery
4. ISatelliteDataAcquisition

Layer 2: Data Ingestion & Management
5. ISatelliteIngestionDetector
6. ISatelliteMetadataExtractor
7. ISatellitePreValidator
8. ISatelliteCacheStorageAdapter

Layer 3: Satellite Data Processing
9. ISatelliteImageryProcessor
10. ISatelliteSpectralProcessor
11. ISatelliteGeospatialProcessor
12. ISatelliteTemporalProcessor

Layer 4: Satellite Intelligence
13. ISatelliteIndicatorExtractor
14. ISatelliteMultiSourceFusion
15. ISatelliteUncertaintyAssessor
16. ISatelliteAgronomicFeatureExtractor

Layer 5: Evidence & Validation
17. ISatelliteEvidenceBuilder
18. ISatelliteEvidenceValidator
19. ISatelliteProvenanceTracker
20. ISatelliteGovernanceGate

Layer 6: EarthMind Integration
21. ISatelliteB2ContextAdapter
22. ISatelliteSarvamContextFormatter
23. ISatelliteCrossModuleDataSharing
24. ISatelliteDiagnostics
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from core.schemas.satellite import (
    EarthMindSatelliteEvidence,
    SatelliteAcquisitionResult,
    SatelliteDataFormat,
    SatelliteDataQuality,
    SatelliteDataRequest,
    SatelliteDatasetMetadata,
    SatelliteGeospatialMetadata,
    SatelliteIndicator,
    SatelliteIntegrationRequest,
    SatelliteIntegrationResponse,
    SatelliteProcessedData,
    SatelliteProvider,
    SatelliteRawDataReference,
    SatelliteSpectralBand,
    SatelliteTemporalMetadata,
)


# ============================================================================
# Layer 1: Satellite Data Access (Components 1 - 4)
# ============================================================================

@runtime_checkable
class ISatelliteProviderRegistry(Protocol):
    """Component 1: Registry of available satellite data providers and access methods."""

    def register_provider(self, provider: SatelliteProvider) -> bool:
        """Register or update a satellite data provider configuration."""
        ...

    def get_provider(self, provider_id: str) -> Optional[SatelliteProvider]:
        """Retrieve provider configuration by unique ID."""
        ...

    def list_providers(self, status: Optional[str] = None) -> List[SatelliteProvider]:
        """List registered providers, optionally filtered by status."""
        ...

    def is_provider_available(self, provider_id: str) -> bool:
        """Check if provider is registered and active."""
        ...


@runtime_checkable
class ISatelliteProviderAdapter(Protocol):
    """Component 2: Standardized adapter contract for third-party satellite data providers."""

    @property
    def provider_id(self) -> str:
        """Unique identifier of the provider adapter."""
        ...

    def search_catalog(self, request: SatelliteDataRequest) -> List[SatelliteDatasetMetadata]:
        """Query provider catalog for available scenes/granules matching request."""
        ...

    def acquire_dataset(self, dataset_id: str, request: SatelliteDataRequest) -> SatelliteAcquisitionResult:
        """Download or fetch satellite scene/granule assets from provider."""
        ...


@runtime_checkable
class ISatelliteCatalogDiscovery(Protocol):
    """Component 3: Search and discovery engine across multiple satellite catalogs."""

    def discover_datasets(self, request: SatelliteDataRequest) -> List[SatelliteDatasetMetadata]:
        """Search across all eligible registered providers and rank suitable datasets."""
        ...

    def select_optimal_dataset(
        self,
        candidates: List[SatelliteDatasetMetadata],
        request: SatelliteDataRequest,
    ) -> Optional[SatelliteDatasetMetadata]:
        """Select the highest-quality, lowest cloud-cover dataset from candidates."""
        ...


@runtime_checkable
class ISatelliteDataAcquisition(Protocol):
    """Component 4: Orchestrator for downloading and acquiring satellite imagery data."""

    def acquire(self, request: SatelliteDataRequest) -> SatelliteAcquisitionResult:
        """Execute acquisition workflow: discovery, selection, provider fetch, and verification."""
        ...


# ============================================================================
# Layer 2: Data Ingestion & Management (Components 5 - 8)
# ============================================================================

@runtime_checkable
class ISatelliteIngestionDetector(Protocol):
    """Component 5: Ingestion gateway and format detection for satellite files and streams."""

    def detect_format(self, payload_sample: bytes, file_name: Optional[str] = None) -> SatelliteDataFormat:
        """Detect satellite data format from magic bytes, header, or file extension."""
        ...

    def ingest_raw_data(
        self,
        dataset_id: str,
        provider_id: str,
        data_bytes: bytes,
        data_format: SatelliteDataFormat,
    ) -> SatelliteRawDataReference:
        """Safely ingest raw satellite asset bytes and generate an immutable data reference."""
        ...


@runtime_checkable
class ISatelliteMetadataExtractor(Protocol):
    """Component 6: Extractor for geospatial, temporal, and sensor metadata from satellite containers."""

    def extract_metadata(
        self,
        raw_ref: SatelliteRawDataReference,
        manifest_payload: Optional[Dict[str, Any]] = None,
    ) -> SatelliteDatasetMetadata:
        """Extract standardized dataset metadata from raw raster headers and provider manifests."""
        ...


@runtime_checkable
class ISatellitePreValidator(Protocol):
    """Component 7: Pre-processing validator for physical limits and data integrity."""

    def validate_preliminary_quality(
        self,
        dataset_metadata: SatelliteDatasetMetadata,
    ) -> SatelliteDataQuality:
        """Evaluate scene cloud cover, missing bands, corrupted blocks, and acquisition sanity."""
        ...


@runtime_checkable
class ISatelliteCacheStorageAdapter(Protocol):
    """Component 8: Provider-independent cache and storage abstraction for satellite data."""

    def store_raw_reference(self, reference: SatelliteRawDataReference) -> bool:
        """Persist a raw data reference pointer."""
        ...

    def get_raw_reference(self, reference_id: str) -> Optional[SatelliteRawDataReference]:
        """Retrieve raw data reference by ID."""
        ...

    def store_processed_data(self, data: SatelliteProcessedData) -> str:
        """Persist processed satellite band data and return storage identifier."""
        ...

    def get_processed_data(self, processed_id: str) -> Optional[SatelliteProcessedData]:
        """Retrieve processed satellite data by ID."""
        ...

    def purge_expired(self, current_time_utc: str) -> int:
        """Purge expired cache entries according to retention policy."""
        ...


# ============================================================================
# Layer 3: Satellite Data Processing (Components 9 - 12)
# ============================================================================

@runtime_checkable
class ISatelliteImageryProcessor(Protocol):
    """Component 9: Radiometric, atmospheric, and cloud masking engine."""

    def apply_atmospheric_correction(
        self,
        raw_bands: Dict[str, Any],
        metadata: SatelliteDatasetMetadata,
    ) -> Dict[str, Any]:
        """Normalize digital numbers / TOA radiance to Bottom-Of-Atmosphere (BOA) surface reflectance."""
        ...

    def generate_cloud_mask(
        self,
        scene_bands: Dict[str, Any],
        metadata: SatelliteDatasetMetadata,
    ) -> Dict[str, Any]:
        """Generate pixel-level cloud, shadow, and cirrus mask mask matrix."""
        ...


@runtime_checkable
class ISatelliteSpectralProcessor(Protocol):
    """Component 10: Spectral band calibration, statistics, and band matrix processing."""

    def process_spectral_bands(
        self,
        raw_ref: SatelliteRawDataReference,
        target_bands: List[str],
        geospatial_crop: Optional[SatelliteGeospatialMetadata] = None,
    ) -> Dict[str, SatelliteSpectralBand]:
        """Calibrate and process designated spectral bands into standardized band objects."""
        ...


@runtime_checkable
class ISatelliteGeospatialProcessor(Protocol):
    """Component 11: Geospatial alignment, CRS reprojection, and field boundary clipping."""

    def process_geospatial(
        self,
        raw_coords: Dict[str, Any],
        target_crs: str = "EPSG:4326",
    ) -> SatelliteGeospatialMetadata:
        """Transform coordinates, normalize to target CRS, and calculate bounding boxes."""
        ...

    def clip_to_field_boundary(
        self,
        band_matrix: Any,
        field_polygon: List[List[float]],
    ) -> Any:
        """Clip raster matrix to target agricultural field polygon without altering source data."""
        ...


@runtime_checkable
class ISatelliteTemporalProcessor(Protocol):
    """Component 12: Observation timestamp normalization and revisit interval modeling."""

    def process_temporal(
        self,
        acquisition_timestamp: str,
        constellation: str,
    ) -> SatelliteTemporalMetadata:
        """Validate UTC timestamps, determine revisit window, and model temporal confidence."""
        ...


# ============================================================================
# Layer 4: Satellite Intelligence (Components 13 - 16)
# ============================================================================

@runtime_checkable
class ISatelliteIndicatorExtractor(Protocol):
    """Component 13: Agricultural indicator extraction engine (NDVI, NDRE, NDWI, EVI)."""

    def extract_indicator(
        self,
        indicator_name: str,
        processed_bands: Dict[str, SatelliteSpectralBand],
        source_dataset_id: str,
    ) -> SatelliteIndicator:
        """Extract a single standardized agricultural vegetation or moisture index."""
        ...

    def extract_available_indicators(
        self,
        processed_bands: Dict[str, SatelliteSpectralBand],
        source_dataset_id: str,
    ) -> List[SatelliteIndicator]:
        """Extract all possible agricultural indicators supported by present spectral bands."""
        ...


@runtime_checkable
class ISatelliteMultiSourceFusion(Protocol):
    """Component 14: Multi-satellite constellation and multi-temporal observation fusion."""

    def fuse_constellations(
        self,
        observations: List[SatelliteProcessedData],
    ) -> Dict[str, Any]:
        """Spatially and temporally harmonize observations from disparate constellations (e.g. S2 + Landsat)."""
        ...


@runtime_checkable
class ISatelliteUncertaintyAssessor(Protocol):
    """Component 15: Multi-dimensional uncertainty and confidence assessor."""

    def assess_uncertainty(
        self,
        quality_status: SatelliteDataQuality,
        cloud_cover_target: float,
        is_calibrated: bool,
        revisit_age_days: float,
    ) -> Dict[str, Any]:
        """Assess transparent confidence dimensions across quality, cloud, calibration, and temporal signals."""
        ...


@runtime_checkable
class ISatelliteAgronomicFeatureExtractor(Protocol):
    """Component 16: Agronomic feature synthesizer (canopy cover, vigor trend, moisture status)."""

    def extract_agronomic_features(
        self,
        indicators: List[SatelliteIndicator],
        temporal_history: Optional[List[SatelliteIndicator]] = None,
    ) -> Dict[str, Any]:
        """Synthesize objective agronomic features without final diagnostic claims."""
        ...


# ============================================================================
# Layer 5: Evidence & Validation (Components 17 - 20)
# ============================================================================

@runtime_checkable
class ISatelliteEvidenceBuilder(Protocol):
    """Component 17: Satellite evidence synthesis engine."""

    def build_evidence(
        self,
        request: SatelliteDataRequest,
        processed_data: SatelliteProcessedData,
        indicators: List[SatelliteIndicator],
    ) -> EarthMindSatelliteEvidence:
        """Assemble the canonical EarthMindSatelliteEvidence artifact conforming to schema v1.0."""
        ...


@runtime_checkable
class ISatelliteEvidenceValidator(Protocol):
    """Component 18: Evidence validation gate ensuring compliance with schema v1.0."""

    def validate_evidence(self, evidence: EarthMindSatelliteEvidence) -> bool:
        """Validate candidate satellite evidence against schema v1.0 constraints and boundaries."""
        ...


@runtime_checkable
class ISatelliteProvenanceTracker(Protocol):
    """Component 19: End-to-end lineage, provider attribution, and audit tracking."""

    def record_provenance(
        self,
        dataset_id: str,
        provider_id: str,
        transformation_step: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Record an immutable transformation step in the satellite evidence lineage."""
        ...


@runtime_checkable
class ISatelliteGovernanceGate(Protocol):
    """Component 20: Governance gate preventing unauthorized memory/KB promotions and data leaks."""

    def enforce_governance(
        self,
        evidence: EarthMindSatelliteEvidence,
        tenant_id: str,
    ) -> bool:
        """Enforce tenant isolation, license attribution checks, and prevent automatic KB promotion."""
        ...


# ============================================================================
# Layer 6: EarthMind Integration (Components 21 - 24)
# ============================================================================

@runtime_checkable
class ISatelliteB2ContextAdapter(Protocol):
    """Component 21: Bridge interface delivering validated evidence to B2 Context Manager."""

    def format_for_context(
        self,
        integration_response: SatelliteIntegrationResponse,
    ) -> Any:
        """Transform validated satellite integration response into B2 ContextItem."""
        ...


@runtime_checkable
class ISatelliteSarvamContextFormatter(Protocol):
    """Component 22: Context formatter structuring satellite observations for Sarvam-105B."""

    def format_observation_summary(
        self,
        evidence: EarthMindSatelliteEvidence,
    ) -> str:
        """Generate structured text summary of satellite evidence for Sarvam-105B reasoning context."""
        ...


@runtime_checkable
class ISatelliteCrossModuleDataSharing(Protocol):
    """Component 23: Clean contract-based data sharing interface with Drone and Vision modules."""

    def share_with_drone_module(
        self,
        evidence: EarthMindSatelliteEvidence,
        field_id: str,
    ) -> Dict[str, Any]:
        """Export macro-level vegetation indices for drone flight mission planning context."""
        ...

    def share_with_vision_module(
        self,
        evidence: EarthMindSatelliteEvidence,
        field_id: str,
    ) -> Dict[str, Any]:
        """Export multispectral overview for correlating visual leaf symptom analyses."""
        ...


@runtime_checkable
class ISatelliteDiagnostics(Protocol):
    """Component 24: Operational telemetry, health checks, and performance metrics."""

    def get_health_status(self) -> Dict[str, Any]:
        """Return operational health status dictionary."""
        ...

    def record_metric(self, metric_name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a telemetry or diagnostic metric."""
        ...
