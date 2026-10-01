"""Regression Evaluator for Stage R15 (Comparing Run A vs Run B)."""

import uuid
from typing import Any, Dict, List, Optional
from core.interfaces.evaluation import IRegressionEvaluator
from core.schemas.evaluation import EvaluationReport, RegressionResult


class RegressionEvaluator(IRegressionEvaluator):
    """Compares base report vs target report to identify metric regressions or improvements."""

    def evaluate_regression(
        self,
        base_report: EvaluationReport,
        target_report: EvaluationReport,
    ) -> RegressionResult:
        comp_id = f"cmp_{uuid.uuid4().hex[:8]}"

        regressions: List[str] = []
        improvements: List[str] = []
        diffs: Dict[str, Dict[str, Any]] = {}

        # Compare Quality Metrics
        base_mrr = base_report.quality_metrics.mrr
        target_mrr = target_report.quality_metrics.mrr
        mrr_diff = round(target_mrr - base_mrr, 4)
        mrr_rel = round(mrr_diff / base_mrr, 4) if base_mrr > 0 else 0.0

        diffs["mrr"] = {"base": base_mrr, "target": target_mrr, "abs_diff": mrr_diff, "rel_diff": mrr_rel}
        if mrr_diff < -0.05:
            regressions.append(f"MRR degraded from {base_mrr} to {target_mrr} (diff: {mrr_diff})")
        elif mrr_diff > 0.05:
            improvements.append(f"MRR improved from {base_mrr} to {target_mrr} (diff: +{mrr_diff})")

        # Compare Latency
        base_lat = base_report.performance_metrics.avg_e2e_latency_ms
        target_lat = target_report.performance_metrics.avg_e2e_latency_ms
        lat_diff = round(target_lat - base_lat, 2)
        lat_rel = round(lat_diff / base_lat, 4) if base_lat > 0 else 0.0

        diffs["avg_e2e_latency_ms"] = {"base": base_lat, "target": target_lat, "abs_diff": lat_diff, "rel_diff": lat_rel}
        if lat_rel > 0.20:
            regressions.append(f"Average latency degraded by {round(lat_rel * 100, 1)}% ({base_lat}ms -> {target_lat}ms)")
        elif lat_rel < -0.20:
            improvements.append(f"Average latency improved by {round(abs(lat_rel) * 100, 1)}% ({base_lat}ms -> {target_lat}ms)")

        # Compare Reliability
        base_succ = base_report.reliability_metrics.success_rate
        target_succ = target_report.reliability_metrics.success_rate
        succ_diff = round(target_succ - base_succ, 4)

        diffs["success_rate"] = {"base": base_succ, "target": target_succ, "abs_diff": succ_diff}
        if succ_diff < -0.05:
            regressions.append(f"Success rate degraded from {base_succ} to {target_succ}")
        elif succ_diff > 0.05:
            improvements.append(f"Success rate improved from {base_succ} to {target_succ}")

        overall_status = "NO_REGRESSION"
        if regressions:
            overall_status = "REGRESSION_DETECTED"
        elif improvements:
            overall_status = "IMPROVEMENT_DETECTED"

        return RegressionResult(
            comparison_id=comp_id,
            base_run_id=base_report.evaluation_run_id,
            target_run_id=target_report.evaluation_run_id,
            metrics_diff=diffs,
            regressions_detected=regressions,
            improvements_detected=improvements,
            overall_status=overall_status,
        )
