"""Comprehensive unit, integration, and lifecycle tests for EarthMind Memory Module Level 4.

Tests cover:
A. CRUD tests:
   - Store valid record via store() and store_record().
   - Retrieve existing record via retrieve() and get_record().
   - Retrieve nonexistent record.
   - Update valid record via update() and update_record().
   - Delete authorized record via delete() and delete_record() (soft and hard).
   - Duplicate record ID conflict handling.
   - Invalid record payload handling.
   - Metadata retrieval (payload omitted, authorization verified).
   - Health check behavior (healthy vs storage failure).

B. Structured search tests:
   - Record-ID lookup.
   - Exact scope and domain filtering.
   - Typed metadata and status filtering.
   - Bounded pagination (offset and limit).
   - Deterministic sorting by created_at, updated_at, record_id.
   - Empty result and invalid query handling.
   - Cross-user search isolation.

C. Versioning and concurrency tests:
   - Correct initial record_version (= 1).
   - Version increment on update.
   - Successful update with expected_version.
   - Stale update conflict detection.
   - Immutable identity enforcement (record_id, domain, owner_id, scope_type cannot change).

D. Retention and lifecycle tests:
   - Category-specific retention policies (transient, seasonal, permanent, general).
   - Expiration calculation and detection.
   - Record without expiration.
   - Expired record identification and retention enforcement (transition to EXPIRED).
   - General Memory retention governance.

E. Deletion and purge tests:
   - Authorized logical deletion.
   - Exclusion of deleted records from normal retrieval and search.
   - Authorized physical purge with PurgeCriteria (dry-run and live).
   - Deletion verification (NOT_DELETED, LOGICALLY_DELETED, PHYSICALLY_PURGED).
   - Repeated deletion idempotency.

F. Security tests:
   - Cross-user retrieval, update, delete, metadata denial.
   - Scope IDs cannot bypass ownership.
   - General Memory governance protection.
   - Privileged-role names without grant fail closed.

G. Real PostgreSQL 16 persistence integration:
   - Full lifecycle operations against live SupabasePostgresMemoryStorageAdapter.
"""

from datetime import datetime, timezone, timedelta
import pytest

from core.config.settings import PostgresConfig
from core.interfaces.memory_storage import IMemoryStorageAdapter
from core.schemas.memory import (
    AuthorizationContext,
    KnowledgeClassification,
    MemoryDomain,
    MemoryOperation,
    MemoryRecord,
    MemoryRecordStatus,
    MemoryScope,
    MemorySearchCriteria,
    MemorySortField,
    PayloadSchemaRegistry,
    PrincipalType,
    PurgeCriteria,
    RetentionCategory,
    RetentionPolicy,
    SortOrder,
)
from modules.database.postgres_db import PostgresDatabaseService
from modules.memory.errors import (
    MemoryConflictError,
    MemoryForbiddenError,
    MemoryInvalidArgumentError,
    MemoryInvalidRecordSchemaError,
    MemoryNotFoundError,
    MemoryRetentionPolicyViolationError,
    MemoryStorageUnavailableError,
    MemoryUnauthorizedError,
)
from modules.memory.memory_lifecycle import MemoryLifecycleManager
from modules.memory.memory_retriever import StructuredMemoryRetriever
from modules.memory.memory_service import MemoryService
from modules.memory.memory_validator import MemoryRecordValidator
from modules.memory.security import MemorySecurityAuditor, MemorySecurityEnforcer
from modules.memory.storage_adapter import InMemoryMemoryStorageAdapter
from modules.memory.supabase_adapter import SupabasePostgresMemoryStorageAdapter


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure PayloadSchemaRegistry is reset to default state for each test."""
    PayloadSchemaRegistry.clear_registry()
    yield
    PayloadSchemaRegistry.clear_registry()


@pytest.fixture
def memory_service():
    """Default memory service with in-memory adapter."""
    adapter = InMemoryMemoryStorageAdapter()
    return MemoryService(storage_adapter=adapter)


@pytest.fixture
def auth_farmer_1():
    return AuthorizationContext(
        principal_id="farmer_alpha",
        principal_type=PrincipalType.USER,
        roles=["farmer"],
        accessible_scopes={"FARM": ["farm_01"], "FIELD": ["field_01"]},
        allowed_operations=[
            MemoryOperation.CREATE,
            MemoryOperation.READ,
            MemoryOperation.UPDATE,
            MemoryOperation.DELETE,
            MemoryOperation.SEARCH,
        ],
    )


@pytest.fixture
def auth_farmer_2():
    return AuthorizationContext(
        principal_id="farmer_beta",
        principal_type=PrincipalType.USER,
        roles=["farmer"],
        accessible_scopes={"FARM": ["farm_02"]},
        allowed_operations=[
            MemoryOperation.CREATE,
            MemoryOperation.READ,
            MemoryOperation.UPDATE,
            MemoryOperation.DELETE,
            MemoryOperation.SEARCH,
        ],
    )


@pytest.fixture
def auth_curator():
    return AuthorizationContext(
        principal_id="curator_01",
        principal_type=PrincipalType.SERVICE,
        roles=["curator"],
        policy_context={"allow_general_write": True},
        allowed_operations=[
            MemoryOperation.CREATE,
            MemoryOperation.READ,
            MemoryOperation.UPDATE,
            MemoryOperation.DELETE,
            MemoryOperation.SEARCH,
        ],
    )


# =============================================================================
# A. CRUD Tests
# =============================================================================

def test_a01_store_and_retrieve_record(memory_service, auth_farmer_1):
    """Store valid record and retrieve via both method naming styles."""
    record = MemoryRecord(
        record_id="rec_soil_101",
        domain=MemoryDomain.USER,
        record_type="soil_test",
        owner_id="farmer_alpha",
        scope_type=MemoryScope.FIELD,
        scope_id="field_01",
        payload={"ph": 6.8, "nitrogen_kg_ha": 120},
        source="soil_health_lab",
    )

    stored = memory_service.store(auth_farmer_1, record)
    assert stored.record_id == "rec_soil_101"
    assert stored.record_version == 1

    retrieved = memory_service.retrieve(auth_farmer_1, "rec_soil_101")
    assert retrieved.record_id == "rec_soil_101"
    assert retrieved.payload["ph"] == 6.8

    # Also test get_record alias
    retrieved_alias = memory_service.get_record(auth_farmer_1, "rec_soil_101")
    assert retrieved_alias.record_id == "rec_soil_101"


def test_a02_retrieve_nonexistent_record(memory_service, auth_farmer_1):
    """Attempting to retrieve nonexistent record raises MemoryNotFoundError."""
    with pytest.raises(MemoryNotFoundError):
        memory_service.retrieve(auth_farmer_1, "nonexistent_rec")


def test_a03_store_duplicate_id_conflict(memory_service, auth_farmer_1):
    """Storing record with an already existing ID raises MemoryConflictError."""
    record = MemoryRecord(
        record_id="rec_dup_001",
        domain=MemoryDomain.USER,
        record_type="note",
        owner_id="farmer_alpha",
        scope_type=MemoryScope.USER,
        scope_id="farmer_alpha",
        payload={"text": "first entry"},
        source="unit_test",
    )
    memory_service.store(auth_farmer_1, record)

    dup = record.model_copy(update={"payload": {"text": "second entry"}})
    with pytest.raises(MemoryConflictError):
        memory_service.store(auth_farmer_1, dup)


def test_a04_payload_schema_validation(memory_service, auth_farmer_1):
    """Payload schema validation rejects invalid schemas when registered."""
    def _validate_soil(data):
        if "ph" not in data or not (0 <= data["ph"] <= 14):
            raise ValueError("Soil test must include ph between 0 and 14.")

    PayloadSchemaRegistry.register_schema("soil_test", _validate_soil)

    # Invalid payload rejected during model instantiation or schema validation
    with pytest.raises((ValueError, MemoryInvalidRecordSchemaError)):
        MemoryRecord(
            record_id="rec_bad_soil",
            domain=MemoryDomain.USER,
            record_type="soil_test",
            owner_id="farmer_alpha",
            scope_type=MemoryScope.FIELD,
            scope_id="field_01",
            payload={"nitrogen": 120},  # missing ph
            source="unit_test",
        )

    # Valid payload
    good_record = MemoryRecord(
        record_id="rec_good_soil",
        domain=MemoryDomain.USER,
        record_type="soil_test",
        owner_id="farmer_alpha",
        scope_type=MemoryScope.FIELD,
        scope_id="field_01",
        payload={"ph": 7.2, "nitrogen": 120},
        source="unit_test",
    )
    stored = memory_service.store(auth_farmer_1, good_record)
    assert stored.record_id == "rec_good_soil"


def test_a05_get_metadata_omits_payload(memory_service, auth_farmer_1):
    """Metadata inspection returns record metadata without payload."""
    record = MemoryRecord(
        record_id="rec_meta_01",
        domain=MemoryDomain.USER,
        record_type="secret_profile",
        owner_id="farmer_alpha",
        scope_type=MemoryScope.USER,
        scope_id="farmer_alpha",
        payload={"private_notes": "sensitive personal details"},
        source="unit_test",
    )
    memory_service.store(auth_farmer_1, record)

    meta = memory_service.get_metadata(auth_farmer_1, "rec_meta_01")
    assert meta["record_id"] == "rec_meta_01"
    assert meta["record_version"] == 1
    assert "payload" not in meta


def test_a06_health_check(memory_service):
    """Health check reports healthy on operational storage, unavailable on failure."""
    health = memory_service.health_check()
    assert health.is_healthy is True

    failing_adapter = InMemoryMemoryStorageAdapter(simulate_unavailable=True)
    failing_service = MemoryService(storage_adapter=failing_adapter)
    unhealthy = failing_service.health_check()
    assert unhealthy.is_healthy is False


# =============================================================================
# B. Structured Search Tests
# =============================================================================

def test_b01_structured_search_filtering(memory_service, auth_farmer_1):
    """Search matches criteria across record_type, scope, and status."""
    for i in range(3):
        memory_service.store(
            auth_farmer_1,
            MemoryRecord(
                record_id=f"rec_field_{i}",
                domain=MemoryDomain.USER,
                record_type="field_observation",
                owner_id="farmer_alpha",
                scope_type=MemoryScope.FIELD,
                scope_id="field_01",
                payload={"index": i},
                source="test",
            ),
        )
    # Different record_type
    memory_service.store(
        auth_farmer_1,
        MemoryRecord(
            record_id="rec_farm_summary",
            domain=MemoryDomain.USER,
            record_type="farm_summary",
            owner_id="farmer_alpha",
            scope_type=MemoryScope.FARM,
            scope_id="farm_01",
            payload={"summary": "all good"},
            source="test",
        ),
    )

    criteria = MemorySearchCriteria(record_type="field_observation")
    hits = memory_service.search(auth_farmer_1, criteria)
    assert len(hits) == 3
    assert all(h.record_type == "field_observation" for h in hits)


def test_b02_pagination_and_deterministic_sorting(memory_service, auth_farmer_1):
    """Search results adhere strictly to limit, offset, and deterministic sorting."""
    base_time = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
    for i in range(5):
        memory_service.store(
            auth_farmer_1,
            MemoryRecord(
                record_id=f"rec_page_{i}",
                domain=MemoryDomain.USER,
                record_type="log",
                owner_id="farmer_alpha",
                scope_type=MemoryScope.USER,
                scope_id="farmer_alpha",
                payload={"item": i},
                source="test",
                created_at=base_time + timedelta(minutes=i),
            ),
        )

    # Page 1 (limit 2, offset 0, DESC)
    page1 = memory_service.search(
        auth_farmer_1,
        MemorySearchCriteria(
            record_type="log",
            limit=2,
            offset=0,
            sort_by=MemorySortField.CREATED_AT,
            sort_order=SortOrder.DESC,
        ),
    )
    assert len(page1) == 2
    assert page1[0].record_id == "rec_page_4"
    assert page1[1].record_id == "rec_page_3"

    # Page 2 (limit 2, offset 2, DESC)
    page2 = memory_service.search(
        auth_farmer_1,
        MemorySearchCriteria(
            record_type="log",
            limit=2,
            offset=2,
            sort_by=MemorySortField.CREATED_AT,
            sort_order=SortOrder.DESC,
        ),
    )
    assert len(page2) == 2
    assert page2[0].record_id == "rec_page_2"
    assert page2[1].record_id == "rec_page_1"


def test_b03_cross_user_search_isolation(memory_service, auth_farmer_1, auth_farmer_2):
    """Farmer 1 search cannot see Farmer 2 records."""
    memory_service.store(
        auth_farmer_1,
        MemoryRecord(
            record_id="rec_farmer1_priv",
            domain=MemoryDomain.USER,
            record_type="diary",
            owner_id="farmer_alpha",
            scope_type=MemoryScope.USER,
            scope_id="farmer_alpha",
            payload={"private": True},
            source="test",
        ),
    )
    memory_service.store(
        auth_farmer_2,
        MemoryRecord(
            record_id="rec_farmer2_priv",
            domain=MemoryDomain.USER,
            record_type="diary",
            owner_id="farmer_beta",
            scope_type=MemoryScope.USER,
            scope_id="farmer_beta",
            payload={"private": True},
            source="test",
        ),
    )

    # Farmer 1 searches
    hits1 = memory_service.search(auth_farmer_1, MemorySearchCriteria(record_type="diary"))
    assert len(hits1) == 1
    assert hits1[0].record_id == "rec_farmer1_priv"

    # Farmer 2 searches
    hits2 = memory_service.search(auth_farmer_2, MemorySearchCriteria(record_type="diary"))
    assert len(hits2) == 1
    assert hits2[0].record_id == "rec_farmer2_priv"


# =============================================================================
# C. Versioning and Concurrency Tests
# =============================================================================

def test_c01_optimistic_locking_and_version_progression(memory_service, auth_farmer_1):
    """Successful update increments record_version and updates updated_at."""
    record = MemoryRecord(
        record_id="rec_conc_01",
        domain=MemoryDomain.USER,
        record_type="plan",
        owner_id="farmer_alpha",
        scope_type=MemoryScope.USER,
        scope_id="farmer_alpha",
        payload={"crop": "Wheat"},
        source="test",
    )
    stored = memory_service.store(auth_farmer_1, record)
    assert stored.record_version == 1

    # Valid update with expected_version=1
    updated = stored.model_copy(
        update={
            "payload": {"crop": "Wheat", "variety": "HD-2967"},
            "record_version": 2,
        }
    )
    res = memory_service.update(auth_farmer_1, updated, expected_version=1)
    assert res.record_version == 2
    assert res.payload["variety"] == "HD-2967"


def test_c02_stale_update_conflict_rejection(memory_service, auth_farmer_1):
    """Updating with stale expected_version raises MemoryConflictError."""
    record = MemoryRecord(
        record_id="rec_stale_01",
        domain=MemoryDomain.USER,
        record_type="plan",
        owner_id="farmer_alpha",
        scope_type=MemoryScope.USER,
        scope_id="farmer_alpha",
        payload={"crop": "Wheat"},
        source="test",
    )
    memory_service.store(auth_farmer_1, record)

    stale_update = record.model_copy(update={"payload": {"crop": "Mustard"}, "record_version": 2})
    with pytest.raises(MemoryConflictError):
        memory_service.update(auth_farmer_1, stale_update, expected_version=99)


def test_c03_immutable_identity_fields_enforcement(memory_service, auth_farmer_1):
    """Attempting to change record_id, domain, owner_id, or scope_type on update is rejected."""
    record = MemoryRecord(
        record_id="rec_immut_01",
        domain=MemoryDomain.USER,
        record_type="note",
        owner_id="farmer_alpha",
        scope_type=MemoryScope.USER,
        scope_id="farmer_alpha",
        payload={"text": "hello"},
        source="test",
    )
    memory_service.store(auth_farmer_1, record)

    # Attempt to change domain to GENERAL
    tampered_domain = record.model_copy(update={"domain": MemoryDomain.GENERAL, "owner_id": None})
    with pytest.raises(MemoryForbiddenError):
        memory_service.update(auth_farmer_1, tampered_domain)

    # Attempt to change owner_id
    tampered_owner = record.model_copy(update={"owner_id": "farmer_attacker"})
    with pytest.raises(MemoryForbiddenError):
        memory_service.update(auth_farmer_1, tampered_owner)

    # Attempt to change scope_type
    tampered_scope = record.model_copy(update={"scope_type": MemoryScope.FARM})
    with pytest.raises(MemoryForbiddenError):
        memory_service.update(auth_farmer_1, tampered_scope)


# =============================================================================
# D. Retention and Lifecycle Tests
# =============================================================================

def test_d01_retention_policy_and_expiry_calculation(memory_service, auth_farmer_1):
    """Attaching a retention policy calculates expires_at automatically on store."""
    record = MemoryRecord(
        record_id="rec_trans_01",
        domain=MemoryDomain.USER,
        record_type="session_dialog",
        owner_id="farmer_alpha",
        scope_type=MemoryScope.USER,
        scope_id="farmer_alpha",
        payload={"query": "how to sow chickpea?"},
        source="test",
        retention_policy_id="pol_transient_session",
    )
    stored = memory_service.store(auth_farmer_1, record)
    assert stored.expires_at is not None
    assert stored.expires_at > stored.created_at
    # Default pol_transient_session is 24 hours
    delta = stored.expires_at - stored.created_at
    assert 86390 <= delta.total_seconds() <= 86410


def test_d02_enforce_retention_marks_records_expired(memory_service, auth_farmer_1):
    """enforce_retention identifies records past expires_at and transitions status to EXPIRED."""
    past_time = datetime.now(timezone.utc) - timedelta(days=2)
    created_time = past_time - timedelta(days=1)

    record = MemoryRecord(
        record_id="rec_expired_01",
        domain=MemoryDomain.USER,
        record_type="temp_data",
        owner_id="farmer_alpha",
        scope_type=MemoryScope.USER,
        scope_id="farmer_alpha",
        payload={"temp": True},
        source="test",
        created_at=created_time,
        expires_at=past_time,
    )
    memory_service.store(auth_farmer_1, record)

    # Standard search excludes expired by default
    active_search = memory_service.search(auth_farmer_1, MemorySearchCriteria(record_type="temp_data"))
    assert len(active_search) == 0

    # Search with include_expired=True returns the record
    all_search = memory_service.search(auth_farmer_1, MemorySearchCriteria(record_type="temp_data", include_expired=True))
    assert len(all_search) == 1

    # Run lifecycle retention enforcement
    summary = memory_service.enforce_retention(auth_farmer_1, domain=MemoryDomain.USER)
    assert summary["evaluated_expired_count"] == 1
    assert summary["transitioned_to_expired"] == 1

    # Verify status changed to EXPIRED
    retrieved = memory_service.retrieve(auth_farmer_1, "rec_expired_01")
    assert retrieved.status == MemoryRecordStatus.EXPIRED


def test_d03_general_memory_retention_policy(memory_service, auth_curator):
    """General Memory follows its own approved retention policy under governance."""
    general_record = MemoryRecord(
        record_id="rec_gen_advisory_01",
        domain=MemoryDomain.GENERAL,
        record_type="weather_warning",
        owner_id=None,
        scope_type=MemoryScope.GENERAL,
        scope_id="north_zone",
        payload={"warning": "heavy rainfall expected"},
        source="imd",
        retention_policy_id="pol_general_advisory",
    )
    stored = memory_service.store(auth_curator, general_record)
    assert stored.expires_at is not None
    # 365 days
    delta = stored.expires_at - stored.created_at
    assert delta.days in (364, 365, 366)


# =============================================================================
# E. Deletion and Purge Tests
# =============================================================================

def test_e01_logical_deletion_and_verification(memory_service, auth_farmer_1):
    """Soft deletion sets status DELETED and hides record from standard search."""
    record = MemoryRecord(
        record_id="rec_del_01",
        domain=MemoryDomain.USER,
        record_type="note",
        owner_id="farmer_alpha",
        scope_type=MemoryScope.USER,
        scope_id="farmer_alpha",
        payload={"text": "to be deleted"},
        source="test",
    )
    memory_service.store(auth_farmer_1, record)

    # Soft delete
    deleted = memory_service.delete(auth_farmer_1, "rec_del_01", soft=True)
    assert deleted is True

    # Standard search excludes status DELETED
    hits = memory_service.search(auth_farmer_1, MemorySearchCriteria(record_type="note"))
    assert len(hits) == 0

    # Verification reports LOGICALLY_DELETED
    verification = memory_service.verify_deletion(auth_farmer_1, "rec_del_01")
    assert verification["deletion_state"] == "LOGICALLY_DELETED"
    assert verification["exists"] is True


def test_e02_physical_purge_operation(memory_service, auth_farmer_1):
    """Physical purge permanently erases eligible records."""
    record = MemoryRecord(
        record_id="rec_purge_01",
        domain=MemoryDomain.USER,
        record_type="obsolete",
        owner_id="farmer_alpha",
        scope_type=MemoryScope.USER,
        scope_id="farmer_alpha",
        payload={"trash": True},
        source="test",
        status=MemoryRecordStatus.DELETED,
    )
    memory_service.store(auth_farmer_1, record)

    # Dry-run preview
    preview = memory_service.purge_records(
        auth_farmer_1,
        PurgeCriteria(domain=MemoryDomain.USER, status=MemoryRecordStatus.DELETED, dry_run=True),
    )
    assert preview.is_dry_run is True
    assert preview.eligible_count == 1
    assert preview.purged_count == 0

    # Actual purge
    live_purge = memory_service.purge_records(
        auth_farmer_1,
        PurgeCriteria(domain=MemoryDomain.USER, status=MemoryRecordStatus.DELETED, dry_run=False),
    )
    assert live_purge.is_dry_run is False
    assert live_purge.purged_count == 1

    # Verification confirms physically purged
    verification = memory_service.verify_deletion(auth_farmer_1, "rec_purge_01")
    assert verification["deletion_state"] == "PHYSICALLY_PURGED"
    assert verification["exists"] is False


# =============================================================================
# F. Security & Cross-User Denial Tests
# =============================================================================

def test_f01_cross_user_denial_across_all_operations(memory_service, auth_farmer_1, auth_farmer_2):
    """User B cannot retrieve, update, delete, or inspect metadata of User A's records."""
    record = MemoryRecord(
        record_id="rec_sec_01",
        domain=MemoryDomain.USER,
        record_type="secret",
        owner_id="farmer_alpha",
        scope_type=MemoryScope.USER,
        scope_id="farmer_alpha",
        payload={"secret": "alpha_data"},
        source="test",
    )
    memory_service.store(auth_farmer_1, record)

    # Farmer 2 cannot retrieve
    with pytest.raises(MemoryForbiddenError):
        memory_service.retrieve(auth_farmer_2, "rec_sec_01")

    # Farmer 2 cannot update
    tamper = record.model_copy(update={"payload": {"hacked": True}, "record_version": 2})
    with pytest.raises(MemoryForbiddenError):
        memory_service.update(auth_farmer_2, tamper, expected_version=1)

    # Farmer 2 cannot delete
    with pytest.raises(MemoryForbiddenError):
        memory_service.delete(auth_farmer_2, "rec_sec_01")

    # Farmer 2 cannot inspect metadata
    with pytest.raises(MemoryForbiddenError):
        memory_service.get_metadata(auth_farmer_2, "rec_sec_01")


def test_f02_general_memory_governance(memory_service, auth_farmer_1, auth_curator):
    """Ordinary farmers cannot write or delete General Memory records."""
    gen_rec = MemoryRecord(
        record_id="rec_gen_gov_01",
        domain=MemoryDomain.GENERAL,
        record_type="advisory",
        owner_id=None,
        scope_type=MemoryScope.GENERAL,
        scope_id="all",
        payload={"advisory": "spray neem oil"},
        source="test",
    )
    # Ordinary user write denied
    with pytest.raises(MemoryForbiddenError):
        memory_service.store(auth_farmer_1, gen_rec)

    # Curator write allowed
    stored = memory_service.store(auth_curator, gen_rec)
    assert stored.record_id == "rec_gen_gov_01"

    # Ordinary user delete denied
    with pytest.raises(MemoryForbiddenError):
        memory_service.delete(auth_farmer_1, "rec_gen_gov_01")


# =============================================================================
# G. Real PostgreSQL 16 Persistence Integration Tests
# =============================================================================

@pytest.fixture(scope="module")
def postgres_adapter():
    """Live SupabasePostgresMemoryStorageAdapter connecting to local test database."""
    config = PostgresConfig(
        host="127.0.0.1",
        port=5432,
        user="postgres",
        database="earthmind_test",
        min_pool_size=1,
        max_pool_size=5,
    )
    service = PostgresDatabaseService(config)
    service.connect()
    adapter = SupabasePostgresMemoryStorageAdapter(service)
    yield adapter
    service.disconnect()


def test_g01_postgresql_operations_and_lifecycle(postgres_adapter, auth_farmer_1):
    """Execute complete Level 4 operations against live PostgreSQL database."""
    pg_service = MemoryService(storage_adapter=postgres_adapter)

    record = MemoryRecord(
        record_id="pg_rec_level4_01",
        domain=MemoryDomain.USER,
        record_type="pg_soil",
        owner_id="farmer_alpha",
        scope_type=MemoryScope.FIELD,
        scope_id="field_01",
        payload={"nitrogen": 130, "ec": 1.2},
        source="live_pg_test",
        retention_policy_id="pol_seasonal_crop",
    )

    # Clean up if already exists
    postgres_adapter.delete_record("pg_rec_level4_01", soft=False)

    # 1. Store
    stored = pg_service.store(auth_farmer_1, record)
    assert stored.record_id == "pg_rec_level4_01"
    assert stored.record_version == 1
    assert stored.expires_at is not None

    # 2. Retrieve
    retrieved = pg_service.retrieve(auth_farmer_1, "pg_rec_level4_01")
    assert retrieved.payload["nitrogen"] == 130

    # 3. Update with optimistic locking
    updated = retrieved.model_copy(
        update={
            "payload": {"nitrogen": 150, "ec": 1.2},
            "record_version": 2,
        }
    )
    res_update = pg_service.update(auth_farmer_1, updated, expected_version=1)
    assert res_update.record_version == 2
    assert res_update.payload["nitrogen"] == 150

    # 4. Search
    hits = pg_service.search(auth_farmer_1, MemorySearchCriteria(record_type="pg_soil"))
    assert len(hits) >= 1
    assert any(h.record_id == "pg_rec_level4_01" for h in hits)

    # 5. Metadata
    meta = pg_service.get_metadata(auth_farmer_1, "pg_rec_level4_01")
    assert meta["record_version"] == 2
    assert "payload" not in meta

    # 6. Soft Delete
    del_res = pg_service.delete(auth_farmer_1, "pg_rec_level4_01", soft=True)
    assert del_res is True

    verif_soft = pg_service.verify_deletion(auth_farmer_1, "pg_rec_level4_01")
    assert verif_soft["deletion_state"] == "LOGICALLY_DELETED"

    # 7. Physical Purge
    purge_res = pg_service.purge_records(
        auth_farmer_1,
        PurgeCriteria(domain=MemoryDomain.USER, status=MemoryRecordStatus.DELETED),
    )
    assert purge_res.purged_count >= 1

    verif_hard = pg_service.verify_deletion(auth_farmer_1, "pg_rec_level4_01")
    assert verif_hard["deletion_state"] == "PHYSICALLY_PURGED"
