"""Stage R15 Regression Evaluator."""

from typing import List, Optional
from core.schemas.evaluation import EvaluationRun, QualityStatus, RegressionResult


class RegressionEvaluator:
    """Compares two evaluation runs (Run A vs Run B) to detect quality and performance regressions."""

    def __init__(self, default_threshold_pct: float = 5.0):
        self.default_threshold_pct = default_threshold_pct

    def _compare_metric(
        self,
        metric_name: str,
        run_a: EvaluationRun,
        run_b: EvaluationRun,
        val_a: Optional[float],
        val_b: Optional[float],
        threshold_pct: float,
        higher_is_better: bool = True,
    ) -> RegressionResult:
        if val_a is None or val_b is None:
            return RegressionResult(
                metric_name=metric_name,
                run_a_id=run_a.run_id,
                run_b_id=run_b.run_id,
                value_a=val_a,
                value_b=val_b,
                absolute_diff=None,
                relative_diff_pct=None,
                regression_detected=False,
                details=f"Metric '{metric_name}' is not evaluable on one or both runs.",
            )

        abs_diff = round(val_b - val_a, 4)
        rel_diff_pct = round(((val_b - val_a) / float(val_a)) * 100.0, 2) if val_a != 0 else 0.0

        regression = False
        if higher_is_better:
            if rel_diff_pct < -abs(threshold_pct):
                regression = True
        else:
            if rel_diff_pct > abs(threshold_pct):
                regression = True

        details = f"{metric_name}: Run A={val_a}, Run B={val_b} ({rel_diff_pct:+.2f}%)."
        if regression:
            details += f" REGRESSION DETECTED (exceeded threshold {threshold_pct}%)."

        return RegressionResult(
            metric_name=metric_name,
            run_a_id=run_a.run_id,
            run_b_id=run_b.run_id,
            value_a=val_a,
            value_b=val_b,
            absolute_diff=abs_diff,
            relative_diff_pct=rel_diff_pct,
            regression_detected=regression,
            details=details,
        )

    def compare_runs(
        self,
        previous_run: EvaluationRun,
        current_run: EvaluationRun,
        threshold_pct: Optional[float] = None,
    ) -> List[RegressionResult]:
        """
        Compares quality (MRR, Hit Rate, nDCG), performance (Latency, QPS), and reliability (Success Rate).
        """
        thresh = threshold_pct if threshold_pct is not None else self.default_threshold_pct
        results: List[RegressionResult] = []

        q_a = previous_run.quality_metrics
        q_b = current_run.quality_metrics

        if q_a and q_b and q_a.status == QualityStatus.EVALUATED and q_b.status == QualityStatus.EVALUATED:
            results.append(self._compare_metric("mrr", previous_run, current_run, q_a.mrr, q_b.mrr, thresh, higher_is_better=True))
            results.append(self._compare_metric("hit_rate@5", previous_run, current_run, q_a.hit_rate_at_k.get(5), q_b.hit_rate_at_k.get(5), thresh, higher_is_better=True))
            results.append(self._compare_metric("ndcg@5", previous_run, current_run, q_a.ndcg_at_k.get(5), q_b.ndcg_at_k.get(5), thresh, higher_is_better=True))

        p_a = previous_run.performance_metrics
        p_b = current_run.performance_metrics

        if p_a and p_b:
            results.append(self._compare_metric("p50_latency_ms", previous_run, current_run, p_a.total_latency.p50_ms, p_b.total_latency.p50_ms, thresh, higher_is_better=False))
            results.append(self._compare_metric("p90_latency_ms", previous_run, current_run, p_a.total_latency.p90_ms, p_b.total_latency.p90_ms, thresh, higher_is_better=False))
            results.append(self._compare_metric("throughput_qps", previous_run, current_run, p_a.throughput_qps, p_b.throughput_qps, thresh, higher_is_better=True))

        r_a = previous_run.reliability_metrics
        r_b = current_run.reliability_metrics

        if r_a and r_b:
            results.append(self._compare_metric("success_rate", previous_run, current_run, r_a.success_rate, r_b.success_rate, thresh, higher_is_better=True))

        return results
