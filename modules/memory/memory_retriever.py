"""EarthMind Memory Module: Structured Retrieval Component.

Implements exact domain/scope lookups, typed metadata filtering, bounded pagination,
and deterministic sorting without vector search, semantic embeddings, or pgvector.
"""

from typing import Any, Dict, List, Optional

from core.interfaces.memory_storage import IMemoryStorageAdapter
from core.schemas.memory import (
    AuthorizationContext,
    MemoryDomain,
    MemoryOperation,
    MemoryRecord,
    MemoryRecordStatus,
    MemoryScope,
    MemorySearchCriteria,
    MemorySortField,
    SortOrder,
)
from modules.memory.errors import (
    MemoryForbiddenError,
    MemoryInvalidArgumentError,
    MemoryNotFoundError,
    MemoryUnauthorizedError,
)
from modules.memory.security import MemorySecurityEnforcer


class MemoryRetriever:
    """Starter alias preserved for backward compatibility."""
    pass


class StructuredMemoryRetriever(MemoryRetriever):
    """Provides secure, structured, deterministic retrieval and filtering for memory records."""

    def __init__(
        self,
        storage_adapter: IMemoryStorageAdapter,
        enforcer: Optional[MemorySecurityEnforcer] = None,
    ):
        self.storage = storage_adapter
        self.enforcer = enforcer or MemorySecurityEnforcer()

    def get_by_id(
        self,
        context: Optional[AuthorizationContext],
        record_id: str,
    ) -> MemoryRecord:
        """Fetch a single record by record_id under authorization enforcement."""
        if not record_id or not str(record_id).strip():
            raise MemoryInvalidArgumentError("Record ID cannot be empty.", operation="get_by_id")

        record = self.storage.get_record(record_id)
        if record is None:
            raise MemoryNotFoundError(record_id, operation="get_by_id")

        self.enforcer.enforce_authorization(
            context=context,
            operation=MemoryOperation.READ,
            domain=record.domain,
            scope_type=record.scope_type,
            scope_id=record.scope_id,
            owner_id=record.owner_id,
            record_id=record.record_id,
            record=record,
        )

        return record

    def search(
        self,
        context: Optional[AuthorizationContext],
        criteria: MemorySearchCriteria,
    ) -> List[MemoryRecord]:
        """Execute authorized structured search with bounded pagination and deterministic sorting."""
        if not isinstance(criteria, MemorySearchCriteria):
            raise MemoryInvalidArgumentError("Criteria must be an instance of MemorySearchCriteria.", operation="search")

        effective_domain = criteria.domain or MemoryDomain.USER

        if effective_domain == MemoryDomain.USER:
            claimed_owner = criteria.owner_id or (context.principal_id.strip() if context and context.principal_id else None)
            self.enforcer.enforce_authorization(
                context=context,
                operation=MemoryOperation.SEARCH,
                domain=MemoryDomain.USER,
                scope_type=criteria.scope_type or MemoryScope.USER,
                scope_id=criteria.scope_id,
                owner_id=claimed_owner,
                correlation_id=criteria.correlation_id,
            )
            criteria = criteria.model_copy(update={"domain": MemoryDomain.USER, "owner_id": claimed_owner})
        else:
            self.enforcer.enforce_authorization(
                context=context,
                operation=MemoryOperation.SEARCH,
                domain=MemoryDomain.GENERAL,
                scope_type=criteria.scope_type or MemoryScope.GENERAL,
                scope_id=criteria.scope_id,
                owner_id=None,
                correlation_id=criteria.correlation_id,
            )
            criteria = criteria.model_copy(update={"domain": MemoryDomain.GENERAL, "owner_id": None})

        # Fetch matching records from storage adapter
        records = self.storage.search_records(criteria)

        # Apply secondary authorization filtering to guarantee no leakage
        authorized_records: List[MemoryRecord] = []
        for rec in records:
            try:
                self.enforcer.enforce_authorization(
                    context=context,
                    operation=MemoryOperation.READ,
                    domain=rec.domain,
                    scope_type=rec.scope_type,
                    scope_id=rec.scope_id,
                    owner_id=rec.owner_id,
                    record_id=rec.record_id,
                    correlation_id=rec.correlation_id,
                    record=rec,
                )
                authorized_records.append(rec)
            except (MemoryForbiddenError, MemoryUnauthorizedError, MemoryInvalidArgumentError):
                continue

        # Deterministic in-memory sort enforcement if storage provider sort needs guarantee
        reverse = (criteria.sort_order == SortOrder.DESC)
        if criteria.sort_by == MemorySortField.CREATED_AT:
            authorized_records.sort(key=lambda r: (r.created_at, r.record_id), reverse=reverse)
        elif criteria.sort_by == MemorySortField.UPDATED_AT:
            authorized_records.sort(key=lambda r: (r.updated_at, r.record_id), reverse=reverse)
        elif criteria.sort_by == MemorySortField.RECORD_ID:
            authorized_records.sort(key=lambda r: r.record_id, reverse=reverse)

        return authorized_records
