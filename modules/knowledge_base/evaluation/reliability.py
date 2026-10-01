"""Stage R15 System Reliability and Error Rate Evaluator."""

from typing import Dict, List
from core.schemas.evaluation import EvaluationMeasurement, ReliabilityMetrics, ReliabilityStatus


class ReliabilityEvaluator:
    """Evaluates execution status classifications, error rates, and failure breakdowns."""

    def evaluate_reliability(
        self,
        measurements: List[EvaluationMeasurement],
    ) -> ReliabilityMetrics:
        """
        Calculates case success rate, failure rate, empty result rate, and failure taxonomy breakdown.
        """
        if not measurements:
            return ReliabilityMetrics(
                total_cases=0,
                success_count=0,
                valid_empty_count=0,
                system_failure_count=0,
                partial_result_count=0,
                timeout_count=0,
                success_rate=0.0,
                failure_rate=0.0,
                empty_result_rate=0.0,
                failure_breakdown={},
            )

        total = len(measurements)
        success = 0
        valid_empty = 0
        system_failure = 0
        partial = 0
        timeout = 0
        breakdown: Dict[str, int] = {}

        for m in measurements:
            status = m.status
            if status == ReliabilityStatus.SUCCESS:
                success += 1
            elif status == ReliabilityStatus.VALID_EMPTY_RESULT:
                valid_empty += 1
            elif status == ReliabilityStatus.SYSTEM_FAILURE:
                system_failure += 1
                err_key = m.error_code or "SYSTEM_ERROR"
                breakdown[err_key] = breakdown.get(err_key, 0) + 1
            elif status == ReliabilityStatus.PARTIAL_RESULT:
                partial += 1
                err_key = "PARTIAL_RESULT"
                breakdown[err_key] = breakdown.get(err_key, 0) + 1
            elif status == ReliabilityStatus.TIMEOUT:
                timeout += 1
                err_key = "TIMEOUT"
                breakdown[err_key] = breakdown.get(err_key, 0) + 1

        success_rate = round(success / float(total), 4)
        failure_rate = round((system_failure + timeout) / float(total), 4)
        empty_rate = round(valid_empty / float(total), 4)

        return ReliabilityMetrics(
            total_cases=total,
            success_count=success,
            valid_empty_count=valid_empty,
            system_failure_count=system_failure,
            partial_result_count=partial,
            timeout_count=timeout,
            success_rate=success_rate,
            failure_rate=failure_rate,
            empty_result_rate=empty_rate,
            failure_breakdown=breakdown,
        )
