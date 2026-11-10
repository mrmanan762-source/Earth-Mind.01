"""EarthMind Satellite Intelligence Module.

Provides satellite data access, catalog discovery, ingestion, preprocessing,
spectral and temporal analysis, agricultural indicator extraction, and validated
evidence delivery to Sarvam-105B via B2 Context Manager.
"""

from modules.satellite.adapters import (
    BaseSatelliteProviderAdapter,
    CopernicusCdseAdapter,
    IsroBhuvanAdapter,
    MockSatelliteProviderAdapter,
    NasaEarthdataAdapter,
    SatelliteAdapterRegistry,
)
from modules.satellite.capabilities import (
    ProviderCapabilityManager,
    ProviderCapabilityProfile,
)
from modules.satellite.diagnostics import SatelliteDiagnostics
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
from modules.satellite.lifecycle import (
    SatelliteLifecycleManager,
    SatelliteLifecycleState,
    SatelliteLifecycleTracker,
)
from modules.satellite.registry import SatelliteProviderRegistry
from modules.satellite.request_validator import SatelliteRequestValidator
from modules.satellite.satellite_module import SatelliteModule
from modules.satellite.satellite_service import SatelliteService

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
    # Request Validation
    "SatelliteRequestValidator",
    # Diagnostics
    "SatelliteDiagnostics",
    # Service & Module
    "SatelliteService",
    "SatelliteModule",
]
