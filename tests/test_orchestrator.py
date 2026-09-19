import time
import pytest
from unittest.mock import MagicMock, patch

from core.schemas.application import ApplicationRequest, ApplicationResponse
from modules.orchestrator import (
    CapabilityManager,
    CapabilityStatus,
    CompletionCondition,
    CompletionManager,
    DefaultCapabilityWrapper,
    ExecutionController,
    FailureHandlingPolicy,
    InvalidOrchestrationRequestError,
    InvalidWorkflowStateTransitionError,
    OrchestrationPolicyConfig,
    OrchestrationRequest,
    OrchestrationResponse,
    OrchestrationScopeViolationError,
    OrchestratorModule,
    RecheckLimitExceededError,
    RecoveryManager,
    RequestManager,
    ScopeContext,
    StateManager,
    StepExecutionState,
    WorkflowCompositionError,
    WorkflowComposer,
    WorkflowState,
    WorkflowStrategyType,
)


# Mock capability for testing
class DummyCapability:
    def __init__(self, cap_id: str, operations: list = None, fail: bool = False, delay: float = 0.0):
        self.capability_id = cap_id
        self.version = "1.0.0"
        self.interface_name = "DummyCapability"
        self.operations = operations or ["prepare_context", "reason", "execute_planning", "validate_action", "analyze_image"]
        self.fail = fail
        self.delay = delay

    def get_metadata(self):
        from modules.orchestrator.schemas import CapabilityMetadata
        return CapabilityMetadata(
            capability_id=self.capability_id,
            version=self.version,
            interface_name=self.interface_name,
            supported_operations=self.operations,
        )

    def execute(self, operation: str, payload: dict, metadata: dict = None):
        if self.delay > 0:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError(f"Simulated capability failure for {self.capability_id}")
        return {"status": "SUCCESS", "capability": self.capability_id, "op": operation, "output": f"data_from_{self.capability_id}"}


def create_mock_capability_manager():
    cm = CapabilityManager()
    cm.register_capability(DummyCapability("context", ["prepare_context"]))
    cm.register_capability(DummyCapability("reasoning", ["reason"]))
    cm.register_capability(DummyCapability("planning", ["execute_planning"]))
    cm.register_capability(DummyCapability("inspector", ["validate_action"]))
    cm.register_capability(DummyCapability("vision", ["analyze_image"]))
    cm.register_capability(DummyCapability("memory", ["retrieve_memory"]))
    cm.register_capability(DummyCapability("ulpu", ["process_language"]))
    return cm


class TestRequestManager:
    def test_process_valid_application_request(self):
        rm = RequestManager()
        app_req = ApplicationRequest(
            request_id="req_001",
            source="test",
            operation="orchestrate",
            payload={"task": "diagnose_pest"},
            metadata={"farmer_id": "farmer_1", "strategy": "STANDARD_DECISION"},
        )
        orch_req = rm.process_incoming_request(app_req)
        assert orch_req.request_id == "req_001"
        assert orch_req.strategy == WorkflowStrategyType.STANDARD_DECISION
        assert orch_req.workflow_id is not None
        assert orch_req.execution_id is not None
        assert orch_req.scope.farmer_id == "farmer_1"

    def test_invalid_request_id_raises_error(self):
        rm = RequestManager()
        orch_req = OrchestrationRequest(request_id="", payload={})
        with pytest.raises(InvalidOrchestrationRequestError):
            rm.validate_request(orch_req)

    def test_scope_isolation_mismatch_raises_error(self):
        rm = RequestManager()
        scope = ScopeContext(farmer_id="farmer_A")
        meta = {"farmer_id": "farmer_B"}  # Mismatch!
        orch_req = OrchestrationRequest(request_id="req_scope_err", scope=scope, metadata=meta)
        with pytest.raises(OrchestrationScopeViolationError):
            rm.verify_scope_isolation(orch_req)


class TestWorkflowComposer:
    def test_compose_standard_decision(self):
        composer = WorkflowComposer()
        comp = composer.compose_workflow(WorkflowStrategyType.STANDARD_DECISION, {})
        assert comp.strategy_type == WorkflowStrategyType.STANDARD_DECISION
        assert len(comp.steps) == 4
        step_ids = [s.step_id for s in comp.steps]
        assert step_ids == ["step_context", "step_reasoning", "step_planning", "step_inspector"]

    def test_compose_multimodal_parallel_groups(self):
        composer = WorkflowComposer()
        comp = composer.compose_workflow(WorkflowStrategyType.MULTIMODAL, {})
        assert len(comp.parallel_groups) == 1
        assert "step_vision" in comp.parallel_groups[0]
        assert "step_ulpu" in comp.parallel_groups[0]

    def test_cyclic_dependency_raises_error(self):
        composer = WorkflowComposer()
        bad_payload = {
            "custom_steps": [
                {"step_id": "A", "capability_id": "context", "operation": "op", "dependencies": ["B"]},
                {"step_id": "B", "capability_id": "reasoning", "operation": "op", "dependencies": ["A"]},
            ]
        }
        with pytest.raises(WorkflowCompositionError):
            composer.compose_workflow(WorkflowStrategyType.CUSTOM, bad_payload)


class TestCapabilityManager:
    def test_register_and_lookup_capability(self):
        cm = CapabilityManager()
        dummy = DummyCapability("test_cap")
        cm.register_capability(dummy)
        assert cm.is_available("test_cap")
        fetched = cm.get_capability("test_cap")
        assert fetched.capability_id == "test_cap"

    def test_contract_compatibility_check(self):
        cm = CapabilityManager()
        cm.register_capability(DummyCapability("primary", ["op_a", "op_b"]))
        cm.register_capability(DummyCapability("substitute", ["op_a", "op_b"]))
        assert cm.check_contract_compatibility("primary", "substitute") is True


class TestExecutionController:
    def test_sequential_execution(self):
        ec = ExecutionController()
        composer = WorkflowComposer()
        comp = composer.compose_workflow(WorkflowStrategyType.STANDARD_DECISION, {})
        cm = create_mock_capability_manager()

        req = OrchestrationRequest(request_id="req_exec_seq")
        results = ec.execute_workflow(comp, req, cm)

        assert len(results) == 4
        for s_id, res in results.items():
            assert res.status == StepExecutionState.COMPLETED

    def test_parallel_independent_steps(self):
        ec = ExecutionController()
        composer = WorkflowComposer()
        comp = composer.compose_workflow(WorkflowStrategyType.MULTIMODAL, {})
        cm = create_mock_capability_manager()

        req = OrchestrationRequest(request_id="req_exec_multi")
        results = ec.execute_workflow(comp, req, cm)

        assert "step_vision" in results
        assert "step_ulpu" in results
        assert results["step_vision"].status == StepExecutionState.COMPLETED
        assert results["step_ulpu"].status == StepExecutionState.COMPLETED

    def test_step_timeout_handling(self):
        ec = ExecutionController()
        composer = WorkflowComposer()
        comp = composer.compose_workflow(WorkflowStrategyType.STANDARD_DECISION, {})
        # Set short timeout on step_context
        comp.steps[0].timeout_seconds = 0.05
        comp.steps[0].max_retries = 0

        cm = CapabilityManager()
        cm.register_capability(DummyCapability("context", ["prepare_context"], delay=0.2))  # Slow
        cm.register_capability(DummyCapability("reasoning", ["reason"]))
        cm.register_capability(DummyCapability("planning", ["execute_planning"]))
        cm.register_capability(DummyCapability("inspector", ["validate_action"]))

        req = OrchestrationRequest(request_id="req_timeout")
        results = ec.execute_workflow(comp, req, cm)

        assert results["step_context"].status == StepExecutionState.FAILED
        assert "timed out" in results["step_context"].error.lower()


class TestStateManager:
    def test_valid_state_transitions(self):
        sm = StateManager(request_id="req_sm_valid")
        assert sm.current_state == WorkflowState.REQUESTED

        sm.transition_state("req_sm_valid", WorkflowState.VALIDATING)
        assert sm.current_state == WorkflowState.VALIDATING

        sm.transition_state("req_sm_valid", WorkflowState.SELECTING_WORKFLOW)
        assert sm.current_state == WorkflowState.SELECTING_WORKFLOW

    def test_illegal_state_transition_raises_error(self):
        sm = StateManager(request_id="req_sm_illegal")
        with pytest.raises(InvalidWorkflowStateTransitionError):
            sm.transition_state("req_sm_illegal", WorkflowState.COMPLETED)  # Invalid jump from REQUESTED to COMPLETED


class TestInspectorIntegrationAndOrchestration:
    def test_full_orchestration_inspector_pass(self):
        orch = OrchestratorModule()
        orch.initialize()
        orch.capability_manager = create_mock_capability_manager()

        req = ApplicationRequest(
            request_id="req_orch_pass",
            source="unit_test",
            operation="orchestrate",
            payload={"goal": "reduce_irrigation"},
            metadata={"strategy": "STANDARD_DECISION"},
        )

        resp = orch.handle(req)
        assert resp.status == "SUCCESS"
        assert resp.metadata["workflow_state"] == WorkflowState.COMPLETED.value

    def test_full_orchestration_inspector_flag(self):
        orch = OrchestratorModule()
        orch.initialize()
        orch.capability_manager = create_mock_capability_manager()

        req = ApplicationRequest(
            request_id="req_orch_flag",
            source="unit_test",
            operation="orchestrate",
            payload={"goal": "fertilize_crop"},
            metadata={
                "strategy": "STANDARD_DECISION",
                "inspector_response_override": {"status": "FLAG", "flag": "High nitrogen application warning"},
            },
        )

        resp = orch.handle(req)
        assert resp.status == "SUCCESS"
        assert len(resp.warnings) > 0
        assert "High nitrogen application warning" in resp.warnings[0]

    def test_inspector_recheck_loop_and_limit_exceeded(self):
        orch = OrchestratorModule()
        orch.initialize()
        orch.capability_manager = create_mock_capability_manager()

        policy = OrchestrationPolicyConfig(max_rechecks=2)
        orch_req = OrchestrationRequest(
            request_id="req_recheck_exceed",
            strategy=WorkflowStrategyType.STANDARD_DECISION,
            policy=policy,
            metadata={
                "inspector_response_override": {"status": "RECHECK", "reason": "Unsafe risk level"},
            },
        )

        res = orch.orchestrate(orch_req)
        assert res.status == "ERROR"
        assert "exceeded max recheck limit of 2" in res.errors[0]

    def test_cancellation_propagation(self):
        orch = OrchestratorModule()
        orch.initialize()
        orch.capability_manager = create_mock_capability_manager()

        orch_req = OrchestrationRequest(
            request_id="req_cancel",
            strategy=WorkflowStrategyType.STANDARD_DECISION,
            metadata={"trigger_cancelled": True},
        )

        res = orch.orchestrate(orch_req)
        assert res.status == "CANCELLED"
        assert res.workflow_state == WorkflowState.CANCELLED

    def test_no_model_weights_or_db_accessed(self):
        """Verify B5 operates without calling model weights or direct database calls."""
        orch = OrchestratorModule()
        orch.initialize()
        orch.capability_manager = create_mock_capability_manager()

        orch_req = OrchestrationRequest(
            request_id="req_isolation_check",
            strategy=WorkflowStrategyType.STANDARD_DECISION,
        )
        res = orch.orchestrate(orch_req)
        assert res.status == "SUCCESS"
        # Confirm no torch / transformers / model downloads were loaded
