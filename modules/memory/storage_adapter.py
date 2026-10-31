"""In-memory reference storage adapter implementation of IMemoryStorageAdapter.

Used for testing, interface verification, and local development.
Enforces optimistic locking, record isolation (deep copy on read/write),
deterministic sorting & pagination, and explicit failure simulation.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import copy

from core.interfaces.memory_storage import IMemoryStorageAdapter
from core.schemas.memory import (
    MemoryRecord,
    MemoryRecordStatus,
    MemorySearchCriteria,
    StorageHealthResult,
)
from modules.memory.errors import (
    MemoryConflictError,
    MemoryNotFoundError,
    MemoryStorageUnavailableError,
)


class InMemoryMemoryStorageAdapter(IMemoryStorageAdapter):
    """In-memory reference implementation of IMemoryStorageAdapter."""

    provider_name: str = "in_memory_reference"

    def __init__(self, simulate_unavailable: bool = False):
        self._records: Dict[str, MemoryRecord] = {}
        self.simulate_unavailable = simulate_unavailable

    def _ensure_available(self) -> None:
        if self.simulate_unavailable:
            raise MemoryStorageUnavailableError(
                self.provider_name,
                "Simulated storage unavailability."
            )

    def store_record(self, record: MemoryRecord) -> MemoryRecord:
        self._ensure_available()
        if record.record_id in self._records:
            raise MemoryConflictError(
                record.record_id,
                f"Record '{record.record_id}' already exists in storage.",
                operation="store_record"
            )
        # Deep copy to guarantee complete storage isolation
        stored = copy.deepcopy(record)
        self._records[record.record_id] = stored
        return copy.deepcopy(stored)

    def get_record(self, record_id: str) -> Optional[MemoryRecord]:
        self._ensure_available()
        record = self._records.get(record_id)
        if record is None:
            return None
        return copy.deepcopy(record)

    def search_records(self, criteria: MemorySearchCriteria) -> List[MemoryRecord]:
        self._ensure_available()
        now = datetime.now(timezone.utc)
        matched: List[MemoryRecord] = []

        for record in self._records.values():
            # Domain filter
            if criteria.domain and record.domain != criteria.domain:
                continue
            # Owner filter
            if criteria.owner_id is not None and record.owner_id != criteria.owner_id:
                continue
            # Scope type filter
            if criteria.scope_type and record.scope_type != criteria.scope_type:
                continue
            # Scope id filter
            if criteria.scope_id and record.scope_id != criteria.scope_id:
                continue
            # Record type filter
            if criteria.record_type and record.record_type != criteria.record_type:
                continue
            # Status filter
            if criteria.status and record.status != criteria.status:
                continue
            # Classification filter
            if criteria.classification and record.classification != criteria.classification:
                continue
            # Correlation ID filter
            if criteria.correlation_id and record.correlation_id != criteria.correlation_id:
                continue
            # Expiration filter
            if not criteria.include_expired and record.expires_at and record.expires_at <= now:
                continue

            matched.append(copy.deepcopy(record))

        # Deterministic sorting: order by created_at descending, then record_id ascending
        matched.sort(key=lambda r: (r.created_at, r.record_id), reverse=True)

        # Pagination: offset & limit
        return matched[criteria.offset : criteria.offset + criteria.limit]

    def update_record(
        self,
        record: MemoryRecord,
        expected_version: Optional[int] = None
    ) -> MemoryRecord:
        self._ensure_available()
        existing = self._records.get(record.record_id)
        if not existing:
            raise MemoryNotFoundError(record.record_id, operation="update_record")

        # Concurrency / optimistic locking check
        if expected_version is not None and existing.record_version != expected_version:
            raise MemoryConflictError(
                record.record_id,
                f"Version mismatch: expected {expected_version}, found {existing.record_version}.",
                operation="update_record"
            )

        # Stale version check: incoming record_version must be strictly greater than existing
        if record.record_version <= existing.record_version:
            raise MemoryConflictError(
                record.record_id,
                f"Stale version update rejected: incoming version {record.record_version} "
                f"is not greater than existing version {existing.record_version}.",
                operation="update_record"
            )

        updated = copy.deepcopy(record)
        self._records[record.record_id] = updated
        return copy.deepcopy(updated)

    def delete_record(self, record_id: str, soft: bool = True) -> bool:
        self._ensure_available()
        existing = self._records.get(record_id)
        if not existing:
            return False

        if soft:
            # Soft delete: update status and timestamp, increment version
            existing.status = MemoryRecordStatus.DELETED
            existing.record_version += 1
            existing.updated_at = datetime.now(timezone.utc)
        else:
            del self._records[record_id]
        return True

    def get_record_metadata(self, record_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_available()
        record = self._records.get(record_id)
        if not record:
            return None
        return {
            "record_id": record.record_id,
            "domain": record.domain.value,
            "record_type": record.record_type,
            "owner_id": record.owner_id,
            "scope_type": record.scope_type.value,
            "scope_id": record.scope_id,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "schema_version": record.schema_version,
            "record_version": record.record_version,
            "status": record.status.value,
            "classification": record.classification.value,
            "correlation_id": record.correlation_id,
        }

    def check_health(self) -> StorageHealthResult:
        if self.simulate_unavailable:
            return StorageHealthResult(
                is_healthy=False,
                provider_name=self.provider_name,
                details={"error": "Storage simulated unavailable."}
            )
        return StorageHealthResult(
            is_healthy=True,
            provider_name=self.provider_name,
            details={"record_count": len(self._records)}
        )
