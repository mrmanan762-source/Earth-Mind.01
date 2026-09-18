import pytest
from core.errors.exceptions import EarthMindException
from core.schemas.application import ApplicationRequest
from modules.planning import (
    CandidateAction,
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    DecisionPolicyConfig,
    DecisionState,
    FeasibilityAnalysisResult,
    FeasibilityState,
    Goal,
    HardSoftType,
    IDecisionStrategy,
    IPlanningCapability,
    IPlanningStrategy,
    ImpossibleConstraintError,
    InvalidConstraintError,
    InvalidDecisionError,
    InvalidPlanningInputError,
    InvalidPlanningReasoningInputError,
    MissingGoalError,
    NoFeasibleOptionError,
    PlanReference,
    PlanningError,
    PlanningInput,
    PlanningIterationLimitError,
    PlanningModule,
    PlanningPolicyConfig,
    PlanningResult,
    PlanningState,
    PlanningTimeoutError,
    PlanningValidationHandoff,
    ResourceRequirement,
    RiskItem,
    RiskLevel,
    UnavailableCapabilityError,
)
from modules.reasoning import ReasoningFinding, ReasoningResult, ReasoningState


def test_planning_enums_and_lifecycle():
    """Test all required lifecycle states and enums exist and behave correctly."""
    assert PlanningState.REQUESTED == "REQUESTED"
    assert PlanningState.VALIDATING == "VALIDATING"
    assert PlanningState.PREPARING == "PREPARING"
    assert PlanningState.INTERPRETING_REASONING == "INTERPRETING_REASONING"
    assert PlanningState.ANALYZING_GOAL == "ANALYZING_GOAL"
    assert PlanningState.ANALYZING_CONSTRAINTS == "ANALYZING_CONSTRAINTS"
    assert PlanningState.GENERATING_OPTIONS == "GENERATING_OPTIONS"
    assert PlanningState.ANALYZING_FEASIBILITY == "ANALYZING_FEASIBILITY"
    assert PlanningState.ANALYZING_RISK == "ANALYZING_RISK"
    assert PlanningState.BUILDING_PLANS == "BUILDING_PLANS"
    assert PlanningState.COMPARING_OPTIONS == "COMPARING_OPTIONS"
    assert PlanningState.FORMING_DECISION == "FORMING_DECISION"
    assert PlanningState.BUILDING_RESULT == "BUILDING_RESULT"
    assert PlanningState.VALIDATING_RESULT == "VALIDATING_RESULT"
    assert PlanningState.INSPECTOR_HANDOFF == "INSPECTOR_HANDOFF"
    assert PlanningState.COMPLETED == "COMPLETED"

    # Terminal failure states
    assert PlanningState.FAILED == "FAILED"
    assert PlanningState.INSUFFICIENT_INFORMATION == "INSUFFICIENT_INFORMATION"
    assert PlanningState.NO_FEASIBLE_OPTION == "NO_FEASIBLE_OPTION"
    assert PlanningState.TIMEOUT == "TIMEOUT"
    assert PlanningState.CANCELLED == "CANCELLED"
    assert PlanningState.REQUIRES_CONFIRMATION == "REQUIRES_CONFIRMATION"
    assert PlanningState.REJECTED == "REJECTED"

    # Explicit Feasibility states (Rule 9)
    assert FeasibilityState.FEASIBLE == "FEASIBLE"
    assert FeasibilityState.INFEASIBLE == "INFEASIBLE"
    assert FeasibilityState.CONDITIONAL == "CONDITIONAL"
    assert FeasibilityState.UNKNOWN == "UNKNOWN"

    # Hard vs Soft constraint distinction (Rule 5)
    assert HardSoftType.HARD == "HARD"
    assert HardSoftType.SOFT == "SOFT"


def test_b4_exceptions_hierarchy():
    """Test that B4 exceptions inherit from PlanningError and EarthMindException."""
    err = InvalidPlanningInputError("bad input")
    assert isinstance(err, PlanningError)
    assert isinstance(err, EarthMindException)
    assert err.error_contract.module == "planning"
    assert err.error_contract.error_code == "INVALID_PLANNING_INPUT"

    missing_goal_err = MissingGoalError("req1")
    assert missing_goal_err.error_contract.error_code == "MISSING_GOAL"
    assert missing_goal_err.error_contract.metadata["request_id"] == "req1"

    invalid_c_err = InvalidConstraintError("c1", "empty description")
    assert invalid_c_err.error_contract.error_code == "INVALID_CONSTRAINT"

    impossible_err = ImpossibleConstraintError("c2", "contradicts c1")
    assert impossible_err.error_contract.error_code == "IMPOSSIBLE_CONSTRAINT"


def test_goal_and_preservation():
    """Test Goal contract and Rule 1 Goal Preservation."""
    goal = Goal(
        goal_id="g1",
        objective="Optimize irrigation for Field A",
        priority="HIGH",
        target_state={"soil_moisture": 0.4},
        deadlines={"complete_by": "2025-06-01T12:00:00Z"},
        trace_id="trace_123",
    )
    assert goal.goal_id == "g1"
    assert goal.objective == "Optimize irrigation for Field A"
    assert goal.trace_id == "trace_123"


def test_constraint_contract_and_hard_soft_analysis():
    """Test Constraint contract and Hard vs Soft constraint distinction (Rules 4 & 5)."""
    module = PlanningModule()

    c_hard = Constraint(
        constraint_id="c_hard_1",
        type=ConstraintType.WATER_LIMIT if hasattr(ConstraintType, "WATER_LIMIT") else ConstraintType.RESOURCE,
        severity=ConstraintSeverity.HIGH,
        source="water_permit",
        description="Water usage must not exceed 5000L",
        hard_or_soft=HardSoftType.HARD,
        value_reference=5000,
    )

    c_soft = Constraint(
        constraint_id="c_soft_1",
        type=ConstraintType.OPERATIONAL,
        severity=ConstraintSeverity.LOW,
        source="preference",
        description="Prefer irrigation in early morning",
        hard_or_soft=HardSoftType.SOFT,
    )

    categorized = module.analyze_constraints([c_hard, c_soft])
    assert len(categorized["hard"]) == 1
    assert len(categorized["soft"]) == 1
    assert categorized["hard"][0].constraint_id == "c_hard_1"
    assert categorized["soft"][0].constraint_id == "c_soft_1"


def test_explicit_feasibility_evaluation():
    """Test explicit feasibility analysis on CandidateAction (Rule 9)."""
    module = PlanningModule()

    action = CandidateAction(
        action_id="act_irrigate_1",
        name="Irrigate Field A",
        description="Apply 6000L water",
        feasibility_state=FeasibilityState.UNKNOWN,
    )

    c_hard_violated = Constraint(
        constraint_id="c1",
        source="permit",
        description="Max water 5000L",
        hard_or_soft=HardSoftType.HARD,
        metadata={"violates_action": "act_irrigate_1"},
    )

    feasibility_res = module.evaluate_action_feasibility(action, [c_hard_violated])
    assert feasibility_res.overall_state == FeasibilityState.INFEASIBLE
    assert "c1" in feasibility_res.hard_violations


def test_planning_policy_and_decision_policy_config():
    """Test configurable planning policy and decision policy structures."""
    p_policy = PlanningPolicyConfig(
        max_planning_iterations=8,
        max_alternatives=10,
        timeout_seconds=15.0,
        enforce_inspector=True,
    )
    assert p_policy.max_planning_iterations == 8
    assert p_policy.max_alternatives == 10

    d_policy = DecisionPolicyConfig(
        min_feasibility_threshold=0.7,
        max_acceptable_risk=RiskLevel.MEDIUM,
        require_explicit_confirmation=True,
    )
    assert d_policy.min_feasibility_threshold == 0.7
    assert d_policy.max_acceptable_risk == RiskLevel.MEDIUM
    assert d_policy.require_explicit_confirmation is True


def test_planning_module_execution_and_inspector_handoff():
    """Test B4 planning execution with B3 reasoning input and Inspector handoff structure."""
    module = PlanningModule()
    module.initialize()
    assert module.is_initialized is True

    goal = Goal(goal_id="g100", objective="Reduce pest risk in Sector 3")

    reasoning_res = ReasoningResult(
        request_id="req_b3_1",
        status=ReasoningState.COMPLETED,
        findings=[
            ReasoningFinding(
                finding_id="f1",
                statement="High pest activity detected in Sector 3",
                confidence_score=0.9,
            )
        ],
    )

    planning_input = PlanningInput(
        request_id="req_b4_100",
        objective=goal,
        reasoning_result=reasoning_res,
        constraints=[
            Constraint(
                constraint_id="c_env_1",
                source="environmental_policy",
                description="No spray during heavy wind",
                hard_or_soft=HardSoftType.HARD,
            )
        ],
    )

    res = module.execute_planning(planning_input)
    assert res.request_id == "req_b4_100"
    assert res.status == PlanningState.COMPLETED
    assert res.goal.objective == "Reduce pest risk in Sector 3"
    assert len(res.operation_trace) >= 3

    # Check Inspector handoff preparation (Rule 20)
    handoff = module.prepare_inspector_handoff(res, planning_input.constraints)
    assert handoff.request_id == "req_b4_100"
    assert handoff.validation_status.value == "PENDING"
    assert len(handoff.constraints_applied) == 1

    module.shutdown()
    assert module.is_initialized is False


def test_missing_goal_validation_failure():
    """Test that missing goal raises MissingGoalError."""
    module = PlanningModule()
    invalid_input = PlanningInput(
        request_id="req_no_goal",
        objective=None,
    )
    with pytest.raises(MissingGoalError):
        module.execute_planning(invalid_input)


def test_invalid_constraint_validation_failure():
    """Test that invalid constraint raises InvalidConstraintError."""
    module = PlanningModule()
    bad_constraint = Constraint(
        constraint_id="",
        source="sys",
        description="",
    )
    goal = Goal(goal_id="g1", objective="Test objective")
    bad_input = PlanningInput(
        request_id="req_bad_c",
        objective=goal,
        constraints=[bad_constraint],
    )
    with pytest.raises(InvalidConstraintError):
        module.execute_planning(bad_input)


def test_module_handle_application_request():
    """Test standard ModuleInterface handle entry point."""
    module = PlanningModule()
    app_req = ApplicationRequest(
        request_id="app_req_1",
        source="user",
        operation="execute_planning",
        payload={"goal": "Increase crop yield for Field 2"},
    )
    app_resp = module.handle(app_req)
    assert app_resp.request_id == "app_req_1"
    assert app_resp.status == "COMPLETED"
    assert app_resp.response["goal"]["objective"] == "Increase crop yield for Field 2"
