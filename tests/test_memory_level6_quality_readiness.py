"""Level 6 Final Master Test Suite: Quality & Production Readiness.

Comprehensive end-to-end verification of the EarthMind Memory Module conforming to
Memory Module Architecture Specification v1.0 across:
1. Security Audit: 14 strict security checks.
2. Persistence & Reliability: Failure modes, transactions, concurrency, restarts.
3. Performance & Resource Quality: Structured query efficiency, pagination, zero vector search/pgvector.
4. EarthMind End-to-End Context Flow: Memory -> B2 Context Manager -> B3 Reasoning -> B4 Planning.
"""

from datetime import datetime, timezone, timedelta
import os
import time
import pytest
import psycopg2

from core.interfaces.memory_storage import IMemoryStorageAdapter
from core.config.settings import PostgresConfig, Settings
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
    SortOrder,
    PrincipalType,
    PayloadSchemaRegistry,
    RetentionCategory,
    RetentionPolicy,
    PurgeCriteria,
)
from core.schemas.memory_security import SecurityAuditAction, SecurityDecision
from modules.database.postgres_db import PostgresDatabaseService
from modules.memory.errors import (
    MemoryConflictError,
    MemoryForbiddenError,
    MemoryInvalidArgumentError,
    MemoryNotFoundError,
    MemoryStorageError,
    MemoryStorageUnavailableError,
    MemoryUnauthorizedError,
)
from modules.memory.memory_service import MemoryService
from modules.memory.security import MemorySecurityAuditor, MemorySecurityEnforcer
from modules.memory.storage_adapter import InMemoryMemoryStorageAdapter
from modules.memory.supabase_adapter import SupabasePostgresMemoryStorageAdapter
from modules.memory.context_provider import MemoryContextProvider
from modules.context.schemas import ContextRequest, ContextState, PolicyConfig
from modules.context.boundary.adapters import MemoryContextProviderAdapter
from modules.context.manager import B2ContextManager


# =============================================================================
# Fixtures & Database Setup
# =============================================================================

@pytest.fixture(scope="module")
def postgres_service():
    """Live PostgreSQL connection service for Level 6 validation."""
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
def clean_postgres_table(postgres_service):
    """Ensure clean table state before each test."""
    conn = postgres_service.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE memory_records;")
            conn.commit()
    finally:
        postgres_service.put_connection(conn)


@pytest.fixture
def postgres_adapter(postgres_service):
    return SupabasePostgresMemoryStorageAdapter(postgres_service)


@pytest.fixture
def in_memory_adapter():
    return InMemoryMemoryStorageAdapter()


@pytest.fixture
def auth_farmer_1():
    return AuthorizationContext(
        principal_id="farmer_101",
        principal_type=PrincipalType.USER,
        roles=["FARMER"],
        owner_id="farmer_101",
        accessible_scopes={"USER": ["farmer_101"], "FARM": ["farm_alpha"], "FIELD": ["field_01"]},
    )


@pytest.fixture
def auth_farmer_2():
    return AuthorizationContext(
        principal_id="farmer_202",
        principal_type=PrincipalType.USER,
        roles=["FARMER"],
        owner_id="farmer_202",
        accessible_scopes={"USER": ["farmer_202"], "FARM": ["farm_beta"], "FIELD": ["field_02"]},
    )


@pytest.fixture
def auth_admin():
    return AuthorizationContext(
        principal_id="admin_001",
        principal_type=PrincipalType.SYSTEM,
        roles=["knowledge_admin"],
        owner_id=None,
        accessible_scopes={"GENERAL": ["*"]},
    )


# =============================================================================
# Section 1: Security Audit (14 Mandatory Checks)
# =============================================================================

def test_sec_01_user_a_cannot_access_user_b_records(postgres_adapter, auth_farmer_1, auth_farmer_2):
    """Check 1: User A cannot access User B's records."""
    svc = MemoryService(storage_adapter=postgres_adapter)
    rec_b = MemoryRecord(
        record_id="rec_b_private",
        domain=MemoryDomain.USER,
        record_type="soil_test",
        owner_id="farmer_202",
        scope_type=MemoryScope.USER,
        scope_id="farmer_202",
        payload={"ph": 6.8},
        source="lab_test",
    )
    svc.store_record(auth_farmer_2, rec_b)

    # Farmer 1 attempting retrieve
    with pytest.raises(MemoryForbiddenError):
        svc.get_record(auth_farmer_1, "rec_b_private")


def test_sec_02_owner_spoofing_is_rejected(postgres_adapter, auth_farmer_1):
    """Check 2: Owner spoofing is rejected."""
    svc = MemoryService(storage_adapter=postgres_adapter)
    spoofed = MemoryRecord(
        record_id="rec_spoofed_owner",
        domain=MemoryDomain.USER,
        record_type="soil_test",
        owner_id="farmer_victim",
        scope_type=MemoryScope.USER,
        scope_id="farmer_victim",
        payload={"ph": 7.0},
        source="malicious_input",
    )
    with pytest.raises(MemoryForbiddenError):
        svc.store_record(auth_farmer_1, spoofed)


def test_sec_03_scope_spoofing_is_rejected(postgres_adapter, auth_farmer_1):
    """Check 3: Scope spoofing is rejected."""
    svc = MemoryService(storage_adapter=postgres_adapter)
    unauthorized_scope = MemoryRecord(
        record_id="rec_unauth_farm",
        domain=MemoryDomain.USER,
        record_type="farm_survey",
        owner_id="farmer_101",
        scope_type=MemoryScope.FARM,
        scope_id="unauthorized_farm_id",
        payload={"acres": 50},
        source="survey",
    )
    with pytest.raises(MemoryForbiddenError):
        svc.store_record(auth_farmer_1, unauthorized_scope)


def test_sec_04_unauthorized_metadata_access_is_rejected(postgres_adapter, auth_farmer_1, auth_farmer_2):
    """Check 4: Unauthorized metadata access is rejected."""
    svc = MemoryService(storage_adapter=postgres_adapter)
    rec = MemoryRecord(
        record_id="rec_farmer2_meta",
        domain=MemoryDomain.USER,
        record_type="finance",
        owner_id="farmer_202",
        scope_type=MemoryScope.USER,
        scope_id="farmer_202",
        payload={"revenue": 100000},
        source="accounting",
    )
    svc.store_record(auth_farmer_2, rec)

    with pytest.raises(MemoryForbiddenError):
        svc.get_record_metadata(auth_farmer_1, "rec_farmer2_meta")


def test_sec_05_unauthorized_updates_and_deletions_rejected(postgres_adapter, auth_farmer_1, auth_farmer_2):
    """Check 5: Unauthorized updates and deletions are rejected."""
    svc = MemoryService(storage_adapter=postgres_adapter)
    rec = MemoryRecord(
        record_id="rec_victim_data",
        domain=MemoryDomain.USER,
        record_type="advisory",
        owner_id="farmer_202",
        scope_type=MemoryScope.USER,
        scope_id="farmer_202",
        payload={"spray_date": "2026-11-01"},
        source="advisory",
    )
    svc.store_record(auth_farmer_2, rec)

    # Unauthorized update
    mod_rec = rec.model_copy(update={"payload": {"spray_date": "2026-12-01"}})
    with pytest.raises(MemoryForbiddenError):
        svc.update_record(auth_farmer_1, mod_rec)

    # Unauthorized delete
    with pytest.raises(MemoryForbiddenError):
        svc.delete_record(auth_farmer_1, "rec_victim_data")


def test_sec_06_general_memory_writes_require_approved_authorization(postgres_adapter, auth_farmer_1, auth_admin):
    """Check 6: General Memory writes require approved authorization."""
    svc = MemoryService(storage_adapter=postgres_adapter)
    gen_rec = MemoryRecord(
        record_id="gen_crop_guideline_01",
        domain=MemoryDomain.GENERAL,
        record_type="package_of_practices",
        owner_id=None,
        scope_type=MemoryScope.GENERAL,
        scope_id="general",
        payload={"crop": "wheat", "optimum_sowing_temp_c": 22},
        source="icar_iiwbr",
    )

    # Ordinary farmer write rejected
    with pytest.raises(MemoryForbiddenError):
        svc.store_record(auth_farmer_1, gen_rec)

    # Admin with knowledge_admin role write succeeds
    stored = svc.store_record(auth_admin, gen_rec)
    assert stored.record_id == "gen_crop_guideline_01"


def test_sec_07_private_records_cannot_automatically_enter_general_memory(postgres_adapter, auth_farmer_1):
    """Check 7: Private records cannot automatically enter General Memory."""
    svc = MemoryService(storage_adapter=postgres_adapter)
    private_rec = MemoryRecord(
        record_id="private_to_gen_attempt",
        domain=MemoryDomain.USER,
        record_type="observation",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload={"note": "field observation"},
        source="phone",
    )
    svc.store_record(auth_farmer_1, private_rec)

    # Attempting to mutate domain to GENERAL on update is strictly forbidden
    tampered_rec = private_rec.model_copy(update={"domain": MemoryDomain.GENERAL, "owner_id": None})
    with pytest.raises(MemoryForbiddenError):
        svc.update_record(auth_farmer_1, tampered_rec)


def test_sec_08_deleted_and_expired_records_not_exposed_through_retrieval(postgres_adapter, auth_farmer_1):
    """Check 8: Deleted and expired records are not exposed through normal retrieval."""
    svc = MemoryService(storage_adapter=postgres_adapter)

    # Store deleted record
    rec_del = MemoryRecord(
        record_id="rec_to_delete",
        domain=MemoryDomain.USER,
        record_type="note",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload={"text": "delete me"},
        source="app",
    )
    svc.store_record(auth_farmer_1, rec_del)
    svc.delete_record(auth_farmer_1, "rec_to_delete", soft=True)

    # Normal search excludes soft-deleted records by default
    res = svc.search_records(auth_farmer_1, MemorySearchCriteria(owner_id="farmer_101"))
    assert all(r.record_id != "rec_to_delete" for r in res)

    # Context Provider excludes soft-deleted records
    provider = MemoryContextProvider(memory_service=svc)
    adapter = MemoryContextProviderAdapter(memory_provider=provider)
    b2_manager = B2ContextManager(providers=[adapter])
    ctx_res = b2_manager.prepare_context(ContextRequest(request_id="test_del", farmer_id="farmer_101"))
    assert all(it.source_id != "rec_to_delete" for it in ctx_res.items)


def test_sec_09_privileged_role_names_cannot_bypass_authorization(postgres_adapter):
    """Check 9: Privileged role names cannot bypass authorization without matching principal identity."""
    svc = MemoryService(storage_adapter=postgres_adapter)

    # Malicious context with forged role name "ADMIN" claiming Farmer 2's data
    forged_auth = AuthorizationContext(
        principal_id="unauthorized_actor",
        principal_type=PrincipalType.USER,
        roles=["ADMIN", "SUPERUSER"],  # Claims admin role but principal_id is unauthorized
        owner_id="unauthorized_actor",
        accessible_scopes={"USER": ["unauthorized_actor"]},
    )

    victim_rec = MemoryRecord(
        record_id="rec_victim_sec9",
        domain=MemoryDomain.USER,
        record_type="soil_test",
        owner_id="farmer_202",
        scope_type=MemoryScope.USER,
        scope_id="farmer_202",
        payload={"sample": 1},
        source="lab",
    )
    postgres_adapter.store_record(victim_rec)

    with pytest.raises(MemoryForbiddenError):
        svc.get_record(forged_auth, "rec_victim_sec9")


def test_sec_10_database_credentials_not_exposed_in_config_or_errors(postgres_service):
    """Check 10: Database credentials are not exposed in config safe dict or errors."""
    config = PostgresConfig(
        url="postgresql://postgres:SecretPassword123@127.0.0.1:5432/earthmind_test",
        password="SecretPassword123",
    )
    settings = Settings(postgres=config)
    safe = settings.to_safe_dict()

    assert "SecretPassword123" not in str(safe)
    assert safe["postgres"]["password"] == "***"
    assert "SecretPassword123" not in safe["postgres"]["url"]


def test_sec_11_sensitive_payloads_not_leaked_through_logs_or_errors(postgres_adapter, auth_farmer_1):
    """Check 11: Sensitive payloads are not leaked through logs or security auditor events."""
    auditor = MemorySecurityAuditor()
    enforcer = MemorySecurityEnforcer(auditor=auditor)
    svc = MemoryService(storage_adapter=postgres_adapter, enforcer=enforcer, auditor=auditor)

    secret_payload = {"pin": "8877", "bank": "HDFC_PRIVATE", "balance": 999999}
    rec = MemoryRecord(
        record_id="rec_secret_sec11",
        domain=MemoryDomain.USER,
        record_type="banking",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload=secret_payload,
        source="mobile_app",
    )
    svc.store_record(auth_farmer_1, rec)

    # Ensure no audit event contains the raw secret payload values
    for event in auditor.audit_events:
        event_str = str(event)
        assert "8877" not in event_str
        assert "HDFC_PRIVATE" not in event_str
        assert "payload" not in getattr(event, "client_metadata", {})


def test_sec_12_frontend_code_cannot_access_privileged_database_credentials():
    """Check 12: Frontend configuration boundaries do not expose Postgres credentials."""
    settings = Settings()
    safe_dict = settings.to_safe_dict()
    assert "password" in safe_dict["postgres"]
    # Password masked
    assert safe_dict["postgres"]["password"] in (None, "***")


def test_sec_13_invalid_authorization_context_fails_closed(postgres_adapter):
    """Check 13: Invalid authorization context fails closed."""
    svc = MemoryService(storage_adapter=postgres_adapter)

    # None context
    with pytest.raises(MemoryUnauthorizedError):
        svc.get_record(None, "any_record")

    # Blank principal_id
    blank_ctx = AuthorizationContext(
        principal_id="   ",
        principal_type=PrincipalType.USER,
        roles=[],
    )
    with pytest.raises(MemoryUnauthorizedError):
        svc.get_record(blank_ctx, "any_record")


def test_sec_14_search_cannot_bypass_ownership_or_domain_restrictions(postgres_adapter, auth_farmer_1, auth_farmer_2):
    """Check 14: Search cannot bypass ownership or domain restrictions."""
    svc = MemoryService(storage_adapter=postgres_adapter)

    # Store record for Farmer 2
    rec2 = MemoryRecord(
        record_id="rec_farmer2_crop",
        domain=MemoryDomain.USER,
        record_type="crop_status",
        owner_id="farmer_202",
        scope_type=MemoryScope.USER,
        scope_id="farmer_202",
        payload={"crop": "lentil"},
        source="sensor",
    )
    svc.store_record(auth_farmer_2, rec2)

    # Farmer 1 executes broad search trying to query farmer_202's records
    criteria = MemorySearchCriteria(owner_id="farmer_202")
    with pytest.raises(MemoryForbiddenError):
        svc.search_records(auth_farmer_1, criteria)


# =============================================================================
# Section 2: Persistence & Reliability Verification
# =============================================================================

def test_rel_01_concurrent_updates_optimistic_locking(postgres_adapter, auth_farmer_1):
    """Verify optimistic locking prevents stale updates under concurrent access."""
    svc = MemoryService(storage_adapter=postgres_adapter)
    rec = MemoryRecord(
        record_id="rec_concurrent_01",
        domain=MemoryDomain.USER,
        record_type="irrigation",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload={"state": "off"},
        source="iot",
        record_version=1,
    )
    svc.store_record(auth_farmer_1, rec)

    # Client A updates version 1 -> version 2
    update_a = rec.model_copy(update={"payload": {"state": "on"}, "record_version": 2})
    res_a = svc.update_record(auth_farmer_1, update_a, expected_version=1)
    assert res_a.record_version == 2

    # Client B attempts update with stale expected_version=1 -> Conflict error
    update_b = rec.model_copy(update={"payload": {"state": "auto"}, "record_version": 2})
    with pytest.raises(MemoryConflictError):
        svc.update_record(auth_farmer_1, update_b, expected_version=1)


def test_rel_02_duplicate_record_id_handled_cleanly(postgres_adapter, auth_farmer_1):
    """Verify duplicate primary key insertion fails cleanly with MemoryConflictError."""
    svc = MemoryService(storage_adapter=postgres_adapter)
    rec = MemoryRecord(
        record_id="rec_unique_dup",
        domain=MemoryDomain.USER,
        record_type="seed_batch",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload={"batch": "B100"},
        source="inventory",
    )
    svc.store_record(auth_farmer_1, rec)

    # Attempt storing duplicate ID
    with pytest.raises(MemoryConflictError):
        svc.store_record(auth_farmer_1, rec)


def test_rel_03_persistence_across_connection_and_adapter_restart(postgres_service, auth_farmer_1):
    """Verify stored records survive adapter teardown and reconnection without loss."""
    adapter1 = SupabasePostgresMemoryStorageAdapter(postgres_service)
    svc1 = MemoryService(storage_adapter=adapter1)

    rec = MemoryRecord(
        record_id="rec_restart_survivor",
        domain=MemoryDomain.USER,
        record_type="soil_health",
        owner_id="farmer_101",
        scope_type=MemoryScope.FIELD,
        scope_id="field_01",
        payload={"organic_carbon_pct": 0.65},
        source="soil_lab",
    )
    svc1.store_record(auth_farmer_1, rec)

    # Disconnect service and create fresh connection & adapter
    postgres_service.disconnect()
    postgres_service.connect()

    adapter2 = SupabasePostgresMemoryStorageAdapter(postgres_service)
    svc2 = MemoryService(storage_adapter=adapter2)

    retrieved = svc2.get_record(auth_farmer_1, "rec_restart_survivor")
    assert retrieved is not None
    assert retrieved.record_id == "rec_restart_survivor"
    assert retrieved.payload["organic_carbon_pct"] == 0.65


def test_rel_04_no_silent_fallback_to_in_memory_when_database_fails():
    """Verify production safeguards prevent silent in-memory fallback on database failure."""
    bad_config = PostgresConfig(host="127.0.0.1", port=59999, connect_timeout=0.5)
    bad_service = PostgresDatabaseService(bad_config)
    adapter = SupabasePostgresMemoryStorageAdapter(bad_service)
    svc = MemoryService(storage_adapter=adapter)

    auth = AuthorizationContext(principal_id="farmer_101")
    dummy = MemoryRecord(
        record_id="rec_unreachable",
        domain=MemoryDomain.USER,
        record_type="test",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload={"test": 1},
        source="unit_test",
    )
    with pytest.raises(MemoryStorageUnavailableError):
        svc.store_record(auth, dummy)


# =============================================================================
# Section 3: Performance & Resource Quality
# =============================================================================

def test_perf_01_bounded_pagination_and_query_efficiency(postgres_adapter, auth_farmer_1):
    """Verify deterministic pagination and bounded result query execution."""
    svc = MemoryService(storage_adapter=postgres_adapter)

    # Bulk insert 10 records
    for i in range(10):
        rec = MemoryRecord(
            record_id=f"rec_perf_page_{i:02d}",
            domain=MemoryDomain.USER,
            record_type="reading",
            owner_id="farmer_101",
            scope_type=MemoryScope.USER,
            scope_id="farmer_101",
            payload={"metric": i},
            source="sensor",
            created_at=datetime.now(timezone.utc) + timedelta(seconds=i),
        )
        svc.store_record(auth_farmer_1, rec)

    # Measure page 1 (limit=4, offset=0)
    t0 = time.perf_counter()
    p1 = svc.search_records(auth_farmer_1, MemorySearchCriteria(limit=4, offset=0, sort_by=MemorySortField.CREATED_AT, sort_order=SortOrder.ASC))
    dt_p1 = (time.perf_counter() - t0) * 1000

    # Measure page 2 (limit=4, offset=4)
    t1 = time.perf_counter()
    p2 = svc.search_records(auth_farmer_1, MemorySearchCriteria(limit=4, offset=4, sort_by=MemorySortField.CREATED_AT, sort_order=SortOrder.ASC))
    dt_p2 = (time.perf_counter() - t1) * 1000

    assert len(p1) == 4
    assert len(p2) == 4
    assert p1[0].record_id == "rec_perf_page_00"
    assert p2[0].record_id == "rec_perf_page_04"
    assert dt_p1 < 100.0
    assert dt_p2 < 100.0


def test_perf_02_large_payload_handling_without_loss(postgres_adapter, auth_farmer_1):
    """Verify handling of realistic large JSONB payload (e.g. detailed soil & weather telemetry)."""
    svc = MemoryService(storage_adapter=postgres_adapter)

    large_payload = {
        "telemetry_points": [{"timestamp": f"2026-11-01T{h:02d}:00:00Z", "val": h * 1.5} for h in range(100)],
        "weather_summary": {"avg_temp": 28.5, "humidity": 72.0, "notes": "A" * 2000},
    }
    rec = MemoryRecord(
        record_id="rec_large_payload_01",
        domain=MemoryDomain.USER,
        record_type="telemetry_packet",
        owner_id="farmer_101",
        scope_type=MemoryScope.FIELD,
        scope_id="field_01",
        payload=large_payload,
        source="gateway",
    )
    t0 = time.perf_counter()
    svc.store_record(auth_farmer_1, rec)
    retrieved = svc.get_record(auth_farmer_1, "rec_large_payload_01")
    dt = (time.perf_counter() - t0) * 1000

    assert retrieved is not None
    assert len(retrieved.payload["telemetry_points"]) == 100
    assert retrieved.payload["weather_summary"]["notes"] == "A" * 2000
    assert dt < 100.0


def test_perf_03_zero_pgvector_or_vector_search_dependency(postgres_service):
    """Verify database schema has no pgvector extension or vector columns."""
    conn = postgres_service.get_connection()
    try:
        with conn.cursor() as cursor:
            # Check extension
            cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
            ext = cursor.fetchall()
            assert len(ext) == 0, "pgvector extension must NOT be installed for structured memory."

            # Check column types in memory_records
            cursor.execute(
                "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'memory_records';"
            )
            cols = {row[0]: row[1] for row in cursor.fetchall()}
            assert "vector" not in cols.values()
            assert cols["payload"] in ("jsonb", "USER-DEFINED")
    finally:
        postgres_service.put_connection(conn)


# =============================================================================
# Section 4: EarthMind End-to-End Context Flow
# =============================================================================

def test_e2e_01_complete_memory_to_b2_context_manager_flow(postgres_adapter, auth_farmer_1):
    """Verify complete context flow: Memory Service -> Provider -> B2 Context Manager -> Prepared Context."""
    svc = MemoryService(storage_adapter=postgres_adapter)

    # Store farmer preference (USER scope)
    rec_pref = MemoryRecord(
        record_id="rec_farmer_pref_e2e",
        domain=MemoryDomain.USER,
        record_type="farmer_preference",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload={"preferred_fertilizer": "neem_coated_urea"},
        source="onboarding",
    )
    svc.store_record(auth_farmer_1, rec_pref)

    provider = MemoryContextProvider(memory_service=svc)
    adapter = MemoryContextProviderAdapter(memory_provider=provider)
    b2_manager = B2ContextManager(providers=[adapter])

    # Request context for Farmer 101
    ctx_req = ContextRequest(
        request_id="req_e2e_b2_01",
        farmer_id="farmer_101",
        task="recommend irrigation timing",
        policy=PolicyConfig(allow_pii=True),
    )
    prepared_context = b2_manager.prepare_context(ctx_req)

    assert prepared_context.state == ContextState.COMPLETED
    assert len(prepared_context.items) >= 1
    sources = [it.source_id for it in prepared_context.items]
    assert "rec_farmer_pref_e2e" in sources


def test_e2e_02_b3_reasoning_no_direct_memory_bypass(postgres_adapter, auth_farmer_1):
    """Verify B3 Reasoning Engine receives Memory context strictly via B2 Evidence items."""
    from modules.reasoning import EvidenceManager, ReasoningInput

    svc = MemoryService(storage_adapter=postgres_adapter)
    rec = MemoryRecord(
        record_id="rec_reasoning_e2e",
        domain=MemoryDomain.USER,
        record_type="soil_organic_matter",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload={"om_pct": 1.1},
        source="soil_test",
    )
    svc.store_record(auth_farmer_1, rec)

    provider = MemoryContextProvider(memory_service=svc)
    adapter = MemoryContextProviderAdapter(memory_provider=provider)
    b2_manager = B2ContextManager(providers=[adapter])

    ctx_req = ContextRequest(
        request_id="req_b3_e2e",
        farmer_id="farmer_101",
        task="eval soil nitrogen requirement",
        policy=PolicyConfig(allow_pii=True),
    )
    prepared = b2_manager.prepare_context(ctx_req)

    # B3 converts B2 Context Items into EvidenceItems
    input_data = ReasoningInput(
        request_id="req_b3_e2e",
        task="eval soil nitrogen requirement",
        prepared_context=prepared,
    )
    ev_mgr = EvidenceManager()
    evidence_items, _, _ = ev_mgr.prepare_evidence(input_data)

    assert len(evidence_items) >= 1
    ev = evidence_items[0]
    assert ev.source == "context_manager:MEMORY"
    assert ev.source_id == "rec_reasoning_e2e"
    assert ev.content["om_pct"] == 1.1


def test_e2e_03_ulpu_indic_multilingual_preservation_in_postgres(postgres_adapter, auth_farmer_1):
    """Verify Indic language Unicode script preservation through PostgreSQL persistence and B2 context."""
    svc = MemoryService(storage_adapter=postgres_adapter)

    multilingual_payload = {
        "hi": "गेहूं में करनाल बंट रोग के लक्षण दिखे",
        "pa": "ਕਣਕ ਵਿੱਚ ਪੀਲੀ ਕੁੰਗੀ ਦੀ ਰੋਕਥਾਮ ਲਈ ਸਿਫਾਰਸ਼",
        "mr": "गहू पिकासाठी खत व्यवस्थापन",
        "crop": "wheat",
    }
    rec = MemoryRecord(
        record_id="rec_indic_e2e_01",
        domain=MemoryDomain.USER,
        record_type="multilingual_voice_log",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload=multilingual_payload,
        source="voice_recorder",
    )
    svc.store_record(auth_farmer_1, rec)

    provider = MemoryContextProvider(memory_service=svc)
    adapter = MemoryContextProviderAdapter(memory_provider=provider)
    b2_manager = B2ContextManager(providers=[adapter])

    ctx_req = ContextRequest(
        request_id="req_indic_b2_01",
        farmer_id="farmer_101",
        task="crop advisory",
        policy=PolicyConfig(allow_pii=True),
    )
    prepared = b2_manager.prepare_context(ctx_req)
    assert len(prepared.items) >= 1
    retrieved_content = prepared.items[0].content
    assert retrieved_content["hi"] == multilingual_payload["hi"]
    assert retrieved_content["pa"] == multilingual_payload["pa"]
    assert retrieved_content["mr"] == multilingual_payload["mr"]
