"""Secure Memory Domain Service Layer for EarthMind Memory Module Level 2.

Wraps an IMemoryStorageAdapter with MemorySecurityEnforcer and MemorySecurityAuditor,
enforcing centralized domain separation, user ownership, scope boundaries,
General Memory governance, and anti-promotion rules across all operations.
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
    StorageHealthResult,
)
from modules.memory.errors import (
    MemoryForbiddenError,
    MemoryInvalidArgumentError,
    MemoryNotFoundError,
    MemoryUnauthorizedError,
)
from modules.memory.security import (
    MemorySecurityAuditor,
    MemorySecurityEnforcer,
)


class MemoryService:
    """Secure memory service managing User and General memory domains.

    Enforces:
    - Mandatory, trusted AuthorizationContext on all operations.
    - User ownership and cross-user isolation.
    - Scope-aware permissions (USER, CONVERSATION, FARM, FIELD, CROP_CYCLE, GENERAL).
    - General Memory governance (preventing ordinary users from modifying shared knowledge).
    - Prevention of private User Memory leaking into General Memory.
    - Centralized audit events without sensitive payload leakage.
    - Fail-closed behavior for all unauthorized access attempts.
    """

    def __init__(
        self,
        storage_adapter: IMemoryStorageAdapter,
        enforcer: Optional[MemorySecurityEnforcer] = None,
        auditor: Optional[MemorySecurityAuditor] = None,
    ):
        self.storage = storage_adapter
        self.auditor = auditor or (enforcer.auditor if enforcer else MemorySecurityAuditor())
        self.enforcer = enforcer or MemorySecurityEnforcer(auditor=self.auditor)

    def store_record(
        self,
        context: Optional[AuthorizationContext],
        record: MemoryRecord,
    ) -> MemoryRecord:
        """Store a new memory record under security governance.

        Raises:
            MemoryUnauthorizedError: If context is missing or invalid.
            MemoryForbiddenError: If unauthorized, cross-user write, or invalid General write.
            MemoryInvalidArgumentError: If domain or scope combinations are invalid.
            MemoryConflictError: If record_id already exists in storage.
        """
        # Validate record structure
        if not isinstance(record, MemoryRecord):
            raise MemoryInvalidArgumentError("Record must be a valid MemoryRecord instance.", operation="store_record")

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

        return self.storage.store_record(record)

    def get_record(
        self,
        context: Optional[AuthorizationContext],
        record_id: str,
    ) -> MemoryRecord:
        """Retrieve a single record by record_id subject to authorization.

        Raises:
            MemoryUnauthorizedError: If context is missing or invalid.
            MemoryNotFoundError: If record does not exist.
            MemoryForbiddenError: If principal lacks access to record's domain, scope, or owner.
        """
        # Validate context presence first to fail closed
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

        # Fetch record from storage
        record = self.storage.get_record(record_id)
        if record is None:
            raise MemoryNotFoundError(record_id, operation="get_record")

        # Enforce security authorization against retrieved record
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

    def search_records(
        self,
        context: Optional[AuthorizationContext],
        criteria: MemorySearchCriteria,
    ) -> List[MemoryRecord]:
        """Search records subject to authorization.

        Ensures that:
        - For USER domain: criteria is bound to authorized owner and scope boundaries.
        - For GENERAL domain: read authorization is enforced.
        - Unfiltered broad searches across other users are rejected fail-closed.
        """
        if not isinstance(criteria, MemorySearchCriteria):
            raise MemoryInvalidArgumentError("Criteria must be a MemorySearchCriteria instance.", operation="search_records")

        # Check missing or invalid auth context immediately
        if context is None or not getattr(context, "principal_id", None) or not context.principal_id.strip():
            self.enforcer.enforce_authorization(
                context=context,
                operation=MemoryOperation.SEARCH,
                domain=criteria.domain or MemoryDomain.USER,
                scope_type=criteria.scope_type or MemoryScope.USER,
            )

        # If domain is not specified, evaluate based on owner_id or fail-closed
        effective_domain = criteria.domain
        if effective_domain is None:
            # If search specifies no domain, default to USER domain bound to the authenticated principal
            effective_domain = MemoryDomain.USER

        if effective_domain == MemoryDomain.USER:
            # The search must be restricted to the authenticated principal or context owner
            principal = context.principal_id.strip()
            claimed_owner = criteria.owner_id or principal

            # Authorize scope and owner
            self.enforcer.enforce_authorization(
                context=context,
                operation=MemoryOperation.SEARCH,
                domain=MemoryDomain.USER,
                scope_type=criteria.scope_type or MemoryScope.USER,
                scope_id=criteria.scope_id,
                owner_id=claimed_owner,
                correlation_id=criteria.correlation_id,
            )

            # Restrict search criteria strictly to the authorized owner
            criteria = criteria.model_copy(update={"domain": MemoryDomain.USER, "owner_id": claimed_owner})

        elif effective_domain == MemoryDomain.GENERAL:
            # Authorize General search
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

        # Execute search on storage adapter
        records = self.storage.search_records(criteria)

        # Secondary filtering to guarantee zero information leakage
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

    def update_record(
        self,
        context: Optional[AuthorizationContext],
        record: MemoryRecord,
        expected_version: Optional[int] = None,
    ) -> MemoryRecord:
        """Update an existing record with security enforcement and concurrency control."""
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

        # Verify existing record first to prevent spoofing record identity/owner
        existing = self.storage.get_record(record.record_id)
        if existing is None:
            raise MemoryNotFoundError(record.record_id, operation="update_record")

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

        # Enforce that updated record cannot change domain or ownership
        if record.domain != existing.domain:
            raise MemoryForbiddenError("Cannot change domain of an existing record.", operation="update_record")
        if record.owner_id != existing.owner_id:
            raise MemoryForbiddenError("Cannot reassign ownership of an existing record.", operation="update_record")
        if record.scope_type != existing.scope_type:
            raise MemoryForbiddenError("Cannot change scope_type of an existing record.", operation="update_record")

        # Enforce authorization against the new updated record
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

        return self.storage.update_record(record, expected_version=expected_version)

    def delete_record(
        self,
        context: Optional[AuthorizationContext],
        record_id: str,
        soft: bool = True,
    ) -> bool:
        """Delete a record subject to authorization."""
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

        # Enforce delete permission
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

        # Enforce authorization
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

    def check_health(self) -> StorageHealthResult:
        """Evaluate storage connectivity and status."""
        return self.storage.check_health()
