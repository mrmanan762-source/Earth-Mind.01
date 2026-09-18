import time
from typing import Any, Dict, List, Optional, Tuple

from core.interfaces.services import InspectorInterface
from core.logging.logger import get_logger
from modules.reasoning.capability import ModelLayerReasoningCapability
from modules.reasoning.components.comparison_analyzer import EvidenceComparisonAnalyzer
from modules.reasoning.components.conflict_analyzer import ConflictAnalyzer
from modules.reasoning.components.context_processor import InputValidator, ReasoningContextProcessor
from modules.reasoning.components.hypothesis_analyzer import HypothesisAnalyzer
from modules.reasoning.components.iteration_controller import IterationController
from modules.reasoning.components.missing_info_analyzer import MissingInformationAnalyzer
from modules.reasoning.components.result_builder import ReasoningResultBuilder
from modules.reasoning.components.result_validator import ResultValidator
from modules.reasoning.components.state_manager import ReasoningStateManager
from modules.reasoning.components.uncertainty_analyzer import UncertaintyAnalyzer
from modules.reasoning.enums import ReasoningState, ValidationStatus
from modules.reasoning.errors import (
    InsufficientEvidenceError,
    ReasoningCapabilityUnavailableError,
    ReasoningError,
    ReasoningTimeoutError,
)
from modules.reasoning.evidence import EvidenceManager
from modules.reasoning.interfaces import IReasoningCapability
from modules.reasoning.schemas import (
    AssumptionItem,
    EvidenceConflict,
    EvidenceItem,
    EvidenceRelationship,
    MissingInformationItem,
    ReasoningFinding,
    ReasoningHypothesis,
    ReasoningInput,
    ReasoningResult,
    ReasoningValidationHandoff,
    UncertaintyItem,
)
from modules.reasoning.traceability import ReasoningTraceManager
from modules.reasoning.validation import InspectorHandoffManager

logger = get_logger("modules.reasoning.engine")


class ReasoningEngine:
    """Executable B3 Reasoning Engine coordinating the 16 single-responsibility components

    and 12-state lifecycle pipeline.
    """

    def __init__(
        self,
        capability: Optional[IReasoningCapability] = None,
        inspector: Optional[InspectorInterface] = None
    ):
        self._capability = capability or ModelLayerReasoningCapability()
        self._evidence_manager = EvidenceManager()
        self._input_validator = InputValidator()
        self._context_processor = ReasoningContextProcessor(self._evidence_manager)
        self._comparison_analyzer = EvidenceComparisonAnalyzer()
        self._conflict_analyzer = ConflictAnalyzer()
        self._uncertainty_analyzer = UncertaintyAnalyzer()
        self._missing_info_analyzer = MissingInformationAnalyzer()
        self._hypothesis_analyzer = HypothesisAnalyzer()
        self._result_builder = ReasoningResultBuilder()
        self._result_validator = ResultValidator()
        self._trace_manager = ReasoningTraceManager()
        self._handoff_manager = InspectorHandoffManager(inspector=inspector)

    def set_capability(self, capability: IReasoningCapability) -> None:
        """Set or replace the underlying model reasoning capability."""
        self._capability = capability

    def set_inspector(self, inspector: InspectorInterface) -> None:
        """Set or update the Inspector service for validation handoffs."""
        self._handoff_manager.set_inspector(inspector)

    def execute(
        self,
        input_data: ReasoningInput,
        cancel_requested: bool = False
    ) -> Tuple[ReasoningResult, ReasoningValidationHandoff]:
        """Execute complete B3 reasoning pipeline."""
        start_time = time.time()
        req_id = input_data.request_id
        policy = input_data.policy
        timeout_sec = policy.strategy_timeout_seconds
        trace_id = input_data.trace_id or f"trace_{req_id}"

        # Initialize State Manager
        state_mgr = ReasoningStateManager(request_id=req_id, initial_state=ReasoningState.REQUESTED)

        # Check early cancellation
        if cancel_requested:
            state_mgr.transition_to(ReasoningState.CANCELLED, "Cancellation requested before start.")
            raise ReasoningError(
                message=f"Reasoning request '{req_id}' was cancelled.",
                error_code="REASONING_CANCELLED",
                operation="execute"
            )

        operation_trace: List[Dict[str, Any]] = []

        try:
            # 1. Input Validation
            state_mgr.transition_to(ReasoningState.VALIDATING, "Validating input request payload.")
            self._input_validator.validate(input_data)
            self._trace_manager.record_operation(req_id, "validate_input", metadata={"task": input_data.task})

            # Check timeout
            self._check_timeout(start_time, timeout_sec, req_id)

            # 2. Context Preparation
            state_mgr.transition_to(ReasoningState.PREPARING_CONTEXT, "Processing context items from Context Manager.")
            evidence_items, assumption_items, missing_items = self._context_processor.process_context(input_data)
            self._trace_manager.record_operation(
                req_id,
                "prepare_context",
                evidence_ids=[e.evidence_id for e in evidence_items]
            )

            # Check insufficient evidence
            if not evidence_items and not policy.allow_assumptions:
                state_mgr.transition_to(ReasoningState.INSUFFICIENT_EVIDENCE, "No evidence items and assumptions forbidden.")
                raise InsufficientEvidenceError(req_id, "No direct evidence provided and policy forbids assumptions.")

            # Check timeout
            self._check_timeout(start_time, timeout_sec, req_id)

            # 3. Evidence Analysis
            state_mgr.transition_to(ReasoningState.ANALYZING_EVIDENCE, "Analyzing evidence quality and provenance.")
            self._trace_manager.record_operation(req_id, "analyze_evidence", evidence_ids=[e.evidence_id for e in evidence_items])

            # 4. Evidence Comparison
            state_mgr.transition_to(ReasoningState.COMPARING_EVIDENCE, "Comparing evidence items.")

            # 5. Relationship Analysis
            state_mgr.transition_to(ReasoningState.ANALYZING_RELATIONSHIPS, "Identifying evidence relationships.")
            relationships: List[EvidenceRelationship] = self._comparison_analyzer.analyze_relationships(evidence_items)

            # 6. Conflict Analysis
            state_mgr.transition_to(ReasoningState.ANALYZING_CONFLICTS, "Detecting evidence conflicts.")
            conflicts: List[EvidenceConflict] = self._conflict_analyzer.analyze_conflicts(evidence_items)

            # 7. Uncertainty & Missing Information Analysis
            state_mgr.transition_to(ReasoningState.ANALYZING_UNCERTAINTY, "Analyzing uncertainty and missing information.")
            task_missing = self._missing_info_analyzer.analyze_missing_info(input_data.task, evidence_items, trace_id)
            missing_items.extend(task_missing)

            uncertainties: List[UncertaintyItem] = self._uncertainty_analyzer.analyze_uncertainty(
                evidence_items=evidence_items,
                conflicts=conflicts,
                missing_items=missing_items,
                trace_id=trace_id
            )

            hypotheses: List[ReasoningHypothesis] = self._hypothesis_analyzer.generate_hypotheses(
                task=input_data.task,
                evidence_items=evidence_items,
                conflicts=conflicts,
                trace_id=trace_id
            )

            # 8. Controlled Iteration
            state_mgr.transition_to(ReasoningState.ITERATING, "Entering controlled iteration loop.")
            iteration_ctrl = IterationController(policy)
            current_iteration = 1
            findings: List[ReasoningFinding] = []

            while True:
                self._check_timeout(start_time, timeout_sec, req_id)

                if self._capability:
                    try:
                        cap_res = self._capability.reason(input_data)
                        findings = cap_res.findings
                    except ReasoningCapabilityUnavailableError:
                        raise
                    except Exception as e:
                        logger.error(f"Reasoning capability invocation error: {str(e)}")
                        raise ReasoningCapabilityUnavailableError("capability", str(e)) from e
                else:
                    finding_statement = (
                        f"Reasoning analysis for '{input_data.task}': Derived from evidence analysis."
                        if evidence_items
                        else f"Reasoning analysis for '{input_data.task}': Derived under declared assumptions."
                    )
                    finding = ReasoningFinding(
                        finding_id=f"finding_{req_id}_{current_iteration}",
                        statement=finding_statement,
                        confidence_score=0.85 if evidence_items else 0.50,
                        evidence_ids=[e.evidence_id for e in evidence_items],
                        assumption_ids=[a.assumption_id for a in assumption_items],
                        relationship_ids=[r.relationship_id for r in relationships],
                        conflict_ids=[c.conflict_id for c in conflicts],
                        uncertainty_ids=[u.uncertainty_id for u in uncertainties],
                        trace_id=trace_id
                    )
                    findings = [finding]

                has_unresolved = any(not c.is_resolved for c in conflicts)
                should_continue, term_reason = iteration_ctrl.should_continue(
                    current_iteration=current_iteration,
                    findings=findings,
                    has_unresolved_conflicts=has_unresolved
                )

                iteration_ctrl.record_iteration(
                    iteration_number=current_iteration,
                    strategy_operation="execute_model_reasoning",
                    evidence_references=[e.evidence_id for e in evidence_items],
                    result_status=ReasoningState.ITERATING,
                    termination_reason=term_reason if not should_continue else None
                )

                operation_trace.append(
                    {
                        "iteration": current_iteration,
                        "operation": "execute_model_reasoning",
                        "findings_count": len(findings),
                        "should_continue": should_continue,
                        "termination_reason": term_reason,
                    }
                )

                if not should_continue:
                    break

                current_iteration += 1

            # 9. Result Construction
            state_mgr.transition_to(ReasoningState.BUILDING_RESULT, "Constructing structured ReasoningResult.")
            result = self._result_builder.build_result(
                request_id=req_id,
                status=ReasoningState.COMPLETED,
                findings=findings,
                evidence_items=evidence_items,
                assumptions=assumption_items,
                relationships=relationships,
                conflicts=conflicts,
                uncertainty=uncertainties,
                missing_info=missing_items,
                operation_trace=operation_trace,
                iteration_metadata={
                    "total_iterations": current_iteration,
                    "max_allowed_iterations": policy.max_iterations,
                    "iteration_records": [r.to_dict() for r in iteration_ctrl.iteration_records],
                },
                model_metadata=self._capability.status() if (self._capability and isinstance(self._capability.status(), dict)) else {"status": str(self._capability.status() if self._capability else "none")},
                trace_id=trace_id,
                metadata={"state_history": state_mgr.history}
            )

            # 10. Result Validation
            state_mgr.transition_to(ReasoningState.VALIDATING_RESULT, "Validating result structure and rule compliance.")
            self._result_validator.validate_result(result)

            # 11. Inspector Validation Handoff (Core Rule 7)
            handoff = self._handoff_manager.handoff_validation(result)

            # 12. Final State
            state_mgr.transition_to(ReasoningState.COMPLETED, "Reasoning pipeline completed successfully.")

            return result, handoff

        except ReasoningTimeoutError as te:
            state_mgr.transition_to(ReasoningState.TIMEOUT, str(te))
            raise te
        except (InsufficientEvidenceError, ReasoningCapabilityUnavailableError, ReasoningError) as re:
            if state_mgr.current_state not in (ReasoningState.INSUFFICIENT_EVIDENCE, ReasoningState.TIMEOUT, ReasoningState.CANCELLED):
                try:
                    state_mgr.transition_to(ReasoningState.FAILED, str(re))
                except Exception:
                    pass
            raise re
        except Exception as e:
            try:
                state_mgr.transition_to(ReasoningState.FAILED, str(e))
            except Exception:
                pass
            raise ReasoningError(message=f"Internal reasoning engine error: {str(e)}", operation="execute") from e

    def _check_timeout(self, start_time: float, timeout_sec: float, req_id: str) -> None:
        if (time.time() - start_time) > timeout_sec:
            raise ReasoningTimeoutError(req_id, timeout_sec)
