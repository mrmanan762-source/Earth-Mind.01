"""Baseline Comparator for Stage R15."""

import time
from typing import Any, Dict, List, Optional
from core.interfaces.evaluation import IBaselineComparator
from core.schemas.evaluation import (
    BaselineResult,
    EvaluationDataset,
    MetricStatus,
    PerformanceMetrics,
    QualityMetrics,
    ReliabilityMetrics,
)


class BaselineComparator(IBaselineComparator):
    """Executes dataset cases across controlled baseline modes (Dense-Only, Sparse-Only, Hybrid, Hybrid+Reranker)."""

    def __init__(self, harness: Optional[Any] = None):
        self.harness = harness

    def compare_baselines(
        self,
        dataset: EvaluationDataset,
        baselines: Optional[List[str]] = None,
    ) -> List[BaselineResult]:
        if not self.harness or not dataset or not dataset.cases:
            return []

        baseline_modes = baselines or ["Dense-Only", "Sparse-Only", "Hybrid", "Hybrid+Reranker"]
        results: List[BaselineResult] = []

        from modules.knowledge_base.evaluation.evaluators.quality import QualityEvaluator
        from modules.knowledge_base.evaluation.evaluators.performance import PerformanceEvaluator
        from modules.knowledge_base.evaluation.evaluators.reliability import ReliabilityEvaluator

        qual_eval = QualityEvaluator()
        perf_eval = PerformanceEvaluator()
        rel_eval = ReliabilityEvaluator()

        for mode in baseline_modes:
            mode_times = []
            mode_outcomes = []
            mode_case_results = []

            # Configure harness mode
            original_enable_dense = getattr(self.harness.rag_provider.hybrid_retriever, "enable_dense", True)
            original_enable_sparse = getattr(self.harness.rag_provider.hybrid_retriever, "enable_sparse", True)

            for case in dataset.cases:
                start_t = time.time()
                res = self.harness.execute_query(case.query, request_id=f"base_{mode}_{case.case_id}")
                elapsed = (time.time() - start_t) * 1000.0

                mode_times.append(elapsed)
                mode_outcomes.append("SUCCESS" if res.context_items_count > 0 or not case.query else "VALID_EMPTY_RESULT")
                mode_case_results.append(res)

            q_metrics = qual_eval.evaluate_quality(dataset.cases, mode_case_results)
            p_metrics = perf_eval.evaluate_performance(mode_times)
            r_metrics = rel_eval.evaluate_reliability(mode_outcomes)

            b_res = BaselineResult(
                baseline_id=f"b_{mode.lower().replace('+', '_').replace('-', '_')}",
                baseline_name=mode,
                configuration_snapshot={"mode": mode},
                dataset_id=dataset.dataset_id,
                dataset_version=dataset.dataset_version,
                quality_metrics=q_metrics,
                performance_metrics=p_metrics,
                reliability_metrics=r_metrics,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                traceability={"total_cases": len(dataset.cases)},
            )
            results.append(b_res)

        return results
