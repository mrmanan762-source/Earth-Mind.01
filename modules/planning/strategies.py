from typing import Any, Dict, List, Optional
import uuid

from modules.planning.enums import (
    ConstraintSeverity,
    DecisionStatus,
    FeasibilityState,
    HardSoftType,
    RiskLevel,
)
from modules.planning.interfaces import IDecisionStrategy, IPlanningStrategy
from modules.planning.schemas import (
    CandidateAction,
    Constraint,
    DecisionPolicyConfig,
    FeasibilityAnalysisResult,
    Goal,
    PlanReference,
    PlanningPolicyConfig,
    ResourceRequirement,
    RiskItem,
)


class DefaultPlanningStrategy:
    """Default strategy implementation for action generation and plan structuring."""

    strategy_name: str = "DefaultPlanningStrategy"

    def generate_candidate_actions(
        self,
        goal: Goal,
        reasoning_result: Optional[Any],
        constraints: List[Constraint],
        policy: Any,
    ) -> List[CandidateAction]:
        """Generate candidate actions from goal, B3 reasoning findings, and constraints."""
        actions: List[CandidateAction] = []
        trace_id = goal.trace_id

        # Derive candidate actions from B3 reasoning findings if present
        if reasoning_result and hasattr(reasoning_result, "findings") and reasoning_result.findings:
            for idx, finding in enumerate(reasoning_result.findings):
                finding_id = getattr(finding, "finding_id", f"f_{idx}")
                statement = getattr(finding, "statement", str(finding))
                action_id = f"act_reasoning_{idx + 1}"
                actions.append(
                    CandidateAction(
                        action_id=action_id,
                        name=f"Action derived from finding {finding_id}",
                        description=f"Address finding: {statement}",
                        action_type="REASONING_DERIVED",
                        reasoning_finding_refs=[finding_id],
                        trace_id=trace_id,
                    )
                )

        # Always ensure at least one primary action directly addressing goal objective
        if not actions:
            actions.append(
                CandidateAction(
                    action_id=f"act_goal_{uuid.uuid4().hex[:6]}",
                    name=f"Direct action for {goal.objective[:30]}",
                    description=f"Primary action to achieve goal: {goal.objective}",
                    action_type="GOAL_DIRECT",
                    trace_id=trace_id,
                )
            )

        return actions

    def build_plans(
        self,
        goal: Goal,
        actions: List[CandidateAction],
        constraints: List[Constraint],
        policy: Any,
    ) -> List[PlanReference]:
        """Build candidate plan options from candidate actions."""
        if not actions:
            return []

        trace_id = goal.trace_id
        plans: List[PlanReference] = []

        # Primary Plan incorporating all actions
        primary_plan_id = f"plan_primary_{uuid.uuid4().hex[:6]}"
        reasoning_basis = []
        for act in actions:
            reasoning_basis.extend(act.reasoning_finding_refs)

        primary_plan = PlanReference(
            plan_id=primary_plan_id,
            name=f"Primary Plan for {goal.objective[:30]}",
            description=f"Comprehensive plan to achieve: {goal.objective}",
            actions=actions,
            feasibility_state=FeasibilityState.FEASIBLE,
            reasoning_basis_ids=list(set(reasoning_basis)),
            trace_id=trace_id,
        )
        plans.append(primary_plan)

        # If multiple actions, create alternative focused plan(s)
        if len(actions) > 1:
            alt_plan_id = f"plan_alt_{uuid.uuid4().hex[:6]}"
            alt_actions = actions[:1]  # Focused subset
            alt_plan = PlanReference(
                plan_id=alt_plan_id,
                name=f"Alternative Plan for {goal.objective[:30]}",
                description=f"Alternative targeted plan for: {goal.objective}",
                actions=alt_actions,
                feasibility_state=FeasibilityState.FEASIBLE,
                reasoning_basis_ids=list(set(alt_actions[0].reasoning_finding_refs)),
                trace_id=trace_id,
            )
            plans.append(alt_plan)

        return plans


class DefaultDecisionStrategy:
    """Default strategy implementation for feasibility analysis, risk evaluation, and option selection."""

    strategy_name: str = "DefaultDecisionStrategy"

    def evaluate_feasibility(
        self,
        candidate_plans: List[PlanReference],
        constraints: List[Constraint],
        available_resources: List[Any],
    ) -> List[FeasibilityAnalysisResult]:
        """Evaluate explicit feasibility state for candidate plans."""
        results: List[FeasibilityAnalysisResult] = []

        for plan in candidate_plans:
            hard_violations: List[str] = []
            soft_violations: List[str] = []
            missing_resources: List[str] = []
            evaluated_constraints: List[Constraint] = []

            for c in constraints:
                evaluated_constraints.append(c)
                # Check explicit violation metadata or action matching
                for act in plan.actions:
                    if c.metadata.get("violates_action") == act.action_id or c.metadata.get("violates_plan") == plan.plan_id:
                        if c.hard_or_soft == HardSoftType.HARD:
                            if c.constraint_id not in hard_violations:
                                hard_violations.append(c.constraint_id)
                        else:
                            if c.constraint_id not in soft_violations:
                                soft_violations.append(c.constraint_id)

            if hard_violations:
                overall_state = FeasibilityState.INFEASIBLE
                plan.feasibility_state = FeasibilityState.INFEASIBLE
                rationale = f"Plan '{plan.plan_id}' violates hard constraint(s): {hard_violations}"
            elif soft_violations or missing_resources:
                overall_state = FeasibilityState.CONDITIONAL
                plan.feasibility_state = FeasibilityState.CONDITIONAL
                rationale = f"Plan '{plan.plan_id}' meets hard constraints but has soft violations or missing resources."
            else:
                overall_state = FeasibilityState.FEASIBLE
                plan.feasibility_state = FeasibilityState.FEASIBLE
                rationale = f"Plan '{plan.plan_id}' satisfies all evaluated constraints."

            results.append(
                FeasibilityAnalysisResult(
                    feasibility_id=f"feas_{uuid.uuid4().hex[:6]}",
                    target_id=plan.plan_id,
                    overall_state=overall_state,
                    evaluated_constraints=evaluated_constraints,
                    hard_violations=hard_violations,
                    soft_violations=soft_violations,
                    missing_resources=missing_resources,
                    rationale=rationale,
                    trace_id=plan.trace_id,
                )
            )

        return results

    def select_best_option(
        self,
        candidate_plans: List[PlanReference],
        feasibility_results: List[FeasibilityAnalysisResult],
        decision_policy: Any,
    ) -> Optional[PlanReference]:
        """Compare options based on decision policy and select recommended decision."""
        if not candidate_plans:
            return None

        # Filter out INFEASIBLE plans
        feasibility_map = {f.target_id: f.overall_state for f in feasibility_results}
        feasible_plans = [
            p for p in candidate_plans if feasibility_map.get(p.plan_id) != FeasibilityState.INFEASIBLE
        ]

        if not feasible_plans:
            return None

        # Rank remaining plans
        for plan in feasible_plans:
            state = feasibility_map.get(plan.plan_id, FeasibilityState.UNKNOWN)
            if state == FeasibilityState.FEASIBLE:
                plan.score = 0.9
            elif state == FeasibilityState.CONDITIONAL:
                plan.score = 0.6
            else:
                plan.score = 0.4

        feasible_plans.sort(key=lambda p: p.score or 0.0, reverse=True)
        return feasible_plans[0]
