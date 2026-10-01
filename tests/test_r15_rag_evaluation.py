"""Stage R15 RAG Quality & Performance Evaluation Comprehensive Tests."""

import json
import pytest
from core.schemas.evaluation import (
    BaselineResult,
    EvaluationCase,
    EvaluationDataset,
    EvaluationMeasurement,
    EvaluationReport,
    EvaluationRun,
    PerformanceMetrics,
    QualityMetrics,
    QualityStatus,
    RegressionResult,
    ReliabilityMetrics,
    ReliabilityStatus,
)
from modules.knowledge_base.evaluation.baseline import BaselineComparator
from modules.knowledge_base.evaluation.dataset import EvaluationDatasetRepository
from modules.knowledge_base.evaluation.performance import PerformanceEvaluator
from modules.knowledge_base.evaluation.quality import QualityEvaluator
from modules.knowledge_base.evaluation.regression import RegressionEvaluator
from modules.knowledge_base.evaluation.reliability import ReliabilityEvaluator
from modules.knowledge_base.evaluation.report import EvaluationReportGenerator
from modules.knowledge_base.evaluation.runner import EvaluationRunner


@pytest.fixture
def sample_case():
    return EvaluationCase(
        case_id="case_001",
        query_text="What are GAP for land selection?",
        language="en",
        domain_category="crop_management",
        expected_relevant_chunk_ids=["chk_gap_01"],
        expected_relevant_doc_ids=["doc_gap_01"],
        difficulty="easy",
    )


@pytest.fixture
def sample_dataset(sample_case):
    return EvaluationDataset(
        dataset_id="ds_test_v1",
        name="Test Dataset",
        version="1.0.0",
        description="Dataset for unit testing",
        cases=[sample_case],
        created_at="2026-03-01T00:00:00Z",
    )


# 1. Evaluation contract validation
def test_01_evaluation_contract_validation(sample_case, sample_dataset):
    assert sample_case.case_id == "case_001"
    assert sample_dataset.dataset_id == "ds_test_v1"
    assert len(sample_dataset.cases) == 1


# 2. Dataset loading
def test_02_dataset_loading():
    repo = EvaluationDatasetRepository()
    ds = repo.get_dataset("ds_earthmind_agri_v1")
    assert ds is not None
    assert len(ds.cases) >= 10


# 3. Dataset versioning
def test_03_dataset_versioning(tmp_path):
    repo = EvaluationDatasetRepository(storage_dir=str(tmp_path))
    ds = EvaluationDataset(
        dataset_id="ds_custom_v2",
        name="Custom Dataset",
        version="2.0.0",
        created_at="2026-03-01T00:00:00Z",
        cases=[],
    )
    repo.save_dataset(ds)
    loaded = repo.load_from_file(str(tmp_path / "ds_custom_v2.json"))
    assert loaded.version == "2.0.0"


# 4. Evaluation run creation
def test_04_evaluation_run_creation():
    run = EvaluationRun(
        run_id="run_101",
        dataset_id="ds_test_v1",
        dataset_version="1.0.0",
        timestamp="2026-03-01T00:00:00Z",
        measurements=[],
    )
    assert run.run_id == "run_101"
    assert run.status == "COMPLETED"


# 5. Precision@K
def test_05_precision_at_k(sample_case):
    evaluator = QualityEvaluator(default_k_values=[1, 3, 5])
    meas = EvaluationMeasurement(
        case_id="case_001",
        request_id="req1",
        trace_id="trc1",
        status=ReliabilityStatus.SUCCESS,
        retrieved_chunk_ids=["chk_gap_01", "chk_irrelevant_1", "chk_irrelevant_2"],
        reranked_chunk_ids=["chk_gap_01", "chk_irrelevant_1", "chk_irrelevant_2"],
    )
    q_res = evaluator.evaluate_quality([sample_case], [meas])
    assert q_res.precision_at_k[1] == 1.0
    assert pytest.approx(q_res.precision_at_k[3], 0.01) == 0.3333


# 6. Recall@K
def test_06_recall_at_k():
    case = EvaluationCase(
        case_id="c_multi",
        query_text="query",
        expected_relevant_chunk_ids=["chk1", "chk2"],
    )
    meas = EvaluationMeasurement(
        case_id="c_multi",
        request_id="req1",
        trace_id="trc1",
        status=ReliabilityStatus.SUCCESS,
        retrieved_chunk_ids=["chk1", "chk3"],
        reranked_chunk_ids=["chk1", "chk3"],
    )
    evaluator = QualityEvaluator(default_k_values=[2])
    q_res = evaluator.evaluate_quality([case], [meas])
    assert q_res.recall_at_k[2] == 0.5


# 7. Hit Rate@K
def test_07_hit_rate_at_k(sample_case):
    meas = EvaluationMeasurement(
        case_id="case_001",
        request_id="req1",
        trace_id="trc1",
        status=ReliabilityStatus.SUCCESS,
        retrieved_chunk_ids=["chk_irrelevant", "chk_gap_01"],
        reranked_chunk_ids=["chk_irrelevant", "chk_gap_01"],
    )
    evaluator = QualityEvaluator(default_k_values=[1, 2])
    q_res = evaluator.evaluate_quality([sample_case], [meas])
    assert q_res.hit_rate_at_k[1] == 0.0
    assert q_res.hit_rate_at_k[2] == 1.0


# 8. MRR
def test_08_mrr(sample_case):
    meas = EvaluationMeasurement(
        case_id="case_001",
        request_id="req1",
        trace_id="trc1",
        status=ReliabilityStatus.SUCCESS,
        retrieved_chunk_ids=["chk_other", "chk_gap_01"],
        reranked_chunk_ids=["chk_other", "chk_gap_01"],
    )
    evaluator = QualityEvaluator()
    q_res = evaluator.evaluate_quality([sample_case], [meas])
    assert q_res.mrr == 0.5  # First relevant item at rank 2 -> 1/2 = 0.5


# 9. nDCG
def test_09_ndcg(sample_case):
    meas = EvaluationMeasurement(
        case_id="case_001",
        request_id="req1",
        trace_id="trc1",
        status=ReliabilityStatus.SUCCESS,
        retrieved_chunk_ids=["chk_gap_01"],
        reranked_chunk_ids=["chk_gap_01"],
    )
    evaluator = QualityEvaluator(default_k_values=[1])
    q_res = evaluator.evaluate_quality([sample_case], [meas])
    assert q_res.ndcg_at_k[1] == 1.0


# 10. Empty retrieval
def test_10_empty_retrieval(sample_case):
    meas = EvaluationMeasurement(
        case_id="case_001",
        request_id="req1",
        trace_id="trc1",
        status=ReliabilityStatus.VALID_EMPTY_RESULT,
        retrieved_chunk_ids=[],
        reranked_chunk_ids=[],
    )
    evaluator = QualityEvaluator()
    q_res = evaluator.evaluate_quality([sample_case], [meas])
    assert q_res.mrr == 0.0
    assert q_res.hit_rate_at_k[5] == 0.0


# 11. Missing ground truth
def test_11_missing_ground_truth():
    case_no_gt = EvaluationCase(case_id="c_no_gt", query_text="ambiguous query")
    meas = EvaluationMeasurement(
        case_id="c_no_gt",
        request_id="req1",
        trace_id="trc1",
        status=ReliabilityStatus.SUCCESS,
        retrieved_chunk_ids=["chk1"],
    )
    evaluator = QualityEvaluator()
    q_res = evaluator.evaluate_quality([case_no_gt], [meas])
    assert q_res.status == QualityStatus.NOT_EVALUABLE


# 12. NOT_EVALUABLE handling
def test_12_not_evaluable_handling():
    evaluator = QualityEvaluator()
    q_res = evaluator.evaluate_quality([], [])
    assert q_res.status == QualityStatus.NOT_EVALUABLE
    assert "No ground truth" in q_res.status_reason


# 13. Reranking comparison
def test_13_reranking_comparison(sample_case):
    meas = EvaluationMeasurement(
        case_id="case_001",
        request_id="req1",
        trace_id="trc1",
        status=ReliabilityStatus.SUCCESS,
        retrieved_chunk_ids=["chk_other", "chk_gap_01"],  # Rank 2 before rerank
        reranked_chunk_ids=["chk_gap_01", "chk_other"],  # Rank 1 after rerank
    )
    evaluator = QualityEvaluator()
    q_res = evaluator.evaluate_quality([sample_case], [meas])
    assert q_res.rerank_movement["improvements_count"] == 1
    assert q_res.rerank_movement["improvement_rate"] == 1.0


# 14. Evidence quality calculation
def test_14_evidence_quality_calculation(sample_case):
    meas = EvaluationMeasurement(
        case_id="case_001",
        request_id="req1",
        trace_id="trc1",
        status=ReliabilityStatus.SUCCESS,
        validation_status="VALID",
    )
    evaluator = QualityEvaluator()
    q_res = evaluator.evaluate_quality([sample_case], [meas])
    assert q_res.evidence_metrics["valid_evidence_rate"] == 1.0


# 15. Latency measurement
def test_15_latency_measurement():
    evaluator = PerformanceEvaluator()
    measurements = [
        EvaluationMeasurement(case_id="c1", request_id="r1", trace_id="t1", total_latency_ms=10.0, stage_latencies_ms={"R9": 2.0, "R7": 8.0}),
        EvaluationMeasurement(case_id="c2", request_id="r2", trace_id="t2", total_latency_ms=30.0, stage_latencies_ms={"R9": 5.0, "R7": 25.0}),
    ]
    perf = evaluator.evaluate_performance(measurements, total_time_seconds=0.1)
    assert perf.total_latency.mean_ms == 20.0
    assert perf.total_latency.min_ms == 10.0
    assert perf.total_latency.max_ms == 30.0


# 16. Throughput measurement
def test_16_throughput_measurement():
    evaluator = PerformanceEvaluator()
    measurements = [
        EvaluationMeasurement(case_id="c1", request_id="r1", trace_id="t1", status=ReliabilityStatus.SUCCESS, total_latency_ms=10.0),
        EvaluationMeasurement(case_id="c2", request_id="r2", trace_id="t2", status=ReliabilityStatus.SUCCESS, total_latency_ms=10.0),
    ]
    perf = evaluator.evaluate_performance(measurements, total_time_seconds=1.0)
    assert perf.throughput_qps == 2.0
    assert perf.cases_per_second == 2.0


# 17. Reliability classification
def test_17_reliability_classification():
    evaluator = ReliabilityEvaluator()
    measurements = [
        EvaluationMeasurement(case_id="c1", request_id="r1", trace_id="t1", status=ReliabilityStatus.SUCCESS),
        EvaluationMeasurement(case_id="c2", request_id="r2", trace_id="t2", status=ReliabilityStatus.VALID_EMPTY_RESULT),
    ]
    rel = evaluator.evaluate_reliability(measurements)
    assert rel.success_count == 1
    assert rel.valid_empty_count == 1
    assert rel.success_rate == 0.5


# 18. Failure classification
def test_18_failure_classification():
    evaluator = ReliabilityEvaluator()
    measurements = [
        EvaluationMeasurement(case_id="c1", request_id="r1", trace_id="t1", status=ReliabilityStatus.SYSTEM_FAILURE, error_code="QDRANT_TIMEOUT"),
        EvaluationMeasurement(case_id="c2", request_id="r2", trace_id="t2", status=ReliabilityStatus.TIMEOUT),
    ]
    rel = evaluator.evaluate_reliability(measurements)
    assert rel.system_failure_count == 1
    assert rel.timeout_count == 1
    assert rel.failure_breakdown["QDRANT_TIMEOUT"] == 1
    assert rel.failure_breakdown["TIMEOUT"] == 1


# 19. Baseline comparison
def test_19_baseline_comparison():
    comparator = BaselineComparator()
    base_1 = BaselineResult(
        baseline_name="DENSE_ONLY",
        dataset_id="ds1",
        quality_metrics=QualityMetrics(mrr=0.8, status=QualityStatus.EVALUATED),
        performance_metrics=PerformanceMetrics(),
        reliability_metrics=ReliabilityMetrics(success_rate=1.0),
        timestamp="2026-03-01T00:00:00Z",
    )
    res = comparator.compare_baselines([base_1])
    assert res["baselines_count"] == 1
    assert res["comparison_table"][0]["baseline_name"] == "DENSE_ONLY"


# 20. Regression comparison
def test_20_regression_comparison():
    reg_eval = RegressionEvaluator(default_threshold_pct=5.0)
    run_a = EvaluationRun(
        run_id="run_a",
        dataset_id="ds1",
        timestamp="2026-03-01T00:00:00Z",
        measurements=[],
        quality_metrics=QualityMetrics(mrr=0.90, status=QualityStatus.EVALUATED),
        performance_metrics=PerformanceMetrics(),
        reliability_metrics=ReliabilityMetrics(success_rate=1.0),
    )
    run_b = EvaluationRun(
        run_id="run_b",
        dataset_id="ds1",
        timestamp="2026-03-01T01:00:00Z",
        measurements=[],
        quality_metrics=QualityMetrics(mrr=0.70, status=QualityStatus.EVALUATED),  # Drop from 0.90 to 0.70
        performance_metrics=PerformanceMetrics(),
        reliability_metrics=ReliabilityMetrics(success_rate=1.0),
    )
    reg_list = reg_eval.compare_runs(run_a, run_b)
    mrr_reg = next(r for r in reg_list if r.metric_name == "mrr")
    assert mrr_reg.regression_detected is True


# 21. Reproducibility metadata
def test_21_reproducibility_metadata(sample_dataset):
    runner = EvaluationRunner()
    run = runner.run_evaluation(sample_dataset)
    assert run.knowledge_base_version == "R2_R3_v1.0"
    assert run.embedding_model_version is not None
    assert run.config_snapshot is not None
    assert run.environment_metadata["python_version"] is not None


# 22. Traceability
def test_22_traceability(sample_dataset):
    runner = EvaluationRunner()
    run = runner.run_evaluation(sample_dataset)
    assert len(run.measurements) == 1
    meas = run.measurements[0]
    assert meas.request_id.startswith("req_eval_")
    assert meas.trace_id.startswith("trc_eval_")


# 23. Multilingual grouping
def test_23_multilingual_grouping():
    repo = EvaluationDatasetRepository()
    ds = repo.get_dataset("ds_earthmind_agri_v1")
    runner = EvaluationRunner()
    run = runner.run_evaluation(ds)
    gen = EvaluationReportGenerator()
    rpt = gen.generate_report(run, dataset=ds)
    assert "en" in rpt.multilingual_breakdown
    assert "hi" in rpt.multilingual_breakdown


# 24. Agricultural-domain grouping
def test_24_agricultural_domain_grouping():
    repo = EvaluationDatasetRepository()
    ds = repo.get_dataset("ds_earthmind_agri_v1")
    runner = EvaluationRunner()
    run = runner.run_evaluation(ds)
    gen = EvaluationReportGenerator()
    rpt = gen.generate_report(run, dataset=ds)
    assert "crop_management" in rpt.agricultural_breakdown
    assert "crop_disease" in rpt.agricultural_breakdown


# 25. Partial-result handling
def test_25_partial_result_handling():
    evaluator = ReliabilityEvaluator()
    meas = EvaluationMeasurement(
        case_id="c_part",
        request_id="r1",
        trace_id="t1",
        status=ReliabilityStatus.PARTIAL_RESULT,
    )
    rel = evaluator.evaluate_reliability([meas])
    assert rel.partial_result_count == 1


# 26. Deterministic metrics
def test_26_deterministic_metrics(sample_case):
    evaluator = QualityEvaluator()
    meas = EvaluationMeasurement(
        case_id="case_001",
        request_id="r1",
        trace_id="t1",
        status=ReliabilityStatus.SUCCESS,
        retrieved_chunk_ids=["chk_gap_01"],
    )
    res1 = evaluator.evaluate_quality([sample_case], [meas])
    res2 = evaluator.evaluate_quality([sample_case], [meas])
    assert res1.mrr == res2.mrr
    assert res1.hit_rate_at_k == res2.hit_rate_at_k


# 27. Report generation
def test_27_report_generation(sample_dataset):
    runner = EvaluationRunner()
    run = runner.run_evaluation(sample_dataset)
    gen = EvaluationReportGenerator()
    rpt = gen.generate_report(run, dataset=sample_dataset)
    md = gen.render_markdown_summary(rpt)
    assert "EarthMind RAG Evaluation Report" in md
    assert rpt.report_id.startswith("rpt_")


# 28. Secret/privacy protection
def test_28_secret_privacy_protection():
    gen = EvaluationReportGenerator()
    raw_config = {"api_key": "secret_abc123", "qdrant_url": "localhost", "token": "bearer_xyz"}
    clean = gen._sanitize_dict(raw_config)
    assert clean["api_key"] == "[REDACTED]"
    assert clean["token"] == "[REDACTED]"
    assert clean["qdrant_url"] == "localhost"


# 29. Existing R14 integration
def test_29_existing_r14_integration():
    repo = EvaluationDatasetRepository()
    ds = repo.get_dataset("ds_earthmind_agri_v1")
    runner = EvaluationRunner()
    run = runner.run_evaluation(ds)
    assert run.status == "COMPLETED"
    assert len(run.measurements) == len(ds.cases)


# 30. Full repository regression - handled by pytest execution
