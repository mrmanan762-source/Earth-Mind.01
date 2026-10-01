"""Stage R15 Controlled Baseline Comparator."""

from typing import Any, Dict, List
from core.schemas.evaluation import BaselineResult


class BaselineComparator:
    """Compares metrics across controlled baseline evaluation results."""

    def compare_baselines(
        self,
        baseline_results: List[BaselineResult],
    ) -> Dict[str, Any]:
        """
        Summarizes and compares baseline results across quality, performance, and reliability.
        """
        if not baseline_results:
            return {"baselines_count": 0, "comparison_table": [], "summary": "No baseline results provided."}

        summary_table: List[Dict[str, Any]] = []
        for b in baseline_results:
            summary_table.append({
                "baseline_name": b.baseline_name,
                "dataset_id": b.dataset_id,
                "mrr": b.quality_metrics.mrr,
                "hit_rate_at_5": b.quality_metrics.hit_rate_at_k.get(5),
                "ndcg_at_5": b.quality_metrics.ndcg_at_k.get(5),
                "p50_latency_ms": b.performance_metrics.total_latency.p50_ms,
                "p90_latency_ms": b.performance_metrics.total_latency.p90_ms,
                "throughput_qps": b.performance_metrics.throughput_qps,
                "success_rate": b.reliability_metrics.success_rate,
                "timestamp": b.timestamp,
            })

        return {
            "baselines_count": len(baseline_results),
            "comparison_table": summary_table,
            "summary": f"Successfully compared {len(baseline_results)} controlled baseline scenarios.",
        }
