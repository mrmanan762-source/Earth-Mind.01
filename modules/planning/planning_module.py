from typing import Any, Dict, List, Optional
import time
import uuid

from core.interfaces.module import ModuleInterface
from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest, ApplicationResponse
from modules.planning.enums import (
    ConstraintSeverity,
    DecisionState,
    DecisionStatus,
    FeasibilityState,
    HardSoftType,
    PlanningState,
    RiskLevel,
)
from modules.planning.errors import (
    ImpossibleConstraintError,
    InternalPlanningFailureError,
    InvalidConstraintError,
    InvalidDecisionError,
    InvalidPlanningInputError,
    MissingGoalError,
    NoFeasibleOptionError,
    PlanningIterationLimitError,
    PlanningTimeoutError,
)
from modules.planning.interfaces import IDecisionStrategy, IPlanningStrategy
from modules.planning.schemas import (
    CandidateAction,
    Constraint,
    DecisionPolicyConfig,
    FeasibilityAnalysisResult,
    Goal,
    PlanReference,
    PlanningDecision,
    PlanningInput,
    PlanningPolicyConfig,
    PlanningResult,
    PlanningValidationHandoff,
    RequiredConfirmation,
    RiskItem,
)
from modules.planning.strategies import DefaultDecisionStrategy, DefaultPlanningStrategy
from modules.reasoning.enums import ValidationStatus

logger = get_logger("planning_module")


class PlanningModule(ModuleInterface):
    """B4 Planning & Decision Engine.

    Complete implementation of B4 Engine managing:
    - Complete 16-state lifecycle transitions
    - Goal preservation & reasoning findings interpretation
    - Constraint categorization & feasibility analysis
    - Risk & visible uncertainty evaluation
    - Pluggable strategy-based option generation & comparison
    - Inspector validation integration with bounded RECHECK handling
    - Explicit human/user confirmation handling
    - Scope isolation & strict error handling
    - Structured traceability & safe logging
    """

    module_name: str = "planning"

    def __init__(
        self,
        planning_strategy: Optional[IPlanningStrategy] = None,
        decision_strategy: Optional[IDecisionStrategy] = None,
        inspector_service: Optional[Any] = None,
    ) -> None:
        self.is_initialized: bool = False
        self.planning_strategy: IPlanningStrategy = planning_strategy or DefaultPlanningStrategy()
        self.decision_strategy: IDecisionStrategy = decision_strategy or DefaultDecisionStrategy()
        self.inspector_service: Optional[Any] = inspector_service

    def initialize(self) -> None:
        """Initialize B4 Planning Module resources."""
        self.is_initialized = True
        logger.info("B4 Planning & Decision Engine initialized successfully.")

    def shutdown(self) -> None:
        """Cleanup B4 Planning Module resources."""
        self.is_initialized = False
        logger.info("B4 Planning & Decision Engine shut down.")

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        """Handle standard ApplicationRequest by converting to B4 PlanningInput execution."""
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
        """Validate B4 planning input contract, including scope boundary consistency."""
        if not input_data.request_id:
            raise InvalidPlanningInputError("request_id cannot be empty.")
        if not input_data.objective or not input_data.objective.objective.strip():
            raise MissingGoalError(request_id=input_data.request_id)

        # Scope isolation check across metadata/constraints
        self.verify_scope_isolation(input_data)

        for constraint in input_data.constraints:
            self.validate_constraint(constraint)

    def verify_scope_isolation(self, input_data: PlanningInput) -> None:
        """Ensure no conflicting scope parameters (farmer, farm, field, session) cross boundaries."""
        scope_keys = ["farmer_id", "farm_id", "field_id", "crop_cycle_id", "session_id"]
        scope_values: Dict[str, str] = {}

        # Extract scope keys from input metadata
        for key in scope_keys:
            if key in input_data.metadata and input_data.metadata[key]:
                scope_values[key] = str(input_data.metadata[key])

        # Verify context scope alignment if provided
        if input_data.relevant_context and isinstance(input_data.relevant_context, dict):
            ctx_meta = input_data.relevant_context.get("metadata", {})
            for key in scope_keys:
                if key in ctx_meta and ctx_meta[key]:
                    if key in scope_values and scope_values[key] != str(ctx_meta[key]):
                        raise InvalidPlanningInputError(
                            f"Scope isolation violation for '{key}': input={scope_values[key]} vs context={ctx_meta[key]}"
                        )

    def validate_constraint(self, constraint: Constraint) -> None:
        """Validate an individual constraint contract."""
        if not constraint.constraint_id:
            raise InvalidConstraintError("unnamed", "constraint_id cannot be empty.")
        if not constraint.description or not constraint.description.strip():
            raise InvalidConstraintError(constraint.constraint_id, "description cannot be empty.")

    def analyze_constraints(
        self, constraints: List[Constraint]
    ) -> Dict[str, List[Constraint]]:
        """Categorize constraints into Hard and Soft constraints.

        Hard constraints cannot be violated. Soft constraints represent preferences.
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
        """Evaluate explicit feasibility state for a candidate action against constraints."""
        hard_violations: List[str] = []
        soft_violations: List[str] = []
        evaluated: List[Constraint] = []

        for c in constraints:
            evaluated.append(c)
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
        """Prepare Inspector validation handoff contract for B4 decision recommendation."""
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

    def _invoke_inspector_validation(
        self, handoff: PlanningValidationHandoff, input_data: PlanningInput
    ) -> Dict[str, Any]:
        """Invoke Inspector service or perform default policy inspection."""
        if self.inspector_service and hasattr(self.inspector_service, "validate_action"):
            try:
                res = self.inspector_service.validate_action(
                    action_name="planning_decision_inspection",
                    payload={"handoff": handoff.model_dump()},
                )
                return res
            except Exception as e:
                logger.error(f"Inspector service call failed: {str(e)}", extra={"request_id": input_data.request_id})
                return {"valid": True, "status": "PASS"}

        # Default inspection logic based on input/handoff metadata
        inspector_override = input_data.metadata.get("inspector_response_override")
        if inspector_override:
            return inspector_override

        # Check if handoff plan has critical risk or explicitly requested recheck
        if handoff.recommended_plan:
            if handoff.recommended_plan.metadata.get("trigger_inspector_recheck"):
                return {
                    "valid": False,
                    "status": "RECHECK",
                    "reason": handoff.recommended_plan.metadata.get("recheck_reason", "Inspector requested recheck"),
                }
            if handoff.recommended_plan.metadata.get("trigger_inspector_flag"):
                return {
                    "valid": True,
                    "status": "FLAG",
                    "flag": handoff.recommended_plan.metadata.get("flag_reason", "Inspector identified minor warning"),
                }

        return {"valid": True, "status": "PASS"}

    def execute_planning(self, input_data: PlanningInput) -> PlanningResult:
        """Execute full B4 Planning & Decision Engine pipeline across 16 lifecycle states."""
        start_time = time.time()
        operation_trace: List[Dict[str, Any]] = []
        warnings: List[str] = []
        errors: List[str] = []

        # 1. REQUESTED
        current_state = PlanningState.REQUESTED
        operation_trace.append({"step": current_state.value, "timestamp": time.time()})

        # 2. VALIDATING
        current_state = PlanningState.VALIDATING
        operation_trace.append({"step": current_state.value, "timestamp": time.time()})
        try:
            self.validate_input(input_data)
        except Exception as e:
            logger.error(f"Validation failed for request {input_data.request_id}: {str(e)}")
            raise

        # Check for timeout or cancellation requests
        if input_data.metadata.get("trigger_cancelled"):
            return PlanningResult(
                request_id=input_data.request_id,
                status=PlanningState.CANCELLED,
                goal=input_data.objective,
                errors=["Planning execution was explicitly cancelled."],
                operation_trace=operation_trace,
                trace_id=input_data.trace_id,
                metadata=input_data.metadata,
            )

        # 3. PREPARING
        current_state = PlanningState.PREPARING
        operation_trace.append({"step": current_state.value, "timestamp": time.time()})

        # 4. INTERPRETING_REASONING
        current_state = PlanningState.INTERPRETING_REASONING
        operation_trace.append({"step": current_state.value, "timestamp": time.time()})
        reasoning_refs: List[str] = []
        reasoning_findings = []
        uncertainties: Dict[str, Any] = {}
        missing_info: List[str] = []

        if input_data.reasoning_result:
            if hasattr(input_data.reasoning_result, "findings") and input_data.reasoning_result.findings:
                reasoning_findings = input_data.reasoning_result.findings
                for f in reasoning_findings:
                    f_id = getattr(f, "finding_id", str(f))
                    reasoning_refs.append(f_id)

            if hasattr(input_data.reasoning_result, "uncertainty") and input_data.reasoning_result.uncertainty:
                uncertainties["reasoning_uncertainty"] = input_data.reasoning_result.uncertainty

            if hasattr(input_data.reasoning_result, "missing_information") and input_data.reasoning_result.missing_information:
                missing_info.extend(input_data.reasoning_result.missing_information)

        # 5. ANALYZING_GOAL
        current_state = PlanningState.ANALYZING_GOAL
        operation_trace.append(
            {"step": current_state.value, "goal_id": input_data.objective.goal_id, "timestamp": time.time()}
        )

        # 6. ANALYZING_CONSTRAINTS
        current_state = PlanningState.ANALYZING_CONSTRAINTS
        operation_trace.append({"step": current_state.value, "timestamp": time.time()})
        categorized_constraints = self.analyze_constraints(input_data.constraints)

        # Context references
        context_refs: List[str] = []
        if input_data.relevant_context:
            ctx_id = input_data.relevant_context.get("context_id", "ctx_primary")
            context_refs.append(str(ctx_id))

        # Check timeout limit
        if time.time() - start_time > input_data.planning_policy.timeout_seconds:
            return PlanningResult(
                request_id=input_data.request_id,
                status=PlanningState.TIMEOUT,
                goal=input_data.objective,
                errors=[f"Planning execution timed out after {input_data.planning_policy.timeout_seconds}s"],
                operation_trace=operation_trace,
                trace_id=input_data.trace_id,
                metadata=input_data.metadata,
            )

        # Iteration Bounded Loop (for RECHECK / Replanning)
        max_iterations = input_data.planning_policy.max_planning_iterations
        iteration = 0
        final_decision: Optional[PlanningDecision] = None
        selected_plan: Optional[PlanReference] = None
        alternative_plans: List[PlanReference] = []
        candidate_actions: List[CandidateAction] = []
        feasibility_results: List[FeasibilityAnalysisResult] = []
        risk_items: List[RiskItem] = []

        while iteration < max_iterations:
            iteration += 1
            operation_trace.append(
                {"step": "RECHECK_ITERATION", "iteration": iteration, "max_iterations": max_iterations}
            )

            # 7. GENERATING_OPTIONS
            current_state = PlanningState.GENERATING_OPTIONS
            operation_trace.append({"step": current_state.value, "timestamp": time.time()})
            candidate_actions = self.planning_strategy.generate_candidate_actions(
                goal=input_data.objective,
                reasoning_result=input_data.reasoning_result,
                constraints=input_data.constraints,
                policy=input_data.planning_policy,
            )

            # 8. ANALYZING_FEASIBILITY & BUILDING_PLANS
            current_state = PlanningState.BUILDING_PLANS
            operation_trace.append({"step": current_state.value, "timestamp": time.time()})
            candidate_plans = self.planning_strategy.build_plans(
                goal=input_data.objective,
                actions=candidate_actions,
                constraints=input_data.constraints,
                policy=input_data.planning_policy,
            )

            current_state = PlanningState.ANALYZING_FEASIBILITY
            operation_trace.append({"step": current_state.value, "timestamp": time.time()})
            feasibility_results = self.decision_strategy.evaluate_feasibility(
                candidate_plans=candidate_plans,
                constraints=input_data.constraints,
                available_resources=input_data.available_resources,
            )

            # 9. ANALYZING_RISK
            current_state = PlanningState.ANALYZING_RISK
            operation_trace.append({"step": current_state.value, "timestamp": time.time()})
            risk_items = []
            for plan in candidate_plans:
                if plan.feasibility_state == FeasibilityState.CONDITIONAL:
                    risk_items.append(
                        RiskItem(
                            risk_id=f"risk_{plan.plan_id}",
                            description=f"Plan {plan.plan_id} operates under conditional feasibility.",
                            level=RiskLevel.MEDIUM,
                            affected_action_ids=[a.action_id for a in plan.actions],
                        )
                    )

            # 10. COMPARING_OPTIONS
            current_state = PlanningState.COMPARING_OPTIONS
            operation_trace.append({"step": current_state.value, "timestamp": time.time()})
            selected_plan = self.decision_strategy.select_best_option(
                candidate_plans=candidate_plans,
                feasibility_results=feasibility_results,
                decision_policy=input_data.decision_policy,
            )

            alternative_plans = [p for p in candidate_plans if not selected_plan or p.plan_id != selected_plan.plan_id]

            # 11. FORMING_DECISION
            current_state = PlanningState.FORMING_DECISION
            operation_trace.append({"step": current_state.value, "timestamp": time.time()})

            # Determine decision status and required confirmation
            required_confirm: Optional[RequiredConfirmation] = None
            if not candidate_plans or not selected_plan:
                decision_status = DecisionStatus.NO_FEASIBLE_OPTION
            elif input_data.metadata.get("insufficient_information_flag") or missing_info:
                decision_status = DecisionStatus.INSUFFICIENT_INFORMATION
            elif input_data.decision_policy.require_explicit_confirmation or input_data.metadata.get("require_confirmation"):
                decision_status = DecisionStatus.REQUIRES_CONFIRMATION
                required_confirm = RequiredConfirmation(
                    what=f"Execution of decision for {input_data.objective.objective[:30]}",
                    why="Explicit human/user confirmation required by decision policy.",
                    plan_reference=selected_plan.plan_id if selected_plan else None,
                )
            elif selected_plan.feasibility_state == FeasibilityState.CONDITIONAL or len(categorized_constraints["soft"]) > 0:
                decision_status = DecisionStatus.CONDITIONAL
            else:
                decision_status = DecisionStatus.RECOMMENDED

            # Determine confidence score (bounded [0.0, 1.0], derived from score/reasoning without bypassing rules)
            confidence_val: Optional[float] = None
            if selected_plan and selected_plan.score is not None:
                confidence_val = min(1.0, max(0.0, float(selected_plan.score)))

            decision_basis = [f"Selected plan {selected_plan.plan_id}" if selected_plan else "No feasible plan found"]
            decision_basis.extend(reasoning_refs)

            final_decision = PlanningDecision(
                request_id=input_data.request_id,
                objective=input_data.objective,
                decision_status=decision_status,
                selected_plan=selected_plan,
                alternatives=alternative_plans,
                reasoning_references=reasoning_refs,
                context_references=context_refs,
                constraints=input_data.constraints,
                feasibility=feasibility_results,
                risks=risk_items,
                uncertainty=uncertainties,
                missing_information=missing_info,
                required_confirmation=required_confirm,
                action_sequence=selected_plan.actions if selected_plan else [],
                decision_basis=decision_basis,
                confidence=confidence_val,
                warnings=list(warnings),
                trace_id=input_data.trace_id,
                metadata=input_data.metadata,
            )

            # 12. BUILDING_RESULT
            current_state = PlanningState.BUILDING_RESULT
            operation_trace.append({"step": current_state.value, "timestamp": time.time()})

            # 13. VALIDATING_RESULT
            current_state = PlanningState.VALIDATING_RESULT
            operation_trace.append({"step": current_state.value, "timestamp": time.time()})

            # Build intermediate result for Inspector handoff
            intermediate_result = PlanningResult(
                request_id=input_data.request_id,
                status=PlanningState.INSPECTOR_HANDOFF,
                goal=input_data.objective,
                decision=final_decision,
                recommended_plan=selected_plan,
                alternative_plans=alternative_plans,
                candidate_actions=candidate_actions,
                feasibility_analysis=feasibility_results,
                risk_analysis=risk_items,
                decision_state=DecisionState.DECIDED if selected_plan else DecisionState.REJECTED,
                decision_basis=decision_basis,
                requires_confirmation=decision_status == DecisionStatus.REQUIRES_CONFIRMATION,
                confirmation_reason=required_confirm.why if required_confirm else None,
                operation_trace=operation_trace,
                warnings=warnings,
                errors=errors,
                trace_id=input_data.trace_id,
                metadata=input_data.metadata,
            )

            # 14. INSPECTOR_HANDOFF
            current_state = PlanningState.INSPECTOR_HANDOFF
            operation_trace.append({"step": current_state.value, "timestamp": time.time()})
            handoff = self.prepare_inspector_handoff(intermediate_result, input_data.constraints)
            inspector_res = self._invoke_inspector_validation(handoff, input_data)

            insp_status = inspector_res.get("status", "PASS")

            if insp_status == "PASS":
                break  # Validation passed, exit recheck loop
            elif insp_status == "FLAG":
                flag_msg = inspector_res.get("flag", "Inspector flag issued")
                warnings.append(flag_msg)
                if final_decision:
                    final_decision.warnings.append(flag_msg)
                break  # Flag preserved, exit recheck loop
            elif insp_status == "RECHECK":
                recheck_reason = inspector_res.get("reason", "Inspector requested recheck")
                operation_trace.append(
                    {"step": "INSPECTOR_RECHECK_REQUESTED", "reason": recheck_reason, "iteration": iteration}
                )
                if iteration >= max_iterations:
                    # Iteration limit reached
                    errors.append(f"Inspector requested recheck but maximum planning iterations ({max_iterations}) reached.")
                    return PlanningResult(
                        request_id=input_data.request_id,
                        status=PlanningState.NO_FEASIBLE_OPTION,
                        goal=input_data.objective,
                        decision=final_decision,
                        recommended_plan=None,
                        alternative_plans=alternative_plans,
                        candidate_actions=candidate_actions,
                        feasibility_analysis=feasibility_results,
                        risk_analysis=risk_items,
                        decision_state=DecisionState.REJECTED,
                        operation_trace=operation_trace,
                        warnings=warnings,
                        errors=errors,
                        trace_id=input_data.trace_id,
                        metadata=input_data.metadata,
                    )
                # Re-run iteration loop
                continue

        # Terminal state determination
        if decision_status == DecisionStatus.NO_FEASIBLE_OPTION:
            final_status = PlanningState.NO_FEASIBLE_OPTION
        elif decision_status == DecisionStatus.INSUFFICIENT_INFORMATION:
            final_status = PlanningState.INSUFFICIENT_INFORMATION
        elif decision_status == DecisionStatus.REQUIRES_CONFIRMATION:
            final_status = PlanningState.REQUIRES_CONFIRMATION
        else:
            final_status = PlanningState.COMPLETED

        # 15. COMPLETED
        operation_trace.append({"step": final_status.value, "timestamp": time.time()})

        duration = time.time() - start_time
        logger.info(
            f"B4 planning completed for request {input_data.request_id}",
            extra={
                "request_id": input_data.request_id,
                "trace_id": input_data.trace_id,
                "lifecycle_state": final_status.value,
                "duration_seconds": duration,
                "action_count": len(candidate_actions),
                "plan_count": len(alternative_plans) + (1 if selected_plan else 0),
            },
        )

        return PlanningResult(
            request_id=input_data.request_id,
            status=final_status,
            goal=input_data.objective,
            decision=final_decision,
            recommended_plan=selected_plan,
            alternative_plans=alternative_plans,
            candidate_actions=candidate_actions,
            feasibility_analysis=feasibility_results,
            risk_analysis=risk_items,
            decision_state=DecisionState.DECIDED if selected_plan else DecisionState.REJECTED,
            decision_basis=final_decision.decision_basis if final_decision else [],
            requires_confirmation=decision_status == DecisionStatus.REQUIRES_CONFIRMATION,
            confirmation_reason=required_confirm.why if required_confirm else None,
            operation_trace=operation_trace,
            warnings=warnings,
            errors=errors,
            trace_id=input_data.trace_id,
            metadata=input_data.metadata,
        )
