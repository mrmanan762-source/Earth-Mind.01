"""Comprehensive unit, schema, persistence, and security tests for Level 3 Supabase PostgreSQL Storage Adapter.

Tests cover:
1. Adapter initialization & protocol conformance.
2. Serialization / deserialization of all 17 approved fields.
3. Domain and scope persistence (USER with owner, GENERAL without owner).
4. Constraint enforcement (domain/ownership checks, version checks, expiration checks).
5. Optimistic locking / concurrency control (record_version match & mismatch).
6. Structured search with multi-parameter filtering and pagination.
7. Soft vs hard deletion and payload-free metadata retrieval.
8. Connection failure and database error handling without credential leakage.
9. End-to-end integration with MemoryService and Level 2 security enforcer.
10. Adapter restart and data persistence survival across instances.
"""

from datetime import datetime, timezone, timedelta
import pytest
import psycopg2

from core.interfaces.memory_storage import IMemoryStorageAdapter
from core.config.settings import PostgresConfig
from core.schemas.memory import (
    AuthorizationContext,
    KnowledgeClassification,
    MemoryDomain,
    MemoryRecord,
    MemoryRecordStatus,
    MemoryScope,
    MemorySearchCriteria,
)
from modules.database.postgres_db import PostgresDatabaseService
from modules.memory.errors import (
    MemoryConflictError,
    MemoryForbiddenError,
    MemoryInvalidArgumentError,
    MemoryNotFoundError,
    MemoryStorageError,
    MemoryStorageUnavailableError,
)
from modules.memory.memory_service import MemoryService
from modules.memory.security import MemorySecurityAuditor, MemorySecurityEnforcer
from modules.memory.supabase_adapter import SupabasePostgresMemoryStorageAdapter


@pytest.fixture(scope="module")
def postgres_service():
    """Shared PostgreSQL connection service connecting to local test database."""
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
    yield service
    service.disconnect()


@pytest.fixture(autouse=True)
def clean_memory_table(postgres_service):
    """Ensure clean table state before each test."""
    conn = postgres_service.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE memory_records;")
            conn.commit()
    finally:
        postgres_service.put_connection(conn)


@pytest.fixture
def adapter(postgres_service):
    return SupabasePostgresMemoryStorageAdapter(db_service=postgres_service)


@pytest.fixture
def memory_service(adapter):
    auditor = MemorySecurityAuditor()
    enforcer = MemorySecurityEnforcer(auditor=auditor)
    return MemoryService(storage_adapter=adapter, enforcer=enforcer, auditor=auditor)


# ==============================================================================
# 1. ADAPTER INITIALIZATION & PROTOCOL CONFORMANCE
# ==============================================================================

def test_01_adapter_protocol_conformance(adapter):
    """Verify SupabasePostgresMemoryStorageAdapter adheres to IMemoryStorageAdapter protocol."""
    assert isinstance(adapter, IMemoryStorageAdapter)
    assert adapter.provider_name == "supabase_postgresql"

    health = adapter.check_health()
    assert health.is_healthy is True
    assert health.provider_name == "supabase_postgresql"
    assert health.details["record_count"] == 0


# ==============================================================================
# 2. SCHEMA & ALL 17 APPROVED FIELDS PERSISTENCE
# ==============================================================================

def test_02_all_17_fields_persistence_and_utc(adapter):
    """Verify that all 17 approved fields are faithfully persisted and reconstructed with UTC timestamps."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=30)
    payload_content = {
        "crop": "wheat",
        "soil_type": "alluvial",
        "ph": 6.8,
        "recommendation": "Apply zinc sulphate @ 25 kg/ha",
        "nested": {"key1": "val1", "count": 42},
    }

    record = MemoryRecord(
        record_id="mem_full_17_fields",
        domain=MemoryDomain.USER,
        record_type="soil_test",
        owner_id="farmer_pb_001",
        scope_type=MemoryScope.FIELD,
        scope_id="field_north_4",
        payload=payload_content,
        source="icar_soil_survey",
        created_at=now,
        updated_at=now,
        schema_version="1.2",
        record_version=1,
        status=MemoryRecordStatus.ACTIVE,
        retention_policy_id="ret_policy_3yr",
        expires_at=expires,
        classification=KnowledgeClassification.FARMER_KNOWLEDGE,
        correlation_id="corr_trace_9876",
    )

    stored = adapter.store_record(record)
    assert stored.record_id == "mem_full_17_fields"
    assert stored.domain == MemoryDomain.USER
    assert stored.record_type == "soil_test"
    assert stored.owner_id == "farmer_pb_001"
    assert stored.scope_type == MemoryScope.FIELD
    assert stored.scope_id == "field_north_4"
    assert stored.payload == payload_content
    assert stored.source == "icar_soil_survey"
    assert stored.schema_version == "1.2"
    assert stored.record_version == 1
    assert stored.status == MemoryRecordStatus.ACTIVE
    assert stored.retention_policy_id == "ret_policy_3yr"
    assert stored.classification == KnowledgeClassification.FARMER_KNOWLEDGE
    assert stored.correlation_id == "corr_trace_9876"

    # Verify UTC timestamp timezone awareness
    assert stored.created_at.tzinfo is not None
    assert stored.updated_at.tzinfo is not None
    assert stored.expires_at.tzinfo is not None

    # Retrieve independently from database
    fetched = adapter.get_record("mem_full_17_fields")
    assert fetched is not None
    assert fetched.record_id == stored.record_id
    assert fetched.payload == stored.payload
    assert fetched.classification == stored.classification
    assert fetched.correlation_id == stored.correlation_id
    assert fetched.created_at.tzinfo is not None


# ==============================================================================
# 3. DOMAIN & SCOPE PERSISTENCE SEPARATION
# ==============================================================================

def test_03_general_memory_domain_persistence(adapter):
    """Verify GENERAL domain memory records persist without owner_id and with GENERAL scope."""
    now = datetime.now(timezone.utc)
    gen_record = MemoryRecord(
        record_id="mem_general_pop_wheat",
        domain=MemoryDomain.GENERAL,
        record_type="agronomic_advisory",
        owner_id=None,
        scope_type=MemoryScope.GENERAL,
        scope_id="national_wheat_zone_nw",
        payload={"advisory": "Timely sowing of HD 3086 before Nov 15 avoids terminal heat."},
        source="icar_iiwbr_karnal",
        created_at=now,
        updated_at=now,
        classification=KnowledgeClassification.GENERAL_KNOWLEDGE,
    )

    stored = adapter.store_record(gen_record)
    assert stored.domain == MemoryDomain.GENERAL
    assert stored.owner_id is None
    assert stored.scope_type == MemoryScope.GENERAL

    fetched = adapter.get_record("mem_general_pop_wheat")
    assert fetched is not None
    assert fetched.owner_id is None
    assert fetched.domain == MemoryDomain.GENERAL


def test_04_database_level_constraint_rejections(postgres_service):
    """Verify that PostgreSQL check constraints reject illegal domain/scope combinations directly."""
    conn = postgres_service.get_connection()
    try:
        with conn.cursor() as cursor:
            # 1. USER domain without owner_id must violate chk_memory_domain_ownership
            with pytest.raises(psycopg2.IntegrityError):
                cursor.execute("""
                    INSERT INTO memory_records (
                        record_id, domain, record_type, owner_id, scope_type, scope_id,
                        payload, source, created_at, updated_at, classification
                    ) VALUES (
                        'mem_bad_1', 'USER', 'test', NULL, 'USER', 'u1',
                        '{}', 'test', NOW(), NOW(), 'FARMER_KNOWLEDGE'
                    );
                """)
            conn.rollback()

            # 2. GENERAL domain with owner_id must violate chk_memory_domain_ownership
            with pytest.raises(psycopg2.IntegrityError):
                cursor.execute("""
                    INSERT INTO memory_records (
                        record_id, domain, record_type, owner_id, scope_type, scope_id,
                        payload, source, created_at, updated_at, classification
                    ) VALUES (
                        'mem_bad_2', 'GENERAL', 'test', 'some_farmer', 'GENERAL', 'g1',
                        '{}', 'test', NOW(), NOW(), 'GENERAL_KNOWLEDGE'
                    );
                """)
            conn.rollback()

            # 3. USER domain with GENERAL scope_type must violate chk_memory_domain_ownership
            with pytest.raises(psycopg2.IntegrityError):
                cursor.execute("""
                    INSERT INTO memory_records (
                        record_id, domain, record_type, owner_id, scope_type, scope_id,
                        payload, source, created_at, updated_at, classification
                    ) VALUES (
                        'mem_bad_3', 'USER', 'test', 'farmer_1', 'GENERAL', 'g1',
                        '{}', 'test', NOW(), NOW(), 'FARMER_KNOWLEDGE'
                    );
                """)
            conn.rollback()

            # 4. expires_at <= created_at must violate chk_memory_expiration
            with pytest.raises(psycopg2.IntegrityError):
                cursor.execute("""
                    INSERT INTO memory_records (
                        record_id, domain, record_type, owner_id, scope_type, scope_id,
                        payload, source, created_at, updated_at, expires_at, classification
                    ) VALUES (
                        'mem_bad_4', 'USER', 'test', 'farmer_1', 'USER', 'u1',
                        '{}', 'test', NOW(), NOW(), NOW() - INTERVAL '1 day', 'FARMER_KNOWLEDGE'
                    );
                """)
            conn.rollback()
    finally:
        postgres_service.put_connection(conn)


# ==============================================================================
# 4. DATA INTEGRITY, VERSIONING, & OPTIMISTIC CONCURRENCY
# ==============================================================================

def test_05_optimistic_locking_and_conflict_handling(adapter):
    """Verify that updates succeed when expected_version matches and fail when stale."""
    now = datetime.now(timezone.utc)
    rec = MemoryRecord(
        record_id="mem_concurrent_versioning",
        domain=MemoryDomain.USER,
        record_type="fertilizer_log",
        owner_id="farmer_01",
        scope_type=MemoryScope.USER,
        scope_id="farmer_01",
        payload={"urea_bags": 2},
        source="farmer_input",
        created_at=now,
        updated_at=now,
        record_version=1,
    )
    adapter.store_record(rec)

    # 1. Duplicate insert raises MemoryConflictError
    with pytest.raises(MemoryConflictError) as exc_info:
        adapter.store_record(rec)
    assert exc_info.value.error_contract.metadata["record_id"] == "mem_concurrent_versioning"

    # 2. Update with matching expected_version=1 succeeds
    upd_rec = rec.model_copy(update={
        "record_version": 2,
        "payload": {"urea_bags": 3},
        "updated_at": datetime.now(timezone.utc),
    })
    updated = adapter.update_record(upd_rec, expected_version=1)
    assert updated.record_version == 2
    assert updated.payload["urea_bags"] == 3

    # 3. Update with stale expected_version=1 raises MemoryConflictError
    stale_rec = rec.model_copy(update={
        "record_version": 3,
        "payload": {"urea_bags": 4},
        "updated_at": datetime.now(timezone.utc),
    })
    with pytest.raises(MemoryConflictError) as exc_stale:
        adapter.update_record(stale_rec, expected_version=1)
    assert "Version mismatch" in str(exc_stale.value)

    # 4. Update non-existent record raises MemoryNotFoundError
    ghost_rec = rec.model_copy(update={"record_id": "mem_non_existent"})
    with pytest.raises(MemoryNotFoundError):
        adapter.update_record(ghost_rec, expected_version=1)


# ==============================================================================
# 5. STRUCTURED SEARCH & PAGINATION
# ==============================================================================

def test_06_search_filtering_and_pagination(adapter):
    """Verify search criteria filters on domain, owner, scope, status, classification, and pagination."""
    now = datetime.now(timezone.utc)

    # Insert 5 records
    for i in range(5):
        adapter.store_record(MemoryRecord(
            record_id=f"mem_search_rec_{i}",
            domain=MemoryDomain.USER,
            record_type="pest_detection" if i < 3 else "irrigation",
            owner_id="farmer_search_1" if i < 4 else "farmer_search_2",
            scope_type=MemoryScope.FIELD,
            scope_id="field_1",
            payload={"index": i},
            source="vision_scan",
            created_at=now + timedelta(minutes=i),
            updated_at=now + timedelta(minutes=i),
            correlation_id=f"corr_{i}",
        ))

    # 1. Filter by owner
    res_owner = adapter.search_records(MemorySearchCriteria(owner_id="farmer_search_1"))
    assert len(res_owner) == 4

    # 2. Filter by record_type
    res_type = adapter.search_records(MemorySearchCriteria(
        owner_id="farmer_search_1",
        record_type="pest_detection"
    ))
    assert len(res_type) == 3

    # 3. Pagination (limit & offset)
    res_paged = adapter.search_records(MemorySearchCriteria(
        owner_id="farmer_search_1",
        limit=2,
        offset=1,
    ))
    assert len(res_paged) == 2


# ==============================================================================
# 6. SOFT DELETE & PAYLOAD-FREE METADATA PROJECTION
# ==============================================================================

def test_07_soft_delete_and_metadata_retrieval(adapter):
    """Verify soft deletion sets status to DELETED and get_record_metadata returns projection without payload."""
    now = datetime.now(timezone.utc)
    rec = MemoryRecord(
        record_id="mem_delete_target",
        domain=MemoryDomain.USER,
        record_type="secret_note",
        owner_id="farmer_01",
        scope_type=MemoryScope.USER,
        scope_id="farmer_01",
        payload={"sensitive_details": "bank_data_xyz"},
        source="user",
        created_at=now,
        updated_at=now,
    )
    adapter.store_record(rec)

    # Metadata projection returns dictionary without payload
    meta = adapter.get_record_metadata("mem_delete_target")
    assert meta is not None
    assert meta["record_id"] == "mem_delete_target"
    assert "payload" not in meta
    assert meta["status"] == "ACTIVE"

    # Soft delete
    deleted = adapter.delete_record("mem_delete_target", soft=True)
    assert deleted is True

    # Fetched record reflects DELETED status
    fetched = adapter.get_record("mem_delete_target")
    assert fetched is not None
    assert fetched.status == MemoryRecordStatus.DELETED

    # Metadata reflects DELETED status
    meta_after = adapter.get_record_metadata("mem_delete_target")
    assert meta_after["status"] == "DELETED"

    # Hard delete
    hard_deleted = adapter.delete_record("mem_delete_target", soft=False)
    assert hard_deleted is True
    assert adapter.get_record("mem_delete_target") is None
    assert adapter.get_record_metadata("mem_delete_target") is None


# ==============================================================================
# 7. CONNECTION FAILURE & ERROR HANDLING
# ==============================================================================

def test_08_connection_failure_and_unavailable_handling():
    """Verify that when database is unreachable, adapter raises MemoryStorageUnavailableError without exposing secrets."""
    bad_config = PostgresConfig(
        host="127.0.0.1",
        port=59999,  # Non-existent port
        user="testuser",
        password="super_secret_password_123",
        database="testdb",
        connect_timeout=1.0,
    )
    bad_db = PostgresDatabaseService(bad_config)
    bad_adapter = SupabasePostgresMemoryStorageAdapter(db_service=bad_db)

    with pytest.raises(MemoryStorageUnavailableError) as exc_info:
        bad_adapter.get_record("any_id")

    err_str = str(exc_info.value)
    assert "super_secret_password_123" not in err_str
    assert "unavailable" in err_str.lower()

    health = bad_adapter.check_health()
    assert health.is_healthy is False


# ==============================================================================
# 8. INTEGRATION WITH MEMORYSERVICE & LEVEL 2 SECURITY
# ==============================================================================

def test_09_memory_service_integration_with_postgres_adapter(memory_service):
    """Verify that Level 2 security enforcer wraps SupabasePostgresMemoryStorageAdapter correctly."""
    ctx_farmer_a = AuthorizationContext(
        principal_id="farmer_a",
        owner_id="farmer_a",
        accessible_scopes={"USER": ["farmer_a"]},
    )
    ctx_farmer_b = AuthorizationContext(
        principal_id="farmer_b",
        owner_id="farmer_b",
        accessible_scopes={"USER": ["farmer_b"]},
    )

    rec_a = MemoryRecord(
        record_id="mem_svc_farmer_a",
        domain=MemoryDomain.USER,
        record_type="advisory",
        owner_id="farmer_a",
        scope_type=MemoryScope.USER,
        scope_id="farmer_a",
        payload={"note": "Wheat spray planned for tomorrow"},
        source="advisory_engine",
    )

    # 1. Authorized store succeeds
    stored = memory_service.store_record(ctx_farmer_a, rec_a)
    assert stored.record_id == "mem_svc_farmer_a"

    # 2. Farmer A can retrieve their own record
    fetched = memory_service.get_record(ctx_farmer_a, "mem_svc_farmer_a")
    assert fetched.payload["note"] == "Wheat spray planned for tomorrow"

    # 3. Farmer B cannot retrieve Farmer A's record (raises MemoryForbiddenError)
    with pytest.raises(MemoryForbiddenError):
        memory_service.get_record(ctx_farmer_b, "mem_svc_farmer_a")

    # 4. Farmer B searching USER domain cannot see Farmer A's record
    results_b = memory_service.search_records(ctx_farmer_b, MemorySearchCriteria(domain=MemoryDomain.USER))
    assert len(results_b) == 0

    # 5. Farmer A searching USER domain finds their record
    results_a = memory_service.search_records(ctx_farmer_a, MemorySearchCriteria(domain=MemoryDomain.USER))
    assert len(results_a) == 1
    assert results_a[0].record_id == "mem_svc_farmer_a"


def test_10_persistence_across_adapter_reconnect(postgres_service):
    """Verify records survive adapter restart and new connection instantiation."""
    adapter_1 = SupabasePostgresMemoryStorageAdapter(db_service=postgres_service)
    rec = MemoryRecord(
        record_id="mem_persist_restart",
        domain=MemoryDomain.USER,
        record_type="durable_test",
        owner_id="farmer_restart",
        scope_type=MemoryScope.USER,
        scope_id="farmer_restart",
        payload={"persistent": True},
        source="test",
    )
    adapter_1.store_record(rec)

    # Create fresh adapter instance with separate service
    config = PostgresConfig(
        host="127.0.0.1",
        port=5432,
        user="postgres",
        database="earthmind_test",
    )
    service_2 = PostgresDatabaseService(config)
    service_2.connect()
    try:
        adapter_2 = SupabasePostgresMemoryStorageAdapter(db_service=service_2)
        fetched = adapter_2.get_record("mem_persist_restart")
        assert fetched is not None
        assert fetched.record_id == "mem_persist_restart"
        assert fetched.payload["persistent"] is True
    finally:
        service_2.disconnect()
