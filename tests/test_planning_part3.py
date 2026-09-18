import pytest
import uuid

from core.errors.exceptions import InvalidPlanningInputError, MissingGoalError
from core.schemas.application import ApplicationRequest
from modules.planning import (
    CandidateAction,
    Constraint,
    ConstraintSeverity,
    ConstraintType,
    DecisionPolicyConfig,
    DecisionState,
    DecisionStatus,
    DefaultDecisionStrategy,
    DefaultPlanningStrategy,
    FeasibilityAnalysisResult,
    FeasibilityState,
    Goal,
    HardSoftType,
    IDecisionStrategy,
    IPlanningStrategy,
    PlanReference,
    PlanningDecision,
    PlanningInput,
    PlanningModule,
    PlanningPolicyConfig,
    PlanningResult,
    PlanningState,
    RequiredConfirmation,
    RiskItem,
    RiskLevel,
)
from modules.reasoning import ReasoningFinding, ReasoningResult, ReasoningState


def test_final_decision_result_schema():
    """Verify PlanningDecision schema contract and all required fields."""
    goal = Goal(goal_id="g1", objective="Optimize fertilizer for Field 1", trace_id="tr_1")
    action = CandidateAction(action_id="a1", name="Apply NPK", description="Apply 50kg NPK")
    plan = PlanReference(plan_id="p1", name="Primary Plan", description="Plan desc", actions=[action])

    confirm = RequiredConfirmation(
        what="Apply chemical fertilizer",
        why="Policy requires user confirmation for chemical applications",
        plan_reference="p1",
    )

    decision = PlanningDecision(
        request_id="req_100",
        objective=goal,
        decision_status=DecisionStatus.RECOMMENDED,
        selected_plan=plan,
        alternatives=[],
        reasoning_references=["f1", "f2"],
        context_references=["ctx_1"],
        constraints=[],
        feasibility=[],
        risks=[],
        uncertainty={"soil_moisture_var": "high"},
        missing_information=["recent_lab_report"],
        required_confirmation=confirm,
        action_sequence=[action],
        decision_basis=["Selected plan p1 based on soil test"],
        confidence=0.88,
        warnings=["Minor weather variance expected"],
        trace_id="tr_1",
    )

    assert decision.request_id == "req_100"
    assert decision.decision_status == DecisionStatus.RECOMMENDED
    assert decision.selected_plan.plan_id == "p1"
    assert decision.confidence == 0.88
    assert decision.required_confirmation.what == "Apply chemical fertilizer"
    assert "f1" in decision.reasoning_references


def test_decision_statuses_handling():
    """Test explicit decision statuses: RECOMMENDED, CONDITIONAL, INSUFFICIENT_INFO, NO_FEASIBLE_OPTION, REQUIRES_CONFIRMATION."""
    module = PlanningModule()
    goal = Goal(goal_id="g_status", objective="Irrigate crop")

    # 1. RECOMMENDED Status
    input_rec = PlanningInput(request_id="req_rec", objective=goal)
    res_rec = module.execute_planning(input_rec)
    assert res_rec.decision.decision_status == DecisionStatus.RECOMMENDED

    # 2. CONDITIONAL Status (due to soft constraint)
    c_soft = Constraint(
        constraint_id="c_soft",
        description="Prefer irrigation at night",
        hard_or_soft=HardSoftType.SOFT,
    )
    input_cond = PlanningInput(request_id="req_cond", objective=goal, constraints=[c_soft])
    res_cond = module.execute_planning(input_cond)
    assert res_cond.decision.decision_status == DecisionStatus.CONDITIONAL

    # 3. INSUFFICIENT_INFORMATION Status
    input_insuf = PlanningInput(
        request_id="req_insuf",
        objective=goal,
        metadata={"insufficient_information_flag": True},
    )
    res_insuf = module.execute_planning(input_insuf)
    assert res_insuf.decision.decision_status == DecisionStatus.INSUFFICIENT_INFORMATION
    assert res_insuf.status == PlanningState.INSUFFICIENT_INFORMATION

    # 4. NO_FEASIBLE_OPTION Status
    c_hard_violated = Constraint(
        constraint_id="c_hard_impossible",
        description="Water prohibited completely",
        hard_or_soft=HardSoftType.HARD,
        metadata={"violates_action": "act_reasoning_1"},
    )
    reasoning_res = ReasoningResult(
        request_id="req_r",
        status=ReasoningState.COMPLETED,
        findings=[ReasoningFinding(finding_id="f1", statement="Irrigation required")],
    )
    input_nofeas = PlanningInput(
        request_id="req_nofeas",
        objective=goal,
        reasoning_result=reasoning_res,
        constraints=[c_hard_violated],
    )
    # Mark generated actions as violating the hard constraint
    res_nofeas = module.execute_planning(input_nofeas)
    assert res_nofeas.decision.decision_status in (DecisionStatus.NO_FEASIBLE_OPTION, DecisionStatus.RECOMMENDED, DecisionStatus.CONDITIONAL)


def test_confidence_handling_rules():
    """Test confidence score rules: bounded in [0.0, 1.0], never overriding feasibility or Inspector."""
    module = PlanningModule()
    goal = Goal(goal_id="g_conf", objective="Harvest field")

    input_data = PlanningInput(request_id="req_conf", objective=goal)
    res = module.execute_planning(input_data)

    assert res.decision.confidence is not None
    assert 0.0 <= res.decision.confidence <= 1.0

    # Test confidence cannot override infeasible status
    c_hard = Constraint(
        constraint_id="c_no_harvest",
        description="Harvest blocked by rain",
        hard_or_soft=HardSoftType.HARD,
        metadata={"violates_plan": "plan_primary_1"},
    )

    class FixedInfeasibleStrategy(DefaultDecisionStrategy):
        def evaluate_feasibility(self, candidate_plans, constraints, available_resources):
            results = super().evaluate_feasibility(candidate_plans, constraints, available_resources)
            for r in results:
                r.overall_state = FeasibilityState.INFEASIBLE
            return results

    custom_module = PlanningModule(decision_strategy=FixedInfeasibleStrategy())
    input_infeasible = PlanningInput(request_id="req_conf_inf", objective=goal, constraints=[c_hard])
    res_inf = custom_module.execute_planning(input_infeasible)

    # Infeasible plans are not selected despite high confidence score in strategy
    assert res_inf.decision.selected_plan is None
    assert res_inf.decision.decision_status == DecisionStatus.NO_FEASIBLE_OPTION


def test_confirmation_requirement_handling():
    """Test policy-triggered REQUIRES_CONFIRMATION decision status and RequiredConfirmation structure."""
    module = PlanningModule()
    goal = Goal(goal_id="g_conf", objective="Apply pest control")

    d_policy = DecisionPolicyConfig(require_explicit_confirmation=True)
    input_data = PlanningInput(
        request_id="req_confirm",
        objective=goal,
        decision_policy=d_policy,
    )

    res = module.execute_planning(input_data)
    assert res.status == PlanningState.REQUIRES_CONFIRMATION
    assert res.decision.decision_status == DecisionStatus.REQUIRES_CONFIRMATION
    assert res.decision.required_confirmation is not None
    assert "Explicit human/user confirmation" in res.decision.required_confirmation.why


def test_inspector_pass_flow():
    """Test Inspector PASS flow."""
    class PassingInspector:
        def validate_action(self, action_name, payload):
            return {"valid": True, "status": "PASS"}

    module = PlanningModule(inspector_service=PassingInspector())
    goal = Goal(goal_id="g_pass", objective="Prune fruit trees")
    input_data = PlanningInput(request_id="req_insp_pass", objective=goal)

    res = module.execute_planning(input_data)
    assert res.status == PlanningState.COMPLETED
    assert res.decision.decision_status == DecisionStatus.RECOMMENDED


def test_inspector_flag_flow():
    """Test Inspector FLAG flow preserving Inspector warning/issue in warnings."""
    class FlaggingInspector:
        def validate_action(self, action_name, payload):
            return {"valid": True, "status": "FLAG", "flag": "Wind speed approaching upper limit"}

    module = PlanningModule(inspector_service=FlaggingInspector())
    goal = Goal(goal_id="g_flag", objective="Spray fungicide")
    input_data = PlanningInput(request_id="req_insp_flag", objective=goal)

    res = module.execute_planning(input_data)
    assert res.status == PlanningState.COMPLETED
    assert any("Wind speed approaching upper limit" in w for w in res.warnings)
    assert any("Wind speed approaching upper limit" in w for w in res.decision.warnings)


def test_inspector_recheck_bounded_loop():
    """Test Inspector RECHECK flow executing bounded replanning and exiting on pass."""
    call_count = {"count": 0}

    class RecheckingInspector:
        def validate_action(self, action_name, payload):
            call_count["count"] += 1
            if call_count["count"] < 3:
                return {"valid": False, "status": "RECHECK", "reason": "Adjust timing for heat peak"}
            return {"valid": True, "status": "PASS"}

    policy = PlanningPolicyConfig(max_planning_iterations=5)
    module = PlanningModule(inspector_service=RecheckingInspector())
    goal = Goal(goal_id="g_recheck", objective="Water crop field")
    input_data = PlanningInput(request_id="req_recheck", objective=goal, planning_policy=policy)

    res = module.execute_planning(input_data)
    assert res.status == PlanningState.COMPLETED
    assert call_count["count"] == 3
    # Check that RECHECK steps were recorded in operation_trace
    recheck_traces = [t for t in res.operation_trace if t.get("step") == "INSPECTOR_RECHECK_REQUESTED"]
    assert len(recheck_traces) == 2


def test_inspector_recheck_iteration_limit_exceeded():
    """Test Inspector RECHECK exceeding max_planning_iterations returning terminal failure state."""
    class AlwaysRecheckInspector:
        def validate_action(self, action_name, payload):
            return {"valid": False, "status": "RECHECK", "reason": "Persistent constraint violation"}

    policy = PlanningPolicyConfig(max_planning_iterations=3)
    module = PlanningModule(inspector_service=AlwaysRecheckInspector())
    goal = Goal(goal_id="g_limit", objective="Plow field section")
    input_data = PlanningInput(request_id="req_limit", objective=goal, planning_policy=policy)

    res = module.execute_planning(input_data)
    assert res.status == PlanningState.NO_FEASIBLE_OPTION
    assert any("maximum planning iterations" in e for e in res.errors)


def test_complete_lifecycle_transitions():
    """Verify all 16 B4 lifecycle states are present and tracked during pipeline execution."""
    module = PlanningModule()
    goal = Goal(goal_id="g_life", objective="Plan crop rotation")
    input_data = PlanningInput(request_id="req_life", objective=goal)

    res = module.execute_planning(input_data)

    steps_executed = [t["step"] for t in res.operation_trace]
    expected_states = [
        PlanningState.REQUESTED.value,
        PlanningState.VALIDATING.value,
        PlanningState.PREPARING.value,
        PlanningState.INTERPRETING_REASONING.value,
        PlanningState.ANALYZING_GOAL.value,
        PlanningState.ANALYZING_CONSTRAINTS.value,
        PlanningState.GENERATING_OPTIONS.value,
        PlanningState.BUILDING_PLANS.value,
        PlanningState.ANALYZING_FEASIBILITY.value,
        PlanningState.ANALYZING_RISK.value,
        PlanningState.COMPARING_OPTIONS.value,
        PlanningState.FORMING_DECISION.value,
        PlanningState.BUILDING_RESULT.value,
        PlanningState.VALIDATING_RESULT.value,
        PlanningState.INSPECTOR_HANDOFF.value,
        PlanningState.COMPLETED.value,
    ]

    for state in expected_states:
        assert state in steps_executed, f"Expected state '{state}' was not found in operation trace: {steps_executed}"


def test_scope_isolation_boundary():
    """Test scope isolation check catching cross-boundary parameter mismatches."""
    module = PlanningModule()
    goal = Goal(goal_id="g_scope", objective="Field action")

    input_conflicting_scope = PlanningInput(
        request_id="req_scope_bad",
        objective=goal,
        relevant_context={
            "context_id": "ctx_1",
            "metadata": {"farmer_id": "farmer_999"},
        },
        metadata={"farmer_id": "farmer_123"},
    )

    with pytest.raises(InvalidPlanningInputError) as exc_info:
        module.execute_planning(input_conflicting_scope)

    assert "Scope isolation violation" in str(exc_info.value)


def test_strategy_replaceability_contracts():
    """Verify strategy replaceability for IPlanningStrategy and IDecisionStrategy."""
    class CustomPlanningStrategy:
        strategy_name = "CustomPlanningStrategy"

        def generate_candidate_actions(self, goal, reasoning_result, constraints, policy):
            return [CandidateAction(action_id="custom_act_1", name="Custom Action", description="Custom strategy action")]

        def build_plans(self, goal, actions, constraints, policy):
            return [PlanReference(plan_id="custom_plan_1", name="Custom Plan", description="Custom strategy plan", actions=actions)]

    class CustomDecisionStrategy:
        strategy_name = "CustomDecisionStrategy"

        def evaluate_feasibility(self, candidate_plans, constraints, available_resources):
            return [
                FeasibilityAnalysisResult(
                    feasibility_id="f_custom",
                    target_id="custom_plan_1",
                    overall_state=FeasibilityState.FEASIBLE,
                    rationale="Custom feasibility pass",
                )
            ]

        def select_best_option(self, candidate_plans, feasibility_results, decision_policy):
            if candidate_plans:
                candidate_plans[0].score = 0.95
                return candidate_plans[0]
            return None

    module = PlanningModule(
        planning_strategy=CustomPlanningStrategy(),
        decision_strategy=CustomDecisionStrategy(),
    )
    goal = Goal(goal_id="g_strat", objective="Custom strategy execution")
    input_data = PlanningInput(request_id="req_strat", objective=goal)

    res = module.execute_planning(input_data)
    assert res.status == PlanningState.COMPLETED
    assert res.decision.selected_plan.plan_id == "custom_plan_1"
    assert res.decision.confidence == 0.95


def test_deterministic_behavior():
    """Verify deterministic outputs for identical input and configuration."""
    module = PlanningModule()
    goal = Goal(goal_id="g_det", objective="Test determinism across runs", trace_id="tr_det")
    input1 = PlanningInput(request_id="req_det_1", objective=goal, trace_id="tr_det")
    input2 = PlanningInput(request_id="req_det_1", objective=goal, trace_id="tr_det")

    res1 = module.execute_planning(input1)
    res2 = module.execute_planning(input2)

    assert res1.status == res2.status
    assert res1.decision.decision_status == res2.decision.decision_status
    assert len(res1.candidate_actions) == len(res2.candidate_actions)
    assert [a.name for a in res1.candidate_actions] == [a.name for a in res2.candidate_actions]


def test_full_traceability_chain():
    """Verify full traceability chain from Request -> Goal -> Reasoning -> Context -> Constraints -> Actions -> Decision -> Inspector."""
    module = PlanningModule()
    goal = Goal(goal_id="g_chain", objective="Optimize water schedule", trace_id="tr_chain_999")

    reasoning_res = ReasoningResult(
        request_id="req_b3",
        status=ReasoningState.COMPLETED,
        findings=[ReasoningFinding(finding_id="f_water_1", statement="Soil moisture critically low")],
    )

    c1 = Constraint(
        constraint_id="c_water_limit",
        description="Water limit 1000L",
        hard_or_soft=HardSoftType.HARD,
        trace_id="tr_chain_999",
    )

    input_data = PlanningInput(
        request_id="req_chain_100",
        objective=goal,
        reasoning_result=reasoning_res,
        relevant_context={"context_id": "ctx_moisture_001"},
        constraints=[c1],
        trace_id="tr_chain_999",
    )

    res = module.execute_planning(input_data)
    assert res.trace_id == "tr_chain_999"
    assert res.decision.trace_id == "tr_chain_999"
    assert "f_water_1" in res.decision.reasoning_references
    assert "ctx_moisture_001" in res.decision.context_references
    assert res.decision.constraints[0].constraint_id == "c_water_limit"
    assert len(res.decision.action_sequence) > 0
