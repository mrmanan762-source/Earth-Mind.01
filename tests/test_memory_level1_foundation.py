"""Unit and integration tests for EarthMind Memory Module Level 1: Foundation & Contracts.

Covers:
1. Record model creation and validation
2. Required field validation
3. Domain validation (USER vs GENERAL)
4. Scope validation (USER, CONVERSATION, FARM, FIELD, CROP_CYCLE, GENERAL)
5. User ownership requirements
6. General Memory ownership rules
7. UTC timestamp validation
8. Schema version and record version validation
9. Authorization context validation
10. Error contract behavior and error codes
11. Storage adapter interface compliance
12. Existing Memory interface compatibility
13. Existing Context Manager contract compatibility
14. Import and initialization compatibility across the project
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from core.schemas.memory import (
    MemoryDomain,
    MemoryScope,
    MemoryRecordStatus,
    MemoryErrorCode,
    MemoryOperation,
    MemoryRecord,
    AuthorizationContext,
    MemorySearchCriteria,
    StorageHealthResult,
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
from modules.context.boundary.enums import KnowledgeClassification
from modules.memory.memory_module import MemoryModule


def test_01_record_model_creation_and_defaults():
    """Verify that a valid USER memory record can be created with expected defaults."""
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
    """Verify that omitting required fields raises validation errors."""
    # Missing payload
    with pytest.raises(Exception):
        MemoryRecord(
            domain=MemoryDomain.USER,
            record_type="observation",
            owner_id="farmer_001",
            scope_type=MemoryScope.FARM,
            scope_id="farm_001",
            source="sensor",
        )

    # Empty record_type
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

    # Empty scope_id
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


def test_03_domain_validation_user_vs_general():
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


def test_04_scope_validation():
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


def test_05_utc_timestamp_validation():
    """Verify strict requirement of timezone-aware UTC timestamps."""
    # Naive datetime for created_at must be rejected
    naive_dt = datetime.now()  # no tzinfo
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


def test_07_authorization_context_contract():
    """Verify AuthorizationContext data model and permission helpers."""
    auth_ctx = AuthorizationContext(
        principal_id="user_farmer_99",
        roles=["farmer"],
        owner_id="farmer_99",
        accessible_scopes={"FARM": ["farm_alpha", "farm_beta"]},
        requested_operation=MemoryOperation.READ,
    )
    assert auth_ctx.can_access_owner("farmer_99")
    assert not auth_ctx.can_access_owner("farmer_100")

    # Admin access
    admin_ctx = AuthorizationContext(
        principal_id="admin_01",
        roles=["admin"],
        requested_operation=MemoryOperation.DELETE,
    )
    assert admin_ctx.can_access_owner("farmer_100")


def test_08_error_contracts_and_codes():
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
        # Ensure enum code is defined
        assert MemoryErrorCode(code) == code


def test_09_storage_adapter_interface_compliance():
    """Verify InMemoryMemoryStorageAdapter fulfills IMemoryStorageAdapter and behaves correctly."""
    adapter = InMemoryMemoryStorageAdapter()
    assert isinstance(adapter, IMemoryStorageAdapter)

    # Health check
    health = adapter.check_health()
    assert health.is_healthy is True
    assert health.provider_name == "in_memory_reference"

    # Store record
    record = MemoryRecord(
        record_id="mem_001",
        domain=MemoryDomain.USER,
        record_type="soil_test",
        owner_id="farmer_001",
        scope_type=MemoryScope.FIELD,
        scope_id="field_north",
        payload={"nitrogen": 120, "ph": 6.8},
        source="soil_lab",
    )
    stored = adapter.store_record(record)
    assert stored.record_id == "mem_001"

    # Duplicate store raises conflict
    with pytest.raises(MemoryConflictError):
        adapter.store_record(record)

    # Get record
    retrieved = adapter.get_record("mem_001")
    assert retrieved is not None
    assert retrieved.payload["nitrogen"] == 120

    # Search records
    criteria = MemorySearchCriteria(
        domain=MemoryDomain.USER,
        owner_id="farmer_001",
        scope_type=MemoryScope.FIELD,
    )
    hits = adapter.search_records(criteria)
    assert len(hits) == 1
    assert hits[0].record_id == "mem_001"

    # Update record with optimistic concurrency check
    updated_record = retrieved.model_copy(update={"record_version": 2, "payload": {"nitrogen": 140}})
    adapter.update_record(updated_record, expected_version=1)

    # Outdated version update must fail with Conflict
    outdated_record = retrieved.model_copy(update={"record_version": 3})
    with pytest.raises(MemoryConflictError):
        adapter.update_record(outdated_record, expected_version=1)

    # Metadata retrieval
    meta = adapter.get_record_metadata("mem_001")
    assert meta is not None
    assert meta["record_version"] == 2
    assert "payload" not in meta

    # Soft delete
    deleted = adapter.delete_record("mem_001", soft=True)
    assert deleted is True
    assert adapter.get_record("mem_001").status == MemoryRecordStatus.DELETED


def test_10_storage_unavailability_simulation():
    """Verify that storage adapter failure raises explicit exceptions, never silently falling back."""
    failing_adapter = InMemoryMemoryStorageAdapter(simulate_unavailable=True)

    with pytest.raises(MemoryStorageUnavailableError):
        failing_adapter.get_record("mem_123")

    with pytest.raises(MemoryStorageUnavailableError):
        failing_adapter.search_records(MemorySearchCriteria())

    health = failing_adapter.check_health()
    assert health.is_healthy is False


def test_11_legacy_memory_interface_compatibility():
    """Verify that legacy MemoryInterface and MemoryModule continue to work without modification."""
    module = MemoryModule()
    assert isinstance(module, MemoryInterface)

    module.initialize()
    stored = module.store_memory("legacy_key", "legacy_val")
    assert stored is True

    val = module.retrieve_memory("legacy_key")
    assert val == "legacy_val"
    module.shutdown()


def test_12_context_manager_contract_bidirectional_conversion():
    """Verify conversion to and from existing MemoryContextContract."""
    record = MemoryRecord(
        record_id="mem_ctx_1",
        domain=MemoryDomain.USER,
        record_type="farmer_note",
        owner_id="farmer_007",
        scope_type=MemoryScope.FARM,
        scope_id="farm_007",
        payload={"note": "apply bio-fertilizer"},
        source="advisory_engine",
    )

    # Convert to MemoryContextContract
    contract = record.to_context_contract()
    assert isinstance(contract, MemoryContextContract)
    assert contract.memory_id == "mem_ctx_1"
    assert contract.farmer_id == "farmer_007"
    assert contract.content == {"note": "apply bio-fertilizer"}

    # Convert back from MemoryContextContract
    roundtrip = MemoryRecord.from_context_contract(contract)
    assert roundtrip.record_id == "mem_ctx_1"
    assert roundtrip.owner_id == "farmer_007"
    assert roundtrip.domain == MemoryDomain.USER
    assert roundtrip.payload == {"note": "apply bio-fertilizer"}


def test_13_all_17_approved_fields_presence():
    """Verify that all 17 approved fields are explicitly present on MemoryRecord."""
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
    assert expected_fields == model_fields, f"Missing or extra fields: {expected_fields ^ model_fields}"


def test_14_import_and_initialization_compatibility():
    """Verify that top-level modules.memory imports expose all Level 1 contracts cleanly."""
    import modules.memory as memory_pkg

    required_attributes = [
        "MemoryDomain",
        "MemoryScope",
        "MemoryRecordStatus",
        "MemoryErrorCode",
        "MemoryOperation",
        "MemoryRecord",
        "AuthorizationContext",
        "MemorySearchCriteria",
        "StorageHealthResult",
        "IMemoryStorageAdapter",
        "InMemoryMemoryStorageAdapter",
        "MemoryError",
        "MemoryInterface",
        "MemoryModule",
    ]
    for attr in required_attributes:
        assert hasattr(memory_pkg, attr), f"modules.memory missing attribute: {attr}"
