from typing import Any, Dict, List, Optional, Tuple
from modules.reasoning.enums import ReasoningState
from modules.reasoning.schemas import (
    ReasoningFinding,
    ReasoningPolicyConfig,
    ReasoningResult,
)


class IterationRecord:
    """Record of a single reasoning iteration."""

    def __init__(
        self,
        iteration_number: int,
        strategy_operation: str,
        evidence_references: List[str],
        result_status: ReasoningState,
        termination_reason: Optional[str] = None
    ):
        self.iteration_number = iteration_number
        self.strategy_operation = strategy_operation
        self.evidence_references = evidence_references
        self.result_status = result_status
        self.termination_reason = termination_reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration_number": self.iteration_number,
            "strategy_operation": self.strategy_operation,
            "evidence_references": self.evidence_references,
            "result_status": self.result_status.value,
            "termination_reason": self.termination_reason,
        }


class IterationController:
    """Controls bounded reasoning iterations and records iteration metrics and termination reasons."""

    def __init__(self, policy: ReasoningPolicyConfig):
        self.policy = policy
        self.max_iterations = policy.max_iterations
        self._iteration_records: List[IterationRecord] = []

    @property
    def iteration_records(self) -> List[IterationRecord]:
        return list(self._iteration_records)

    def record_iteration(
        self,
        iteration_number: int,
        strategy_operation: str,
        evidence_references: List[str],
        result_status: ReasoningState,
        termination_reason: Optional[str] = None
    ) -> IterationRecord:
        rec = IterationRecord(
            iteration_number=iteration_number,
            strategy_operation=strategy_operation,
            evidence_references=evidence_references,
            result_status=result_status,
            termination_reason=termination_reason
        )
        self._iteration_records.append(rec)
        return rec

    def should_continue(
        self,
        current_iteration: int,
        findings: List[ReasoningFinding],
        has_unresolved_conflicts: bool
    ) -> Tuple[bool, str]:
        """Determine if another iteration is justified or if termination conditions are met."""
        if current_iteration >= self.max_iterations:
            return False, f"Reached maximum allowed iterations limit ({self.max_iterations})."

        if findings and all(f.confidence_score >= self.policy.min_confidence_threshold for f in findings):
            if not has_unresolved_conflicts:
                return False, f"Sufficient confidence threshold ({self.policy.min_confidence_threshold}) reached."

        return True, "Further iteration justified to resolve conflict or increase confidence."
