"""Error classes for EarthMind Satellite Intelligence Module (Stage D1).

Re-exports satellite exceptions from core.errors.exceptions for module-level access.
"""

from core.errors.exceptions import (
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
