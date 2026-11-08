"""Drone Module exception re-exports.

Exposes specialized Drone exceptions defined in core.errors.exceptions.
"""

from core.errors.exceptions import (
    DroneError,
    DroneInvalidArgumentError,
    UnsupportedSensorError,
    UnsupportedFormatError,
    InvalidSensorDataError,
    SensorMetadataMissingError,
    CalibrationUnavailableError,
    UnitConversionFailedError,
    GeolocationInvalidError,
    TimestampInvalidError,
    InsufficientDroneDataError,
    QualityValidationFailedError,
    IndicatorProcessingFailedError,
    SensorConflictError,
    EvidenceValidationFailedError,
    DroneStorageUnavailableError,
    DroneStorageError,
    DroneProcessingTimeoutError,
    DroneInternalError,
)

__all__ = [
    "DroneError",
    "DroneInvalidArgumentError",
    "UnsupportedSensorError",
    "UnsupportedFormatError",
    "InvalidSensorDataError",
    "SensorMetadataMissingError",
    "CalibrationUnavailableError",
    "UnitConversionFailedError",
    "GeolocationInvalidError",
    "TimestampInvalidError",
    "InsufficientDroneDataError",
    "QualityValidationFailedError",
    "IndicatorProcessingFailedError",
    "SensorConflictError",
    "EvidenceValidationFailedError",
    "DroneStorageUnavailableError",
    "DroneStorageError",
    "DroneProcessingTimeoutError",
    "DroneInternalError",
]
