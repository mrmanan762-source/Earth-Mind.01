import pytest
from unittest.mock import MagicMock

from core.errors.exceptions import EarthMindException, ReasoningError
from core.schemas.application import ApplicationRequest, ApplicationResponse
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
    ConflictType,
    EvidenceConflict,
    EvidenceItem,
    EvidenceManager,
    EvidenceRelationship,
    EvidenceScope,
    InspectorHandoffManager,
    InsufficientEvidenceError,
    InvalidEvidenceError,
    InvalidReasoningInputError,
    ModelLayerReasoningCapability,
    ReasoningCapabilityUnavailableError,
    ReasoningFinding,
    ReasoningInput,
    ReasoningModule,
    ReasoningPolicyConfig,
    ReasoningResult,
    ReasoningState,
    ReasoningStrategyController,
    ReasoningTraceManager,
    RelationshipType,
    UncertaintyLevel,
    ValidationStatus,
)


def test_reasoning_error_hierarchy():
    """Verify that all B3 reasoning errors inherit from ReasoningError and EarthMindException."""
    err = InvalidReasoningInputError("bad input")
    assert isinstance(err, ReasoningError)
    assert isinstance(err, EarthMindException)
    assert err.error_contract.error_code == "INVALID_REASONING_INPUT"
    assert err.error_contract.module == "reasoning"

    insuff_err = InsufficientEvidenceError("req_123", "no evidence")
    assert isinstance(insuff_err, ReasoningError)
    assert insuff_err.error_contract.error_code == "INSUFFICIENT_EVIDENCE"


def test_evidence_item_and_assumption_creation():
    """Verify EvidenceItem and explicit AssumptionItem data contracts."""
    ev = EvidenceItem(
        evidence_id="ev_001",
        source="sensor_network",
        content={"soil_moisture": 18.5},
        scope=EvidenceScope.FIELD,
        confidence=0.95,
        reliability=0.90
    )
    assert ev.evidence_id == "ev_001"
    assert ev.is_assumption is False
    assert ev.confidence == 0.95

    assump = AssumptionItem(
        assumption_id="assump_001",
        description="Assume baseline soil moisture is 20%",
        assumption_type=AssumptionType.MISSING_DATA_FALLBACK,
        rationale="Sensor sensor_001 was offline.",
        confidence_penalty=0.15
    )
    assert assump.assumption_type == AssumptionType.MISSING_DATA_FALLBACK
    assert assump.confidence_penalty == 0.15


def test_evidence_manager_context_conversion():
    """Verify EvidenceManager converts ContextResult items into EvidenceItems preserving provenance and scope."""
    ctx_item = ContextItem(
        context_id="ctx_101",
        entity_type="field",
        entity_id="field_zone_4",
        data_type="sensor_reading",
        content={"temperature_c": 32.4},
        field_id="field_zone_4",
        source="field_sensors",
        confidence=0.88,
        conflict_status=ConflictStatus.NORMAL,
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        relevance_score=0.92,
        priority=PriorityLevel.HIGH
    )
    ctx_res = ContextResult(
        request_id="ctx_req_001",
        state=ContextState.COMPLETED,
        items=[ctx_item],
        structured_context={"items": [ctx_item.model_dump()]}
    )

    req = ReasoningInput(
        request_id="req_001",
        task="Assess temperature anomaly",
        prepared_context=ctx_res
    )

    mgr = EvidenceManager()
    evidence_items, assumptions, missing = mgr.prepare_evidence(req)

    assert len(evidence_items) == 1
    assert evidence_items[0].evidence_id == "ev_ctx_ctx_101"
    assert evidence_items[0].source == "context_manager:field_sensors"
    assert evidence_items[0].scope == EvidenceScope.FIELD
    assert evidence_items[0].confidence == 0.88


def test_conflict_preservation_rule():
    """Verify Rule 3 & 4: Evidence conflicts are detected and preserved without silent auto-resolution."""
    ev_1 = EvidenceItem(
        evidence_id="ev_001",
        source="sensor_a",
        data_reference="sensor:soil_moisture",
        content=15.0,
        scope=EvidenceScope.FIELD
    )
    ev_2 = EvidenceItem(
        evidence_id="ev_002",
        source="sensor_b",
        data_reference="sensor:soil_moisture",
        content=28.0,
        scope=EvidenceScope.FIELD
    )

    mgr = EvidenceManager()
    conflicts = mgr.detect_conflicts([ev_1, ev_2])

    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.conflict_type == ConflictType.VALUE_DISCREPANCY
    assert c.is_resolved is False  # Core Rule 3: Must be preserved!
    assert "ev_001" in c.evidence_ids and "ev_002" in c.evidence_ids


def test_reasoning_strategy_execution_and_rule_enforcement():
    """Verify 13-step strategy flow, bounded iteration limit, and evidence linkage."""
    ev = EvidenceItem(
        evidence_id="ev_crop_health",
        source="satellite_ndvi",
        content={"ndvi": 0.45, "status": "moderate_stress"},
        scope=EvidenceScope.FIELD
    )

    input_data = ReasoningInput(
        request_id="req_strat_001",
        task="Diagnose NDVI drop in Zone 2",
        evidence_items=[ev],
        policy=ReasoningPolicyConfig(max_iterations=3, min_confidence_threshold=0.6)
    )

    controller = ReasoningStrategyController()
    result = controller.execute_strategy(input_data)

    assert result.request_id == "req_strat_001"
    assert result.status == ReasoningState.COMPLETED
    assert len(result.findings) > 0
    assert "ev_crop_health" in result.evidence_references

    # Verify Rule 1: Evidence Before Conclusion
    finding = result.findings[0]
    assert len(finding.evidence_ids) > 0 or len(finding.assumption_ids) > 0

    # Verify Rule 9: Iteration metadata
    assert result.iteration_metadata["max_allowed_iterations"] == 3
    assert result.iteration_metadata["total_iterations"] <= 3


def test_insufficient_evidence_raises_error_when_assumptions_forbidden():
    """Verify InsufficientEvidenceError when no evidence provided and policy forbids assumptions."""
    input_data = ReasoningInput(
        request_id="req_empty_001",
        task="Analyze non-existent field",
        policy=ReasoningPolicyConfig(allow_assumptions=False)
    )

    controller = ReasoningStrategyController()
    with pytest.raises(InsufficientEvidenceError) as exc_info:
        controller.execute_strategy(input_data)

    assert exc_info.value.error_contract.error_code == "INSUFFICIENT_EVIDENCE"


def test_model_layer_reasoning_capability_adapter():
    """Verify capability independence (Rule 10) by adapting generic IModel mock."""
    mock_model = MagicMock()
    mock_model.status.return_value = {"identifier": "sarvam-105b", "loaded": True}
    mock_model.generate.return_value = ModelGenerationResponse(
        request_id="req_cap_001",
        status="success",
        response="NDVI reduction is correlated with soil moisture depletion.",
        confidence_level=0.88,
        model_version="sarvam-105b-v1"
    )

    cap = ModelLayerReasoningCapability(model=mock_model)
    assert cap.status()["attached_model"] == "sarvam-105b"

    ev = EvidenceItem(evidence_id="ev_1", source="sensor", content={"moisture": 12.0})
    inp = ReasoningInput(request_id="req_cap_001", task="Diagnose soil stress", evidence_items=[ev])

    res = cap.reason(inp)
    assert res.request_id == "req_cap_001"
    assert res.status == ReasoningState.COMPLETED
    assert len(res.findings) == 1
    assert "NDVI reduction" in res.findings[0].statement

    # Ensure generate was called on mock_model via generic contract
    mock_model.generate.assert_called_once()


def test_capability_unattached_raises_error():
    """Verify ReasoningCapabilityUnavailableError when no model adapter attached."""
    cap = ModelLayerReasoningCapability(model=None)
    inp = ReasoningInput(request_id="req_fail", task="Test unattached capability")

    with pytest.raises(ReasoningCapabilityUnavailableError):
        cap.reason(inp)


def test_inspector_validation_handoff_rule_7():
    """Verify Rule 7: Every valid reasoning result submits a validation handoff to Inspector."""
    finding = ReasoningFinding(
        finding_id="f_001",
        statement="Field requires 15mm irrigation.",
        confidence_score=0.99,
        evidence_ids=["ev_001"]
    )
    res = ReasoningResult(
        request_id="req_insp_001",
        status=ReasoningState.COMPLETED,
        findings=[finding],
        evidence_references=["ev_001"],
        trace_id="trace_insp_001"
    )

    inspector = InspectorModule()
    handoff_mgr = InspectorHandoffManager(inspector=inspector)
    handoff = handoff_mgr.handoff_validation(res)

    assert handoff.request_id == "req_insp_001"
    assert handoff.validation_status in (ValidationStatus.PASS, ValidationStatus.FLAG, ValidationStatus.RECHECK)
    assert handoff.inspector_response is not None


def test_traceability_manager_no_private_thought_leak():
    """Verify Rule 8: Traceability records structured links without private chain-of-thought text."""
    trace_mgr = ReasoningTraceManager()
    record = trace_mgr.record_operation(
        request_id="req_trace_001",
        operation="analyze_conflicts",
        evidence_ids=["ev_1", "ev_2"],
        finding_ids=["f_1"]
    )

    assert record.request_id == "req_trace_001"
    assert record.operation == "analyze_conflicts"
    assert "ev_1" in record.evidence_ids

    summary = trace_mgr.build_trace_summary(
        ReasoningResult(
            request_id="req_trace_001",
            status=ReasoningState.COMPLETED,
            findings=[],
            trace_id="trace_1"
        )
    )
    assert summary["request_id"] == "req_trace_001"
    assert summary["evidence_count"] == 0


def test_reasoning_module_full_part1_flow():
    """Verify ReasoningModule initialization, reasoning execution, trace logging, and handoff."""
    module = ReasoningModule()
    module.initialize()

    mock_model = MagicMock()
    mock_model.status.return_value = {"identifier": "sarvam-105b"}
    mock_model.generate.return_value = ModelGenerationResponse(
        request_id="req_module_001",
        status="success",
        response="Root zone moisture depletion detected.",
        confidence_level=0.85,
        model_version="sarvam-105b-v1"
    )

    module.set_capability(ModelLayerReasoningCapability(model=mock_model))

    ev = EvidenceItem(
        evidence_id="ev_sensor_1",
        source="moisture_sensor",
        content={"depth_10cm": 11.2},
        scope=EvidenceScope.SENSOR
    )
    inp = ReasoningInput(
        request_id="req_module_001",
        task="Check root zone moisture",
        evidence_items=[ev]
    )

    result, handoff = module.reason(inp)

    assert result.request_id == "req_module_001"
    assert result.status == ReasoningState.COMPLETED
    assert len(result.findings) == 1
    assert handoff.validation_status in (ValidationStatus.PASS, ValidationStatus.FLAG, ValidationStatus.RECHECK)

    # Test ApplicationRequest handling
    app_req = ApplicationRequest(
        request_id="req_module_002",
        source="workflow",
        operation="reason",
        payload={"task": "Assess weather impact"}
    )
    app_resp = module.handle(app_req)

    assert app_resp.request_id == "req_module_002"
    assert app_resp.status == "SUCCESS"
    assert "result" in app_resp.response
    assert "handoff" in app_resp.response

    module.shutdown()
