"""Satellite Intelligence Module for EarthMind (Stages D1, D2, D3, D4 & D5).

Provides satellite data access, catalog discovery, ingestion, preprocessing,
hybrid caching, data processing, and analytical intelligence capabilities.
"""

from modules.satellite.acquisition import SatelliteDataAcquisitionEngine
from modules.satellite.adapters import (
    BaseSatelliteProviderAdapter,
    CopernicusCdseAdapter,
    IsroBhuvanAdapter,
    MockSatelliteProviderAdapter,
    NasaEarthdataAdapter,
    SatelliteAdapterRegistry,
)
from modules.satellite.cache import SatelliteHybridCache
from modules.satellite.capabilities import (
    ProviderCapabilityManager,
    ProviderCapabilityProfile,
)
from modules.satellite.catalog import SatelliteDataCatalog
from modules.satellite.change_detection import SatelliteChangeDetector
from modules.satellite.diagnostics import SatelliteDiagnostics
from modules.satellite.discovery import SatelliteDiscoveryEngine
from modules.satellite.errors import (
    SatelliteDatasetNotFoundError,
    SatelliteDatasetUnavailableError,
    SatelliteError,
    SatelliteEvidenceValidationError,
    SatelliteIndicatorProcessingError,
    SatelliteIngestionError,
    SatelliteInsufficientDataError,
    SatelliteIntegrationError,
    SatelliteInternalError,
    SatelliteInvalidArgumentError,
    SatelliteMetadataError,
    SatelliteProcessingError,
    SatelliteProviderError,
    SatelliteProviderUnavailableError,
    SatelliteQualityValidationFailedError,
    SatelliteStorageError,
    SatelliteStorageUnavailableError,
    SatelliteTimeoutError,
    SatelliteUnsupportedFormatError,
)
from modules.satellite.formats import SatelliteFormatCapability, SatelliteFormatDetector
from modules.satellite.fusion import SatelliteMultiSourceFusionEngine
from modules.satellite.geospatial import SatelliteGeospatialProcessor
from modules.satellite.image_processing import SatelliteImageProcessor
from modules.satellite.indices import SatelliteSpectralIndexEngine, SpectralIndexDefinition
from modules.satellite.indicators import SatelliteIndicatorGenerator
from modules.satellite.ingestion import SatelliteIngestionEngine
from modules.satellite.lifecycle import (
    SatelliteLifecycleManager,
    SatelliteLifecycleState,
    SatelliteLifecycleTracker,
)
from modules.satellite.metadata_extractor import SatelliteMetadataExtractor
from modules.satellite.pre_validator import SatellitePreValidator
from modules.satellite.processing_pipeline import SatelliteProcessingPipeline
from modules.satellite.quality import QualityValidationReport, SatelliteQualityValidator
from modules.satellite.radar_thermal import (
    SatelliteSARProcessor,
    SatelliteThermalProcessor,
)
from modules.satellite.registry import SatelliteProviderRegistry
from modules.satellite.request_manager import SatelliteRequestManager, SatelliteRequestState
from modules.satellite.request_validator import SatelliteRequestValidator
from modules.satellite.satellite_module import SatelliteModule
from modules.satellite.satellite_service import SatelliteService
from modules.satellite.spatial_analysis import SatelliteSpatialAnalyzer
from modules.satellite.spectral import SatelliteSpectralProcessor
from modules.satellite.storage import (
    FilesystemSatelliteStorageAdapter,
    InMemorySatelliteStorageAdapter,
    resolve_satellite_storage_adapter,
)
from modules.satellite.temporal_analysis import SatelliteTemporalAnalyzer
from modules.satellite.temporal_numerical import SatelliteTemporalProcessor
from modules.satellite.vegetation_water import VegetationWaterAnalyzer

__all__ = [
    # Errors
    "SatelliteError",
    "SatelliteInvalidArgumentError",
    "SatelliteProviderError",
    "SatelliteProviderUnavailableError",
    "SatelliteDatasetUnavailableError",
    "SatelliteDatasetNotFoundError",
    "SatelliteUnsupportedFormatError",
    "SatelliteIngestionError",
    "SatelliteMetadataError",
    "SatelliteProcessingError",
    "SatelliteInsufficientDataError",
    "SatelliteQualityValidationFailedError",
    "SatelliteIndicatorProcessingError",
    "SatelliteEvidenceValidationError",
    "SatelliteStorageUnavailableError",
    "SatelliteStorageError",
    "SatelliteTimeoutError",
    "SatelliteIntegrationError",
    "SatelliteInternalError",
    # Lifecycle
    "SatelliteLifecycleState",
    "SatelliteLifecycleTracker",
    "SatelliteLifecycleManager",
    # Capabilities & Registry
    "ProviderCapabilityProfile",
    "ProviderCapabilityManager",
    "SatelliteProviderRegistry",
    # Adapters
    "BaseSatelliteProviderAdapter",
    "NasaEarthdataAdapter",
    "IsroBhuvanAdapter",
    "CopernicusCdseAdapter",
    "MockSatelliteProviderAdapter",
    "SatelliteAdapterRegistry",
    # Validation & Diagnostics
    "SatelliteRequestValidator",
    "SatelliteDiagnostics",
    # D3 Catalog, Format, Ingestion, Caching & Acquisition
    "SatelliteDataCatalog",
    "SatellitePreValidator",
    "SatelliteFormatCapability",
    "SatelliteFormatDetector",
    "SatelliteMetadataExtractor",
    "SatelliteIngestionEngine",
    "SatelliteHybridCache",
    "SatelliteDiscoveryEngine",
    "SatelliteRequestState",
    "SatelliteRequestManager",
    "SatelliteDataAcquisitionEngine",
    "InMemorySatelliteStorageAdapter",
    "FilesystemSatelliteStorageAdapter",
    "resolve_satellite_storage_adapter",
    # D4 Processing Components
    "SatelliteImageProcessor",
    "SatelliteSpectralProcessor",
    "SatelliteGeospatialProcessor",
    "SatelliteTemporalProcessor",
    "SatelliteQualityValidator",
    "QualityValidationReport",
    "SatelliteSARProcessor",
    "SatelliteThermalProcessor",
    "SatelliteProcessingPipeline",
    # D5 Analytical Engines
    "SatelliteSpectralIndexEngine",
    "SpectralIndexDefinition",
    "VegetationWaterAnalyzer",
    "SatelliteSpatialAnalyzer",
    "SatelliteTemporalAnalyzer",
    "SatelliteChangeDetector",
    "SatelliteIndicatorGenerator",
    "SatelliteMultiSourceFusionEngine",
    # Core Service and Module
    "SatelliteService",
    "SatelliteModule",
]
