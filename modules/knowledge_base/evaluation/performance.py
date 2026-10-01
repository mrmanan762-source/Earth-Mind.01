"""Stage R15 Latency, Throughput, and Resource Usage Performance Evaluator."""

import resource
from typing import Any, Dict, List, Optional
from core.schemas.evaluation import (
    EvaluationMeasurement,
    LatencySummary,
    PerformanceMetrics,
)


class PerformanceEvaluator:
    """Evaluates latency percentiles, throughput, and optional process resource usage."""

    def _calculate_latency_summary(self, values: List[float]) -> LatencySummary:
        if not values:
            return LatencySummary()

        sorted_vals = sorted(values)
        n = len(sorted_vals)

        def percentile(p: float) -> float:
            idx = int(round((p / 100.0) * (n - 1)))
            idx = max(0, min(n - 1, idx))
            return round(sorted_vals[idx], 2)

        return LatencySummary(
            p50_ms=percentile(50.0),
            p90_ms=percentile(90.0),
            p95_ms=percentile(95.0),
            p99_ms=percentile(99.0),
            mean_ms=round(sum(sorted_vals) / n, 2),
            min_ms=round(sorted_vals[0], 2),
            max_ms=round(sorted_vals[-1], 2),
        )

    def evaluate_performance(
        self,
        measurements: List[EvaluationMeasurement],
        total_time_seconds: float,
        execution_mode: str = "sequential",
    ) -> PerformanceMetrics:
        """
        Calculates E2E latency summary, stage latency breakdown, throughput, and process resources.
        """
        if not measurements:
            return PerformanceMetrics(
                total_latency=LatencySummary(),
                stage_latencies={},
                throughput_qps=0.0,
                cases_per_second=0.0,
                execution_mode=execution_mode,
                resource_usage={"memory_rss_mb": "UNAVAILABLE", "cpu_percent": "UNAVAILABLE"},
            )

        total_latencies = [m.total_latency_ms for m in measurements if m.total_latency_ms > 0]
        e2e_summary = self._calculate_latency_summary(total_latencies)

        # Collect stage latencies
        stage_map: Dict[str, List[float]] = {}
        for m in measurements:
            for stage, lat in m.stage_latencies_ms.items():
                if stage not in stage_map:
                    stage_map[stage] = []
                stage_map[stage].append(lat)

        stage_summaries = {stage: self._calculate_latency_summary(lats) for stage, lats in stage_map.items()}

        cases_count = len(measurements)
        successful_count = sum(1 for m in measurements if m.status == "SUCCESS")

        qps = round(successful_count / total_time_seconds, 2) if total_time_seconds > 0 else 0.0
        cps = round(cases_count / total_time_seconds, 2) if total_time_seconds > 0 else 0.0

        # Collect process resource metrics using stdlib resource module
        res_info: Dict[str, Any] = {}
        try:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            # maxrss in Linux is in kilobytes
            res_info["max_rss_mb"] = round(usage.ru_maxrss / 1024.0, 2)
            res_info["user_cpu_time_s"] = round(usage.ru_utime, 2)
            res_info["system_cpu_time_s"] = round(usage.ru_stime, 2)
        except Exception:
            res_info = {"memory_rss_mb": "UNAVAILABLE", "cpu_percent": "UNAVAILABLE"}

        return PerformanceMetrics(
            total_latency=e2e_summary,
            stage_latencies=stage_summaries,
            throughput_qps=qps,
            cases_per_second=cps,
            execution_mode=execution_mode,
            resource_usage=res_info,
        )
