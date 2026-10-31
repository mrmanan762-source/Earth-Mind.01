"""Memory module specific exceptions re-exported from core exception hierarchy."""

from core.errors.exceptions import (
    MemoryError,
    MemoryInvalidArgumentError,
    MemoryInvalidRecordSchemaError,
    MemoryUnauthorizedError,
    MemoryForbiddenError,
    MemoryNotFoundError,
    MemoryConflictError,
    MemoryStorageUnavailableError,
    MemoryStorageError,
    MemoryRetentionPolicyViolationError,
    MemoryIntegrityError,
    MemoryInternalError,
)

__all__ = [
    "MemoryError",
    "MemoryInvalidArgumentError",
    "MemoryInvalidRecordSchemaError",
    "MemoryUnauthorizedError",
    "MemoryForbiddenError",
    "MemoryNotFoundError",
    "MemoryConflictError",
    "MemoryStorageUnavailableError",
    "MemoryStorageError",
    "MemoryRetentionPolicyViolationError",
    "MemoryIntegrityError",
    "MemoryInternalError",
]
