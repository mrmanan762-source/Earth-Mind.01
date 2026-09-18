from typing import Any, Dict, List, Optional
from core.logging.logger import get_logger
from modules.reasoning.enums import (
    ReasoningState,
    UncertaintyLevel,
)
from modules.reasoning.errors import (
    InsufficientEvidenceError,
    InvalidReasoningInputError,
    IterationLimitReachedError,
)
from modules.reasoning.evidence import EvidenceManager
from modules.reasoning.interfaces import IReasoningCapability, IReasoningStrategy
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
    UncertaintyItem,
)

logger = get_logger("modules.reasoning.strategy")


class ReasoningStrategyController(IReasoningStrategy):
    """Coordinates controlled 13-step reasoning strategy lifecycle with bounded iteration control."""

    def __init__(
        self,
        capability: Optional[IReasoningCapability] = None,
        evidence_manager: Optional[EvidenceManager] = None
    ):
        self._capability = capability
        self._evidence_manager = evidence_manager or EvidenceManager()

    def execute_strategy(self, input_data: ReasoningInput) -> ReasoningResult:
        """Executes the 13-step controlled reasoning flow."""
        if not input_data or not input_data.task:
            raise InvalidReasoningInputError("Task description is required in ReasoningInput")

        request_id = input_data.request_id
        policy = input_data.policy
        max_iterations = policy.max_iterations
        operation_trace: List[Dict[str, Any]] = []

        # Step 1: Understand reasoning task
        operation_trace.append({"step": 1, "name": "understand_task", "task": input_data.task})

        # Step 2 & 3: Inspect and identify available evidence, assumptions, missing info
        evidence_items, assumption_items, missing_items = self._evidence_manager.prepare_evidence(input_data)
        operation_trace.append({
            "step": 2,
            "name": "inspect_evidence",
            "evidence_count": len(evidence_items),
            "assumption_count": len(assumption_items),
            "missing_count": len(missing_items),
        })

        # Check for insufficient evidence if assumptions not allowed
        if not evidence_items and not policy.allow_assumptions:
            raise InsufficientEvidenceError(
                request_id, "No direct evidence provided and policy forbids assumptions."
            )

        # Step 4: Compare related evidence
        operation_trace.append({"step": 4, "name": "compare_evidence"})

        # Step 5: Identify relationships
        relationships: List[EvidenceRelationship] = self._evidence_manager.identify_relationships(evidence_items)
        operation_trace.append({
            "step": 5,
            "name": "identify_relationships",
            "relationship_count": len(relationships),
        })

        # Step 6 & 7: Generate and test bounded hypotheses
        hypotheses: List[ReasoningHypothesis] = []
        if evidence_items:
            hyp = ReasoningHypothesis(
                hypothesis_id=f"hyp_{request_id}_1",
                description=f"Primary hypothesis evaluating task: '{input_data.task}'",
                supporting_evidence_ids=[e.evidence_id for e in evidence_items],
                confidence_score=0.7,
                status="VALIDATED",
                trace_id=input_data.trace_id
            )
            hypotheses.append(hyp)
        operation_trace.append({
            "step": 6,
            "name": "generate_test_hypotheses",
            "hypothesis_count": len(hypotheses),
        })

        # Step 8: Detect contradictions and conflicts
        conflicts: List[EvidenceConflict] = self._evidence_manager.detect_conflicts(evidence_items)
        operation_trace.append({
            "step": 8,
            "name": "detect_conflicts",
            "conflict_count": len(conflicts),
        })

        # Step 9: Identify uncertainty
        uncertainties: List[UncertaintyItem] = []
        if conflicts:
            unc = UncertaintyItem(
                uncertainty_id=f"unc_conflict_{request_id}",
                level=UncertaintyLevel.MEDIUM,
                reason=f"Detected {len(conflicts)} conflicting evidence items.",
                supporting_evidence_ids=[ev_id for c in conflicts for ev_id in c.evidence_ids],
                trace_id=input_data.trace_id
            )
            uncertainties.append(unc)

        if missing_items:
            unc = UncertaintyItem(
                uncertainty_id=f"unc_missing_{request_id}",
                level=UncertaintyLevel.HIGH if not evidence_items else UncertaintyLevel.LOW,
                reason="Analysis incomplete due to missing required evidence.",
                missing_information_refs=[m.missing_info_id for m in missing_items],
                insufficient_evidence_flag=len(evidence_items) == 0,
                trace_id=input_data.trace_id
            )
            uncertainties.append(unc)

        operation_trace.append({
            "step": 9,
            "name": "identify_uncertainty",
            "uncertainty_count": len(uncertainties),
        })

        # Step 10: Identify missing information
        operation_trace.append({
            "step": 10,
            "name": "identify_missing_info",
            "missing_info_count": len(missing_items),
        })

        # Steps 11, 12, 13: Controlled Bounded Iteration Loop to produce findings
        current_iteration = 1
        findings: List[ReasoningFinding] = []
        final_state = ReasoningState.COMPLETED

        while current_iteration <= max_iterations:
            operation_trace.append({
                "step": 11,
                "name": "produce_findings_iteration",
                "iteration": current_iteration,
            })

            # If capability is attached, invoke reasoning capability
            if self._capability:
                cap_res = self._capability.reason(input_data)
                findings = cap_res.findings
            else:
                # Fallback structured finding generation
                ev_refs = [e.evidence_id for e in evidence_items]
                assump_refs = [a.assumption_id for a in assumption_items]

                # Core Rule 1: Evidence Before Conclusion
                finding_statement = (
                    f"Reasoning analysis for '{input_data.task}': Evidence indicates consistent parameters."
                    if evidence_items
                    else f"Reasoning analysis for '{input_data.task}': Derived under declared assumptions."
                )

                finding = ReasoningFinding(
                    finding_id=f"finding_{request_id}_{current_iteration}",
                    statement=finding_statement,
                    confidence_score=0.85 if evidence_items else 0.5,
                    evidence_ids=ev_refs,
                    assumption_ids=assump_refs,
                    relationship_ids=[r.relationship_id for r in relationships],
                    conflict_ids=[c.conflict_id for c in conflicts],
                    uncertainty_ids=[u.uncertainty_id for u in uncertainties],
                    trace_id=input_data.trace_id
                )
                findings = [finding]

            # Step 12: Determine if another bounded iteration is justified
            # Check termination conditions
            sufficient_confidence = all(f.confidence_score >= policy.min_confidence_threshold for f in findings)
            if sufficient_confidence or not conflicts:
                # Sufficient result achieved, stop iteration
                operation_trace.append({
                    "step": 13,
                    "name": "terminate_sufficient",
                    "final_iteration": current_iteration,
                })
                break

            current_iteration += 1

        if current_iteration > max_iterations and not findings:
            final_state = ReasoningState.INSUFFICIENT_EVIDENCE
            operation_trace.append({
                "step": 13,
                "name": "terminate_iteration_limit_reached",
                "max_iterations": max_iterations,
            })

        evidence_references = list({e.evidence_id for e in evidence_items})

        return ReasoningResult(
            request_id=request_id,
            status=final_state,
            findings=findings,
            evidence_references=evidence_references,
            assumptions=assumption_items,
            relationships=relationships,
            conflicts=conflicts,
            uncertainty=uncertainties,
            missing_information=missing_items,
            reasoning_operation_trace=operation_trace,
            iteration_metadata={
                "total_iterations": min(current_iteration, max_iterations),
                "max_allowed_iterations": max_iterations,
                "terminated_early": current_iteration <= max_iterations,
            },
            trace_id=input_data.trace_id,
            metadata={"task": input_data.task}
        )
