"""Master Evaluation Runner for Stage R15 RAG Quality & Performance Framework."""

import os
import platform
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from core.interfaces.evaluation import IEvaluationRunner
from core.schemas.evaluation import (
    BaselineResult,
    EvaluationCase,
    EvaluationDataset,
    EvaluationOutcome,
    EvaluationReport,
    EvaluationRunStatus,
    MetricStatus,
    PerformanceMetrics,
    QualityMetrics,
    RegressionResult,
    ReliabilityMetrics,
)
from modules.knowledge_base.evaluation.dataset import EvaluationDatasetLoader
from modules.knowledge_base.evaluation.evaluators.comparator import BaselineComparator
from modules.knowledge_base.evaluation.evaluators.evidence import EvidenceEvaluator
from modules.knowledge_base.evaluation.evaluators.performance import PerformanceEvaluator
from modules.knowledge_base.evaluation.evaluators.quality import QualityEvaluator
from modules.knowledge_base.evaluation.evaluators.regression import RegressionEvaluator
from modules.knowledge_base.evaluation.evaluators.reliability import ReliabilityEvaluator
from modules.knowledge_base.integration.harness import R14RealRetrievalHarness


class R15EvaluationRunner(IEvaluationRunner):
    """
    Master coordinator executing evaluation datasets through R14 E2E harness,
    calculating quality, performance, and reliability metrics, and generating EvaluationReport.
    """

    def __init__(
        self,
        dataset_loader: Optional[EvaluationDatasetLoader] = None,
        harness: Optional[R14RealRetrievalHarness] = None,
        quality_evaluator: Optional[QualityEvaluator] = None,
        performance_evaluator: Optional[PerformanceEvaluator] = None,
        reliability_evaluator: Optional[ReliabilityEvaluator] = None,
        evidence_evaluator: Optional[EvidenceEvaluator] = None,
        baseline_comparator: Optional[BaselineComparator] = None,
        regression_evaluator: Optional[RegressionEvaluator] = None,
    ):
        self.dataset_loader = dataset_loader or EvaluationDatasetLoader()
        self.harness = harness or R14RealRetrievalHarness(enable_web_search=False)
        self.quality_evaluator = quality_evaluator or QualityEvaluator()
        self.performance_evaluator = performance_evaluator or PerformanceEvaluator()
        self.reliability_evaluator = reliability_evaluator or ReliabilityEvaluator()
        self.evidence_evaluator = evidence_evaluator or EvidenceEvaluator()
        self.baseline_comparator = baseline_comparator or BaselineComparator(harness=self.harness)
        self.regression_evaluator = regression_evaluator or RegressionEvaluator()

    def run_evaluation(
        self,
        dataset_path_or_id: Optional[str] = None,
        k_values: Optional[List[int]] = None,
        compare_baselines: bool = False,
        base_report: Optional[EvaluationReport] = None,
    ) -> EvaluationReport:
        """
        Executes a complete evaluation run over the specified benchmark dataset.
        """
        run_id = f"eval_run_{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        dataset = self.dataset_loader.load_dataset(dataset_path_or_id)

        case_times_ms: List[float] = []
        case_outcomes: List[EvaluationOutcome] = []
        case_results: List[Any] = []
        failures_summary: List[Dict[str, Any]] = []

        for case in dataset.cases:
            t0 = time.time()
            try:
                res = self.harness.execute_query(
                    query_text=case.query,
                    request_id=f"{run_id}_{case.case_id}",
                    metadata={"case_id": case.case_id, "domain": case.domain_category},
                )
                elapsed_ms = round((time.time() - t0) * 1000.0, 2)
                case_times_ms.append(elapsed_ms)
                case_results.append(res)

                if res.context_items_count > 0:
                    case_outcomes.append(EvaluationOutcome.SUCCESS)
                elif not case.query or case.expected_chunk_ids == []:
                    case_outcomes.append(EvaluationOutcome.VALID_EMPTY_RESULT)
                else:
                    case_outcomes.append(EvaluationOutcome.VALID_EMPTY_RESULT)

            except Exception as e:
                elapsed_ms = round((time.time() - t0) * 1000.0, 2)
                case_times_ms.append(elapsed_ms)
                case_results.append(None)
                case_outcomes.append(EvaluationOutcome.SYSTEM_FAILURE)
                failures_summary.append({
                    "case_id": case.case_id,
                    "query": case.query,
                    "error": str(e),
                })

        total_elapsed_ms = round((time.time() - start_time) * 1000.0, 2)

        # 1. Compute Aggregated Metrics
        q_metrics = self.quality_evaluator.evaluate_quality(dataset.cases, case_results, k_values=k_values)
        p_metrics = self.performance_evaluator.evaluate_performance(case_times_ms, total_time_ms=total_elapsed_ms)
        r_metrics = self.reliability_evaluator.evaluate_reliability(case_outcomes)

        # 2. Compute Multilingual Breakdown
        multilingual_breakdown: Dict[str, QualityMetrics] = {}
        by_lang: Dict[str, tuple[List[EvaluationCase], List[Any]]] = {}
        for c, r in zip(dataset.cases, case_results):
            lang = c.language.lower()
            if lang not in by_lang:
                by_lang[lang] = ([], [])
            by_lang[lang][0].append(c)
            by_lang[lang][1].append(r)

        for lang, (lang_cases, lang_results) in by_lang.items():
            multilingual_breakdown[lang] = self.quality_evaluator.evaluate_quality(lang_cases, lang_results, k_values=k_values)

        # 3. Compute Agricultural Domain Breakdown
        domain_breakdown: Dict[str, QualityMetrics] = {}
        by_domain: Dict[str, tuple[List[EvaluationCase], List[Any]]] = {}
        for c, r in zip(dataset.cases, case_results):
            dom = c.domain_category.lower()
            if dom not in by_domain:
                by_domain[dom] = ([], [])
            by_domain[dom][0].append(c)
            by_domain[dom][1].append(r)

        for dom, (dom_cases, dom_results) in by_domain.items():
            domain_breakdown[dom] = self.quality_evaluator.evaluate_quality(dom_cases, dom_results, k_values=k_values)

        # 4. Controlled Baseline Comparison if requested
        baseline_results: Optional[List[BaselineResult]] = None
        if compare_baselines:
            baseline_results = self.baseline_comparator.compare_baselines(dataset)

        # 5. Regression Comparison if base report provided
        regression_result: Optional[RegressionResult] = None

        report = EvaluationReport(
            evaluation_run_id=run_id,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            status=EvaluationRunStatus.COMPLETED if not failures_summary else EvaluationRunStatus.PARTIAL,
            dataset_info={
                "dataset_id": dataset.dataset_id,
                "dataset_name": dataset.dataset_name,
                "dataset_version": dataset.dataset_version,
                "total_cases": len(dataset.cases),
            },
            system_versions={
                "r15_version": "1.0.0",
                "rag_pipeline": "Stage R14 Real E2E",
                "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                "sparse_model": "earthmind-bm25-agri-v1",
                "vector_db": "Qdrant",
            },
            environment_info={
                "python_version": sys.version.split()[0],
                "platform": platform.platform(),
            },
            quality_metrics=q_metrics,
            performance_metrics=p_metrics,
            reliability_metrics=r_metrics,
            multilingual_breakdown=multilingual_breakdown,
            agricultural_domain_breakdown=domain_breakdown,
            baseline_comparison=baseline_results,
            regression_comparison=regression_result,
            failure_summary=failures_summary,
            limitations=[
                "Evaluation dataset is bounded to the 8 R3 agricultural documents in data/knowledge/raw/.",
                "R15 sits strictly outside production without performing agricultural reasoning or B3 context modification.",
            ],
            not_evaluable_reasons={
                "missing_labels": "Cases without ground truth document/chunk IDs return NOT_EVALUABLE quality metrics."
            },
        )

        if base_report:
            report.regression_comparison = self.regression_evaluator.evaluate_regression(base_report, report)

        return report
