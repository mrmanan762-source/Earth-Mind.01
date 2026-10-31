"""Memory Module Level 1 Contracts and Record Models.

Defines foundational schemas for the EarthMind Memory Module:
- MemoryDomain (USER, GENERAL)
- MemoryScope (USER, CONVERSATION, FARM, FIELD, CROP_CYCLE, GENERAL)
- MemoryRecordStatus (ACTIVE, ARCHIVED, DELETED, EXPIRED, PENDING)
- MemoryErrorCode (Approved error categories)
- MemoryOperation (CREATE, READ, UPDATE, DELETE, SEARCH)
- PrincipalType (USER, SERVICE, SYSTEM, ANONYMOUS)
- MemoryRecord (Core record model with 17 approved fields and strict validation)
- AuthorizationContext (Contract for trusted identity/authorization from Auth boundary)
- MemorySearchCriteria (Structured search query contract)
- StorageHealthResult (Storage health and capability status)
- PayloadSchemaRegistry (Extensible record-type payload validator registry)
"""

from datetime import datetime, timezone
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


class PrincipalType(str, Enum):
    """Type of acting principal for authorization context."""
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
    def validate_payload(cls, record_type: str, payload: Dict[str, Any]) -> None:
        """Validate payload against registered schema for record_type.

        Raises:
            ValueError: If payload fails validation or if unregistered types are disallowed.
        """
        if not isinstance(payload, dict):
            raise ValueError(f"Payload must be a dictionary, got {type(payload).__name__}.")

        validator = cls._validators.get(record_type)
        if validator is not None:
            try:
                validator(payload)
            except Exception as e:
                raise ValueError(f"Payload failed validation for record_type '{record_type}': {str(e)}") from e
        elif not cls._allow_unregistered:
            raise ValueError(f"No schema registered for record_type '{record_type}' and unregistered schemas are disallowed.")

    @classmethod
    def clear(cls) -> None:
        """Reset registry state."""
        cls._validators.clear()
        cls._allow_unregistered = True


class AuthorizationContext(BaseModel):
    """Safe, provider-independent authorization context supplied by separate authentication/identity boundary.

    Memory Module does not perform authentication. This contract represents verified credentials
    and permissions passed into memory operations.

    Security rules enforced:
    - Distinguishes UNAUTHORIZED (missing or anonymous principal) from FORBIDDEN (lacking required permission).
    - Fails closed when trusted authorization information is missing.
    - Never grants unrestricted access merely because a role is named 'admin' or 'system' without explicit permission.
    - Does not trust user-supplied owner IDs as authenticated identity.
    - Scopes alone never confer ownership or permissions.
    """
    principal_id: str = Field(..., min_length=1, description="Unique trusted identity identifier of the acting subject")
    principal_type: PrincipalType = Field(PrincipalType.USER, description="Type of principal")
    roles: List[str] = Field(default_factory=list, description="Assigned roles for the subject")
    owner_id: Optional[str] = Field(None, description="Owner entity identifier if subject is authorized to act on behalf of owner")
    accessible_scopes: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Map of scope type to allowed scope IDs, e.g. {'FARM': ['farm_123']}"
    )
    allowed_operations: List[MemoryOperation] = Field(
        default_factory=lambda: [MemoryOperation.READ, MemoryOperation.SEARCH],
        description="Explicit operations permitted for this authorization context"
    )
    requested_operation: MemoryOperation = Field(
        MemoryOperation.READ,
        description="The memory operation being attempted"
    )
    policy_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional policy or governance metadata evaluated by authorization engine"
    )

    def is_authenticated(self) -> bool:
        """Verify principal identity is authenticated (not anonymous or empty)."""
        if self.principal_type == PrincipalType.ANONYMOUS:
            return False
        if not self.principal_id or not self.principal_id.strip():
            return False
        return True

    def is_operation_permitted(self, operation: Optional[MemoryOperation] = None) -> bool:
        """Check if requested operation is explicitly permitted."""
        op = operation or self.requested_operation
        return op in self.allowed_operations

    def can_access_record(
        self,
        domain: MemoryDomain,
        record_owner_id: Optional[str],
        scope_type: MemoryScope,
        scope_id: str,
        operation: Optional[MemoryOperation] = None,
    ) -> bool:
        """Evaluate access authorization for a target record under fail-closed security.

        Returns True only if:
        1. Context is authenticated.
        2. Operation is permitted in allowed_operations.
        3. For GENERAL domain: read/search are allowed, modifications require explicit policy context flag.
        4. For USER domain: principal matches record_owner_id, or owner_id delegation matches,
           or scope access is explicitly granted in accessible_scopes for the specific scope_id.
        """
        if not self.is_authenticated():
            return False

        op = operation or self.requested_operation
        if not self.is_operation_permitted(op):
            return False

        if domain == MemoryDomain.GENERAL:
            # General memory records are shared readable; modifications require explicit manage_general_memory permission
            if op in (MemoryOperation.READ, MemoryOperation.SEARCH):
                return True
            return bool(self.policy_context.get("can_manage_general_memory", False))

        # USER domain records
        if not record_owner_id:
            return False

        # Direct ownership match
        if self.principal_id == record_owner_id:
            return True

        # Authorized delegation for owner
        if self.owner_id and self.owner_id == record_owner_id:
            return True

        # Scope-based access check (if acting on a shared farm/field with explicit grant)
        scope_key = scope_type.value
        allowed_ids = self.accessible_scopes.get(scope_key, [])
        if scope_id in allowed_ids and op in (MemoryOperation.READ, MemoryOperation.SEARCH):
            return True

        return False


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

    def to_context_contract(self) -> Any:
        """Convert this MemoryRecord into a B2 / C.3 MemoryContextContract preserving all scopes and entity IDs."""
        from modules.context.boundary.models import MemoryContextContract
        from modules.context.boundary.enums import ContextScope as C3ContextScope

        scope_map = {
            MemoryScope.USER: C3ContextScope.FARMER,
            MemoryScope.CONVERSATION: C3ContextScope.SESSION,
            MemoryScope.FARM: C3ContextScope.FARM,
            MemoryScope.FIELD: C3ContextScope.FIELD,
            MemoryScope.CROP_CYCLE: C3ContextScope.CROP_CYCLE,
            MemoryScope.GENERAL: C3ContextScope.GLOBAL,
        }
        c3_scope = scope_map.get(self.scope_type, C3ContextScope.FARMER)

        # Populate scope entity references accurately
        farmer_id = self.owner_id
        session_id = self.scope_id if self.scope_type == MemoryScope.CONVERSATION else None
        farm_id = self.scope_id if self.scope_type == MemoryScope.FARM else None
        field_id = self.scope_id if self.scope_type == MemoryScope.FIELD else None
        crop_cycle_id = self.scope_id if self.scope_type == MemoryScope.CROP_CYCLE else None

        return MemoryContextContract(
            memory_id=self.record_id,
            classification=self.classification,
            scope=c3_scope,
            content=self.payload,
            farmer_id=farmer_id,
            farm_id=farm_id,
            field_id=field_id,
            crop_cycle_id=crop_cycle_id,
            session_id=session_id,
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
        """Factory creating a MemoryRecord from an existing MemoryContextContract.

        Never fabricates ownership identities; raises ValueError if required ownership is missing.
        """
        from modules.context.boundary.enums import ContextScope as C3ContextScope

        resolved_owner = owner_id or getattr(contract, "farmer_id", None)
        if domain == MemoryDomain.USER and not resolved_owner:
            raise ValueError(
                "Cannot convert MemoryContextContract to USER domain MemoryRecord: "
                "missing required owner identity (farmer_id)."
            )

        # Map C3ContextScope back to MemoryScope
        c3_scope = getattr(contract, "scope", C3ContextScope.FARMER)
        scope_map = {
            C3ContextScope.FARMER: MemoryScope.USER,
            C3ContextScope.SESSION: MemoryScope.CONVERSATION,
            C3ContextScope.FARM: MemoryScope.FARM,
            C3ContextScope.FIELD: MemoryScope.FIELD,
            C3ContextScope.CROP_CYCLE: MemoryScope.CROP_CYCLE,
            C3ContextScope.GLOBAL: MemoryScope.GENERAL,
            C3ContextScope.REGIONAL: MemoryScope.GENERAL,
        }
        mem_scope = scope_map.get(c3_scope, MemoryScope.USER if domain == MemoryDomain.USER else MemoryScope.GENERAL)

        # Resolve scope_id from specific contract field
        scope_id = (
            getattr(contract, "field_id", None)
            or getattr(contract, "farm_id", None)
            or getattr(contract, "crop_cycle_id", None)
            or getattr(contract, "session_id", None)
            or resolved_owner
            or "general_scope"
        )

        content = getattr(contract, "content", {})
        payload = {"content": content} if not isinstance(content, dict) else content

        return cls(
            record_id=contract.memory_id,
            domain=domain,
            record_type=record_type,
            owner_id=resolved_owner if domain == MemoryDomain.USER else None,
            scope_type=mem_scope,
            scope_id=scope_id,
            payload=payload,
            source=source or (contract.provenance.get("source") if hasattr(contract, "provenance") else "b2_context"),
            classification=getattr(contract, "classification", KnowledgeClassification.FARMER_KNOWLEDGE),
            correlation_id=getattr(contract, "trace_id", None),
        )


class MemorySearchCriteria(BaseModel):
    """Structured query criteria for provider-independent record search."""
    domain: Optional[MemoryDomain] = Field(None, description="Target domain filter")
    owner_id: Optional[str] = Field(None, description="Owner ID filter")
    scope_type: Optional[MemoryScope] = Field(None, description="Scope type filter")
    scope_id: Optional[str] = Field(None, description="Scope ID filter")
    record_type: Optional[str] = Field(None, description="Record type filter")
    status: Optional[MemoryRecordStatus] = Field(MemoryRecordStatus.ACTIVE, description="Record status filter")
    classification: Optional[KnowledgeClassification] = Field(None, description="Classification filter")
    correlation_id: Optional[str] = Field(None, description="Correlation ID filter")
    include_expired: bool = Field(False, description="Whether to include expired records")
    limit: int = Field(50, ge=1, le=1000, description="Maximum number of records to return")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class StorageHealthResult(BaseModel):
    """Health check outcome for storage adapter."""
    is_healthy: bool = Field(..., description="Whether storage is healthy and accepting operations")
    provider_name: str = Field(..., description="Identifier of storage adapter provider")
    details: Dict[str, Any] = Field(default_factory=dict, description="Health and capability diagnostics")
    checked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timezone-aware UTC timestamp of check"
    )
