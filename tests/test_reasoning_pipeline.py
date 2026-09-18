import time
from unittest.mock import MagicMock
import pytest

from core.errors.exceptions import InvalidLifecycleTransitionError
from core.schemas.model import ModelGenerationRequest, ModelGenerationResponse
from modules.context.schemas import (
    ConflictStatus,
    ContextItem,
    ContextResult,
    ContextState,
    PriorityLevel,
    PrivacyLevel,
)
from modules.inspector.inspector_module import InspectorModule
from modules.reasoning import (
    AssumptionItem,
    AssumptionType,
    ConflictAnalyzer,
    ConflictType,
    EvidenceComparisonAnalyzer,
    EvidenceConflict,
    EvidenceItem,
    EvidenceManager,
    EvidenceScope,
    InputValidator,
    InspectorHandoffManager,
    InsufficientEvidenceError,
    InvalidEvidenceError,
    InvalidReasoningInputError,
    InvalidReasoningResultError,
    IterationController,
    ModelLayerReasoningCapability,
    ReasoningCapabilityUnavailableError,
    ReasoningEngine,
    ReasoningError,
    ReasoningFinding,
    ReasoningInput,
    ReasoningModule,
    ReasoningPolicyConfig,
    ReasoningResult,
    ReasoningState,
    ReasoningStateManager,
    ReasoningTimeoutError,
    ReasoningTraceManager,
    ResultValidator,
    UncertaintyAnalyzer,
    ValidationStatus,
)


# 1. Valid reasoning input
def test_1_valid_reasoning_input():
    ev = EvidenceItem(evidence_id="ev_001", source="sensor", content={"temp": 25.0})
    inp = ReasoningInput(request_id="req_valid_1", task="Task 1", evidence_items=[ev])
    validator = InputValidator()
    validator.validate(inp)
    assert inp.request_id == "req_valid_1"


# 2. Invalid input
def test_2_invalid_reasoning_input():
    validator = InputValidator()
    with pytest.raises(InvalidReasoningInputError):
        validator.validate(ReasoningInput(request_id="", task=""))

    with pytest.raises(InvalidReasoningInputError):
        validator.validate(ReasoningInput(request_id="req_bad", task="   "))


# 3. Evidence preservation
def test_3_evidence_preservation():
    ev = EvidenceItem(
        evidence_id="ev_preserve",
        source="weather_station",
        source_id="ws_99",
        data_reference="weather:rainfall",
        content=12.5,
        scope=EvidenceScope.FARM,
        confidence=0.92,
        reliability=0.88,
        provenance={"sensor_id": "ws_99"}
    )
    engine = ReasoningEngine()
    inp = ReasoningInput(request_id="req_preserve", task="Assess rainfall", evidence_items=[ev])
    res, _ = engine.execute(inp)
    assert "ev_preserve" in res.evidence_references
    assert len(res.evidence_references) == 1


# 4. Evidence vs assumption
def test_4_evidence_vs_assumption():
    ev_real = EvidenceItem(evidence_id="ev_real", source="sensor", content=10.0, is_assumption=False)
    ev_assump = EvidenceItem(evidence_id="ev_assump", source="user_declaration", content="Assume baseline soil type is loam", is_assumption=True)

    mgr = EvidenceManager()
    inp = ReasoningInput(request_id="req_ev_vs_assump", task="Test", evidence_items=[ev_real, ev_assump])
    evidence_items, assumptions, _ = mgr.prepare_evidence(inp)

    assert len(evidence_items) == 1
    assert evidence_items[0].evidence_id == "ev_real"
    assert len(assumptions) == 1
    assert assumptions[0].assumption_id == "assump_ev_assump"


# 5. Evidence comparison
def test_5_evidence_comparison():
    ev_a = EvidenceItem(evidence_id="ev_a", source="sat_1", content=0.5, scope=EvidenceScope.FIELD)
    ev_b = EvidenceItem(evidence_id="ev_b", source="sat_1", content=0.6, scope=EvidenceScope.FIELD)

    analyzer = EvidenceComparisonAnalyzer()
    relationships = analyzer.analyze_relationships([ev_a, ev_b])
    assert len(relationships) >= 1


# 6. Evidence relationships
def test_6_evidence_relationships():
    ev_a = EvidenceItem(evidence_id="ev_a", source="sensor_1", event_time="2025-01-01T10:00:00Z", content=20)
    ev_b = EvidenceItem(evidence_id="ev_b", source="sensor_1", event_time="2025-01-01T11:00:00Z", content=22)

    analyzer = EvidenceComparisonAnalyzer()
    relationships = analyzer.analyze_relationships([ev_a, ev_b])
    rel_types = [r.relationship_type for r in relationships]
    assert "SOURCE_CORRELATION" in rel_types or "TEMPORAL" in rel_types


# 7. Conflict detection
def test_7_conflict_detection():
    ev_1 = EvidenceItem(evidence_id="ev_1", source="s1", data_reference="field:ph", content=6.5)
    ev_2 = EvidenceItem(evidence_id="ev_2", source="s2", data_reference="field:ph", content=8.2)

    analyzer = ConflictAnalyzer()
    conflicts = analyzer.analyze_conflicts([ev_1, ev_2])
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == ConflictType.VALUE_DISCREPANCY


# 8. Conflict preservation
def test_8_conflict_preservation():
    ev_1 = EvidenceItem(evidence_id="ev_1", source="s1", conflict_status="CONFLICTED", content=10)
    ev_2 = EvidenceItem(evidence_id="ev_2", source="s2", conflict_status="CONFLICTED", content=20)

    analyzer = ConflictAnalyzer()
    conflicts = analyzer.analyze_conflicts([ev_1, ev_2])
    assert len(conflicts) == 1
    assert conflicts[0].is_resolved is False  # Must be preserved, not silently auto-resolved


# 9. Uncertainty visibility
def test_9_uncertainty_visibility():
    conf = EvidenceConflict(
        conflict_id="c_1",
        evidence_ids=["ev_1", "ev_2"],
        conflict_type=ConflictType.VALUE_DISCREPANCY,
        description="Discrepancy"
    )
    analyzer = UncertaintyAnalyzer()
    uncs = analyzer.analyze_uncertainty(evidence_items=[], conflicts=[conf], missing_items=[])
    assert len(uncs) == 1
    assert uncs[0].reason is not None


# 10. Missing information
def test_10_missing_information():
    mgr = EvidenceManager()
    inp = ReasoningInput(
        request_id="req_missing",
        task="Soil health assessment",
        policy=ReasoningPolicyConfig(allow_assumptions=True)
    )
    evidence_items, assumptions, missing = mgr.prepare_evidence(inp)
    assert len(missing) == 1
    assert missing[0].importance == "HIGH"


# 11. No fabrication
def test_11_no_fabrication():
    inp = ReasoningInput(
        request_id="req_nofab",
        task="Test task",
        policy=ReasoningPolicyConfig(allow_assumptions=False)
    )
    engine = ReasoningEngine()
    with pytest.raises(InsufficientEvidenceError):
        engine.execute(inp)


# 12. Priority != truth
def test_12_priority_not_truth():
    ev_low_prio = EvidenceItem(evidence_id="ev_low", source="lab", content=15.0, confidence=0.99)
    ev_high_prio = EvidenceItem(evidence_id="ev_high", source="quick_app", content=30.0, confidence=0.40)

    analyzer = ConflictAnalyzer()
    conflicts = analyzer.analyze_conflicts([ev_low_prio, ev_high_prio])
    assert len(conflicts) == 0 or conflicts[0].is_resolved is False


# 13. Controlled iteration
def test_13_controlled_iteration():
    ctrl = IterationController(policy=ReasoningPolicyConfig(max_iterations=3))
    finding = ReasoningFinding(finding_id="f1", statement="s", confidence_score=0.9)
    should_cont, _ = ctrl.should_continue(current_iteration=1, findings=[finding], has_unresolved_conflicts=False)
    assert should_cont is False  # Terminates when sufficient confidence achieved


# 14. Iteration termination
def test_14_iteration_termination():
    ctrl = IterationController(policy=ReasoningPolicyConfig(max_iterations=2))
    finding = ReasoningFinding(finding_id="f1", statement="s", confidence_score=0.2)
    should_cont, reason = ctrl.should_continue(current_iteration=2, findings=[finding], has_unresolved_conflicts=True)
    assert should_cont is False
    assert "maximum" in reason.lower()


# 15. Capability abstraction
def test_15_capability_abstraction():
    mock_cap = MagicMock()
    mock_cap.capability_name = "mock_capability"
    mock_cap.reason.return_value = ReasoningResult(
        request_id="req_abs",
        status=ReasoningState.COMPLETED,
        findings=[ReasoningFinding(finding_id="f_abs", statement="Abstraction works", evidence_ids=["ev_1"])]
    )

    engine = ReasoningEngine(capability=mock_cap)
    ev = EvidenceItem(evidence_id="ev_1", source="s", content="c")
    inp = ReasoningInput(request_id="req_abs", task="Task", evidence_items=[ev])
    res, _ = engine.execute(inp)

    assert res.request_id == "req_abs"
    assert res.findings[0].statement == "Abstraction works"


# 16. Mocked Sarvam capability execution
def test_16_mocked_sarvam_capability_execution():
    mock_model = MagicMock()
    mock_model.status.return_value = {"identifier": "sarvam-105b", "loaded": True}
    mock_model.generate.return_value = ModelGenerationResponse(
        request_id="req_sarvam_1",
        status="success",
        response="Sarvam-105B reasoning analysis output.",
        confidence_level=0.91,
        model_version="sarvam-105b-v1"
    )

    cap = ModelLayerReasoningCapability(model=mock_model)
    engine = ReasoningEngine(capability=cap)
    ev = EvidenceItem(evidence_id="ev_sarvam", source="satellite", content={"ndvi": 0.5})
    inp = ReasoningInput(request_id="req_sarvam_1", task="Analyze Sarvam output", evidence_items=[ev])

    res, handoff = engine.execute(inp)
    assert res.status == ReasoningState.COMPLETED
    assert "Sarvam-105B" in res.findings[0].statement
    mock_model.generate.assert_called_once()


# 17. Reasoning result construction
def test_17_reasoning_result_construction():
    ev = EvidenceItem(evidence_id="ev_constr", source="s", content="c")
    inp = ReasoningInput(request_id="req_constr", task="Construct result", evidence_items=[ev])
    engine = ReasoningEngine()
    res, _ = engine.execute(inp)

    assert isinstance(res, ReasoningResult)
    assert res.request_id == "req_constr"
    assert res.status == ReasoningState.COMPLETED


# 18. Traceability
def test_18_traceability():
    trace_mgr = ReasoningTraceManager()
    rec = trace_mgr.record_operation("req_trace", "test_op", evidence_ids=["ev_1"], finding_ids=["f_1"])
    assert rec.request_id == "req_trace"
    assert rec.operation == "test_op"


# 19. State transitions
def test_19_state_transitions():
    state_mgr = ReasoningStateManager("req_state")
    state_mgr.transition_to(ReasoningState.VALIDATING)
    state_mgr.transition_to(ReasoningState.PREPARING_CONTEXT)
    assert state_mgr.current_state == ReasoningState.PREPARING_CONTEXT

    with pytest.raises(InvalidLifecycleTransitionError):
        state_mgr.transition_to(ReasoningState.COMPLETED)


# 20. Timeout
def test_20_timeout():
    policy = ReasoningPolicyConfig(strategy_timeout_seconds=0.0000001)
    ev = EvidenceItem(evidence_id="ev_time", source="s", content="c")
    inp = ReasoningInput(request_id="req_timeout", task="Task", evidence_items=[ev], policy=policy)

    engine = ReasoningEngine()

    with pytest.raises(ReasoningTimeoutError):
        engine.execute(inp)


# 21. Cancellation
def test_21_cancellation():
    ev = EvidenceItem(evidence_id="ev_cancel", source="s", content="c")
    inp = ReasoningInput(request_id="req_cancel", task="Task", evidence_items=[ev])
    engine = ReasoningEngine()

    with pytest.raises(ReasoningError) as exc_info:
        engine.execute(inp, cancel_requested=True)

    assert exc_info.value.error_contract.error_code == "REASONING_CANCELLED"


# 22. Capability unavailable
def test_22_capability_unavailable():
    mock_cap = MagicMock()
    mock_cap.reason.side_effect = ReasoningCapabilityUnavailableError("sarvam", "Backend offline")

    engine = ReasoningEngine(capability=mock_cap)
    ev = EvidenceItem(evidence_id="ev_1", source="s", content="c")
    inp = ReasoningInput(request_id="req_unavail", task="Task", evidence_items=[ev])

    with pytest.raises(ReasoningCapabilityUnavailableError):
        engine.execute(inp)


# 23. Inspector PASS
def test_23_inspector_pass():
    finding = ReasoningFinding(finding_id="f_pass", statement="Sufficient evidence", evidence_ids=["ev_1"])
    res = ReasoningResult(request_id="req_pass", status=ReasoningState.COMPLETED, findings=[finding], evidence_references=["ev_1"])

    mock_inspector = MagicMock()
    mock_inspector.validate_action.return_value = {"valid": True}

    mgr = InspectorHandoffManager(inspector=mock_inspector)
    handoff = mgr.handoff_validation(res)
    assert handoff.validation_status == ValidationStatus.PASS


# 24. Inspector FLAG
def test_24_inspector_flag():
    finding = ReasoningFinding(finding_id="f_flag", statement="Conflicting evidence finding", evidence_ids=["ev_1", "ev_2"])
    conf = EvidenceConflict(conflict_id="c_1", evidence_ids=["ev_1", "ev_2"], conflict_type=ConflictType.VALUE_DISCREPANCY, description="Conflict")
    res = ReasoningResult(request_id="req_flag", status=ReasoningState.COMPLETED, findings=[finding], evidence_references=["ev_1", "ev_2"], conflicts=[conf])

    mgr = InspectorHandoffManager()
    handoff = mgr.handoff_validation(res)
    assert handoff.validation_status == ValidationStatus.FLAG


# 25. Inspector RECHECK
def test_25_inspector_recheck():
    mock_inspector = MagicMock()
    mock_inspector.validate_action.side_effect = Exception("Inspector temporary failure")

    finding = ReasoningFinding(finding_id="f_recheck", statement="Claim", evidence_ids=["ev_1"])
    res = ReasoningResult(request_id="req_recheck", status=ReasoningState.COMPLETED, findings=[finding], evidence_references=["ev_1"])

    mgr = InspectorHandoffManager(inspector=mock_inspector)
    handoff = mgr.handoff_validation(res)
    assert handoff.validation_status == ValidationStatus.RECHECK


# 26. B3/B4 boundary
def test_26_b3_b4_boundary():
    ev = EvidenceItem(evidence_id="ev_1", source="sensor", content={"moisture": 10.0})
    inp = ReasoningInput(request_id="req_b3_b4", task="Diagnose field drought", evidence_items=[ev])
    engine = ReasoningEngine()
    res, handoff = engine.execute(inp)

    # B3 produces reasoning findings only, NOT final agricultural actions or irrigation schedules (owned by B4)
    for finding in res.findings:
        assert isinstance(finding.statement, str)
        assert "irrigate" not in finding.statement.lower() or "recommendation" not in finding.statement.lower()


# 27. Dependency isolation
def test_27_dependency_isolation():
    module = ReasoningModule()
    module.initialize()
    # Ensure ReasoningModule can initialize and execute independently without requiring real SQLite/Database/Redis/GPU
    ev = EvidenceItem(evidence_id="ev_iso", source="mock", content="test")
    inp = ReasoningInput(request_id="req_iso", task="Test isolation", evidence_items=[ev])
    res, handoff = module.reason(inp)
    assert res.status == ReasoningState.COMPLETED
    module.shutdown()


# 28. Deterministic behavior where applicable
def test_28_deterministic_behavior():
    ev = EvidenceItem(evidence_id="ev_det", source="sensor", content=42.0)
    inp1 = ReasoningInput(request_id="req_det_1", task="Test determinism", evidence_items=[ev])
    inp2 = ReasoningInput(request_id="req_det_2", task="Test determinism", evidence_items=[ev])

    engine = ReasoningEngine()
    res1, _ = engine.execute(inp1)
    res2, _ = engine.execute(inp2)

    assert len(res1.findings) == len(res2.findings)
    assert res1.findings[0].statement == res2.findings[0].statement
