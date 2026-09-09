from app.lifecycle import LifecycleManager
from app.workflow import WorkflowEngine
from core.schemas.application import ApplicationRequest
from modules.ai.ai_module import AIModule
from modules.inspector.inspector_module import InspectorModule

def test_workflow_engine_dispatch():
    lifecycle = LifecycleManager()
    ai = AIModule()
    inspector = InspectorModule()

    lifecycle.register_module("ai", ai)
    lifecycle.register_module("inspector", inspector)
    lifecycle.initialize_all()

    engine = WorkflowEngine(lifecycle)

    req = ApplicationRequest(
        request_id="req-201",
        source="unit_test",
        operation="process_text",
        payload={"prompt": "Hello EarthMind"},
        metadata={"target_module": "ai"}
    )

    resp = engine.dispatch(req)
    assert resp.request_id == "req-201"
    assert resp.status == "SUCCESS"
    assert "AI Processing Result" in resp.response["text"]

    lifecycle.shutdown_all()

def test_workflow_engine_missing_target():
    lifecycle = LifecycleManager()
    engine = WorkflowEngine(lifecycle)

    req = ApplicationRequest(
        request_id="req-202",
        source="unit_test",
        operation="unknown",
        metadata={"target_module": "non_existent"}
    )

    resp = engine.dispatch(req)
    assert resp.status == "ERROR"
    assert len(resp.warnings) > 0
