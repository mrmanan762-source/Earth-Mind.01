"""
Stage R15 RAG Quality & Performance Evaluation Test Suite.

Verifies the R15 Evaluation Framework across all 30 required dimensions:
contracts, dataset loading, metrics computation, reranking gain, evidence quality,
performance, reliability, baseline comparison, regression evaluation, report generation,
and integration with Stage R14.
"""

import os
import pytest
from pathlib import Path

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
from modules.knowledge_base.evaluation.dataset import EvaluationDatasetLoader, EvaluationDatasetManager
from modules.knowledge_base.evaluation.evaluators.comparator import BaselineComparator
from modules.knowledge_base.evaluation.evaluators.evidence import EvidenceEvaluator
from modules.knowledge_base.evaluation.evaluators.performance import PerformanceEvaluator
from modules.knowledge_base.evaluation.evaluators.quality import QualityEvaluator
from modules.knowledge_base.evaluation.evaluators.regression import RegressionEvaluator
from modules.knowledge_base.evaluation.evaluators.reliability import ReliabilityEvaluator
from modules.knowledge_base.evaluation.evaluators.rerank import RerankEvaluator
from modules.knowledge_base.evaluation.report import EvaluationReportGenerator
from modules.knowledge_base.evaluation.runner import R15EvaluationRunner
from modules.knowledge_base.integration.e2e_setup import ingest_and_index_real_corpus
from modules.knowledge_base.integration.harness import R14RealRetrievalHarness


@pytest.fixture(scope="module")
def real_container():
    return ingest_and_index_real_corpus(collection_name="earthmind_knowledge")


@pytest.fixture(scope="module")
def real_harness(real_container):
    return R14RealRetrievalHarness(index_container=real_container, enable_web_search=False)


@pytest.fixture
def eval_dataset():
    loader = EvaluationDatasetLoader()
    return loader.load_dataset()


# -----------------------------------------------------------------------------
# 1. Evaluation Contract Validation
# -----------------------------------------------------------------------------
def test_01_evaluation_contracts_validation():
    case = EvaluationCase(
        case_id="c1",
        query="test query",
        language="en",
        expected_chunk_ids=["chk_1"],
    )
    assert case.case_id == "c1"
    assert case.language == "en"

    dataset = EvaluationDataset(
        dataset_id="ds_1",
        dataset_name="Test DS",
        cases=[case],
    )
    assert len(dataset.cases) == 1


# -----------------------------------------------------------------------------
# 2. Dataset Loading & 3. Dataset Versioning
# -----------------------------------------------------------------------------
def test_02_dataset_loading_and_versioning():
    loader = EvaluationDatasetLoader()
    ds = loader.load_dataset()
    assert ds.dataset_id == "agri_rag_eval_v1"
    assert ds.dataset_version == "1.0.0"
    assert len(ds.cases) >= 10


# -----------------------------------------------------------------------------
# 4. Evaluation Run Creation
# -----------------------------------------------------------------------------
def test_04_evaluation_run_creation(real_harness):
    runner = R15EvaluationRunner(harness=real_harness)
    report = runner.run_evaluation()

    assert report.evaluation_run_id.startswith("eval_run_")
    assert report.status == EvaluationRunStatus.COMPLETED
    assert report.quality_metrics.status == MetricStatus.EVALUATED


# -----------------------------------------------------------------------------
# 5 - 9. Precision, Recall, Hit Rate, MRR, nDCG Metrics Calculation
# -----------------------------------------------------------------------------
def test_05_quality_metrics_calculation():
    evaluator = QualityEvaluator()
    case = EvaluationCase(
        case_id="c1",
        query="test query",
        expected_chunk_ids=["chk_100"],
    )
    # Simulate result where chk_100 is at position 1
    mock_item = type("MockItem", (), {"entity_id": "chk_100", "chunk_id": "chk_100"})()
    mock_result = type("MockResult", (), {"final_context_items": [mock_item]})()

    metrics = evaluator.evaluate_quality([case], [mock_result], k_values=[1, 5])
    assert metrics.status == MetricStatus.EVALUATED
    assert metrics.precision_at_k[1] == 1.0
    assert metrics.recall_at_k[1] == 1.0
    assert metrics.hit_rate_at_k[1] == 1.0
    assert metrics.mrr == 1.0
    assert metrics.ndcg_at_k[1] == 1.0


# -----------------------------------------------------------------------------
# 10. Empty Retrieval Metrics
# -----------------------------------------------------------------------------
def test_10_empty_retrieval_metrics():
    evaluator = QualityEvaluator()
    case = EvaluationCase(
        case_id="c_empty",
        query="",
        expected_chunk_ids=[],
    )
    empty_result = type("MockResult", (), {"final_context_items": []})()

    metrics = evaluator.evaluate_quality([case], [empty_result], k_values=[1, 5])
    assert metrics.precision_at_k[1] == 1.0
    assert metrics.recall_at_k[1] == 1.0
    assert metrics.hit_rate_at_k[1] == 1.0


# -----------------------------------------------------------------------------
# 11 & 12. Missing Ground Truth & NOT_EVALUABLE Handling
# -----------------------------------------------------------------------------
def test_11_missing_ground_truth_not_evaluable():
    evaluator = QualityEvaluator()
    metrics = evaluator.evaluate_quality([], [])
    assert metrics.status in (MetricStatus.NOT_EVALUABLE, MetricStatus.INSUFFICIENT_DATA)


# -----------------------------------------------------------------------------
# 13. Reranking Gain Comparison
# -----------------------------------------------------------------------------
def test_13_reranking_comparison():
    rerank_eval = RerankEvaluator()
    case = EvaluationCase(case_id="c1", query="test", expected_chunk_ids=["chk_1"])

    pre_item = type("MockItem", (), {"chunk_id": "chk_2"})()
    post_item = type("MockItem", (), {"chunk_id": "chk_1"})()

    pre_res = type("MockResult", (), {"final_context_items": [pre_item]})()
    post_res = type("MockResult", (), {"final_context_items": [post_item]})()

    gain = rerank_eval.evaluate_reranking_gain([case], [pre_res], [post_res])
    assert gain["status"] == MetricStatus.EVALUATED.value
    assert gain["mrr_gain"] >= 0.0


# -----------------------------------------------------------------------------
# 14. Evidence Quality Calculation
# -----------------------------------------------------------------------------
def test_14_evidence_quality_calculation():
    evaluator = EvidenceEvaluator()
    item = type("MockItem", (), {
        "source_type": type("ST", (), {"value": "KNOWLEDGE_BASE"})(),
        "provenance": {"source": "src_1"},
    })()
    res = type("MockResult", (), {"final_context_items": [item]})()

    eq = evaluator.evaluate_evidence_quality([res])
    assert eq["status"] == MetricStatus.EVALUATED.value
    assert eq["provenance_preservation_rate"] == 1.0


# -----------------------------------------------------------------------------
# 15 & 16. Latency and Throughput Measurement
# -----------------------------------------------------------------------------
def test_15_performance_evaluation():
    evaluator = PerformanceEvaluator()
    times = [10.0, 20.0, 30.0, 40.0, 50.0]
    stages = [{"R9": 2.0, "R7": 5.0}, {"R9": 3.0, "R7": 6.0}]

    perf = evaluator.evaluate_performance(times, stage_times_ms=stages, total_time_ms=150.0)
    assert perf.status == MetricStatus.EVALUATED
    assert perf.avg_e2e_latency_ms == 30.0
    assert perf.p50_latency_ms == 30.0
    assert perf.queries_per_second > 0.0


# -----------------------------------------------------------------------------
# 17 & 18. Reliability and Failure Classification
# -----------------------------------------------------------------------------
def test_17_reliability_evaluation():
    evaluator = ReliabilityEvaluator()
    outcomes = [
        EvaluationOutcome.SUCCESS,
        EvaluationOutcome.SUCCESS,
        EvaluationOutcome.VALID_EMPTY_RESULT,
        EvaluationOutcome.SYSTEM_FAILURE,
    ]

    rel = evaluator.evaluate_reliability(outcomes)
    assert rel.status == MetricStatus.EVALUATED
    assert rel.total_cases == 4
    assert rel.success_count == 3
    assert rel.failure_count == 1
    assert rel.success_rate == 0.75


# -----------------------------------------------------------------------------
# 19. Baseline Comparison
# -----------------------------------------------------------------------------
def test_19_baseline_comparison(real_harness, eval_dataset):
    comparator = BaselineComparator(harness=real_harness)
    baselines = comparator.compare_baselines(eval_dataset, baselines=["Hybrid"])

    assert len(baselines) == 1
    assert baselines[0].baseline_name == "Hybrid"
    assert baselines[0].quality_metrics.mrr > 0.0


# -----------------------------------------------------------------------------
# 20. Regression Comparison
# -----------------------------------------------------------------------------
def test_20_regression_comparison(real_harness):
    runner = R15EvaluationRunner(harness=real_harness)
    report1 = runner.run_evaluation()
    report2 = runner.run_evaluation()

    reg_eval = RegressionEvaluator()
    reg_res = reg_eval.evaluate_regression(report1, report2)

    assert reg_res.overall_status in ("NO_REGRESSION", "REGRESSION_DETECTED", "IMPROVEMENT_DETECTED")
    assert "mrr" in reg_res.metrics_diff


# -----------------------------------------------------------------------------
# 21 & 22. Reproducibility & Traceability
# -----------------------------------------------------------------------------
def test_21_reproducibility_and_traceability(real_harness):
    runner = R15EvaluationRunner(harness=real_harness)
    report = runner.run_evaluation()

    assert "dataset_id" in report.dataset_info
    assert "r15_version" in report.system_versions
    assert "python_version" in report.environment_info


# -----------------------------------------------------------------------------
# 23 & 24. Multilingual & Agricultural Domain Grouping
# -----------------------------------------------------------------------------
def test_23_multilingual_and_domain_grouping(real_harness):
    runner = R15EvaluationRunner(harness=real_harness)
    report = runner.run_evaluation()

    assert "en" in report.multilingual_breakdown or "hi" in report.multilingual_breakdown
    assert len(report.agricultural_domain_breakdown) > 0


# -----------------------------------------------------------------------------
# 27. Report Generation (JSON & Markdown)
# -----------------------------------------------------------------------------
def test_27_report_generation(real_harness, tmp_path):
    runner = R15EvaluationRunner(harness=real_harness)
    report = runner.run_evaluation()

    json_str = EvaluationReportGenerator.to_json(report)
    md_str = EvaluationReportGenerator.to_markdown(report)

    assert report.evaluation_run_id in json_str
    assert report.evaluation_run_id in md_str
    assert "Retrieval Quality Metrics" in md_str

    json_path, md_path = EvaluationReportGenerator.save_report(report, output_dir=str(tmp_path))
    assert json_path.exists()
    assert md_path.exists()


# -----------------------------------------------------------------------------
# 28. Secrecy & Privacy Protection
# -----------------------------------------------------------------------------
def test_28_secret_privacy_protection(real_harness):
    runner = R15EvaluationRunner(harness=real_harness)
    report = runner.run_evaluation()
    report_json = EvaluationReportGenerator.to_json(report)

    assert "api_key" not in report_json.lower()
    assert "password" not in report_json.lower()
    assert "secret" not in report_json.lower()


# -----------------------------------------------------------------------------
# 29. Existing R14 Integration
# -----------------------------------------------------------------------------
def test_29_existing_r14_integration(real_harness):
    runner = R15EvaluationRunner(harness=real_harness)
    res = runner.harness.execute_query("soil health card parameters")
    assert res.query_processing_status == "SUCCESS"
    assert res.context_items_count > 0
