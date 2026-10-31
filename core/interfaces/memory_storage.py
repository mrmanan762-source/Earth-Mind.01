"""Storage Adapter Protocol for the EarthMind Memory Module.

Defines a clean, provider-independent storage abstraction.
Any persistent storage backend (e.g., Supabase PostgreSQL, SQLite, In-Memory)
implements this protocol without exposing database-specific SDK types or behaviors.
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from core.schemas.memory import (
    MemoryRecord,
    MemorySearchCriteria,
    StorageHealthResult,
)


@runtime_checkable
class IMemoryStorageAdapter(Protocol):
    """Provider-independent storage adapter protocol for memory records.

    Contract guarantees:
    1. Full support for USER and GENERAL memory records.
    2. Preservation of record ownership, versions, and metadata.
    3. Optimistic locking / conflict detection on updates via expected_version.
    4. Deterministic error raising on storage failure (never silent fallback).
    5. Clean separation from database SDK specifics.
    """

    provider_name: str

    def store_record(self, record: MemoryRecord) -> MemoryRecord:
        """Store a new memory record.

        Raises:
            MemoryConflictError: If a record with the same record_id already exists.
            MemoryStorageUnavailableError: If storage backend is unreachable.
            MemoryStorageError: On storage failure.
        """
        ...

    def get_record(self, record_id: str) -> Optional[MemoryRecord]:
        """Retrieve a single memory record by its immutable record_id.

        Returns None if record does not exist.
        Raises:
            MemoryStorageUnavailableError: If storage backend is unreachable.
            MemoryStorageError: On storage failure.
        """
        ...

    def search_records(self, criteria: MemorySearchCriteria) -> List[MemoryRecord]:
        """Search memory records using structured criteria.

        Raises:
            MemoryStorageUnavailableError: If storage backend is unreachable.
            MemoryStorageError: On storage failure.
        """
        ...

    def update_record(
        self,
        record: MemoryRecord,
        expected_version: Optional[int] = None
    ) -> MemoryRecord:
        """Update an existing memory record with optimistic concurrency control.

        Args:
            record: The updated record with incremented record_version.
            expected_version: If provided, the existing record version in storage must match this value.

        Raises:
            MemoryNotFoundError: If record does not exist.
            MemoryConflictError: If expected_version does not match stored version.
            MemoryStorageUnavailableError: If storage backend is unreachable.
            MemoryStorageError: On storage failure.
        """
        ...

    def delete_record(self, record_id: str, soft: bool = True) -> bool:
        """Delete a memory record by record_id.

        Args:
            record_id: Target record identifier.
            soft: If True, marks record as DELETED; if False, removes record permanently.

        Returns:
            bool: True if record was found and deleted, False if record did not exist.

        Raises:
            MemoryStorageUnavailableError: If storage backend is unreachable.
            MemoryStorageError: On storage failure.
        """
        ...

    def get_record_metadata(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve record metadata without fetching the entire payload.

        Returns None if record does not exist.
        """
        ...

    def check_health(self) -> StorageHealthResult:
        """Evaluate connectivity and operational capability of storage provider."""
        ...
