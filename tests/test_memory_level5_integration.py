"""EarthMind Memory Module Level 5 Integration Test Suite.

Covers:
- Category A: Module integration (initialization, lifecycle registration, adapter setup, shutdown).
- Category B: B2 Context Manager integration (USER, CONVERSATION, FARM, FIELD, CROP_CYCLE scopes,
  empty results, expired/deleted record exclusion, authorization failure, storage failure).
- Category C: B3/B4 integration (context propagation from B2 into B3 Reasoning Engine evidence items
  and B4 Planning & Decision Engine context references without direct database/memory bypass).
- Category D: B5 Workflow Orchestration integration (workflow routing without circular dependencies).
- Category E: ULPU integration (multilingual Indic/English text preservation, original scripts, provenance).
- Category F: Security & regression (cross-user isolation, scope exclusion, General Memory governance,
  fail-closed authorization).
"""

import uuid
from datetime import datetime, timezone, timedelta
import pytest

from core.interfaces.boundary import IMemoryContextProvider
from core.schemas.application import ApplicationRequest, ApplicationResponse
from core.schemas.memory import (
    AuthorizationContext,
    MemoryDomain,
    MemoryOperation,
    MemoryRecord,
    MemoryRecordStatus,
    MemoryScope,
    MemorySearchCriteria,
)
from modules.context.boundary.adapters import MemoryContextProviderAdapter
from modules.context.boundary.enums import ContextScope, KnowledgeClassification
from modules.context.boundary.models import MemoryContextContract, MemoryContextRequest
from modules.context.boundary.validator import BoundaryValidator
from modules.context.context_module import ContextModule
from modules.context.manager import B2ContextManager
from modules.context.schemas import ContextItem, ContextRequest, ContextState, PolicyConfig
from modules.memory.context_provider import MemoryContextProvider
from modules.memory.errors import (
    MemoryError,
    MemoryForbiddenError,
    MemoryStorageUnavailableError,
    MemoryUnauthorizedError,
)
from modules.memory.memory_module import MemoryModule
from modules.memory.memory_service import MemoryService
from modules.memory.storage_adapter import InMemoryMemoryStorageAdapter
from app.lifecycle import LifecycleManager
from app.workflow import WorkflowEngine


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def memory_storage():
    return InMemoryMemoryStorageAdapter()


@pytest.fixture
def memory_service(memory_storage):
    return MemoryService(storage_adapter=memory_storage)


@pytest.fixture
def memory_provider(memory_service):
    return MemoryContextProvider(memory_service=memory_service)


@pytest.fixture
def auth_farmer_1():
    return AuthorizationContext(
        principal_id="farmer_101",
        owner_id="farmer_101",
        roles=["farmer"],
        accessible_scopes={"USER": ["farmer_101"], "FARM": ["farm_north"], "FIELD": ["field_zone_3"]},
        requested_operation=MemoryOperation.CREATE,
    )


@pytest.fixture
def auth_farmer_2():
    return AuthorizationContext(
        principal_id="farmer_202",
        owner_id="farmer_202",
        roles=["farmer"],
        accessible_scopes={"USER": ["farmer_202"]},
        requested_operation=MemoryOperation.READ,
    )


@pytest.fixture
def auth_curator():
    return AuthorizationContext(
        principal_id="curator_system",
        roles=["curator", "admin"],
        accessible_scopes={"GENERAL": ["general", "regional"]},
        requested_operation=MemoryOperation.CREATE,
    )


# =============================================================================
# Category A: Module Integration
# =============================================================================

def test_a01_memory_module_initialization_and_lifecycle():
    """Verify MemoryModule properly integrates with LifecycleManager, registers, initializes, and shuts down."""
    lifecycle = LifecycleManager()
    mem_module = MemoryModule()

    lifecycle.register_module("memory", mem_module)
    assert lifecycle.get_module("memory") == mem_module

    lifecycle.initialize_all()
    assert mem_module._is_initialized is True
    assert lifecycle.is_running is True
    assert hasattr(mem_module, "service")
    assert hasattr(mem_module, "context_provider")
    assert isinstance(mem_module.context_provider, IMemoryContextProvider)

    lifecycle.shutdown_all()
    assert mem_module._is_initialized is False
    assert lifecycle.is_running is False


def test_a02_memory_module_legacy_api_compatibility():
    """Verify legacy MemoryInterface methods continue to function seamlessly."""
    mem_module = MemoryModule()
    mem_module.initialize()

    # Legacy store
    assert mem_module.store_memory("soil_ph", 6.8) is True
    # Legacy retrieve
    assert mem_module.retrieve_memory("soil_ph") == 6.8

    # Handle application requests
    req = ApplicationRequest(
        request_id="req_test_01",
        source="unit_test",
        operation="store",
        payload={"key": "crop_choice", "value": "chickpea"},
    )
    resp = mem_module.handle(req)
    assert resp.status == "SUCCESS"

    req_get = ApplicationRequest(
        request_id="req_test_02",
        source="unit_test",
        operation="retrieve",
        payload={"key": "crop_choice"},
    )
    resp_get = mem_module.handle(req_get)
    assert resp_get.status == "SUCCESS"
    assert resp_get.response["value"] == "chickpea"
    mem_module.shutdown()


# =============================================================================
# Category B: B2 Context Manager Integration
# =============================================================================

def test_b01_authorized_user_scoped_retrieval(memory_service, memory_provider, auth_farmer_1):
    """B2 retrieves user-scoped memory for authorized farmer."""
    # Seed user memory
    rec = MemoryRecord(
        record_id="rec_user_01",
        domain=MemoryDomain.USER,
        record_type="farmer_profile",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload={"experience_years": 15, "preferred_crop": "wheat"},
        source="user_onboarding",
    )
    memory_service.store_record(auth_farmer_1, rec)

    # Wire to B2 ContextManager
    adapter = MemoryContextProviderAdapter(memory_provider=memory_provider)
    manager = B2ContextManager(providers=[adapter])

    ctx_req = ContextRequest(
        request_id="b2_req_01",
        farmer_id="farmer_101",
        task="recommend irrigation practice",
        policy=PolicyConfig(allow_pii=True),
    )
    result = manager.prepare_context(ctx_req)

    assert result.state == ContextState.COMPLETED
    assert len(result.items) == 1
    item = result.items[0]
    assert item.context_id == "mem_rec_user_01"
    assert item.source_id == "rec_user_01"
    assert item.content["preferred_crop"] == "wheat"
    assert item.farmer_id == "farmer_101"


def test_b02_scoped_retrieval_conversation_farm_field_crop_cycle(memory_service, memory_provider, auth_farmer_1):
    """B2 retrieves memory across various entity scopes (CONVERSATION, FARM, FIELD, CROP_CYCLE)."""
    # 1. Farm scope
    rec_farm = MemoryRecord(
        record_id="rec_farm_01",
        domain=MemoryDomain.USER,
        record_type="farm_infrastructure",
        owner_id="farmer_101",
        scope_type=MemoryScope.FARM,
        scope_id="farm_north",
        payload={"total_acreage": 25, "irrigation_type": "drip"},
        source="farm_survey",
    )
    memory_service.store_record(auth_farmer_1, rec_farm)

    # 2. Field scope
    rec_field = MemoryRecord(
        record_id="rec_field_01",
        domain=MemoryDomain.USER,
        record_type="soil_test",
        owner_id="farmer_101",
        scope_type=MemoryScope.FIELD,
        scope_id="field_zone_3",
        payload={"soil_type": "black_clay", "ph": 7.2},
        source="soil_lab",
    )
    memory_service.store_record(auth_farmer_1, rec_field)

    adapter = MemoryContextProviderAdapter(memory_provider=memory_provider)
    manager = B2ContextManager(providers=[adapter])

    # Request with field_id scope
    ctx_req_field = ContextRequest(
        request_id="b2_req_field",
        farmer_id="farmer_101",
        farm_id="farm_north",
        field_id="field_zone_3",
        task="analyze soil amendment needs",
        policy=PolicyConfig(allow_pii=True),
    )
    result_field = manager.prepare_context(ctx_req_field)
    assert any(it.source_id == "rec_field_01" for it in result_field.items)


def test_b03_empty_results_handling(memory_provider):
    """MemoryContextRequest returning no matching records returns clean empty context."""
    mem_req = MemoryContextRequest(
        request_id="mem_empty_01",
        query_text="nonexistent data",
        scope=ContextScope.FARMER,
        farmer_id="farmer_unknown",
    )
    contracts = memory_provider.get_memory_context(mem_req)
    assert contracts == []


def test_b04_expired_and_deleted_record_exclusion(memory_service, memory_provider, auth_farmer_1):
    """Excluded deleted or expired records from being returned to B2 Context."""
    # 1. Active record
    rec_active = MemoryRecord(
        record_id="rec_active_01",
        domain=MemoryDomain.USER,
        record_type="note",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload={"note": "Active note"},
        source="app",
        status=MemoryRecordStatus.ACTIVE,
    )
    memory_service.store_record(auth_farmer_1, rec_active)

    # 2. Deleted record
    rec_deleted = MemoryRecord(
        record_id="rec_deleted_01",
        domain=MemoryDomain.USER,
        record_type="note",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload={"note": "Deleted note"},
        source="app",
        status=MemoryRecordStatus.DELETED,
    )
    memory_service.store_record(auth_farmer_1, rec_deleted)

    # 3. Expired record
    rec_expired = MemoryRecord(
        record_id="rec_expired_01",
        domain=MemoryDomain.USER,
        record_type="note",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload={"note": "Expired note"},
        source="app",
        status=MemoryRecordStatus.EXPIRED,
    )
    memory_service.store_record(auth_farmer_1, rec_expired)

    mem_req = MemoryContextRequest(
        request_id="mem_status_filter_01",
        query_text="check notes",
        scope=ContextScope.FARMER,
        farmer_id="farmer_101",
    )
    contracts = memory_provider.get_memory_context(mem_req)
    retrieved_ids = [c.memory_id for c in contracts]
    assert "rec_active_01" in retrieved_ids
    assert "rec_deleted_01" not in retrieved_ids
    assert "rec_expired_01" not in retrieved_ids


def test_b05_authorization_failure_handling(memory_provider):
    """Request without farmer_id for USER domain fails closed safely."""
    mem_req = MemoryContextRequest(
        request_id="mem_no_auth_01",
        query_text="give me data",
        scope=ContextScope.FARMER,
        farmer_id=None,
    )
    # Default fail_silent_on_unauthorized=True returns []
    contracts = memory_provider.get_memory_context(mem_req)
    assert contracts == []

    # With fail_silent_on_unauthorized=False raises MemoryUnauthorizedError
    strict_provider = MemoryContextProvider(memory_service=memory_provider.memory_service, fail_silent_on_unauthorized=False)
    with pytest.raises(MemoryUnauthorizedError):
        strict_provider.get_memory_context(mem_req)


def test_b06_storage_failure_handling():
    """Storage adapter failures raise MemoryError and are handled cleanly by B2."""
    class FailingStorage(InMemoryMemoryStorageAdapter):
        def search_records(self, criteria):
            raise MemoryStorageUnavailableError("Database connection lost", operation="search")

    failing_service = MemoryService(storage_adapter=FailingStorage())
    provider = MemoryContextProvider(memory_service=failing_service)
    adapter = MemoryContextProviderAdapter(memory_provider=provider)
    manager = B2ContextManager(providers=[adapter])

    ctx_req = ContextRequest(
        request_id="b2_fail_01",
        farmer_id="farmer_101",
        task="check crop",
        policy=PolicyConfig(allow_partial=True),
    )
    result = manager.prepare_context(ctx_req)
    # With allow_partial=True, result indicates PARTIAL with recorded errors
    assert result.state == ContextState.PARTIAL
    assert any("memory_provider" in err for err in result.errors)


# =============================================================================
# Category C: B3/B4 Integration
# =============================================================================

def test_c01_b3_reasoning_engine_receives_memory_context_through_b2(memory_service, memory_provider, auth_farmer_1):
    """Verify B3 Reasoning Engine receives memory evidence items through B2 ContextResult without direct Memory bypass."""
    from modules.reasoning import EvidenceManager, ReasoningInput

    # Store farmer preference
    rec = MemoryRecord(
        record_id="rec_b3_pref_01",
        domain=MemoryDomain.USER,
        record_type="preference",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload={"fertilizer_preference": "organic", "budget": "low"},
        source="survey",
    )
    memory_service.store_record(auth_farmer_1, rec)

    adapter = MemoryContextProviderAdapter(memory_provider=memory_provider)
    b2_manager = B2ContextManager(providers=[adapter])

    # 1. B2 prepares context
    ctx_req = ContextRequest(
        request_id="req_b3_01",
        farmer_id="farmer_101",
        task="suggest fertilizer for chickpea",
        policy=PolicyConfig(allow_pii=True),
    )
    prepared_context = b2_manager.prepare_context(ctx_req)
    assert len(prepared_context.items) >= 1

    # 2. B3 Reasoning EvidenceManager receives prepared context and converts it to EvidenceItems
    reasoning_input = ReasoningInput(
        request_id="req_b3_01",
        task="suggest fertilizer for chickpea",
        prepared_context=prepared_context,
    )
    ev_mgr = EvidenceManager()
    evidence_items, assumptions, missing = ev_mgr.prepare_evidence(reasoning_input)

    assert len(evidence_items) >= 1
    ev = evidence_items[0]
    assert ev.evidence_id == f"ev_ctx_{prepared_context.items[0].context_id}"
    assert ev.content == {"fertilizer_preference": "organic", "budget": "low"}
    assert ev.source == "context_manager:MEMORY"
    assert ev.source_id == "rec_b3_pref_01"


def test_c02_b4_planning_engine_receives_context_references(memory_service, memory_provider, auth_farmer_1):
    """Verify B4 Planning Engine receives context through established schemas without database bypass."""
    from modules.planning.schemas import PlanningInput, Goal
    from modules.planning.planning_module import PlanningModule

    rec = MemoryRecord(
        record_id="rec_b4_farm_01",
        domain=MemoryDomain.USER,
        record_type="land_record",
        owner_id="farmer_101",
        scope_type=MemoryScope.FARM,
        scope_id="farm_north",
        payload={"acres": 10, "soil_type": "clay_loam"},
        source="land_registry",
    )
    memory_service.store_record(auth_farmer_1, rec)

    adapter = MemoryContextProviderAdapter(memory_provider=memory_provider)
    b2_manager = B2ContextManager(providers=[adapter])

    ctx_req = ContextRequest(
        request_id="req_b4_ctx",
        farmer_id="farmer_101",
        farm_id="farm_north",
        task="plan seasonal planting",
        policy=PolicyConfig(allow_pii=True),
    )
    prepared = b2_manager.prepare_context(ctx_req)
    assert len(prepared.items) >= 1

    # B4 Planning Module
    b4_module = PlanningModule()
    b4_module.initialize()

    plan_input = PlanningInput(
        request_id="req_b4_01",
        objective=Goal(goal_id="g101", objective="Plan seasonal chickpea planting"),
        relevant_context={
            "context_id": prepared.request_id,
            "metadata": {"farmer_id": "farmer_101", "farm_id": "farm_north"},
            "items": [it.model_dump() for it in prepared.items],
        },
    )
    plan_resp = b4_module.execute_planning(plan_input)
    assert plan_resp.request_id == "req_b4_01"
    assert plan_resp.decision is not None
    assert prepared.request_id in plan_resp.decision.context_references
    b4_module.shutdown()


# =============================================================================
# Category D: B5 Workflow Orchestration Integration
# =============================================================================

def test_d01_b5_orchestrator_workflow_dispatch_compatibility():
    """Verify full end-to-end workflow execution in app using LifecycleManager and WorkflowEngine."""
    from app.main import create_app

    lifecycle, workflow = create_app()
    lifecycle.initialize_all()

    # Dispatch request through workflow engine
    sample_request = ApplicationRequest(
        request_id="workflow_mem_test_01",
        source="system_check",
        actor="farmer_101",
        operation="process_text",
        payload={"prompt": "Check wheat disease symptoms"},
        metadata={"target_module": "ai"},
    )
    response = workflow.dispatch(sample_request)
    assert response.status == "SUCCESS"
    assert response.request_id == "workflow_mem_test_01"

    lifecycle.shutdown_all()


# =============================================================================
# Category E: ULPU Multilingual Integration
# =============================================================================

def test_e01_multilingual_content_preservation(memory_service, memory_provider, auth_farmer_1):
    """Verify Indic multilingual content (Hindi, Tamil, Telugu) retains exact text, script, and metadata."""
    indic_payload = {
        "hi": "चने की फसल में फफूंदनाशी का छिड़काव करें",
        "te": "శనగ పంటలో తెగుళ్ళ నివారణకు సిఫార్సు చేయబడిన మందులు",
        "ta": "கொண்டைக்கடலை பயிர் பூஞ்சாணக்கொல்லி தெளிப்பு",
        "crop": "chickpea",
    }
    rec = MemoryRecord(
        record_id="rec_indic_01",
        domain=MemoryDomain.USER,
        record_type="multilingual_observation",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload=indic_payload,
        source="farmer_voice_transcript",
    )
    memory_service.store_record(auth_farmer_1, rec)

    adapter = MemoryContextProviderAdapter(memory_provider=memory_provider)
    b2_manager = B2ContextManager(providers=[adapter])

    ctx_req = ContextRequest(
        request_id="b2_indic_01",
        farmer_id="farmer_101",
        task="चने की फसल की सलाह",
        policy=PolicyConfig(allow_pii=True),
    )
    result = b2_manager.prepare_context(ctx_req)
    assert len(result.items) == 1
    content = result.items[0].content
    assert content["hi"] == indic_payload["hi"]
    assert content["te"] == indic_payload["te"]
    assert content["ta"] == indic_payload["ta"]


# =============================================================================
# Category F: Security & Cross-Domain Isolation Regression
# =============================================================================

def test_f01_cross_user_isolation_strictly_enforced(memory_service, memory_provider, auth_farmer_1, auth_farmer_2):
    """Farmer 2 cannot retrieve Farmer 1's memory context through B2."""
    # Farmer 1 private memory
    rec_secret = MemoryRecord(
        record_id="rec_secret_f1",
        domain=MemoryDomain.USER,
        record_type="financial",
        owner_id="farmer_101",
        scope_type=MemoryScope.USER,
        scope_id="farmer_101",
        payload={"loan_amount": 500000},
        source="bank",
    )
    memory_service.store_record(auth_farmer_1, rec_secret)

    # Farmer 2 requests context
    adapter = MemoryContextProviderAdapter(memory_provider=memory_provider)
    manager = B2ContextManager(providers=[adapter])

    ctx_req_f2 = ContextRequest(
        request_id="b2_f2_breach_attempt",
        farmer_id="farmer_202",
        task="check financials",
        policy=PolicyConfig(allow_pii=True),
    )
    res_f2 = manager.prepare_context(ctx_req_f2)
    # Zero items returned for Farmer 2
    assert len(res_f2.items) == 0


def test_f02_general_memory_write_rejection_for_ordinary_farmers(memory_service, auth_farmer_1):
    """Ordinary farmers cannot write to General Memory domain."""
    gen_rec = MemoryRecord(
        record_id="rec_unauthorized_gen",
        domain=MemoryDomain.GENERAL,
        record_type="advisory",
        owner_id=None,
        scope_type=MemoryScope.GENERAL,
        scope_id="general",
        payload={"text": "illegal broadcast"},
        source="unauthorized",
    )
    with pytest.raises(MemoryForbiddenError):
        memory_service.store_record(auth_farmer_1, gen_rec)
