class StorageError(Exception):
    """Base exception for all C.2 storage errors."""
    pass


class ArtifactNotFoundError(StorageError):
    """Raised when a requested raw artifact is not found in storage."""
    pass


class RecordNotFoundError(StorageError):
    """Raised when a canonical record is not found in repository storage."""
    pass


class StorageConfigurationError(StorageError):
    """Raised when a storage configuration parameter is invalid or missing."""
    pass
