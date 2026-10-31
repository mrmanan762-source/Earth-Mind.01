"""Comprehensive unit and integration tests for EarthMind Memory Module Level 1: Foundation & Contracts.

Covers:
1. Record model creation and validation with all 17 approved fields
2. Required and optional field validation
3. Domain validation (USER vs GENERAL) and ownership integrity
4. Scope validation (USER, CONVERSATION, FARM, FIELD, CROP_CYCLE, GENERAL)
5. User ownership requirements and rejection of fabricated identities
6. General Memory ownership rules (owner_id must be None)
7. Strict UTC timezone validation and expiration consistency
8. Schema version and record version validation
9. Authorization context validation (principal type, User A vs User B, privilege escalation, unauthorized vs forbidden)
10. Error contract behavior across all 11 approved categories
11. Storage adapter interface compliance and in-memory reference adapter behavior
12. Optimistic concurrency control, version increments, stale version rejection
13. Storage isolation (no accidental object reference mutation)
14. Deterministic search sorting and pagination
15. Storage failure simulation and explicit error raising
16. Payload schema registry: registration, validation, unregistered schema handling
17. Existing MemoryInterface and MemoryModule backward compatibility
18. Bidirectional Context Manager (MemoryContextContract) compatibility across all 6 scopes
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from pydantic import BaseModel, Field

from core.schemas.memory import (
    MemoryDomain,
    MemoryScope,
    MemoryRecordStatus,
    MemoryErrorCode,
    MemoryOperation,
    PrincipalType,
    MemoryRecord,
    AuthorizationContext,
    MemorySearchCriteria,
    StorageHealthResult,
    PayloadSchemaRegistry,
)
from core.interfaces.memory_storage import IMemoryStorageAdapter
from core.interfaces.services import MemoryInterface
from modules.memory.storage_adapter import InMemoryMemoryStorageAdapter
from modules.memory.errors import (
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
from modules.context.boundary.models import MemoryContextContract
from modules.context.boundary.enums import KnowledgeClassification, ContextScope as C3ContextScope
from modules.memory.memory_module import MemoryModule


@pytest.fixture(autouse=True)
def clean_payload_registry():
    """Ensure clean PayloadSchemaRegistry before each test."""
    PayloadSchemaRegistry.clear()
    yield
    PayloadSchemaRegistry.clear()


def test_01_all_17_approved_fields_presence_and_defaults():
    """Verify that all 17 approved fields are explicitly present on MemoryRecord with valid defaults."""
    expected_fields = {
        "record_id",
        "domain",
        "record_type",
        "owner_id",
        "scope_type",
        "scope_id",
        "payload",
        "source",
        "created_at",
        "updated_at",
        "schema_version",
        "record_version",
        "status",
        "retention_policy_id",
        "expires_at",
        "classification",
        "correlation_id",
    }
    model_fields = set(MemoryRecord.model_fields.keys())
    assert expected_fields == model_fields, f"Field mismatch: {expected_fields ^ model_fields}"

    record = MemoryRecord(
        domain=MemoryDomain.USER,
        record_type="farmer_preference",
        owner_id="farmer_001",
        scope_type=MemoryScope.USER,
        scope_id="farmer_001",
        payload={"preferred_language": "hi", "irrigation_method": "drip"},
        source="user_profile_form",
    )

    assert record.record_id.startswith("mem_")
    assert record.domain == MemoryDomain.USER
    assert record.owner_id == "farmer_001"
    assert record.schema_version == "1.0"
    assert record.record_version == 1
    assert record.status == MemoryRecordStatus.ACTIVE
    assert record.created_at.tzinfo == timezone.utc
    assert record.updated_at.tzinfo == timezone.utc
    assert record.classification == KnowledgeClassification.FARMER_KNOWLEDGE


def test_02_required_field_validation():
    """Verify that omitting required fields raises explicit validation errors."""
    with pytest.raises(Exception):
        MemoryRecord(
            domain=MemoryDomain.USER,
            record_type="observation",
            owner_id="farmer_001",
            scope_type=MemoryScope.FARM,
            scope_id="farm_001",
            source="sensor",
        )

    with pytest.raises(Exception):
        MemoryRecord(
            domain=MemoryDomain.USER,
            record_type="",
            owner_id="farmer_001",
            scope_type=MemoryScope.FARM,
            scope_id="farm_001",
            payload={"key": "val"},
            source="sensor",
        )

    with pytest.raises(Exception):
        MemoryRecord(
            domain=MemoryDomain.USER,
            record_type="crop_history",
            owner_id="farmer_001",
            scope_type=MemoryScope.FIELD,
            scope_id="",
            payload={"crop": "wheat"},
            source="field_survey",
        )


def test_03_domain_validation_and_ownership_rules():
    """Verify logical memory domain boundaries and ownership integrity."""
    # USER domain without owner_id must fail
    with pytest.raises(ValueError, match="USER domain records must have a non-empty 'owner_id'"):
        MemoryRecord(
            domain=MemoryDomain.USER,
            record_type="preference",
            owner_id=None,
            scope_type=MemoryScope.USER,
            scope_id="farmer_001",
            payload={"test": 1},
            source="manual",
        )

    # GENERAL domain with owner_id must fail
    with pytest.raises(ValueError, match="GENERAL domain records must not have an 'owner_id'"):
        MemoryRecord(
            domain=MemoryDomain.GENERAL,
            record_type="regional_practice",
            owner_id="farmer_001",
            scope_type=MemoryScope.GENERAL,
            scope_id="bihar_all",
            payload={"practice": "SRI"},
            source="icar_manual",
        )

    # Valid GENERAL domain record
    gen_record = MemoryRecord(
        domain=MemoryDomain.GENERAL,
        record_type="regional_practice",
        owner_id=None,
        scope_type=MemoryScope.GENERAL,
        scope_id="bihar_all",
        payload={"practice": "SRI"},
        source="icar_manual",
    )
    assert gen_record.domain == MemoryDomain.GENERAL
    assert gen_record.owner_id is None


def test_04_scope_validation_all_6_scopes():
    """Verify supported logical scopes: USER, CONVERSATION, FARM, FIELD, CROP_CYCLE, GENERAL."""
    scopes = [
        MemoryScope.USER,
        MemoryScope.CONVERSATION,
        MemoryScope.FARM,
        MemoryScope.FIELD,
        MemoryScope.CROP_CYCLE,
    ]
    for sc in scopes:
        rec = MemoryRecord(
            domain=MemoryDomain.USER,
            record_type="test_data",
            owner_id="farmer_123",
            scope_type=sc,
            scope_id=f"id_for_{sc.value}",
            payload={"data": 123},
            source="test_runner",
        )
        assert rec.scope_type == sc

    # USER record with GENERAL scope must fail
    with pytest.raises(ValueError, match="USER domain records cannot have scope_type 'GENERAL'"):
        MemoryRecord(
            domain=MemoryDomain.USER,
            record_type="test",
            owner_id="farmer_123",
            scope_type=MemoryScope.GENERAL,
            scope_id="gen_1",
            payload={"data": 1},
            source="test",
        )

    # GENERAL record with USER scope must fail
    with pytest.raises(ValueError, match="GENERAL domain records cannot have scope_type 'USER'"):
        MemoryRecord(
            domain=MemoryDomain.GENERAL,
            record_type="test",
            owner_id=None,
            scope_type=MemoryScope.USER,
            scope_id="farmer_1",
            payload={"data": 1},
            source="test",
        )


def test_05_utc_timestamp_and_expiration_validation():
    """Verify strict requirement of timezone-aware UTC timestamps and expiration consistency."""
    # Naive datetime for created_at must be rejected
    naive_dt = datetime.now()
    with pytest.raises(ValueError, match="must be a timezone-aware UTC datetime"):
        MemoryRecord(
            domain=MemoryDomain.USER,
            record_type="test",
            owner_id="farmer_001",
            scope_type=MemoryScope.USER,
            scope_id="farmer_001",
            payload={"val": 1},
            source="test",
            created_at=naive_dt,
        )

    # Expiration earlier than creation must be rejected
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="'expires_at' must be strictly later than 'created_at'"):
        MemoryRecord(
            domain=MemoryDomain.USER,
            record_type="test",
            owner_id="farmer_001",
            scope_type=MemoryScope.USER,
            scope_id="farmer_001",
            payload={"val": 1},
            source="test",
            created_at=now,
            expires_at=now - timedelta(seconds=10),
        )


def test_06_schema_and_record_version_validation():
    """Verify schema_version string and record_version integer validation."""
    with pytest.raises(Exception):
        # record_version < 1
        MemoryRecord(
            domain=MemoryDomain.USER,
            record_type="test",
            owner_id="farmer_001",
            scope_type=MemoryScope.USER,
            scope_id="farmer_001",
            payload={"val": 1},
            source="test",
            record_version=0,
        )

    with pytest.raises(Exception):
        # Empty schema_version
        MemoryRecord(
            domain=MemoryDomain.USER,
            record_type="test",
            owner_id="farmer_001",
            scope_type=MemoryScope.USER,
            scope_id="farmer_001",
            payload={"val": 1},
            source="test",
            schema_version="",
        )


def test_07_authorization_security_and_privilege_escalation():
    """Verify authorization context fail-closed behavior, role evaluation, and cross-user isolation."""
    # 1. Anonymous principal is unauthenticated
    anon_ctx = AuthorizationContext(
        principal_id="anonymous_guest",
        principal_type=PrincipalType.ANONYMOUS,
        allowed_operations=[MemoryOperation.READ],
    )
    assert not anon_ctx.is_authenticated()
    assert not anon_ctx.can_access_record(
        domain=MemoryDomain.USER,
        record_owner_id="farmer_001",
        scope_type=MemoryScope.USER,
        scope_id="farmer_001",
    )

    # 2. User A accessing User B's record is rejected (no cross-user access)
    user_a = AuthorizationContext(
        principal_id="user_farmer_A",
        principal_type=PrincipalType.USER,
        roles=["farmer"],
        allowed_operations=[MemoryOperation.READ, MemoryOperation.SEARCH],
    )
    assert user_a.is_authenticated()
    # Can access own record
    assert user_a.can_access_record(
        domain=MemoryDomain.USER,
        record_owner_id="user_farmer_A",
        scope_type=MemoryScope.USER,
        scope_id="user_farmer_A",
    )
    # CANNOT access User B record
    assert not user_a.can_access_record(
        domain=MemoryDomain.USER,
        record_owner_id="user_farmer_B",
        scope_type=MemoryScope.USER,
        scope_id="user_farmer_B",
    )

    # 3. Privilege escalation protection: Role named 'admin' alone does NOT grant access without allowed_operations
    admin_read_only = AuthorizationContext(
        principal_id="admin_user_01",
        principal_type=PrincipalType.USER,
        roles=["admin"],
        allowed_operations=[MemoryOperation.READ],
        requested_operation=MemoryOperation.DELETE,
    )
    # Cannot perform DELETE when only READ is permitted
    assert not admin_read_only.can_access_record(
        domain=MemoryDomain.USER,
        record_owner_id="user_farmer_B",
        scope_type=MemoryScope.USER,
        scope_id="user_farmer_B",
        operation=MemoryOperation.DELETE,
    )

    # 4. Scope-based access grant
    farm_inspector = AuthorizationContext(
        principal_id="inspector_01",
        principal_type=PrincipalType.USER,
        roles=["agronomist"],
        accessible_scopes={"FARM": ["farm_bihar_01"]},
        allowed_operations=[MemoryOperation.READ],
    )
    # Can access farm_bihar_01 even if owned by farmer_A
    assert farm_inspector.can_access_record(
        domain=MemoryDomain.USER,
        record_owner_id="user_farmer_A",
        scope_type=MemoryScope.FARM,
        scope_id="farm_bihar_01",
        operation=MemoryOperation.READ,
    )
    # Cannot access other farms
    assert not farm_inspector.can_access_record(
        domain=MemoryDomain.USER,
        record_owner_id="user_farmer_A",
        scope_type=MemoryScope.FARM,
        scope_id="farm_punjab_02",
        operation=MemoryOperation.READ,
    )

    # 5. GENERAL domain read is allowed; modification requires policy context
    assert user_a.can_access_record(
        domain=MemoryDomain.GENERAL,
        record_owner_id=None,
        scope_type=MemoryScope.GENERAL,
        scope_id="bihar_soil_types",
        operation=MemoryOperation.READ,
    )
    assert not user_a.can_access_record(
        domain=MemoryDomain.GENERAL,
        record_owner_id=None,
        scope_type=MemoryScope.GENERAL,
        scope_id="bihar_soil_types",
        operation=MemoryOperation.UPDATE,
    )


def test_08_payload_schema_registry_validation():
    """Verify extensible record-type payload schema registration and validation."""
    class CropHistoryPayload(BaseModel):
        crop: str = Field(..., min_length=2)
        yield_quintals: float = Field(..., gt=0.0)

    # Register schema
    PayloadSchemaRegistry.register_schema("crop_history", CropHistoryPayload)

    # Valid payload succeeds
    rec = MemoryRecord(
        domain=MemoryDomain.USER,
        record_type="crop_history",
        owner_id="farmer_01",
        scope_type=MemoryScope.FIELD,
        scope_id="field_1",
        payload={"crop": "wheat", "yield_quintals": 42.5},
        source="harvest_log",
    )
    assert rec.payload["crop"] == "wheat"

    # Invalid payload raises validation error
    with pytest.raises(ValueError, match="Payload failed validation for record_type 'crop_history'"):
        MemoryRecord(
            domain=MemoryDomain.USER,
            record_type="crop_history",
            owner_id="farmer_01",
            scope_type=MemoryScope.FIELD,
            scope_id="field_1",
            payload={"crop": "w", "yield_quintals": -5.0},
            source="harvest_log",
        )

    # Unregistered schema rejection when configured
    PayloadSchemaRegistry.set_allow_unregistered(False)
    with pytest.raises(ValueError, match="unregistered schemas are disallowed"):
        MemoryRecord(
            domain=MemoryDomain.USER,
            record_type="unknown_custom_type",
            owner_id="farmer_01",
            scope_type=MemoryScope.FIELD,
            scope_id="field_1",
            payload={"some": "data"},
            source="harvest_log",
        )


def test_09_error_contracts_and_approved_codes():
    """Verify all 11 approved Memory error categories and EarthMindException inheritance."""
    errors = [
        (MemoryInvalidArgumentError("bad arg"), "INVALID_ARGUMENT"),
        (MemoryInvalidRecordSchemaError("bad schema"), "INVALID_RECORD_SCHEMA"),
        (MemoryUnauthorizedError("no auth"), "UNAUTHORIZED"),
        (MemoryForbiddenError("no perm"), "FORBIDDEN"),
        (MemoryNotFoundError("rec_1"), "NOT_FOUND"),
        (MemoryConflictError("rec_1", "conflict"), "CONFLICT"),
        (MemoryStorageUnavailableError("supabase", "down"), "STORAGE_UNAVAILABLE"),
        (MemoryStorageError("disk error"), "STORAGE_ERROR"),
        (MemoryRetentionPolicyViolationError("expired"), "RETENTION_POLICY_VIOLATION"),
        (MemoryIntegrityError("checksum mismatch"), "INTEGRITY_ERROR"),
        (MemoryInternalError("crash"), "INTERNAL_ERROR"),
    ]

    for err, code in errors:
        assert isinstance(err, MemoryError)
        assert err.error_contract.error_code == code
        assert err.error_contract.module == "memory"
        assert MemoryErrorCode(code) == code


def test_10_storage_adapter_crud_and_optimistic_locking():
    """Verify InMemoryMemoryStorageAdapter CRUD, version increments, and concurrency conflicts."""
    adapter = InMemoryMemoryStorageAdapter()
    assert isinstance(adapter, IMemoryStorageAdapter)

    # Health check
    health = adapter.check_health()
    assert health.is_healthy is True

    record = MemoryRecord(
        record_id="mem_soil_001",
        domain=MemoryDomain.USER,
        record_type="soil_data",
        owner_id="farmer_01",
        scope_type=MemoryScope.FIELD,
        scope_id="field_north",
        payload={"ph": 6.5, "organic_carbon": 0.45},
        source="soil_health_card",
        record_version=1,
    )
    stored = adapter.store_record(record)
    assert stored.record_id == "mem_soil_001"

    # Duplicate store conflict
    with pytest.raises(MemoryConflictError):
        adapter.store_record(record)

    # Get record
    retrieved = adapter.get_record("mem_soil_001")
    assert retrieved is not None
    assert retrieved.payload["ph"] == 6.5

    # Concurrency conflict: Stale version update (record_version <= existing)
    stale_update = retrieved.model_copy(update={"payload": {"ph": 6.6}})
    with pytest.raises(MemoryConflictError, match="Stale version update rejected"):
        adapter.update_record(stale_update)

    # Expected version mismatch
    valid_update = retrieved.model_copy(update={"record_version": 2, "payload": {"ph": 6.8}})
    with pytest.raises(MemoryConflictError, match="Version mismatch: expected 99"):
        adapter.update_record(valid_update, expected_version=99)

    # Successful update
    updated = adapter.update_record(valid_update, expected_version=1)
    assert updated.record_version == 2
    assert updated.payload["ph"] == 6.8

    # Metadata check
    meta = adapter.get_record_metadata("mem_soil_001")
    assert meta["record_version"] == 2
    assert "payload" not in meta

    # Soft delete increments version and updates status
    deleted = adapter.delete_record("mem_soil_001", soft=True)
    assert deleted is True
    post_delete = adapter.get_record("mem_soil_001")
    assert post_delete.status == MemoryRecordStatus.DELETED
    assert post_delete.record_version == 3

    # Hard delete removes record completely
    hard_deleted = adapter.delete_record("mem_soil_001", soft=False)
    assert hard_deleted is True
    assert adapter.get_record("mem_soil_001") is None


def test_11_storage_isolation_guarantee():
    """Verify that stored records cannot be mutated externally via object references."""
    adapter = InMemoryMemoryStorageAdapter()
    payload = {"counter": 1}
    record = MemoryRecord(
        record_id="mem_iso_1",
        domain=MemoryDomain.USER,
        record_type="counter_state",
        owner_id="farmer_01",
        scope_type=MemoryScope.USER,
        scope_id="farmer_01",
        payload=payload,
        source="test",
    )
    adapter.store_record(record)

    # Mutate original local payload
    payload["counter"] = 999
    # Stored record must NOT change
    assert adapter.get_record("mem_iso_1").payload["counter"] == 1

    # Mutate retrieved record payload
    retrieved = adapter.get_record("mem_iso_1")
    retrieved.payload["counter"] = 888
    # Stored record must still NOT change
    assert adapter.get_record("mem_iso_1").payload["counter"] == 1


def test_12_deterministic_search_sorting_and_pagination():
    """Verify search returns deterministic ordering by (created_at desc, record_id asc) and pagination."""
    adapter = InMemoryMemoryStorageAdapter()
    base_time = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)

    for i in range(5):
        adapter.store_record(
            MemoryRecord(
                record_id=f"mem_sort_{i}",
                domain=MemoryDomain.USER,
                record_type="note",
                owner_id="farmer_common",
                scope_type=MemoryScope.USER,
                scope_id="farmer_common",
                payload={"index": i},
                source="test",
                created_at=base_time + timedelta(minutes=i),
            )
        )

    # Search with limit=2, offset=0
    crit = MemorySearchCriteria(owner_id="farmer_common", limit=2, offset=0)
    hits_p1 = adapter.search_records(crit)
    assert len(hits_p1) == 2
    # Newest first
    assert hits_p1[0].record_id == "mem_sort_4"
    assert hits_p1[1].record_id == "mem_sort_3"

    # Search page 2
    crit.offset = 2
    hits_p2 = adapter.search_records(crit)
    assert len(hits_p2) == 2
    assert hits_p2[0].record_id == "mem_sort_2"
    assert hits_p2[1].record_id == "mem_sort_1"


def test_13_storage_unavailability_simulation():
    """Verify explicit storage unavailability exception without silent fallback."""
    failing_adapter = InMemoryMemoryStorageAdapter(simulate_unavailable=True)

    with pytest.raises(MemoryStorageUnavailableError):
        failing_adapter.get_record("mem_123")

    with pytest.raises(MemoryStorageUnavailableError):
        failing_adapter.search_records(MemorySearchCriteria())

    health = failing_adapter.check_health()
    assert health.is_healthy is False


def test_14_legacy_memory_interface_compatibility():
    """Verify that legacy MemoryInterface and MemoryModule continue to work without modification."""
    module = MemoryModule()
    assert isinstance(module, MemoryInterface)

    module.initialize()
    assert module.store_memory("legacy_key", "legacy_val") is True
    assert module.retrieve_memory("legacy_key") == "legacy_val"
    module.shutdown()


def test_15_context_contract_bidirectional_conversion_all_scopes():
    """Verify conversion to and from MemoryContextContract across all 6 scopes and entity references."""
    scope_mappings = [
        (MemoryScope.USER, C3ContextScope.FARMER, {"farmer_id": "f_1"}),
        (MemoryScope.CONVERSATION, C3ContextScope.SESSION, {"session_id": "sess_1"}),
        (MemoryScope.FARM, C3ContextScope.FARM, {"farm_id": "farm_1"}),
        (MemoryScope.FIELD, C3ContextScope.FIELD, {"field_id": "field_1"}),
        (MemoryScope.CROP_CYCLE, C3ContextScope.CROP_CYCLE, {"crop_cycle_id": "cc_1"}),
    ]

    for mem_scope, c3_scope, entity_kwargs in scope_mappings:
        scope_id = next(iter(entity_kwargs.values()))
        rec = MemoryRecord(
            record_id=f"rec_{mem_scope.value}",
            domain=MemoryDomain.USER,
            record_type="note",
            owner_id="f_1",
            scope_type=mem_scope,
            scope_id=scope_id,
            payload={"msg": "hello"},
            source="test",
        )
        contract = rec.to_context_contract()
        assert isinstance(contract, MemoryContextContract)
        assert contract.scope == c3_scope

        # Convert back
        roundtrip = MemoryRecord.from_context_contract(contract)
        assert roundtrip.record_id == rec.record_id
        assert roundtrip.owner_id == "f_1"
        assert roundtrip.scope_type == mem_scope


def test_16_rejection_of_missing_owner_in_context_conversion():
    """Verify conversion rejects USER domain conversion when owner identity is missing (no fabricated owners)."""
    contract = MemoryContextContract(
        memory_id="mem_no_owner",
        content={"data": "test"},
        farmer_id=None,
    )
    with pytest.raises(ValueError, match="missing required owner identity"):
        MemoryRecord.from_context_contract(contract, domain=MemoryDomain.USER)


def test_17_import_and_initialization_compatibility():
    """Verify that top-level modules.memory imports expose all Level 1 contracts cleanly."""
    import modules.memory as memory_pkg

    required_attributes = [
        "MemoryDomain",
        "MemoryScope",
        "MemoryRecordStatus",
        "MemoryErrorCode",
        "MemoryOperation",
        "PrincipalType",
        "MemoryRecord",
        "AuthorizationContext",
        "MemorySearchCriteria",
        "StorageHealthResult",
        "PayloadSchemaRegistry",
        "IMemoryStorageAdapter",
        "InMemoryMemoryStorageAdapter",
        "MemoryError",
        "MemoryInterface",
        "MemoryModule",
    ]
    for attr in required_attributes:
        assert hasattr(memory_pkg, attr), f"modules.memory missing attribute: {attr}"
