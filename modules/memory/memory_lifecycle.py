"""EarthMind Memory Module: Lifecycle & Retention Management Component.

Manages retention policies, lifecycle transitions, expiry identification,
authorized physical purge, and deletion verification.
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
    RetentionCategory,
    RetentionPolicy,
)
from modules.memory.errors import (
    MemoryForbiddenError,
    MemoryInvalidArgumentError,
    MemoryNotFoundError,
    MemoryRetentionPolicyViolationError,
    MemoryUnauthorizedError,
)
from modules.memory.security import MemorySecurityEnforcer


class MemoryLifecycle:
    """Starter alias preserved for backward compatibility."""
    pass


class MemoryLifecycleManager(MemoryLifecycle):
    """Manages record lifecycles, retention policies, expiry, and secure physical purge."""

    def __init__(
        self,
        storage_adapter: IMemoryStorageAdapter,
        enforcer: Optional[MemorySecurityEnforcer] = None,
    ):
        self.storage = storage_adapter
        self.enforcer = enforcer or MemorySecurityEnforcer()
        self._retention_policies: Dict[str, RetentionPolicy] = {}
        self._register_default_policies()

    def _register_default_policies(self) -> None:
        """Register initial system retention policies."""
        # Transient session memory: 24-hour TTL, auto-purgeable
        self.register_policy(
            RetentionPolicy(
                policy_id="pol_transient_session",
                category=RetentionCategory.TRANSIENT_SESSION,
                description="Transient conversation and session context memory (24h TTL)",
                ttl_seconds=86400,
                auto_purge_on_expiry=True,
                allow_extension=False,
                require_governance_for_purge=False,
            )
        )
        # Seasonal crop cycle memory: 180-day TTL (~6 months)
        self.register_policy(
            RetentionPolicy(
                policy_id="pol_seasonal_crop",
                category=RetentionCategory.OPERATIONAL_SEASONAL,
                description="Seasonal agricultural crop cycle observations (180 days TTL)",
                ttl_seconds=180 * 86400,
                auto_purge_on_expiry=False,
                allow_extension=True,
                require_governance_for_purge=True,
            )
        )
        # Long-term farm profile: Permanent, no TTL
        self.register_policy(
            RetentionPolicy(
                policy_id="pol_permanent_farm",
                category=RetentionCategory.LONG_TERM_FARM,
                description="Permanent farm boundaries, soil profiles, and asset records",
                ttl_seconds=None,
                auto_purge_on_expiry=False,
                allow_extension=True,
                require_governance_for_purge=True,
            )
        )
        # General shared advisories: 365-day TTL
        self.register_policy(
            RetentionPolicy(
                policy_id="pol_general_advisory",
                category=RetentionCategory.GENERAL_REGULATORY,
                description="General agromet and crop advisory retention (1 year TTL)",
                ttl_seconds=365 * 86400,
                auto_purge_on_expiry=False,
                allow_extension=True,
                require_governance_for_purge=True,
            )
        )

    def register_policy(self, policy: RetentionPolicy) -> None:
        """Register or update a retention policy."""
        if not isinstance(policy, RetentionPolicy):
            raise MemoryInvalidArgumentError("Policy must be an instance of RetentionPolicy.", operation="register_policy")
        self._retention_policies[policy.policy_id] = policy

    def get_policy(self, policy_id: str) -> Optional[RetentionPolicy]:
        """Fetch a retention policy by policy_id."""
        return self._retention_policies.get(policy_id)

    def list_policies(self) -> List[RetentionPolicy]:
        """List all active retention policies."""
        return list(self._retention_policies.values())

    def apply_retention_policy(self, record: MemoryRecord, policy_id: Optional[str] = None) -> MemoryRecord:
        """Apply a retention policy to a memory record, calculating expires_at if applicable.

        Returns a modified copy of the record with retention_policy_id and calculated expires_at.
        """
        target_policy_id = policy_id or record.retention_policy_id
        if not target_policy_id:
            return record

        policy = self.get_policy(target_policy_id)
        if not policy:
            raise MemoryRetentionPolicyViolationError(
                target_policy_id,
                f"Retention policy '{target_policy_id}' is not registered.",
                operation="apply_retention_policy"
            )

        # Ensure general domain records use general retention policies
        if record.domain == MemoryDomain.GENERAL and policy.category not in (RetentionCategory.GENERAL_REGULATORY, RetentionCategory.CUSTOM):
            raise MemoryRetentionPolicyViolationError(
                target_policy_id,
                f"Policy '{target_policy_id}' category '{policy.category.value}' cannot be applied to GENERAL domain.",
                operation="apply_retention_policy"
            )

        expires_at = policy.calculate_expiration(from_time=record.created_at)
        return record.model_copy(
            update={
                "retention_policy_id": target_policy_id,
                "expires_at": expires_at or record.expires_at,
            }
        )

    def identify_expired_records(
        self,
        context: Optional[AuthorizationContext],
        domain: Optional[MemoryDomain] = None,
        owner_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[MemoryRecord]:
        """Find active or deleted records that have exceeded their expires_at timestamp.

        Enforces security authorization to prevent discovering another user's records.
        """
        now = as_of or datetime.now(timezone.utc)
        effective_domain = domain or MemoryDomain.USER

        if effective_domain == MemoryDomain.USER:
            claimed_owner = owner_id or (context.principal_id if context else None)
            self.enforcer.enforce_authorization(
                context=context,
                operation=MemoryOperation.SEARCH,
                domain=MemoryDomain.USER,
                scope_type=MemoryScope.USER,
                owner_id=claimed_owner,
            )
            criteria = MemorySearchCriteria(
                domain=MemoryDomain.USER,
                owner_id=claimed_owner,
                status=None,  # match any status
                include_expired=True,
                limit=limit,
            )
        else:
            self.enforcer.enforce_authorization(
                context=context,
                operation=MemoryOperation.SEARCH,
                domain=MemoryDomain.GENERAL,
                scope_type=MemoryScope.GENERAL,
                owner_id=None,
            )
            criteria = MemorySearchCriteria(
                domain=MemoryDomain.GENERAL,
                owner_id=None,
                status=None,
                include_expired=True,
                limit=limit,
            )

        candidates = self.storage.search_records(criteria)
        expired = [r for r in candidates if r.expires_at is not None and r.expires_at <= now]
        return expired

    def enforce_retention(
        self,
        context: Optional[AuthorizationContext],
        domain: Optional[MemoryDomain] = None,
        owner_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Mark eligible expired records with status EXPIRED.

        Returns summary of evaluated and transitioned records.
        """
        expired_records = self.identify_expired_records(
            context=context,
            domain=domain,
            owner_id=owner_id,
            as_of=as_of,
            limit=500,
        )

        transitioned = 0
        for rec in expired_records:
            if rec.status != MemoryRecordStatus.EXPIRED:
                # Update status to EXPIRED
                updated = rec.model_copy(
                    update={
                        "status": MemoryRecordStatus.EXPIRED,
                        "record_version": rec.record_version + 1,
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
                self.storage.update_record(updated, expected_version=rec.record_version)
                transitioned += 1

        return {
            "evaluated_expired_count": len(expired_records),
            "transitioned_to_expired": transitioned,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def purge_records(
        self,
        context: Optional[AuthorizationContext],
        criteria: PurgeCriteria,
    ) -> PurgeResult:
        """Physically erase eligible records matching criteria under strict governance.

        Enforces:
        - Context authorization (USER domain records require owner match; GENERAL requires governance role).
        - If criteria.dry_run is True, computes count without executing physical delete.
        - Deletes records permanently using storage.delete_record(record_id, soft=False).
        """
        now = datetime.now(timezone.utc)
        effective_domain = criteria.domain or MemoryDomain.USER

        if effective_domain == MemoryDomain.USER:
            claimed_owner = criteria.owner_id or (context.principal_id if context else None)
            self.enforcer.enforce_authorization(
                context=context,
                operation=MemoryOperation.DELETE,
                domain=MemoryDomain.USER,
                scope_type=MemoryScope.USER,
                owner_id=claimed_owner,
            )
            search_crit = MemorySearchCriteria(
                domain=MemoryDomain.USER,
                owner_id=claimed_owner,
                status=criteria.status,
                retention_policy_id=criteria.retention_policy_id,
                include_expired=True,
                limit=1000,
            )
        else:
            self.enforcer.enforce_authorization(
                context=context,
                operation=MemoryOperation.DELETE,
                domain=MemoryDomain.GENERAL,
                scope_type=MemoryScope.GENERAL,
                owner_id=None,
            )
            search_crit = MemorySearchCriteria(
                domain=MemoryDomain.GENERAL,
                owner_id=None,
                status=criteria.status,
                retention_policy_id=criteria.retention_policy_id,
                include_expired=True,
                limit=1000,
            )

        candidates = self.storage.search_records(search_crit)
        eligible: List[MemoryRecord] = []

        for rec in candidates:
            # Check purge_expired_only
            if criteria.purge_expired_only:
                if rec.expires_at is None or rec.expires_at > now:
                    continue
            # Check older_than
            if criteria.older_than:
                if rec.updated_at > criteria.older_than:
                    continue
            eligible.append(rec)

        if criteria.dry_run:
            return PurgeResult(
                purged_count=0,
                eligible_count=len(eligible),
                is_dry_run=True,
                details={"message": f"{len(eligible)} records match purge criteria; none purged in dry-run."},
            )

        purged_count = 0
        for rec in eligible:
            success = self.storage.delete_record(rec.record_id, soft=False)
            if success:
                purged_count += 1

        return PurgeResult(
            purged_count=purged_count,
            eligible_count=len(eligible),
            is_dry_run=False,
            details={"message": f"Successfully physically purged {purged_count} records."},
        )

    def verify_deletion(
        self,
        context: Optional[AuthorizationContext],
        record_id: str,
    ) -> Dict[str, Any]:
        """Verify whether a record has been logically or physically deleted.

        Returns status indicating if record exists, is active, is logically deleted, or is physically purged.
        """
        record = self.storage.get_record(record_id)
        if record is None:
            return {
                "record_id": record_id,
                "exists": False,
                "deletion_state": "PHYSICALLY_PURGED",
                "is_accessible": False,
            }

        # If record exists, verify authorization before reporting state
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

        if record.status == MemoryRecordStatus.DELETED:
            return {
                "record_id": record_id,
                "exists": True,
                "deletion_state": "LOGICALLY_DELETED",
                "is_accessible": False,
                "deleted_at": record.updated_at.isoformat(),
            }

        return {
            "record_id": record_id,
            "exists": True,
            "deletion_state": "NOT_DELETED",
            "is_accessible": True,
            "status": record.status.value,
        }
