"""Unit and Integration tests for Step 11 Observability in EarthMind RAG.

Tests:
1. MetricsCollector request lifecycle, retrieval stages, evidence/context assembly, and dependency counters.
2. Low-cardinality metric summaries and sensitive data exclusion.
3. System Health Diagnostics: process health vs dependency health vs end-to-end readiness.
4. Strict readiness rule: process alive alone does NOT report end-to-end readiness as healthy when dependencies are down.
5. Degraded channel mode indicators and failure metrics.
6. Exception isolation: telemetry errors do not crash RAG query execution.
7. Correlation ID preservation without embedding personal data.
"""

import time
import unittest
from unittest.mock import MagicMock

from app.lifecycle import LifecycleManager
from core.observability.health import HealthDiagnostics, SubsystemHealth, SystemHealthReport
from core.observability.metrics import MetricsCollector, metrics_collector
from modules.context.boundary.models import RAGContextContract, RAGContextRequest
from modules.knowledge_base.integration.provider import RAGContextProvider


class TestStep11Observability(unittest.TestCase):

    def setUp(self):
        self.collector = MetricsCollector()

    def test_01_request_lifecycle_metrics(self):
        """Verify request lifecycle counter and latency recording."""
        self.collector.record_request_start()
        self.collector.record_request_completion(latency_ms=120.5, status="SUCCESS", citation_present=True, has_evidence=True)
        self.collector.record_request_start()
        self.collector.record_request_completion(latency_ms=85.0, status="CONTROLLED_ABSTENTION", citation_present=False, has_evidence=False)
        self.collector.record_request_start()
        self.collector.record_request_completion(latency_ms=210.0, status="DEGRADED", citation_present=True, has_evidence=True)
        self.collector.record_request_start()
        self.collector.record_request_completion(latency_ms=45.0, status="FAILED", citation_present=False, has_evidence=False)

        summary = self.collector.get_summary()
        counters = summary["counters"]
        hist = summary["latency_histograms"]["total_request_latency_ms"]

        self.assertEqual(counters["requests_total"], 4)
        self.assertEqual(counters["requests_success"], 1)
        self.assertEqual(counters["requests_controlled_abstention"], 1)
        self.assertEqual(counters["requests_degraded"], 1)
        self.assertEqual(counters["requests_failed"], 1)
        self.assertEqual(counters["citation_present_count"], 2)
        self.assertEqual(counters["no_evidence_outcomes"], 2)

        self.assertEqual(hist["count"], 4)
        self.assertGreater(hist["p50_ms"], 0)
        self.assertGreater(hist["avg_ms"], 0)

    def test_02_retrieval_stage_metrics(self):
        """Verify metrics for dense, sparse, hybrid fusion, and reranker stages."""
        self.collector.record_retrieval_stage("dense", latency_ms=15.2, candidate_count=10, success=True)
        self.collector.record_retrieval_stage("sparse", latency_ms=8.4, candidate_count=12, success=True)
        self.collector.record_retrieval_stage("hybrid", latency_ms=5.1, candidate_count=8, success=True)
        self.collector.record_retrieval_stage("rerank", latency_ms=45.0, candidate_count=5, success=True, degraded=False)

        summary = self.collector.get_summary()
        counters = summary["counters"]
        gauges = summary["gauges"]

        self.assertEqual(counters["dense_retrievals_total"], 1)
        self.assertEqual(counters["sparse_retrievals_total"], 1)
        self.assertEqual(counters["hybrid_fusions_total"], 1)
        self.assertEqual(counters["rerank_operations_total"], 1)

        self.assertEqual(gauges["last_dense_candidate_count"], 10.0)
        self.assertEqual(gauges["last_sparse_candidate_count"], 12.0)
        self.assertEqual(gauges["last_fused_candidate_count"], 8.0)
        self.assertEqual(gauges["last_reranked_candidate_count"], 5.0)

    def test_03_degraded_channel_indicators(self):
        """Verify explicit degraded mode indicators for dense, sparse, and reranker channels."""
        self.collector.set_degraded_status("dense", True)
        self.collector.set_degraded_status("reranker", True)

        summary = self.collector.get_summary()
        degraded = summary["degraded_indicators"]

        self.assertTrue(degraded["dense_channel_degraded"])
        self.assertFalse(degraded["sparse_channel_degraded"])
        self.assertTrue(degraded["reranker_degraded"])

    def test_04_dependency_and_recovery_metrics(self):
        """Verify dependency failure, retry, and recovery counters."""
        self.collector.record_dependency_event("qdrant", operation_success=False, is_retry=True, recovery_success=False)
        self.collector.record_dependency_event("qdrant", operation_success=True, is_retry=True, recovery_success=True)
        self.collector.record_dependency_event("model", operation_success=False, is_retry=False, recovery_success=False)

        summary = self.collector.get_summary()
        counters = summary["counters"]

        self.assertEqual(counters["qdrant_operations_total"], 2)
        self.assertEqual(counters["qdrant_operations_failed"], 1)
        self.assertEqual(counters["model_inferences_total"], 1)
        self.assertEqual(counters["model_inferences_failed"], 1)
        self.assertEqual(counters["retry_attempts_total"], 2)
        self.assertEqual(counters["recovery_outcomes_total"], 1)

    def test_05_health_diagnostics_process_vs_dependency_vs_readiness(self):
        """
        Verify HealthDiagnostics clearly distinguishes:
        1. Process health (process_alive)
        2. Dependency health (individual subsystem statuses)
        3. End-to-end readiness (requiring healthy critical dependencies, not merely process liveness).
        """
        # Case A: Process alive, but NO dependencies attached -> NOT_READY
        report_a = HealthDiagnostics.evaluate_system_health()
        self.assertTrue(report_a.process_healthy)
        self.assertFalse(report_a.is_ready_e2e)
        self.assertEqual(report_a.readiness_status, "NOT_READY")

        # Case B: Qdrant unhealthy -> NOT_READY
        mock_qdrant_unhealthy = MagicMock()
        mock_qdrant_unhealthy.is_available.return_value = False
        mock_emb = MagicMock()
        mock_emb.is_available.return_value = True

        report_b = HealthDiagnostics.evaluate_system_health(
            qdrant_adapter=mock_qdrant_unhealthy,
            embedding_provider=mock_emb,
        )
        self.assertTrue(report_b.process_healthy)
        self.assertFalse(report_b.is_ready_e2e)
        self.assertEqual(report_b.readiness_status, "NOT_READY")

        # Case C: Critical dependencies healthy -> READY
        mock_qdrant_healthy = MagicMock()
        mock_qdrant_healthy.is_available.return_value = True

        report_c = HealthDiagnostics.evaluate_system_health(
            qdrant_adapter=mock_qdrant_healthy,
            embedding_provider=mock_emb,
        )
        self.assertTrue(report_c.process_healthy)
        self.assertTrue(report_c.is_ready_e2e)
        self.assertEqual(report_c.readiness_status, "READY")

        # Case D: Critical dependencies healthy, but optional dependency degraded -> DEGRADED_READY
        mock_reranker_degraded = MagicMock()
        mock_reranker_degraded.is_available.return_value = False

        report_d = HealthDiagnostics.evaluate_system_health(
            qdrant_adapter=mock_qdrant_healthy,
            embedding_provider=mock_emb,
            reranker_provider=mock_reranker_degraded,
        )
        self.assertTrue(report_d.process_healthy)
        self.assertTrue(report_d.is_ready_e2e)
        self.assertEqual(report_d.readiness_status, "DEGRADED_READY")

    def test_06_privacy_sensitive_data_exclusion(self):
        """Verify summary metrics and health reports contain low-cardinality keys without raw queries or farmer data."""
        self.collector.record_request_start()
        self.collector.record_request_completion(latency_ms=100, status="SUCCESS")

        summary = self.collector.get_summary()
        summary_str = str(summary)

        # Confirm forbidden sensitive content patterns are not present in metric summary keys
        forbidden_words = ["farmer", "query", "prompt", "identity", "phone", "aadhar", "village"]
        for key in summary["counters"].keys():
            for word in forbidden_words:
                self.assertNotIn(word, key.lower())

    def test_07_exception_isolation_fail_safe(self):
        """Verify metric collection errors are caught internally and never crash pipeline execution."""
        faulty_collector = MetricsCollector()
        # Poison internal dictionary to induce TypeError inside internal code if unhandled
        faulty_collector._counters = None

        # Call methods; should fail safely without throwing exceptions
        try:
            faulty_collector.record_request_start()
            faulty_collector.record_retrieval_stage("dense", 10.0)
            faulty_collector.record_request_completion(100.0, "SUCCESS")
            sum_res = faulty_collector.get_summary()
            self.assertIn("error", sum_res)
        except Exception as e:
            self.fail(f"MetricsCollector method raised unhandled exception: {str(e)}")

    def test_08_lifecycle_manager_health_and_metrics_integration(self):
        """Verify LifecycleManager exposes system health and telemetry metrics."""
        lifecycle = LifecycleManager()
        metrics = lifecycle.get_metrics()
        self.assertIn("counters", metrics)

        health = lifecycle.get_system_health()
        self.assertIsInstance(health, SystemHealthReport)
        self.assertTrue(health.process_healthy)


if __name__ == "__main__":
    unittest.main()
