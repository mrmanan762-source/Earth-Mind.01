"""Memory Module Level 1 & Level 4 Contracts, Record Models, and Lifecycle Schemas.

Defines foundational schemas for the EarthMind Memory Module:
- MemoryDomain (USER, GENERAL)
- MemoryScope (USER, CONVERSATION, FARM, FIELD, CROP_CYCLE, GENERAL)
- MemoryRecordStatus (ACTIVE, ARCHIVED, DELETED, EXPIRED, PENDING)
- MemoryErrorCode (Approved error categories)
- MemoryOperation (CREATE, READ, UPDATE, DELETE, SEARCH, PURGE)
- PrincipalType (USER, SERVICE, SYSTEM, ANONYMOUS)
- MemoryRecord (Core record model with 17 approved fields and strict validation)
- AuthorizationContext (Contract for trusted identity/authorization from Auth boundary)
- MemorySearchCriteria (Structured search query contract with deterministic sorting)
- StorageHealthResult (Storage health and capability status)
- PayloadSchemaRegistry (Extensible record-type payload validator registry)
- RetentionPolicy & RetentionCategory (Record retention and lifecycle governance)
- PurgeCriteria & PurgeResult (Authorized physical purge models)
"""

from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type
from pydantic import BaseModel, Field, model_validator
import uuid

from modules.context.boundary.enums import KnowledgeClassification
from modules.context.schemas import PrivacyLevel


class MemoryDomain(str, Enum):
    """Approved logical memory domains."""
    USER = "USER"
    GENERAL = "GENERAL"


class MemoryScope(str, Enum):
    """Approved logical memory scopes."""
    USER = "USER"
    CONVERSATION = "CONVERSATION"
    FARM = "FARM"
    FIELD = "FIELD"
    CROP_CYCLE = "CROP_CYCLE"
    GENERAL = "GENERAL"


class MemoryRecordStatus(str, Enum):
    """Lifecycle statuses for memory records."""
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"
    EXPIRED = "EXPIRED"
    PENDING = "PENDING"


class MemoryErrorCode(str, Enum):
    """Approved error categories for the Memory Module."""
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    INVALID_RECORD_SCHEMA = "INVALID_RECORD_SCHEMA"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    STORAGE_ERROR = "STORAGE_ERROR"
    RETENTION_POLICY_VIOLATION = "RETENTION_POLICY_VIOLATION"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class MemoryOperation(str, Enum):
    """Supported memory operations for authorization checks."""
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SEARCH = "SEARCH"
    PURGE = "PURGE"


class PrincipalType(str, Enum):
    """Approved principal types representing acting subjects."""
    USER = "USER"
    SERVICE = "SERVICE"
    SYSTEM = "SYSTEM"
    ANONYMOUS = "ANONYMOUS"


class PayloadSchemaRegistry:
    """Extensible registry for record-type payload schemas and validation functions."""

    _validators: Dict[str, Callable[[Dict[str, Any]], None]] = {}
    _allow_unregistered: bool = True

    @classmethod
    def register_schema(
        cls,
        record_type: str,
        validator_or_model: Any,
    ) -> None:
        """Register a validation callable or Pydantic model for a given record_type."""
        if hasattr(validator_or_model, "model_validate"):
            def _validate_pydantic(payload: Dict[str, Any]) -> None:
                validator_or_model.model_validate(payload)
            cls._validators[record_type] = _validate_pydantic
        elif callable(validator_or_model):
            cls._validators[record_type] = validator_or_model
        else:
            raise ValueError("Validator must be a callable or Pydantic model class.")

    @classmethod
    def set_allow_unregistered(cls, allow: bool) -> None:
        """Configure whether unregistered record types are accepted or rejected."""
        cls._allow_unregistered = allow

    @classmethod
    def is_unregistered_allowed(cls) -> bool:
        """Return whether unregistered record types are accepted."""
        return cls._allow_unregistered

    @classmethod
    def clear_registry(cls) -> None:
        """Clear all registered payload validators and reset defaults."""
        cls._validators.clear()
        cls._allow_unregistered = True

    @classmethod
    def validate_payload(cls, record_type: str, payload: Dict[str, Any]) -> None:
        """Validate payload against registered schema for record_type.

        Raises:
            ValueError: If payload fails validation or if unregistered types are disallowed.
        """
        if not isinstance(payload, dict):
            raise ValueError(f"Payload must be a dictionary, got {type(payload).__name__}.")

        validator = cls._validators.get(record_type)
        if validator is not None:
            validator(payload)
        elif not cls._allow_unregistered:
            raise ValueError(f"Unregistered record_type '{record_type}' is not allowed by PayloadSchemaRegistry.")


class RetentionCategory(str, Enum):
    """Category classification for record retention policies."""
    TRANSIENT_SESSION = "TRANSIENT_SESSION"
    OPERATIONAL_SEASONAL = "OPERATIONAL_SEASONAL"
    LONG_TERM_FARM = "LONG_TERM_FARM"
    LEGAL_AUDIT = "LEGAL_AUDIT"
    GENERAL_REGULATORY = "GENERAL_REGULATORY"
    CUSTOM = "CUSTOM"


class RetentionPolicy(BaseModel):
    """Specification of retention rules for a record category."""
    policy_id: str = Field(..., min_length=1, description="Unique policy identifier")
    category: RetentionCategory = Field(RetentionCategory.OPERATIONAL_SEASONAL, description="Retention category")
    description: str = Field("", description="Human-readable explanation of retention purpose")
    ttl_seconds: Optional[int] = Field(None, ge=1, description="Optional time-to-live duration in seconds")
    auto_purge_on_expiry: bool = Field(False, description="Whether expired records may be automatically physically purged")
    allow_extension: bool = Field(True, description="Whether expiry timestamp can be renewed on update")
    require_governance_for_purge: bool = Field(True, description="Whether purge requires elevated governance context")

    def calculate_expiration(self, from_time: Optional[datetime] = None) -> Optional[datetime]:
        """Compute expiration timestamp based on TTL policy."""
        if self.ttl_seconds is None:
            return None
        base = from_time or datetime.now(timezone.utc)
        return base + timedelta(seconds=self.ttl_seconds)


class AuthorizationContext(BaseModel):
    """Trusted identity and authorization contract supplied by separate authentication/identity boundary.

    Memory Module does not perform authentication. This contract represents verified credentials
    and permissions passed into memory operations.
    """
    principal_id: str = Field(..., min_length=1, description="Unique trusted identity identifier of the acting subject")
    principal_type: PrincipalType = Field(PrincipalType.USER, description="Type of principal")
    roles: List[str] = Field(default_factory=list, description="Assigned roles for the subject")
    owner_id: Optional[str] = Field(None, description="Owner entity identifier if subject is acting on behalf of owner")
    accessible_scopes: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Map of scope type to allowed scope IDs, e.g. {'FARM': ['farm_123']}"
    )
    requested_operation: MemoryOperation = Field(
        MemoryOperation.READ,
        description="The memory operation being attempted"
    )
    policy_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional policy or governance metadata evaluated by authorization engine"
    )

    def can_access_owner(self, record_owner_id: Optional[str]) -> bool:
        """Check whether principal matches record owner or has elevated access."""
        if "admin" in self.roles or "system" in self.roles:
            return True
        if self.owner_id and record_owner_id and self.owner_id == record_owner_id:
            return True
        return self.principal_id == record_owner_id

    def is_authenticated(self) -> bool:
        """Verify principal identity is authenticated."""
        if self.principal_type == PrincipalType.ANONYMOUS:
            return False
        if not self.principal_id or not self.principal_id.strip():
            return False
        return True


class MemoryRecord(BaseModel):
    """Core memory record data model conforming to EarthMind Memory Architecture Specification v1.0.

    Contains all 17 approved fields with strict validation of domains, ownership, versions,
    UTC timestamps, and schemas.
    """
    record_id: str = Field(
        default_factory=lambda: f"mem_{uuid.uuid4().hex[:16]}",
        description="Unique immutable identifier for the memory record"
    )
    domain: MemoryDomain = Field(..., description="Logical memory domain (USER or GENERAL)")
    record_type: str = Field(..., min_length=1, description="Domain-specific record type classification")
    owner_id: Optional[str] = Field(None, description="Owner identity; mandatory for USER, must be None for GENERAL")
    scope_type: MemoryScope = Field(..., description="Logical scope category")
    scope_id: str = Field(..., min_length=1, description="Specific identifier for the assigned scope")
    payload: Dict[str, Any] = Field(..., description="Validated structured payload data")
    source: str = Field(..., min_length=1, description="Origin source or provenance producer")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timezone-aware UTC timestamp of creation"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timezone-aware UTC timestamp of last update"
    )
    schema_version: str = Field("1.0", min_length=1, description="Schema version of payload")
    record_version: int = Field(1, ge=1, description="Monotonically increasing version counter for optimistic locking")
    status: MemoryRecordStatus = Field(MemoryRecordStatus.ACTIVE, description="Lifecycle status")
    retention_policy_id: Optional[str] = Field(None, description="Associated retention policy identifier")
    expires_at: Optional[datetime] = Field(None, description="Optional timezone-aware UTC expiration timestamp")
    classification: KnowledgeClassification = Field(
        KnowledgeClassification.FARMER_KNOWLEDGE,
        description="C.3 knowledge classification category"
    )
    correlation_id: Optional[str] = Field(None, description="Traceability or request correlation identifier")

    @model_validator(mode="after")
    def validate_record_rules(self) -> "MemoryRecord":
        # 1. UTC Timestamp validation
        for field_name, ts in [
            ("created_at", self.created_at),
            ("updated_at", self.updated_at),
            ("expires_at", self.expires_at),
        ]:
            if ts is not None:
                if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
                    raise ValueError(f"Field '{field_name}' must be a timezone-aware UTC datetime.")

        # 2. Domain & Ownership validation
        if self.domain == MemoryDomain.USER:
            if not self.owner_id or not self.owner_id.strip():
                raise ValueError("USER domain records must have a non-empty 'owner_id'.")
            if self.scope_type == MemoryScope.GENERAL:
                raise ValueError("USER domain records cannot have scope_type 'GENERAL'.")
        elif self.domain == MemoryDomain.GENERAL:
            if self.owner_id is not None:
                raise ValueError("GENERAL domain records must not have an 'owner_id' (must be None).")
            if self.scope_type == MemoryScope.USER:
                raise ValueError("GENERAL domain records cannot have scope_type 'USER'.")

        # 3. Expiration consistency
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("'expires_at' must be strictly later than 'created_at'.")

        # 4. Record ID format
        if not self.record_id or not self.record_id.strip():
            raise ValueError("'record_id' must be a non-empty string.")

        # 5. Payload validation via registry
        PayloadSchemaRegistry.validate_payload(self.record_type, self.payload)

        return self

    def is_expired(self, current_time: Optional[datetime] = None) -> bool:
        """Evaluate if record is past its expiration timestamp."""
        if self.expires_at is None:
            return False
        now = current_time or datetime.now(timezone.utc)
        return self.expires_at <= now

    def to_context_contract(self) -> Any:
        """Convert this MemoryRecord into a B2 / C.3 MemoryContextContract."""
        from modules.context.boundary.models import MemoryContextContract
        from modules.context.boundary.enums import ContextScope as C3ContextScope

        # Map MemoryScope to C3ContextScope
        scope_map = {
            MemoryScope.USER: C3ContextScope.FARMER,
            MemoryScope.CONVERSATION: C3ContextScope.SESSION,
            MemoryScope.FARM: C3ContextScope.FARM,
            MemoryScope.FIELD: C3ContextScope.FIELD,
            MemoryScope.CROP_CYCLE: C3ContextScope.CROP_CYCLE,
            MemoryScope.GENERAL: C3ContextScope.GLOBAL,
        }
        c3_scope = scope_map.get(self.scope_type, C3ContextScope.FARMER)

        return MemoryContextContract(
            memory_id=self.record_id,
            classification=self.classification,
            scope=c3_scope,
            content=self.payload,
            farmer_id=self.owner_id,
            provenance={
                "source": self.source,
                "domain": self.domain.value,
                "record_type": self.record_type,
                "record_version": self.record_version,
                "schema_version": self.schema_version,
            },
            lifecycle_status=self.status.value,
            timestamp=self.updated_at.isoformat(),
            privacy_level=PrivacyLevel.FARM_PRIVATE if self.domain == MemoryDomain.USER else PrivacyLevel.PUBLIC,
            is_pii=(self.domain == MemoryDomain.USER),
            trace_id=self.correlation_id,
            metadata={
                "retention_policy_id": self.retention_policy_id,
                "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            }
        )

    @classmethod
    def from_context_contract(
        cls,
        contract: Any,
        domain: MemoryDomain = MemoryDomain.USER,
        record_type: str = "context_snapshot",
        owner_id: Optional[str] = None,
        source: Optional[str] = None,
    ) -> "MemoryRecord":
        """Factory creating a MemoryRecord from an existing MemoryContextContract."""
        resolved_owner = owner_id or getattr(contract, "farmer_id", None)
        if domain == MemoryDomain.USER and not resolved_owner:
            resolved_owner = "system_unspecified_user"

        return cls(
            record_id=contract.memory_id,
            domain=domain,
            record_type=record_type,
            owner_id=resolved_owner if domain == MemoryDomain.USER else None,
            scope_type=MemoryScope.USER if domain == MemoryDomain.USER else MemoryScope.GENERAL,
            scope_id=getattr(contract, "farmer_id", None) or "general",
            payload={"content": contract.content} if not isinstance(contract.content, dict) else contract.content,
            source=source or (contract.provenance.get("source") if hasattr(contract, "provenance") else "b2_context"),
            classification=getattr(contract, "classification", KnowledgeClassification.FARMER_KNOWLEDGE),
            correlation_id=getattr(contract, "trace_id", None),
        )


class MemorySortField(str, Enum):
    """Approved sort fields for deterministic memory searches."""
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    RECORD_ID = "record_id"


class SortOrder(str, Enum):
    """Sort direction."""
    ASC = "ASC"
    DESC = "DESC"


class MemorySearchCriteria(BaseModel):
    """Structured query criteria for provider-independent record search with deterministic ordering."""
    domain: Optional[MemoryDomain] = Field(None, description="Target domain filter")
    owner_id: Optional[str] = Field(None, description="Owner ID filter")
    scope_type: Optional[MemoryScope] = Field(None, description="Scope type filter")
    scope_id: Optional[str] = Field(None, description="Scope ID filter")
    record_type: Optional[str] = Field(None, description="Record type filter")
    status: Optional[MemoryRecordStatus] = Field(MemoryRecordStatus.ACTIVE, description="Record status filter")
    classification: Optional[KnowledgeClassification] = Field(None, description="Classification filter")
    correlation_id: Optional[str] = Field(None, description="Correlation ID filter")
    retention_policy_id: Optional[str] = Field(None, description="Retention policy ID filter")
    include_expired: bool = Field(False, description="Whether to include expired records")
    sort_by: MemorySortField = Field(MemorySortField.CREATED_AT, description="Primary field to sort by")
    sort_order: SortOrder = Field(SortOrder.DESC, description="Sort direction")
    limit: int = Field(50, ge=1, le=1000, description="Maximum number of records to return")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class PurgeCriteria(BaseModel):
    """Criteria for authorized physical deletion / purge."""
    domain: Optional[MemoryDomain] = Field(None, description="Domain filter for purge")
    owner_id: Optional[str] = Field(None, description="Owner filter for purge")
    status: Optional[MemoryRecordStatus] = Field(None, description="Target status, e.g. DELETED or EXPIRED")
    retention_policy_id: Optional[str] = Field(None, description="Target policy filter")
    purge_expired_only: bool = Field(False, description="Whether to purge only expired records")
    older_than: Optional[datetime] = Field(None, description="Purge records updated/deleted before this timestamp")
    dry_run: bool = Field(False, description="Preview count without deleting")


class PurgeResult(BaseModel):
    """Outcome of physical purge operation."""
    purged_count: int = Field(..., ge=0, description="Number of records physically erased")
    eligible_count: int = Field(..., ge=0, description="Number of records matching purge criteria")
    is_dry_run: bool = Field(False, description="Whether this was a dry-run preview")
    executed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of purge execution"
    )
    details: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic details")


class StorageHealthResult(BaseModel):
    """Health check outcome for storage adapter."""
    is_healthy: bool = Field(..., description="Whether storage is healthy and accepting operations")
    provider_name: str = Field(..., description="Identifier of storage adapter provider")
    details: Dict[str, Any] = Field(default_factory=dict, description="Health and capability diagnostics")
    checked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timezone-aware UTC timestamp of check"
    )
