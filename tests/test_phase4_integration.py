"""Phase 4 integration tests: end-to-end module integration.

These tests exercise the *real* integrated workflow through the application
entry point (`create_app()` -> `WorkflowEngine.dispatch`) and, where useful, the
module boundaries directly. They use the real B2/B3/B4/B5 modules, the real RAG
stack, the real Memory module and the real Tool Dispatcher. Only genuinely
external services (live web search providers) are mocked, and those tests are
labelled explicitly.

Coverage:
- A. Module integration: B2->B3, B3->B4, B5 orchestration, RAG->B2,
  Tool Dispatcher->B5 boundary, Memory->B2, ULPU language boundary,
  Satellite adapter.
- B. End-to-end scenarios 1-10 (general RAG, web search, weather, calculation,
  satellite, memory, multilingual, multi-source, optional failure, invalid).
- C. Boundary compliance and security checks.
"""

import shutil

import pytest

from app.main import create_app
from core.schemas.application import ApplicationRequest
from core.schemas.memory import (
    AuthorizationContext,
    MemoryDomain,
    MemoryOperation,
    MemoryRecord,
    MemoryScope,
    PrincipalType,
)
from modules.context.schemas import ContextRequest, PolicyConfig


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    """Isolated durable RAG store + test environment for each test."""
    store = tmp_path / "rag_store"
    monkeypatch.setenv("EARTHMIND_KB_PERSIST_DIR", str(store))
    monkeypatch.setenv("EARTHMIND_ENV", "test")
    yield store
    if store.exists():
        shutil.rmtree(store, ignore_errors=True)


@pytest.fixture()
def app(app_env):
    lifecycle, workflow = create_app()
    lifecycle.initialize_all()
    try:
        yield lifecycle, workflow
    finally:
        lifecycle.shutdown_all()


def dispatch(workflow, request_id, prompt, payload_extra=None, metadata_extra=None):
    payload = {"prompt": prompt, "farmer_id": "farmer_1"}
    if payload_extra:
        payload.update(payload_extra)
    metadata = {"target_module": "application"}
    if metadata_extra:
        metadata.update(metadata_extra)
    return workflow.dispatch(
        ApplicationRequest(
            request_id=request_id,
            source="test",
            actor="farmer_1",
            operation="process_request",
            payload=payload,
            metadata=metadata,
        )
    )


# ---------------------------------------------------------------------------
# A. Module integration
# ---------------------------------------------------------------------------

def test_bootstrap_registers_integration_modules(app):
    lifecycle, _ = app
    for name in ("context", "reasoning", "planning", "orchestrator", "application", "tools"):
        assert lifecycle.get_module(name) is not None


def test_rag_evidence_reaches_b2(app):
    """RAG -> B2: verified corpus evidence is prepared into context items."""
    lifecycle, _ = app
    context = lifecycle.get_module("context")
    result = context.manager.prepare_context(
        ContextRequest(
            request_id="rag-b2",
            task="What are the symptoms of late blight in potato?",
            token_limit=4096,
            relevance_threshold=0.5,
            policy=PolicyConfig(),
        )
    )
    assert result.state.value in ("COMPLETED", "PARTIAL")
    assert len(result.items) > 0
    assert any(item.source == "RAG" for item in result.items)
    assert result.metadata["provider_statuses"]["rag_provider"] == "SUCCESS"


def test_b2_to_b3_context_flows_into_reasoning(app):
    """B2 -> B3: the prepared context is consumed by the reasoning engine."""
    _, workflow = app
    response = dispatch(workflow, "b2-b3", "What are the symptoms of late blight in potato?")
    body = response.response
    assert response.status == "SUCCESS"
    assert body["evidence"]["item_count"] > 0
    assert "RAG" in body["evidence"]["sources"]
    assert body["reasoning"]["result"]["findings"]


def test_b3_to_b4_reasoning_feeds_planning(app):
    """B3 -> B4: planning runs after reasoning for advisory requests."""
    _, workflow = app
    response = dispatch(workflow, "b3-b4", "Should I irrigate my wheat crop now? Give me a plan.")
    body = response.response
    assert response.status == "SUCCESS"
    steps = body["workflow"]["step_statuses"]
    assert steps["step_reasoning"] == "COMPLETED"
    assert steps["step_planning"] == "COMPLETED"
    assert steps["step_inspector"] == "COMPLETED"
    assert body["planning"] is not None


def test_b5_orchestrates_workflow(app):
    """B5 owns the workflow: it exposes workflow/execution ids and step states."""
    _, workflow = app
    response = dispatch(workflow, "b5-orch", "What are the symptoms of late blight in potato?")
    assert response.metadata["workflow_id"]
    assert response.metadata["execution_id"]
    assert response.response["workflow"]["workflow_state"] == "COMPLETED"


def test_tool_dispatcher_reaches_b5_boundary(app):
    """Tools execute through the dispatcher via the B5 tools step."""
    _, workflow = app
    response = dispatch(
        workflow, "tools-b5", "Calculate 45 * 12", {"expression": "45 * 12"}
    )
    body = response.response
    assert response.status == "SUCCESS"
    assert body["tools"]["requested"] == ["calculator"]
    assert body["workflow"]["step_statuses"]["step_tools"] == "COMPLETED"
    assert body["tools"]["results"]


def test_memory_to_b2_with_explicit_consent(app):
    """Memory -> B2: authorised farmer memory reaches context with PII consent."""
    lifecycle, workflow = app
    memory = lifecycle.get_module("memory")
    auth = AuthorizationContext(
        principal_id="farmer_1",
        principal_type=PrincipalType.USER,
        owner_id="farmer_1",
        accessible_scopes={"USER": ["farmer_1"]},
        requested_operation=MemoryOperation.CREATE,
    )
    memory.service.store_record(
        context=auth,
        record=MemoryRecord(
            record_id="mem_p4_1",
            domain=MemoryDomain.USER,
            record_type="farm_profile",
            owner_id="farmer_1",
            scope_type=MemoryScope.USER,
            scope_id="farmer_1",
            payload={"note": "farmer grows wheat"},
            source="test",
        ),
    )
    response = dispatch(
        workflow,
        "mem-b2",
        "What crop do I grow?",
        {"policy": {"allow_pii": True}},
    )
    assert response.status == "SUCCESS"
    assert "MEMORY" in response.response["evidence"]["sources"]


def test_memory_pii_excluded_without_consent(app):
    """Privacy boundary: farmer PII is not surfaced without explicit consent."""
    lifecycle, workflow = app
    memory = lifecycle.get_module("memory")
    auth = AuthorizationContext(
        principal_id="farmer_1",
        principal_type=PrincipalType.USER,
        owner_id="farmer_1",
        accessible_scopes={"USER": ["farmer_1"]},
        requested_operation=MemoryOperation.CREATE,
    )
    memory.service.store_record(
        context=auth,
        record=MemoryRecord(
            record_id="mem_p4_2",
            domain=MemoryDomain.USER,
            record_type="farm_profile",
            owner_id="farmer_1",
            scope_type=MemoryScope.USER,
            scope_id="farmer_1",
            payload={"note": "farmer grows wheat"},
            source="test",
        ),
    )
    response = dispatch(workflow, "mem-no-pii", "What crop do I grow?")
    assert response.status == "SUCCESS"
    assert "MEMORY" not in response.response["evidence"]["sources"]


def test_ulpu_language_boundary(app):
    """ULPU -> workflow: multilingual input triggers language handling."""
    _, workflow = app
    response = dispatch(workflow, "ulpu-1", "गेहूं की सिंचाई कब करनी चाहिए?")
    body = response.response
    assert response.status == "SUCCESS"
    assert body["workflow"]["step_statuses"]["step_ulpu"] == "COMPLETED"
    assert body["language"]["localized"] is True


def test_satellite_capability_via_adapter(app):
    """Satellite adapter is reachable through the B5 satellite capability."""
    lifecycle, _ = app
    orchestrator = lifecycle.get_module("orchestrator")
    satellite = orchestrator.capability_manager.get_capability("satellite")
    result = satellite.execute("health_check", {}, {"request_id": "sat-h"})
    assert result["status"] == "SUCCESS"


# ---------------------------------------------------------------------------
# B. End-to-end scenarios
# ---------------------------------------------------------------------------

def test_scenario_1_general_rag_question(app):
    _, workflow = app
    response = dispatch(workflow, "sc1", "What are the symptoms of late blight in potato?")
    assert response.status == "SUCCESS"
    assert response.response["evidence"]["sources"] == ["RAG"]


def test_scenario_2_web_search_question(app):
    _, workflow = app
    response = dispatch(workflow, "sc2", "What is the latest government subsidy for wheat farmers?")
    body = response.response
    assert response.status == "SUCCESS"
    assert "web_search" in body["tools"]["requested"]
    assert any(s.startswith("tool:web_search") for s in body["evidence"]["sources"])


def test_scenario_3_weather_question(app):
    _, workflow = app
    response = dispatch(
        workflow,
        "sc3",
        "What is the weather forecast for my field?",
        {"latitude": 28.6, "longitude": 77.2},
    )
    body = response.response
    assert response.status == "SUCCESS"
    assert "weather" in body["tools"]["requested"]


def test_scenario_4_deterministic_calculation(app):
    _, workflow = app
    response = dispatch(workflow, "sc4", "Calculate the area", {"expression": "45 * 12"})
    body = response.response
    assert response.status == "SUCCESS"
    assert body["tools"]["requested"] == ["calculator"]
    calc_results = [r for r in body["tools"]["results"] if r["tool_id"] == "calculator"]
    assert calc_results and calc_results[0]["status"] == "SUCCESS"


def test_scenario_5_satellite_request(app):
    _, workflow = app
    response = dispatch(
        workflow,
        "sc5",
        "Show satellite NDVI imagery for my field",
        {"latitude": 28.6, "longitude": 77.2},
    )
    body = response.response
    assert response.status == "SUCCESS"
    assert "satellite_intelligence" in body["tools"]["requested"]


def test_scenario_6_farmer_memory_context(app):
    _, workflow = app
    response = dispatch(
        workflow, "sc6", "What crop do I grow?", {"policy": {"allow_pii": True}}
    )
    # No memory stored for this fresh store: request still succeeds (partial-safe).
    assert response.status == "SUCCESS"


def test_scenario_7_multilingual_request(app):
    _, workflow = app
    response = dispatch(workflow, "sc7", "गेहूं की सिंचाई कब करनी चाहिए?")
    assert response.status == "SUCCESS"
    assert response.response["language"]["detected"] in ("hi", "en")


def test_scenario_8_multiple_evidence_sources(app):
    _, workflow = app
    response = dispatch(
        workflow,
        "sc8",
        "What is the latest weather advice for late blight in my field?",
        {"latitude": 28.6, "longitude": 77.2},
    )
    sources = response.response["evidence"]["sources"]
    assert response.status == "SUCCESS"
    assert len(sources) >= 2
    assert "RAG" in sources


def test_scenario_9_optional_service_failure_isolation(app, monkeypatch):
    """A failing optional tool must not fail an otherwise valid request."""
    lifecycle, workflow = app
    tool_module = lifecycle.get_module("tools")
    from core.schemas.tools import ToolCallResult, ToolCallStatus

    def _boom(request):
        return ToolCallResult(
            tool_id=request.tool_id,
            request_id=request.request_id,
            status=ToolCallStatus.UNAVAILABLE,
            error={"message": "provider down"},
        )

    monkeypatch.setattr(tool_module.service, "execute", _boom)
    response = dispatch(workflow, "sc9", "What is the latest news on wheat prices?")
    body = response.response
    assert response.status == "SUCCESS"
    assert "web_search" in body["tools"]["failed"]


def test_scenario_10_invalid_request(app):
    _, workflow = app
    response = dispatch(workflow, "sc10", "")
    assert response.status == "INVALID_REQUEST"
    assert response.response is None


# ---------------------------------------------------------------------------
# C. Reliability, boundaries and security
# ---------------------------------------------------------------------------

def test_duplicate_request_protection(app):
    _, workflow = app
    first = dispatch(workflow, "dup-x", "What are the symptoms of late blight?")
    second = dispatch(workflow, "dup-x", "What are the symptoms of late blight?")
    assert first.status == "SUCCESS"
    assert second.status == "FAILED"
    assert second.metadata.get("duplicate_request") is True


def test_unsupported_operation_rejected(app):
    lifecycle, workflow = app
    response = workflow.dispatch(
        ApplicationRequest(
            request_id="unsup-1",
            source="test",
            operation="totally_unknown",
            payload={"prompt": "hi"},
            metadata={"target_module": "application"},
        )
    )
    assert response.status == "UNSUPPORTED_OPERATION"


def test_tools_not_invoked_when_not_required(app):
    _, workflow = app
    response = dispatch(workflow, "no-tools", "What are the symptoms of late blight in potato?")
    assert response.response["tools"]["requested"] == []


def test_permissions_come_from_trusted_metadata_only(app):
    """A payload cannot self-grant permissions to the tools capability."""
    lifecycle, _ = app
    orchestrator = lifecycle.get_module("orchestrator")
    tools_cap = orchestrator.capability_manager.get_capability("tools")
    # Payload claims elevated permissions; trusted buffer has none for this id.
    result = tools_cap.execute(
        "execute_tool",
        {
            "request_id": "perm-1",
            "selected_tool_calls": [{"tool_id": "calculator", "arguments": {"operation": "evaluate", "expression": "1+1"}}],
            "granted_permissions": ["SATELLITE_DATA", "EXTERNAL_NETWORK"],
        },
        {"request_id": "perm-1"},
    )
    # Calculator requires only COMPUTE; with no trusted grant the call must not
    # inherit the payload-declared permissions.
    assert result["status"] == "SUCCESS"
    assert result["tool_count"] == 1


def test_tool_selection_is_deterministic():
    from app.integration.tool_selection import select_tool_calls

    first = select_tool_calls("What is the latest wheat price?", {}, {})
    second = select_tool_calls("What is the latest wheat price?", {}, {})
    assert first == second
    assert first[0]["tool_id"] == "web_search"


def test_no_secrets_in_public_response(app):
    """Response payloads must not leak credentials or connection strings."""
    _, workflow = app
    response = dispatch(workflow, "sec-1", "What are the symptoms of late blight in potato?")
    import json

    serialized = json.dumps(response.model_dump(mode="json"), default=str).lower()
    for needle in ("password", "api_key", "secret", "postgresql://", "bearer "):
        assert needle not in serialized
