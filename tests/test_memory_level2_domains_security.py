"""Comprehensive Unit and Integration Test Suite for EarthMind Memory Module Level 2: Memory Domains & Security.

Covers:
1. Domain separation:
   - Valid User Memory records.
   - Valid General Memory records.
   - Invalid domain values.
   - Invalid domain/scope combinations.
   - Attempts to store private User Memory as General Memory.
2. User ownership enforcement:
   - User A can access their authorized records.
   - User A cannot access User B's records (cross-user denial).
   - Changing a record ID or owner ID does not bypass ownership.
   - Missing identity is denied.
   - Invalid authorization context is denied.
3. Scope enforcement:
   - Correct USER scope access.
   - Correct CONVERSATION scope access.
   - Correct FARM scope access.
   - Correct FIELD scope access.
   - Correct CROP_CYCLE scope access.
   - Access to an unrelated scope is denied.
   - Client-provided scope ID alone cannot authorize access.
   - Unknown scopes are denied.
4. General Memory governance:
   - Authorized General Memory read.
   - Authorized General Memory write under approved policy/roles.
   - Unauthorized General Memory write is denied.
   - Ordinary user operations cannot modify shared records.
   - Private records cannot be automatically promoted or exposed.
5. Operation-level enforcement:
   - Store.
   - Retrieve.
   - Search.
   - Update.
   - Delete.
   - Metadata access.
6. Security and compatibility tests:
   - No blanket "admin" or "system" role bypass without proper least-privilege context.
   - No authorization bypass through malformed inputs.
   - No sensitive payloads in security logs / audit events.
   - Existing Level 1 tests remain passing.
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Any

from core.schemas.memory import (
    AuthorizationContext,
    MemoryDomain,
    MemoryOperation,
    MemoryRecord,
    MemoryRecordStatus,
    MemoryScope,
    MemorySearchCriteria,
)
from core.schemas.memory_security import (
    MemorySecurityAuditEvent,
    SecurityAuditAction,
    SecurityDecision,
)
from modules.memory.errors import (
    MemoryForbiddenError,
    MemoryInvalidArgumentError,
    MemoryNotFoundError,
    MemoryUnauthorizedError,
)
from modules.memory.memory_service import MemoryService
from modules.memory.security import MemorySecurityAuditor, MemorySecurityEnforcer
from modules.memory.storage_adapter import InMemoryMemoryStorageAdapter


@pytest.fixture
def setup_service():
    """Fixture providing clean MemoryService with in-memory storage and fresh auditor."""
    storage = InMemoryMemoryStorageAdapter()
    auditor = MemorySecurityAuditor()
    enforcer = MemorySecurityEnforcer(auditor=auditor)
    service = MemoryService(storage_adapter=storage, enforcer=enforcer, auditor=auditor)
    return service, storage, auditor, enforcer


# ==============================================================================
# 1. DOMAIN SEPARATION TESTS
# ==============================================================================

def test_01_valid_user_memory_record(setup_service):
    """Verify that a valid USER memory record stores and retrieves successfully."""
    service, _, auditor, _ = setup_service
    ctx = AuthorizationContext(
        principal_id="farmer_raj",
        roles=["farmer"],
        accessible_scopes={"USER": ["farmer_raj"]},
        requested_operation=MemoryOperation.CREATE,
    )
    record = MemoryRecord(
        record_id="mem_user_01",
        domain=MemoryDomain.USER,
        record_type="preferences",
        owner_id="farmer_raj",
        scope_type=MemoryScope.USER,
        scope_id="farmer_raj",
        payload={"language": "hi", "crop": "wheat"},
        source="profile",
    )
    stored = service.store_record(ctx, record)
    assert stored.record_id == "mem_user_01"
    assert stored.domain == MemoryDomain.USER
    assert stored.owner_id == "farmer_raj"

    # Verify audit event emitted
    events = auditor.audit_events
    assert any(e.action == SecurityAuditAction.ACCESS_ALLOWED and e.record_id == "mem_user_01" for e in events)


def test_02_valid_general_memory_record(setup_service):
    """Verify that a valid GENERAL memory record stores under authorized role."""
    service, _, auditor, _ = setup_service
    curator_ctx = AuthorizationContext(
        principal_id="curator_icar",
        roles=["curator"],
        requested_operation=MemoryOperation.CREATE,
    )
    gen_record = MemoryRecord(
        record_id="mem_gen_01",
        domain=MemoryDomain.GENERAL,
        record_type="regional_calendar",
        owner_id=None,
        scope_type=MemoryScope.GENERAL,
        scope_id="north_zone",
        payload={"season": "rabi", "sowing_window": "oct_nov"},
        source="icar_manual",
    )
    stored = service.store_record(curator_ctx, gen_record)
    assert stored.domain == MemoryDomain.GENERAL
    assert stored.owner_id is None


def test_03_invalid_domain_scope_combinations(setup_service):
    """Verify invalid domain and scope combinations are rejected."""
    service, _, auditor, enforcer = setup_service
    ctx = AuthorizationContext(
        principal_id="user_1",
        roles=["farmer"],
        requested_operation=MemoryOperation.CREATE,
    )

    # USER domain with GENERAL scope fails schema validation or enforcer check
    with pytest.raises((ValueError, MemoryInvalidArgumentError)):
        record = MemoryRecord(
            record_id="mem_bad_combo",
            domain=MemoryDomain.USER,
            record_type="test",
            owner_id="user_1",
            scope_type=MemoryScope.GENERAL,
            scope_id="gen_scope",
            payload={"test": 1},
            source="manual",
        )
        service.store_record(ctx, record)

    # GENERAL domain with USER scope fails schema validation or enforcer check
    with pytest.raises((ValueError, MemoryInvalidArgumentError)):
        gen_bad = MemoryRecord(
            record_id="mem_bad_combo_2",
            domain=MemoryDomain.GENERAL,
            record_type="test",
            owner_id=None,
            scope_type=MemoryScope.USER,
            scope_id="user_1",
            payload={"test": 1},
            source="manual",
        )
        service.store_record(ctx, gen_bad)


def test_04_attempt_store_private_user_memory_as_general(setup_service):
    """Verify that attempts to store private user memory as general memory fail closed."""
    service, _, auditor, _ = setup_service
    ctx = AuthorizationContext(
        principal_id="farmer_raj",
        roles=["farmer"],
        requested_operation=MemoryOperation.CREATE,
    )

    # A record having owner_id in GENERAL domain must be rejected
    with pytest.raises((ValueError, MemoryForbiddenError)):
        rec = MemoryRecord(
            domain=MemoryDomain.GENERAL,
            record_type="private_note",
            owner_id="farmer_raj",
            scope_type=MemoryScope.GENERAL,
            scope_id="general_zone",
            payload={"private_data": "secret"},
            source="user",
        )
        service.store_record(ctx, rec)


# ==============================================================================
# 2. USER OWNERSHIP ENFORCEMENT TESTS
# ==============================================================================

def test_05_user_access_authorized_records(setup_service):
    """Verify User A can access their own records."""
    service, _, _, _ = setup_service
    ctx_a = AuthorizationContext(
        principal_id="farmer_a",
        owner_id="farmer_a",
        accessible_scopes={"USER": ["farmer_a"]},
    )
    rec_a = MemoryRecord(
        record_id="mem_a_1",
        domain=MemoryDomain.USER,
        record_type="notes",
        owner_id="farmer_a",
        scope_type=MemoryScope.USER,
        scope_id="farmer_a",
        payload={"note": "first harvest"},
        source="user",
    )
    service.store_record(ctx_a, rec_a)

    retrieved = service.get_record(ctx_a, "mem_a_1")
    assert retrieved.record_id == "mem_a_1"
    assert retrieved.payload["note"] == "first harvest"


def test_06_cross_user_access_strictly_denied(setup_service):
    """Verify User A cannot access User B's records."""
    service, _, auditor, _ = setup_service
    ctx_b = AuthorizationContext(
        principal_id="farmer_b",
        owner_id="farmer_b",
        accessible_scopes={"USER": ["farmer_b"]},
    )
    rec_b = MemoryRecord(
        record_id="mem_b_1",
        domain=MemoryDomain.USER,
        record_type="notes",
        owner_id="farmer_b",
        scope_type=MemoryScope.USER,
        scope_id="farmer_b",
        payload={"note": "farmer B confidential field info"},
        source="user",
    )
    service.store_record(ctx_b, rec_b)

    # Now User A attempts to access User B's record
    ctx_a = AuthorizationContext(
        principal_id="farmer_a",
        owner_id="farmer_a",
        accessible_scopes={"USER": ["farmer_a"]},
    )
    with pytest.raises(MemoryForbiddenError) as exc_info:
        service.get_record(ctx_a, "mem_b_1")
    assert exc_info.value.error_contract.error_code == "FORBIDDEN"

    # Check that CROSS_USER_ATTEMPT was audited
    events = [e for e in auditor.audit_events if e.action == SecurityAuditAction.CROSS_USER_ATTEMPT]
    assert len(events) >= 1
    assert events[-1].principal_id == "farmer_a"
    assert events[-1].owner_id == "farmer_b"


def test_07_changing_identifier_does_not_bypass_ownership(setup_service):
    """Verify changing a record_id or owner_id on update fails closed."""
    service, _, _, _ = setup_service
    ctx_a = AuthorizationContext(
        principal_id="farmer_a",
        owner_id="farmer_a",
        accessible_scopes={"USER": ["farmer_a"]},
    )
    rec_a = MemoryRecord(
        record_id="mem_a_2",
        domain=MemoryDomain.USER,
        record_type="notes",
        owner_id="farmer_a",
        scope_type=MemoryScope.USER,
        scope_id="farmer_a",
        payload={"note": "initial"},
        source="user",
    )
    service.store_record(ctx_a, rec_a)

    # User B attempts to overwrite User A's record by changing owner_id or pretending to update
    ctx_b = AuthorizationContext(
        principal_id="farmer_b",
        owner_id="farmer_b",
        accessible_scopes={"USER": ["farmer_b"]},
    )
    spoofed = rec_a.model_copy(update={"owner_id": "farmer_b", "payload": {"note": "hacked"}})
    with pytest.raises(MemoryForbiddenError):
        service.update_record(ctx_b, spoofed)


def test_08_missing_identity_is_denied(setup_service):
    """Verify missing authorization context is denied with MemoryUnauthorizedError."""
    service, _, auditor, _ = setup_service
    with pytest.raises(MemoryUnauthorizedError) as exc_info:
        service.get_record(None, "mem_any")
    assert exc_info.value.error_contract.error_code == "UNAUTHORIZED"

    events = [e for e in auditor.audit_events if e.action == SecurityAuditAction.INVALID_OR_MISSING_AUTH_CONTEXT]
    assert len(events) >= 1


def test_09_empty_principal_identity_is_denied(setup_service):
    """Verify empty principal in context is denied with MemoryUnauthorizedError."""
    service, _, auditor, _ = setup_service
    bad_ctx = AuthorizationContext(
        principal_id="   ",
        roles=[],
    )
    with pytest.raises(MemoryUnauthorizedError):
        service.get_record(bad_ctx, "mem_any")


# ==============================================================================
# 3. SCOPE ENFORCEMENT TESTS
# ==============================================================================

def test_10_approved_user_scopes_access(setup_service):
    """Verify authorized access across all approved scopes: USER, CONVERSATION, FARM, FIELD, CROP_CYCLE."""
    service, _, _, _ = setup_service

    scopes_data = [
        (MemoryScope.USER, "farmer_01", {"USER": ["farmer_01"]}),
        (MemoryScope.CONVERSATION, "conv_456", {"CONVERSATION": ["conv_456"]}),
        (MemoryScope.FARM, "farm_789", {"FARM": ["farm_789"]}),
        (MemoryScope.FIELD, "field_101", {"FIELD": ["field_101"]}),
        (MemoryScope.CROP_CYCLE, "cycle_2025_rabi", {"CROP_CYCLE": ["cycle_2025_rabi"]}),
    ]

    for scope_type, scope_id, accessible_scopes in scopes_data:
        ctx = AuthorizationContext(
            principal_id="farmer_01",
            owner_id="farmer_01",
            accessible_scopes=accessible_scopes,
        )
        rec = MemoryRecord(
            record_id=f"mem_scope_{scope_type.value.lower()}",
            domain=MemoryDomain.USER,
            record_type=f"test_{scope_type.value.lower()}",
            owner_id="farmer_01",
            scope_type=scope_type,
            scope_id=scope_id,
            payload={"status": "ok", "scope": scope_type.value},
            source="test",
        )
        stored = service.store_record(ctx, rec)
        assert stored.scope_type == scope_type

        retrieved = service.get_record(ctx, stored.record_id)
        assert retrieved.payload["scope"] == scope_type.value


def test_11_unrelated_scope_access_denied(setup_service):
    """Verify that a valid owner cannot access a scope they lack claims for."""
    service, _, auditor, _ = setup_service
    # Context has access only to farm_1
    ctx = AuthorizationContext(
        principal_id="farmer_01",
        owner_id="farmer_01",
        accessible_scopes={"FARM": ["farm_1"]},
    )

    rec_farm_2 = MemoryRecord(
        record_id="mem_farm_2",
        domain=MemoryDomain.USER,
        record_type="farm_profile",
        owner_id="farmer_01",
        scope_type=MemoryScope.FARM,
        scope_id="farm_2",  # Not in accessible_scopes
        payload={"size": 10},
        source="user",
    )

    # Client-provided farm_2 is not authorized
    with pytest.raises(MemoryForbiddenError) as exc_info:
        service.store_record(ctx, rec_farm_2)
    assert exc_info.value.error_contract.error_code == "FORBIDDEN"


def test_12_client_scope_id_alone_not_proof_of_permission(setup_service):
    """Verify client-provided scope ID does not grant authorization without trusted claim."""
    service, _, auditor, _ = setup_service
    # Attacker tries to inject field_secret in payload and request
    ctx = AuthorizationContext(
        principal_id="farmer_01",
        owner_id="farmer_01",
        accessible_scopes={"FIELD": ["field_normal"]},
    )
    rec = MemoryRecord(
        record_id="mem_field_unauthorized",
        domain=MemoryDomain.USER,
        record_type="field_data",
        owner_id="farmer_01",
        scope_type=MemoryScope.FIELD,
        scope_id="field_secret",
        payload={"nitrogen": 50},
        source="sensor",
    )
    with pytest.raises(MemoryForbiddenError):
        service.store_record(ctx, rec)


def test_13_unknown_scope_fails_closed(setup_service):
    """Verify unknown or invalid scope fails closed."""
    service, _, auditor, enforcer = setup_service
    ctx = AuthorizationContext(principal_id="farmer_01", owner_id="farmer_01")
    with pytest.raises(MemoryInvalidArgumentError):
        enforcer.enforce_authorization(
            context=ctx,
            operation=MemoryOperation.READ,
            domain=MemoryDomain.USER,
            scope_type="UNKNOWN_INVALID_SCOPE",  # type: ignore
            scope_id="any",
            owner_id="farmer_01",
        )


# ==============================================================================
# 4. GENERAL MEMORY GOVERNANCE TESTS
# ==============================================================================

def test_14_authorized_general_memory_read(setup_service):
    """Verify General Memory read is permitted for authenticated subjects."""
    service, _, _, _ = setup_service
    curator_ctx = AuthorizationContext(
        principal_id="curator_1",
        roles=["curator"],
    )
    gen_record = MemoryRecord(
        record_id="mem_gen_calendar",
        domain=MemoryDomain.GENERAL,
        record_type="calendar",
        owner_id=None,
        scope_type=MemoryScope.GENERAL,
        scope_id="all_india",
        payload={"month": "june", "crop": "kharif_rice"},
        source="icar",
    )
    service.store_record(curator_ctx, gen_record)

    # Any ordinary user with authenticated context can read General Memory
    farmer_ctx = AuthorizationContext(
        principal_id="farmer_ordinary",
        roles=["farmer"],
    )
    retrieved = service.get_record(farmer_ctx, "mem_gen_calendar")
    assert retrieved.record_id == "mem_gen_calendar"
    assert retrieved.payload["month"] == "june"


def test_15_authorized_general_memory_write_via_role_or_policy(setup_service):
    """Verify General Memory writes succeed with explicit role or policy context."""
    service, _, _, _ = setup_service

    # With role "knowledge_admin"
    admin_ctx = AuthorizationContext(
        principal_id="admin_user",
        roles=["knowledge_admin"],
    )
    rec1 = MemoryRecord(
        record_id="mem_gen_admin_write",
        domain=MemoryDomain.GENERAL,
        record_type="advisory",
        owner_id=None,
        scope_type=MemoryScope.GENERAL,
        scope_id="national",
        payload={"monsoon": "normal"},
        source="imd",
    )
    stored1 = service.store_record(admin_ctx, rec1)
    assert stored1.record_id == "mem_gen_admin_write"

    # With policy_context "allow_general_write": True
    policy_ctx = AuthorizationContext(
        principal_id="service_worker",
        roles=[],
        policy_context={"allow_general_write": True},
    )
    rec2 = MemoryRecord(
        record_id="mem_gen_policy_write",
        domain=MemoryDomain.GENERAL,
        record_type="advisory",
        owner_id=None,
        scope_type=MemoryScope.GENERAL,
        scope_id="national",
        payload={"rainfall": "adequate"},
        source="imd",
    )
    stored2 = service.store_record(policy_ctx, rec2)
    assert stored2.record_id == "mem_gen_policy_write"


def test_16_unauthorized_general_memory_write_denied(setup_service):
    """Verify ordinary users cannot write or modify General Memory records."""
    service, _, auditor, _ = setup_service
    farmer_ctx = AuthorizationContext(
        principal_id="farmer_01",
        roles=["farmer"],
    )
    gen_rec = MemoryRecord(
        record_id="mem_gen_illegal",
        domain=MemoryDomain.GENERAL,
        record_type="rules",
        owner_id=None,
        scope_type=MemoryScope.GENERAL,
        scope_id="national",
        payload={"illegal": "content"},
        source="user",
    )

    with pytest.raises(MemoryForbiddenError) as exc_info:
        service.store_record(farmer_ctx, gen_rec)
    assert exc_info.value.error_contract.error_code == "FORBIDDEN"

    events = [e for e in auditor.audit_events if e.action == SecurityAuditAction.UNAUTHORIZED_GENERAL_WRITE]
    assert len(events) >= 1


def test_17_ordinary_user_cannot_update_or_delete_general_records(setup_service):
    """Verify ordinary users cannot update or delete existing shared general records."""
    service, _, _, _ = setup_service
    curator_ctx = AuthorizationContext(principal_id="curator_1", roles=["curator"])
    gen_rec = MemoryRecord(
        record_id="mem_gen_shared",
        domain=MemoryDomain.GENERAL,
        record_type="guidelines",
        owner_id=None,
        scope_type=MemoryScope.GENERAL,
        scope_id="national",
        payload={"ver": 1},
        source="icar",
    )
    service.store_record(curator_ctx, gen_rec)

    # Ordinary user tries to update
    farmer_ctx = AuthorizationContext(principal_id="farmer_01", roles=["farmer"])
    updated = gen_rec.model_copy(update={"record_version": 2, "payload": {"ver": 2}})
    with pytest.raises(MemoryForbiddenError):
        service.update_record(farmer_ctx, updated, expected_version=1)

    # Ordinary user tries to delete
    with pytest.raises(MemoryForbiddenError):
        service.delete_record(farmer_ctx, "mem_gen_shared")


def test_18_no_automatic_promotion_or_leakage(setup_service):
    """Verify private records cannot be promoted to General Memory."""
    service, _, auditor, _ = setup_service
    ctx = AuthorizationContext(principal_id="farmer_01", roles=["farmer"])
    user_rec = MemoryRecord(
        record_id="mem_private_to_general",
        domain=MemoryDomain.USER,
        record_type="private_note",
        owner_id="farmer_01",
        scope_type=MemoryScope.USER,
        scope_id="farmer_01",
        payload={"confidential": 123},
        source="user",
    )
    service.store_record(ctx, user_rec)

    # Attacker tries to update user record to General Memory domain
    tampered = user_rec.model_copy(update={"domain": MemoryDomain.GENERAL, "owner_id": None, "scope_type": MemoryScope.GENERAL, "scope_id": "all"})
    with pytest.raises(MemoryForbiddenError):
        service.update_record(ctx, tampered)


# ==============================================================================
# 5. OPERATION-LEVEL ENFORCEMENT TESTS
# ==============================================================================

def test_19_all_operations_require_authorization(setup_service):
    """Verify Store, Retrieve, Search, Update, Delete, Metadata require valid auth context."""
    service, _, _, _ = setup_service
    rec = MemoryRecord(
        record_id="mem_ops_check",
        domain=MemoryDomain.USER,
        record_type="test",
        owner_id="farmer_01",
        scope_type=MemoryScope.USER,
        scope_id="farmer_01",
        payload={"test": 1},
        source="test",
    )

    # Store
    with pytest.raises(MemoryUnauthorizedError):
        service.store_record(None, rec)

    # Retrieve
    with pytest.raises(MemoryUnauthorizedError):
        service.get_record(None, "mem_ops_check")

    # Search
    with pytest.raises(MemoryUnauthorizedError):
        service.search_records(None, MemorySearchCriteria())

    # Update
    with pytest.raises(MemoryUnauthorizedError):
        service.update_record(None, rec)

    # Delete
    with pytest.raises(MemoryUnauthorizedError):
        service.delete_record(None, "mem_ops_check")

    # Metadata
    with pytest.raises(MemoryUnauthorizedError):
        service.get_record_metadata(None, "mem_ops_check")


def test_20_search_bound_to_authorized_owner(setup_service):
    """Verify search automatically scopes to the authorized user and rejects cross-user search."""
    service, _, _, _ = setup_service
    ctx_a = AuthorizationContext(principal_id="farmer_a", owner_id="farmer_a", accessible_scopes={"USER": ["farmer_a"]})
    ctx_b = AuthorizationContext(principal_id="farmer_b", owner_id="farmer_b", accessible_scopes={"USER": ["farmer_b"]})

    rec_a = MemoryRecord(
        record_id="mem_search_a",
        domain=MemoryDomain.USER,
        record_type="test",
        owner_id="farmer_a",
        scope_type=MemoryScope.USER,
        scope_id="farmer_a",
        payload={"secret": "A"},
        source="test",
    )
    rec_b = MemoryRecord(
        record_id="mem_search_b",
        domain=MemoryDomain.USER,
        record_type="test",
        owner_id="farmer_b",
        scope_type=MemoryScope.USER,
        scope_id="farmer_b",
        payload={"secret": "B"},
        source="test",
    )
    service.store_record(ctx_a, rec_a)
    service.store_record(ctx_b, rec_b)

    # Farmer A searches with no owner specified: should only return Farmer A's records
    results_a = service.search_records(ctx_a, MemorySearchCriteria())
    assert len(results_a) == 1
    assert results_a[0].record_id == "mem_search_a"

    # Farmer A attempts to explicitly search for Farmer B's owner_id: forbidden
    with pytest.raises(MemoryForbiddenError):
        service.search_records(ctx_a, MemorySearchCriteria(owner_id="farmer_b"))


def test_21_delete_and_metadata_authorized_access(setup_service):
    """Verify delete and metadata access succeed for owner, denied for other user."""
    service, _, _, _ = setup_service
    ctx_a = AuthorizationContext(principal_id="farmer_a", owner_id="farmer_a", accessible_scopes={"USER": ["farmer_a"]})
    ctx_b = AuthorizationContext(principal_id="farmer_b", owner_id="farmer_b", accessible_scopes={"USER": ["farmer_b"]})

    rec = MemoryRecord(
        record_id="mem_meta_del",
        domain=MemoryDomain.USER,
        record_type="test",
        owner_id="farmer_a",
        scope_type=MemoryScope.USER,
        scope_id="farmer_a",
        payload={"test": 1},
        source="test",
    )
    service.store_record(ctx_a, rec)

    # Metadata access by owner succeeds
    meta = service.get_record_metadata(ctx_a, "mem_meta_del")
    assert meta["record_id"] == "mem_meta_del"
    assert "payload" not in meta

    # Metadata access by non-owner fails
    with pytest.raises(MemoryForbiddenError):
        service.get_record_metadata(ctx_b, "mem_meta_del")

    # Delete by non-owner fails
    with pytest.raises(MemoryForbiddenError):
        service.delete_record(ctx_b, "mem_meta_del")

    # Delete by owner succeeds
    del_ok = service.delete_record(ctx_a, "mem_meta_del")
    assert del_ok is True


# ==============================================================================
# 6. SECURITY & AUDITABILITY TESTS
# ==============================================================================

def test_22_no_blanket_admin_role_bypass(setup_service):
    """Verify role 'admin' or 'system' does not bypass cross-user boundary without delegated ownership."""
    service, _, _, _ = setup_service
    ctx_owner = AuthorizationContext(principal_id="farmer_a", owner_id="farmer_a", accessible_scopes={"USER": ["farmer_a"]})
    rec = MemoryRecord(
        record_id="mem_admin_check",
        domain=MemoryDomain.USER,
        record_type="finance",
        owner_id="farmer_a",
        scope_type=MemoryScope.USER,
        scope_id="farmer_a",
        payload={"income": 100000},
        source="survey",
    )
    service.store_record(ctx_owner, rec)

    # An admin without delegation to farmer_a cannot arbitrarily read private farmer data
    admin_ctx = AuthorizationContext(
        principal_id="admin_joe",
        roles=["admin"],
    )
    with pytest.raises(MemoryForbiddenError):
        service.get_record(admin_ctx, "mem_admin_check")

    # With explicit delegation in policy_context
    delegated_admin = AuthorizationContext(
        principal_id="admin_joe",
        roles=["admin"],
        policy_context={"authorized_owners": ["farmer_a"]},
    )
    record_delegated = service.get_record(delegated_admin, "mem_admin_check")
    assert record_delegated.record_id == "mem_admin_check"


def test_23_security_logs_do_not_contain_sensitive_payloads(setup_service):
    """Verify that audit events never contain record payload content or secrets."""
    service, _, auditor, _ = setup_service
    ctx = AuthorizationContext(
        principal_id="farmer_01",
        owner_id="farmer_01",
        accessible_scopes={"USER": ["farmer_01"]},
    )
    secret_payload = {"pin": "1234", "bank_account": "IN99887766", "notes": "my_confidential_farming_financials"}
    rec = MemoryRecord(
        record_id="mem_test_record_01",
        domain=MemoryDomain.USER,
        record_type="banking",
        owner_id="farmer_01",
        scope_type=MemoryScope.USER,
        scope_id="farmer_01",
        payload=secret_payload,
        source="user",
    )
    service.store_record(ctx, rec)

    for event in auditor.audit_events:
        # Check event string representations
        event_str = str(event)
        for secret_val in ["1234", "IN99887766", "my_confidential_farming_financials"]:
            assert secret_val not in event_str

        # Check client_metadata does not have 'payload'
        assert "payload" not in event.client_metadata


def test_24_update_conflict_concurrency(setup_service):
    """Verify optimistic locking conflict detection is preserved in MemoryService."""
    service, _, _, _ = setup_service
    ctx = AuthorizationContext(principal_id="farmer_01", owner_id="farmer_01", accessible_scopes={"USER": ["farmer_01"]})
    rec = MemoryRecord(
        record_id="mem_concurrent",
        domain=MemoryDomain.USER,
        record_type="soil",
        owner_id="farmer_01",
        scope_type=MemoryScope.USER,
        scope_id="farmer_01",
        payload={"ph": 6.5},
        source="sensor",
        record_version=1,
    )
    service.store_record(ctx, rec)

    # Valid update with expected_version=1
    upd = rec.model_copy(update={"record_version": 2, "payload": {"ph": 6.7}})
    stored_upd = service.update_record(ctx, upd, expected_version=1)
    assert stored_upd.record_version == 2

    # Stale update with expected_version=1 must fail
    stale = rec.model_copy(update={"record_version": 3, "payload": {"ph": 7.0}})
    from modules.memory.errors import MemoryConflictError
    with pytest.raises(MemoryConflictError):
        service.update_record(ctx, stale, expected_version=1)
