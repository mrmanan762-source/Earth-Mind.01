from typing import Any, Dict, List, Optional
import uuid

from core.interfaces.module import ModuleInterface
from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest, ApplicationResponse
from modules.planning.enums import (
    ConstraintSeverity,
    DecisionState,
    FeasibilityState,
    HardSoftType,
    PlanningState,
)
from modules.planning.errors import (
    ImpossibleConstraintError,
    InvalidConstraintError,
    InvalidPlanningInputError,
    MissingGoalError,
)
from modules.planning.schemas import (
    CandidateAction,
    Constraint,
    FeasibilityAnalysisResult,
    Goal,
    PlanReference,
    PlanningInput,
    PlanningResult,
    PlanningValidationHandoff,
)
from modules.reasoning.enums import ValidationStatus

logger = get_logger("planning_module")


class PlanningModule(ModuleInterface):
    """B4 Planning & Decision Engine foundation module.

    Owns:
    - Goal interpretation & preservation
    - Action/option candidate structuring
    - Constraint analysis (Hard vs Soft constraints)
    - Feasibility evaluation foundation
    - Risk structure & preserved uncertainty
    - Decision formation & Inspector handoff preparation

    Obeys EarthMind's 5 Fundamental Principles:
    1. Extensibility / Rubber-band principle (pluggable planning & decision policies)
    2. Loose Coupling (uses core interfaces and generic contracts)
    3. Single Responsibility (planning and decision formation only)
    4. Controlled Dependencies (no direct DB/ Sarvam / Hardware dependencies)
    5. Replaceability + Evolution (replaceable strategies and policies)
    """

    module_name: str = "planning"

    def __init__(self) -> None:
        self.is_initialized: bool = False

    def initialize(self) -> None:
        """Initialize B4 Planning Module resources."""
        self.is_initialized = True
        logger.info("B4 Planning & Decision Engine initialized successfully.")

    def shutdown(self) -> None:
        """Cleanup B4 Planning Module resources."""
        self.is_initialized = False
        logger.info("B4 Planning & Decision Engine shut down.")

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        """Handle standard application request (converts to B4 PlanningInput execution)."""
        request_id = request.request_id or str(uuid.uuid4())
        goal_text = str(request.payload.get("goal") or request.payload.get("objective") or "")

        if not goal_text.strip():
            raise MissingGoalError(request_id=request_id)

        goal = Goal(
            goal_id=str(uuid.uuid4()),
            objective=goal_text,
            trace_id=request.metadata.get("trace_id"),
        )

        planning_input = PlanningInput(
            request_id=request_id,
            objective=goal,
            trace_id=request.metadata.get("trace_id"),
            metadata=request.metadata,
        )

        result = self.execute_planning(planning_input)
        return ApplicationResponse(
            request_id=request_id,
            status=result.status.value,
            response=result.model_dump(),
            metadata=result.metadata,
        )

    def validate_input(self, input_data: PlanningInput) -> None:
        """Validate B4 planning input contract according to B4 rules."""
        if not input_data.request_id:
            raise InvalidPlanningInputError("request_id cannot be empty.")
        if not input_data.objective or not input_data.objective.objective.strip():
            raise MissingGoalError(request_id=input_data.request_id)

        for constraint in input_data.constraints:
            self.validate_constraint(constraint)

    def validate_constraint(self, constraint: Constraint) -> None:
        """Validate an individual constraint."""
        if not constraint.constraint_id:
            raise InvalidConstraintError("unnamed", "constraint_id cannot be empty.")
        if not constraint.description or not constraint.description.strip():
            raise InvalidConstraintError(constraint.constraint_id, "description cannot be empty.")

    def analyze_constraints(
        self, constraints: List[Constraint]
    ) -> Dict[str, List[Constraint]]:
        """Categorize constraints into Hard and Soft constraints.

        Rule 4: Constraint First
        Rule 5: Hard vs Soft Constraints (Hard constraints cannot be silently violated).
        """
        hard_constraints: List[Constraint] = []
        soft_constraints: List[Constraint] = []

        for c in constraints:
            self.validate_constraint(c)
            if c.hard_or_soft == HardSoftType.HARD:
                hard_constraints.append(c)
            else:
                soft_constraints.append(c)

        return {"hard": hard_constraints, "soft": soft_constraints}

    def evaluate_action_feasibility(
        self, action: CandidateAction, constraints: List[Constraint]
    ) -> FeasibilityAnalysisResult:
        """Evaluate explicit feasibility state for a candidate action against constraints.

        Rule 9: Explicit Feasibility (FEASIBLE, INFEASIBLE, CONDITIONAL, UNKNOWN).
        """
        hard_violations: List[str] = []
        soft_violations: List[str] = []
        evaluated: List[Constraint] = []

        for c in constraints:
            evaluated.append(c)
            # Check for explicit metadata rule violation flags or impossible markers
            if c.metadata.get("violates_action") == action.action_id:
                if c.hard_or_soft == HardSoftType.HARD:
                    hard_violations.append(c.constraint_id)
                else:
                    soft_violations.append(c.constraint_id)

        if hard_violations:
            state = FeasibilityState.INFEASIBLE
            rationale = f"Action '{action.action_id}' violates hard constraint(s): {hard_violations}"
        elif soft_violations:
            state = FeasibilityState.CONDITIONAL
            rationale = f"Action '{action.action_id}' satisfies hard constraints but violates soft constraint(s): {soft_violations}"
        else:
            state = FeasibilityState.FEASIBLE
            rationale = f"Action '{action.action_id}' satisfies all evaluated constraints."

        return FeasibilityAnalysisResult(
            feasibility_id=str(uuid.uuid4()),
            target_id=action.action_id,
            overall_state=state,
            evaluated_constraints=evaluated,
            hard_violations=hard_violations,
            soft_violations=soft_violations,
            rationale=rationale,
            trace_id=action.trace_id,
        )

    def prepare_inspector_handoff(
        self, result: PlanningResult, constraints: List[Constraint]
    ) -> PlanningValidationHandoff:
        """Prepare Inspector validation handoff contract for B4 recommendation.

        Rule 20: Inspector Requirement.
        """
        plan_id = (
            result.recommended_plan.plan_id
            if result.recommended_plan
            else "no_plan"
        )
        return PlanningValidationHandoff(
            handoff_id=str(uuid.uuid4()),
            request_id=result.request_id,
            plan_id=plan_id,
            recommended_plan=result.recommended_plan,
            constraints_applied=constraints,
            feasibility_summary={
                "decision_state": result.decision_state.value,
                "candidate_action_count": len(result.candidate_actions),
            },
            risk_summary={"risk_count": len(result.risk_analysis)},
            validation_status=ValidationStatus.PENDING,
            trace_id=result.trace_id,
        )

    def execute_planning(self, input_data: PlanningInput) -> PlanningResult:
        """Execute foundational B4 planning pipeline (Part 1 foundation)."""
        self.validate_input(input_data)
        operation_trace: List[Dict[str, Any]] = []

        # 1. Goal Analysis (Rule 1: Goal Preservation)
        operation_trace.append(
            {"step": PlanningState.ANALYZING_GOAL.value, "goal_id": input_data.objective.goal_id}
        )

        # 2. Constraint Analysis (Rules 4, 5)
        categorized = self.analyze_constraints(input_data.constraints)
        operation_trace.append(
            {
                "step": PlanningState.ANALYZING_CONSTRAINTS.value,
                "hard_count": len(categorized["hard"]),
                "soft_count": len(categorized["soft"]),
            }
        )

        # 3. Reasoning Interpretation (Rule 2: Reasoning Dependency)
        reasoning_findings = []
        if input_data.reasoning_result:
            reasoning_findings = input_data.reasoning_result.findings
            operation_trace.append(
                {
                    "step": PlanningState.INTERPRETING_REASONING.value,
                    "finding_count": len(reasoning_findings),
                }
            )

        # Build initial foundation result
        result = PlanningResult(
            request_id=input_data.request_id,
            status=PlanningState.COMPLETED,
            goal=input_data.objective,
            decision_state=DecisionState.PROPOSED,
            operation_trace=operation_trace,
            trace_id=input_data.trace_id,
            metadata=input_data.metadata,
        )
        return result
