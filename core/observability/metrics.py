"""Thread-safe, lightweight, in-memory telemetry metrics collector for EarthMind RAG.

Provides structured instrumentation for:
- Request lifecycle (start, end, latency, status: SUCCESS, CONTROLLED_ABSTENTION, DEGRADED, FAILED)
- Retrieval stages (dense, sparse, hybrid fusion, reranking latencies, candidate counts, degraded status)
- Evidence and reasoning (context assembly latency, evidence counts, citation presence, abstention outcomes)
- Dependencies and recovery (Qdrant operations/failures, model failures, retries, degraded mode flags)

Enforces strict low-cardinality label rules (no raw queries, personal identifiers, source text, or document IDs)
and exception isolation (telemetry failures never crash pipeline execution).
"""

import math
import threading
import time
from typing import Any, Dict, List, Optional


class MetricsCollector:
    """Thread-safe, lightweight, in-memory telemetry metrics collector."""

    def __init__(self):
        self._lock = threading.Lock()
        self._reset_unlocked()

    def _reset_unlocked(self):
        """Reset internal data structures. Caller must hold self._lock."""
        self._counters: Dict[str, int] = {
            # Request lifecycle counters
            "requests_total": 0,
            "requests_success": 0,
            "requests_controlled_abstention": 0,
            "requests_degraded": 0,
            "requests_failed": 0,
            # Stage counters
            "dense_retrievals_total": 0,
            "dense_retrievals_failed": 0,
            "sparse_retrievals_total": 0,
            "sparse_retrievals_failed": 0,
            "hybrid_fusions_total": 0,
            "rerank_operations_total": 0,
            "rerank_operations_failed": 0,
            "web_searches_total": 0,
            "web_searches_failed": 0,
            "context_assemblies_total": 0,
            "reasoning_stages_total": 0,
            "reasoning_stages_failed": 0,
            # Evidence & Attribution counters
            "citation_present_count": 0,
            "no_evidence_outcomes": 0,
            # Dependency & Recovery counters
            "qdrant_operations_total": 0,
            "qdrant_operations_failed": 0,
            "model_inferences_total": 0,
            "model_inferences_failed": 0,
            "retry_attempts_total": 0,
            "recovery_outcomes_total": 0,
            # Degraded channel counter flags
            "dense_channel_degraded_count": 0,
            "sparse_channel_degraded_count": 0,
            "reranker_degraded_count": 0,
        }

        self._histograms: Dict[str, List[float]] = {
            "total_request_latency_ms": [],
            "dense_retrieval_latency_ms": [],
            "sparse_retrieval_latency_ms": [],
            "hybrid_fusion_latency_ms": [],
            "rerank_latency_ms": [],
            "context_assembly_latency_ms": [],
            "reasoning_latency_ms": [],
        }

        self._gauges: Dict[str, float] = {
            "last_dense_candidate_count": 0.0,
            "last_sparse_candidate_count": 0.0,
            "last_fused_candidate_count": 0.0,
            "last_reranked_candidate_count": 0.0,
            "last_evidence_item_count": 0.0,
            "last_context_item_count": 0.0,
        }

        self._degraded_indicators: Dict[str, bool] = {
            "dense_channel_degraded": False,
            "sparse_channel_degraded": False,
            "reranker_degraded": False,
        }

    def reset(self) -> None:
        """Reset all collected metrics."""
        with self._lock:
            self._reset_unlocked()

    def record_request_start(self) -> None:
        """Safely record request start count."""
        try:
            with self._lock:
                self._counters["requests_total"] += 1
        except Exception:
            pass

    def record_request_completion(
        self,
        latency_ms: float,
        status: str,
        citation_present: bool = False,
        has_evidence: bool = True,
    ) -> None:
        """Safely record request completion metrics and outcome status."""
        try:
            with self._lock:
                self._histograms["total_request_latency_ms"].append(max(0.0, latency_ms))
                status_upper = status.upper() if isinstance(status, str) else "UNKNOWN"

                if status_upper in ("SUCCESS", "COMPLETED", "VALID"):
                    self._counters["requests_success"] += 1
                elif status_upper in ("CONTROLLED_ABSTENTION", "ABSTAINED", "NO_EVIDENCE"):
                    self._counters["requests_controlled_abstention"] += 1
                elif status_upper in ("DEGRADED", "PARTIAL"):
                    self._counters["requests_degraded"] += 1
                else:
                    self._counters["requests_failed"] += 1

                if citation_present:
                    self._counters["citation_present_count"] += 1
                if not has_evidence:
                    self._counters["no_evidence_outcomes"] += 1
        except Exception:
            pass

    def record_retrieval_stage(
        self,
        stage_name: str,
        latency_ms: float,
        candidate_count: int = 0,
        success: bool = True,
        degraded: bool = False,
    ) -> None:
        """Safely record metrics for dense, sparse, hybrid, or rerank retrieval stages."""
        try:
            with self._lock:
                stage = stage_name.lower().strip()
                if stage == "dense":
                    self._counters["dense_retrievals_total"] += 1
                    if not success:
                        self._counters["dense_retrievals_failed"] += 1
                    self._histograms["dense_retrieval_latency_ms"].append(max(0.0, latency_ms))
                    self._gauges["last_dense_candidate_count"] = float(max(0, candidate_count))
                    if degraded:
                        self._degraded_indicators["dense_channel_degraded"] = True
                        self._counters["dense_channel_degraded_count"] += 1

                elif stage == "sparse":
                    self._counters["sparse_retrievals_total"] += 1
                    if not success:
                        self._counters["sparse_retrievals_failed"] += 1
                    self._histograms["sparse_retrieval_latency_ms"].append(max(0.0, latency_ms))
                    self._gauges["last_sparse_candidate_count"] = float(max(0, candidate_count))
                    if degraded:
                        self._degraded_indicators["sparse_channel_degraded"] = True
                        self._counters["sparse_channel_degraded_count"] += 1

                elif stage in ("hybrid", "fusion"):
                    self._counters["hybrid_fusions_total"] += 1
                    self._histograms["hybrid_fusion_latency_ms"].append(max(0.0, latency_ms))
                    self._gauges["last_fused_candidate_count"] = float(max(0, candidate_count))

                elif stage in ("rerank", "reranker"):
                    self._counters["rerank_operations_total"] += 1
                    if not success:
                        self._counters["rerank_operations_failed"] += 1
                    self._histograms["rerank_latency_ms"].append(max(0.0, latency_ms))
                    self._gauges["last_reranked_candidate_count"] = float(max(0, candidate_count))
                    if degraded:
                        self._degraded_indicators["reranker_degraded"] = True
                        self._counters["reranker_degraded_count"] += 1
        except Exception:
            pass

    def record_evidence_context(
        self,
        assembly_latency_ms: float,
        evidence_count: int,
        context_count: int,
    ) -> None:
        """Safely record evidence and context assembly metrics."""
        try:
            with self._lock:
                self._counters["context_assemblies_total"] += 1
                self._histograms["context_assembly_latency_ms"].append(max(0.0, assembly_latency_ms))
                self._gauges["last_evidence_item_count"] = float(max(0, evidence_count))
                self._gauges["last_context_item_count"] = float(max(0, context_count))
        except Exception:
            pass

    def record_reasoning_stage(self, latency_ms: float, success: bool = True) -> None:
        """Safely record reasoning stage execution latency and outcome."""
        try:
            with self._lock:
                self._counters["reasoning_stages_total"] += 1
                if not success:
                    self._counters["reasoning_stages_failed"] += 1
                self._histograms["reasoning_latency_ms"].append(max(0.0, latency_ms))
        except Exception:
            pass

    def record_dependency_event(
        self,
        dependency_name: str,
        operation_success: bool,
        is_retry: bool = False,
        recovery_success: bool = False,
    ) -> None:
        """Safely record dependency operations, failures, retries, and recovery outcomes."""
        try:
            with self._lock:
                dep = dependency_name.lower().strip()
                if "qdrant" in dep or "index" in dep:
                    self._counters["qdrant_operations_total"] += 1
                    if not operation_success:
                        self._counters["qdrant_operations_failed"] += 1
                elif "model" in dep or "embedding" in dep or "reasoning" in dep:
                    self._counters["model_inferences_total"] += 1
                    if not operation_success:
                        self._counters["model_inferences_failed"] += 1

                if is_retry:
                    self._counters["retry_attempts_total"] += 1
                if recovery_success:
                    self._counters["recovery_outcomes_total"] += 1
        except Exception:
            pass

    def set_degraded_status(self, channel: str, is_degraded: bool) -> None:
        """Explicitly set degraded mode indicator for a channel."""
        try:
            with self._lock:
                chan = channel.lower().strip()
                keys_to_check = [f"{chan}_channel_degraded", f"{chan}_degraded", chan]
                for key in keys_to_check:
                    if key in self._degraded_indicators:
                        self._degraded_indicators[key] = is_degraded
                        if is_degraded:
                            counter_key = f"{chan}_channel_degraded_count"
                            if counter_key in self._counters:
                                self._counters[counter_key] += 1
                            elif f"{chan}_degraded_count" in self._counters:
                                self._counters[f"{chan}_degraded_count"] += 1
                        break
        except Exception:
            pass

    def get_summary(self) -> Dict[str, Any]:
        """
        Get aggregated metric summary including percentiles, counts, and degraded indicators.
        Returns strict low-cardinality data dictionary.
        """
        try:
            with self._lock:
                hist_summary: Dict[str, Dict[str, float]] = {}
                for name, values in self._histograms.items():
                    if not values:
                        hist_summary[name] = {"p50_ms": 0.0, "p90_ms": 0.0, "p99_ms": 0.0, "avg_ms": 0.0, "count": 0}
                    else:
                        sorted_vals = sorted(values)
                        n = len(sorted_vals)
                        p50_idx = max(0, min(n - 1, math.floor(0.50 * n)))
                        p90_idx = max(0, min(n - 1, math.floor(0.90 * n)))
                        p99_idx = max(0, min(n - 1, math.floor(0.99 * n)))
                        hist_summary[name] = {
                            "p50_ms": round(sorted_vals[p50_idx], 2),
                            "p90_ms": round(sorted_vals[p90_idx], 2),
                            "p99_ms": round(sorted_vals[p99_idx], 2),
                            "avg_ms": round(sum(sorted_vals) / n, 2),
                            "count": n,
                        }

                return {
                    "counters": dict(self._counters),
                    "gauges": dict(self._gauges),
                    "degraded_indicators": dict(self._degraded_indicators),
                    "latency_histograms": hist_summary,
                }
        except Exception as e:
            return {
                "error": f"Failed to retrieve metric summary: {str(e)}",
                "counters": {},
                "gauges": {},
                "degraded_indicators": {},
                "latency_histograms": {},
            }


# Singleton instance for system-wide lightweight telemetry collection
metrics_collector = MetricsCollector()
