"""EarthMind Satellite Intelligence Module.

Provides satellite data access, catalog discovery, ingestion, preprocessing,
spectral and temporal analysis, agricultural indicator extraction, and validated
evidence delivery to Sarvam-105B via B2 Context Manager.
"""

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

__all__ = [
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
]
