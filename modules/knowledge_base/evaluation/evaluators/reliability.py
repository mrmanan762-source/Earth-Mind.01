"""Reliability Evaluator for Stage R15."""

from typing import Any, Dict, List
from core.interfaces.evaluation import IReliabilityEvaluator
from core.schemas.evaluation import EvaluationOutcome, MetricStatus, ReliabilityMetrics


class ReliabilityEvaluator(IReliabilityEvaluator):
    """Evaluates case outcomes and computes success, failure, timeout, empty, and partial rates."""

    def evaluate_reliability(self, outcomes: List[Any]) -> ReliabilityMetrics:
        if not outcomes:
            return ReliabilityMetrics(
                status=MetricStatus.INSUFFICIENT_DATA,
                total_cases=0,
            )

        total = len(outcomes)
        counts: Dict[str, int] = {
            EvaluationOutcome.SUCCESS.value: 0,
            EvaluationOutcome.VALID_EMPTY_RESULT.value: 0,
            EvaluationOutcome.PARTIAL_RESULT.value: 0,
            EvaluationOutcome.TIMEOUT.value: 0,
            EvaluationOutcome.SYSTEM_FAILURE.value: 0,
            EvaluationOutcome.UNAVAILABLE.value: 0,
        }

        for outcome in outcomes:
            status_str = getattr(outcome, "value", str(outcome))
            if status_str in counts:
                counts[status_str] += 1
            else:
                counts[EvaluationOutcome.SYSTEM_FAILURE.value] += 1

        successes = counts[EvaluationOutcome.SUCCESS.value] + counts[EvaluationOutcome.VALID_EMPTY_RESULT.value]
        failures = counts[EvaluationOutcome.SYSTEM_FAILURE.value] + counts[EvaluationOutcome.UNAVAILABLE.value]
        timeouts = counts[EvaluationOutcome.TIMEOUT.value]
        empties = counts[EvaluationOutcome.VALID_EMPTY_RESULT.value]
        partials = counts[EvaluationOutcome.PARTIAL_RESULT.value]

        return ReliabilityMetrics(
            status=MetricStatus.EVALUATED,
            total_cases=total,
            success_count=successes,
            success_rate=round(successes / float(total), 4),
            failure_count=failures,
            failure_rate=round(failures / float(total), 4),
            timeout_count=timeouts,
            timeout_rate=round(timeouts / float(total), 4),
            empty_result_count=empties,
            empty_result_rate=round(empties / float(total), 4),
            partial_result_count=partials,
            partial_result_rate=round(partials / float(total), 4),
            outcome_counts=counts,
        )
