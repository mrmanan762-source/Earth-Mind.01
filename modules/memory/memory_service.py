"""Secure Memory Domain Service Layer for EarthMind Memory Module Level 4.

Wraps an IMemoryStorageAdapter with MemorySecurityEnforcer and MemorySecurityAuditor,
enforcing centralized domain separation, user ownership, scope boundaries,
General Memory governance, anti-promotion rules, version management,
and lifecycle operations across all operations.
"""

from datetime import datetime, timezone
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
    PurgeCriteria,
    PurgeResult,
    RetentionPolicy,
    StorageHealthResult,
)
from modules.memory.errors import (
    MemoryForbiddenError,
    MemoryInvalidArgumentError,
    MemoryNotFoundError,
    MemoryUnauthorizedError,
)
from modules.memory.memory_lifecycle import MemoryLifecycleManager
from modules.memory.memory_validator import MemoryRecordValidator
from modules.memory.security import (
    MemorySecurityAuditor,
    MemorySecurityEnforcer,
)


class MemoryService:
    """Complete and secure memory service managing User and General memory domains.

    Enforces:
    - Mandatory, trusted AuthorizationContext on all operations.
    - User ownership and cross-user isolation.
    - Scope-aware permissions (USER, CONVERSATION, FARM, FIELD, CROP_CYCLE, GENERAL).
    - General Memory governance (preventing ordinary users from modifying shared knowledge).
    - Prevention of private User Memory leaking into General Memory.
    - Centralized audit events without sensitive payload leakage.
    - Fail-closed behavior for all unauthorized access attempts.
    - Level 4 record-type payload schema validation and immutable field enforcement.
    - Version progression and optimistic locking.
    - Lifecycle, retention, expiry evaluation, logical deletion vs physical purge.
    """

    def __init__(
        self,
        storage_adapter: IMemoryStorageAdapter,
        enforcer: Optional[MemorySecurityEnforcer] = None,
        auditor: Optional[MemorySecurityAuditor] = None,
        lifecycle_manager: Optional[MemoryLifecycleManager] = None,
    ):
        self.storage = storage_adapter
        self.auditor = auditor or (enforcer.auditor if enforcer else MemorySecurityAuditor())
        self.enforcer = enforcer or MemorySecurityEnforcer(auditor=self.auditor)
        self.lifecycle = lifecycle_manager or MemoryLifecycleManager(
            storage_adapter=self.storage,
            enforcer=self.enforcer,
        )

    # -------------------------------------------------------------------------
    # Core Memory Operations: store, retrieve, search, update, delete, get_metadata, check_health
    # -------------------------------------------------------------------------

    def store_record(
        self,
        context: Optional[AuthorizationContext],
        record: MemoryRecord,
    ) -> MemoryRecord:
        """Store a new memory record under security governance and record validation."""
        if not isinstance(record, MemoryRecord):
            raise MemoryInvalidArgumentError("Record must be a valid MemoryRecord instance.", operation="store_record")

        # Validate schema and payload rules
        MemoryRecordValidator.validate_new_record(record)

        # Enforce security authorization
        self.enforcer.enforce_authorization(
            context=context,
            operation=MemoryOperation.CREATE,
            domain=record.domain,
            scope_type=record.scope_type,
            scope_id=record.scope_id,
            owner_id=record.owner_id,
            record_id=record.record_id,
            correlation_id=record.correlation_id,
            record=record,
        )

        # Apply retention policy if record has retention_policy_id
        if record.retention_policy_id:
            record = self.lifecycle.apply_retention_policy(record)

        return self.storage.store_record(record)

    def store(
        self,
        context: Optional[AuthorizationContext],
        record: MemoryRecord,
    ) -> MemoryRecord:
        """Alias for store_record satisfying Level 4 API specifications."""
        return self.store_record(context=context, record=record)

    def get_record(
        self,
        context: Optional[AuthorizationContext],
        record_id: str,
    ) -> MemoryRecord:
        """Retrieve a single record by record_id subject to authorization."""
        if context is None or not getattr(context, "principal_id", None) or not context.principal_id.strip():
            self.enforcer.enforce_authorization(
                context=context,
                operation=MemoryOperation.READ,
                domain=MemoryDomain.USER,
                scope_type=MemoryScope.USER,
                record_id=record_id,
            )

        if not record_id or not str(record_id).strip():
            raise MemoryInvalidArgumentError("Record ID cannot be empty.", operation="get_record")

        record = self.storage.get_record(record_id)
        if record is None:
            raise MemoryNotFoundError(record_id, operation="get_record")

        self.enforcer.enforce_authorization(
            context=context,
            operation=MemoryOperation.READ,
            domain=record.domain,
            scope_type=record.scope_type,
            scope_id=record.scope_id,
            owner_id=record.owner_id,
            record_id=record.record_id,
            correlation_id=record.correlation_id,
            record=record,
        )

        return record

    def retrieve(
        self,
        context: Optional[AuthorizationContext],
        record_id: str,
    ) -> MemoryRecord:
        """Alias for get_record satisfying Level 4 API specifications."""
        return self.get_record(context=context, record_id=record_id)

    def search_records(
        self,
        context: Optional[AuthorizationContext],
        criteria: MemorySearchCriteria,
    ) -> List[MemoryRecord]:
        """Search records subject to authorization and bounded pagination."""
        if not isinstance(criteria, MemorySearchCriteria):
            raise MemoryInvalidArgumentError("Criteria must be a MemorySearchCriteria instance.", operation="search_records")

        if context is None or not getattr(context, "principal_id", None) or not context.principal_id.strip():
            self.enforcer.enforce_authorization(
                context=context,
                operation=MemoryOperation.SEARCH,
                domain=criteria.domain or MemoryDomain.USER,
                scope_type=criteria.scope_type or MemoryScope.USER,
            )

        effective_domain = criteria.domain or MemoryDomain.USER

        if effective_domain == MemoryDomain.USER:
            principal = context.principal_id.strip()
            claimed_owner = criteria.owner_id or principal

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

        elif effective_domain == MemoryDomain.GENERAL:
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

        records = self.storage.search_records(criteria)

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

        return authorized_records

    def search(
        self,
        context: Optional[AuthorizationContext],
        criteria: MemorySearchCriteria,
    ) -> List[MemoryRecord]:
        """Alias for search_records satisfying Level 4 API specifications."""
        return self.search_records(context=context, criteria=criteria)

    def update_record(
        self,
        context: Optional[AuthorizationContext],
        record: MemoryRecord,
        expected_version: Optional[int] = None,
    ) -> MemoryRecord:
        """Update an existing record with security enforcement, validation, and optimistic locking."""
        if context is None or not getattr(context, "principal_id", None) or not context.principal_id.strip():
            self.enforcer.enforce_authorization(
                context=context,
                operation=MemoryOperation.UPDATE,
                domain=record.domain if isinstance(record, MemoryRecord) else MemoryDomain.USER,
                scope_type=record.scope_type if isinstance(record, MemoryRecord) else MemoryScope.USER,
                record_id=record.record_id if isinstance(record, MemoryRecord) else None,
            )

        if not isinstance(record, MemoryRecord):
            raise MemoryInvalidArgumentError("Record must be a valid MemoryRecord instance.", operation="update_record")

        existing = self.storage.get_record(record.record_id)
        if existing is None:
            raise MemoryNotFoundError(record.record_id, operation="update_record")

        # Validate update against existing state and schemas
        MemoryRecordValidator.validate_update(existing, record)

        # Enforce authorization against the existing record state
        self.enforcer.enforce_authorization(
            context=context,
            operation=MemoryOperation.UPDATE,
            domain=existing.domain,
            scope_type=existing.scope_type,
            scope_id=existing.scope_id,
            owner_id=existing.owner_id,
            record_id=existing.record_id,
            correlation_id=record.correlation_id,
            record=existing,
        )

        # Enforce authorization against the updated record
        self.enforcer.enforce_authorization(
            context=context,
            operation=MemoryOperation.UPDATE,
            domain=record.domain,
            scope_type=record.scope_type,
            scope_id=record.scope_id,
            owner_id=record.owner_id,
            record_id=record.record_id,
            correlation_id=record.correlation_id,
            record=record,
        )

        # Ensure updated_at is UTC now if not updated
        now = datetime.now(timezone.utc)
        if record.updated_at <= existing.updated_at:
            record = record.model_copy(update={"updated_at": now})

        return self.storage.update_record(record, expected_version=expected_version)

    def update(
        self,
        context: Optional[AuthorizationContext],
        record: MemoryRecord,
        expected_version: Optional[int] = None,
    ) -> MemoryRecord:
        """Alias for update_record satisfying Level 4 API specifications."""
        return self.update_record(context=context, record=record, expected_version=expected_version)

    def delete_record(
        self,
        context: Optional[AuthorizationContext],
        record_id: str,
        soft: bool = True,
    ) -> bool:
        """Delete a record subject to authorization (supports soft deletion and hard purge)."""
        if context is None or not getattr(context, "principal_id", None) or not context.principal_id.strip():
            self.enforcer.enforce_authorization(
                context=context,
                operation=MemoryOperation.DELETE,
                domain=MemoryDomain.USER,
                scope_type=MemoryScope.USER,
                record_id=record_id,
            )

        if not record_id or not str(record_id).strip():
            raise MemoryInvalidArgumentError("Record ID cannot be empty.", operation="delete_record")

        existing = self.storage.get_record(record_id)
        if existing is None:
            return False

        self.enforcer.enforce_authorization(
            context=context,
            operation=MemoryOperation.DELETE,
            domain=existing.domain,
            scope_type=existing.scope_type,
            scope_id=existing.scope_id,
            owner_id=existing.owner_id,
            record_id=existing.record_id,
            correlation_id=existing.correlation_id,
            record=existing,
        )

        return self.storage.delete_record(record_id, soft=soft)

    def delete(
        self,
        context: Optional[AuthorizationContext],
        record_id: str,
        soft: bool = True,
    ) -> bool:
        """Alias for delete_record satisfying Level 4 API specifications."""
        return self.delete_record(context=context, record_id=record_id, soft=soft)

    def get_record_metadata(
        self,
        context: Optional[AuthorizationContext],
        record_id: str,
    ) -> Dict[str, Any]:
        """Retrieve record metadata without payload, subject to authorization."""
        if context is None or not getattr(context, "principal_id", None) or not context.principal_id.strip():
            self.enforcer.enforce_authorization(
                context=context,
                operation=MemoryOperation.READ,
                domain=MemoryDomain.USER,
                scope_type=MemoryScope.USER,
                record_id=record_id,
            )

        if not record_id or not str(record_id).strip():
            raise MemoryInvalidArgumentError("Record ID cannot be empty.", operation="get_record_metadata")

        existing = self.storage.get_record(record_id)
        if existing is None:
            raise MemoryNotFoundError(record_id, operation="get_record_metadata")

        self.enforcer.enforce_authorization(
            context=context,
            operation=MemoryOperation.READ,
            domain=existing.domain,
            scope_type=existing.scope_type,
            scope_id=existing.scope_id,
            owner_id=existing.owner_id,
            record_id=existing.record_id,
            correlation_id=existing.correlation_id,
            record=existing,
        )

        meta = self.storage.get_record_metadata(record_id)
        if meta is None:
            raise MemoryNotFoundError(record_id, operation="get_record_metadata")
        return meta

    def get_metadata(
        self,
        context: Optional[AuthorizationContext],
        record_id: str,
    ) -> Dict[str, Any]:
        """Alias for get_record_metadata satisfying Level 4 API specifications."""
        return self.get_record_metadata(context=context, record_id=record_id)

    def check_health(self) -> StorageHealthResult:
        """Evaluate storage connectivity and status."""
        return self.storage.check_health()

    def health_check(self) -> StorageHealthResult:
        """Alias for check_health satisfying Level 4 API specifications."""
        return self.check_health()

    # -------------------------------------------------------------------------
    # Lifecycle & Retention Operations
    # -------------------------------------------------------------------------

    def register_retention_policy(self, policy: RetentionPolicy) -> None:
        """Register a retention policy in the lifecycle manager."""
        self.lifecycle.register_policy(policy)

    def enforce_retention(
        self,
        context: Optional[AuthorizationContext],
        domain: Optional[MemoryDomain] = None,
        owner_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Mark eligible expired records with status EXPIRED under security context."""
        return self.lifecycle.enforce_retention(
            context=context,
            domain=domain,
            owner_id=owner_id,
            as_of=as_of,
        )

    def purge_records(
        self,
        context: Optional[AuthorizationContext],
        criteria: PurgeCriteria,
    ) -> PurgeResult:
        """Permanently erase eligible records under security governance."""
        return self.lifecycle.purge_records(context=context, criteria=criteria)

    def verify_deletion(
        self,
        context: Optional[AuthorizationContext],
        record_id: str,
    ) -> Dict[str, Any]:
        """Verify whether a record is active, logically deleted, or physically purged."""
        return self.lifecycle.verify_deletion(context=context, record_id=record_id)
