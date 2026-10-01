"""Performance Evaluator for Stage R15 (Latency, Throughput, Resource Usage)."""

import time
from typing import Any, Dict, List, Optional
from core.interfaces.evaluation import IPerformanceEvaluator
from core.schemas.evaluation import MetricStatus, PerformanceMetrics

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    PSUTIL_AVAILABLE = False


class PerformanceEvaluator(IPerformanceEvaluator):
    """Computes monotonic total E2E latency, average, p50, p90, p99 latencies, QPS throughput, and resource usage."""

    def evaluate_performance(
        self,
        execution_times_ms: List[float],
        stage_times_ms: Optional[List[Dict[str, float]]] = None,
        total_time_ms: Optional[float] = None,
    ) -> PerformanceMetrics:
        if not execution_times_ms:
            return PerformanceMetrics(
                status=MetricStatus.INSUFFICIENT_DATA,
                resource_usage={"status": "UNAVAILABLE", "reason": "No execution timing measurements provided."},
            )

        sorted_times = sorted(execution_times_ms)
        n = len(sorted_times)

        total_latency = total_time_ms if total_time_ms is not None else sum(sorted_times)
        avg_latency = round(sum(sorted_times) / float(n), 2)

        p50 = round(self._percentile(sorted_times, 50), 2)
        p90 = round(self._percentile(sorted_times, 90), 2)
        p99 = round(self._percentile(sorted_times, 99), 2)

        total_sec = total_latency / 1000.0 if total_latency > 0 else 0.001
        qps = round(n / total_sec, 2)

        # Average stage latencies if provided
        avg_stages: Dict[str, float] = {}
        if stage_times_ms:
            stage_totals: Dict[str, float] = {}
            stage_counts: Dict[str, int] = {}
            for s_dict in stage_times_ms:
                for stage, st_time in s_dict.items():
                    stage_totals[stage] = stage_totals.get(stage, 0.0) + st_time
                    stage_counts[stage] = stage_counts.get(stage, 0) + 1
            for stage, tot in stage_totals.items():
                avg_stages[stage] = round(tot / float(stage_counts[stage]), 2)

        resource_info = self._get_resource_usage()

        return PerformanceMetrics(
            status=MetricStatus.EVALUATED,
            total_e2e_latency_ms=round(total_latency, 2),
            avg_e2e_latency_ms=avg_latency,
            p50_latency_ms=p50,
            p90_latency_ms=p90,
            p99_latency_ms=p99,
            stage_latencies_ms=avg_stages,
            queries_per_second=qps,
            successful_qps=qps,
            resource_usage=resource_info,
        )

    def _percentile(self, sorted_data: List[float], percentile: float) -> float:
        """Helper to calculate percentile value from sorted numeric list."""
        if not sorted_data:
            return 0.0
        k = (len(sorted_data) - 1) * (percentile / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_data[int(k)]
        d0 = sorted_data[int(f)] * (c - k)
        d1 = sorted_data[int(c)] * (k - f)
        return d0 + d1

    def _get_resource_usage(self) -> Dict[str, Any]:
        """Collects process memory and CPU usage or reports UNAVAILABLE."""
        if PSUTIL_AVAILABLE:
            try:
                proc = psutil.Process()
                mem = proc.memory_info()
                return {
                    "status": "AVAILABLE",
                    "rss_memory_mb": round(mem.rss / (1024.0 * 1024.0), 2),
                    "cpu_percent": proc.cpu_percent(interval=None),
                }
            except Exception:
                pass
        return {"status": "UNAVAILABLE", "reason": "psutil measurement unavailable in current environment."}


import math
