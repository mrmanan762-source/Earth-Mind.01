"""
Data Contracts for EarthMind Stage R15 RAG Quality & Performance Evaluation.

Defines Pydantic models for:
- EvaluationRunStatus & MetricStatus & EvaluationOutcome
- EvaluationCase & EvaluationDataset
- QualityMetrics (Precision@K, Recall@K, Hit Rate@K, MRR, nDCG@K)
- PerformanceMetrics (Latencies, Throughput, Resource Usage)
- ReliabilityMetrics (Success, Failure, Timeout, Empty, Partial Rates)
- BaselineResult & RegressionResult
- EvaluationReport
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvaluationRunStatus(str, Enum):
    """Overall execution status for an evaluation run."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class MetricStatus(str, Enum):
    """Evaluation state status for individual metrics or metric groups."""
    EVALUATED = "EVALUATED"
    NOT_EVALUABLE = "NOT_EVALUABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class EvaluationOutcome(str, Enum):
    """Execution outcome status for an individual evaluation case."""
    SUCCESS = "SUCCESS"
    VALID_EMPTY_RESULT = "VALID_EMPTY_RESULT"
    PARTIAL_RESULT = "PARTIAL_RESULT"
    TIMEOUT = "TIMEOUT"
    SYSTEM_FAILURE = "SYSTEM_FAILURE"
    UNAVAILABLE = "UNAVAILABLE"


class EvaluationCase(BaseModel):
    """Individual test case in an evaluation dataset."""
    case_id: str = Field(..., description="Unique test case identifier")
    query: str = Field(..., description="Evaluation query text string")
    language: str = Field("en", description="ISO language code (e.g., 'en', 'hi')")
    domain_category: str = Field("general", description="Domain category (crop, disease, soil, fertilizer, irrigation)")
    expected_document_ids: List[str] = Field(default_factory=list, description="Ground truth document IDs")
    expected_chunk_ids: List[str] = Field(default_factory=list, description="Ground truth chunk IDs")
    expected_evidence_ids: List[str] = Field(default_factory=list, description="Ground truth evidence IDs")
    expected_source_types: List[str] = Field(default_factory=list, description="Expected source type tags")
    relevance_judgments: Dict[str, float] = Field(default_factory=dict, description="Item ID to relevance score (0.0 to 1.0)")
    difficulty: str = Field("medium", description="Case difficulty (easy, medium, hard)")
    version: str = Field("1.0.0", description="Case schema/data version")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extensible case metadata")


class EvaluationDataset(BaseModel):
    """Collection of evaluation cases forming a benchmark dataset."""
    dataset_id: str = Field(..., description="Unique dataset identifier")
    dataset_name: str = Field(..., description="Human-readable dataset name")
    dataset_version: str = Field("1.0.0", description="Dataset semantic version")
    description: Optional[str] = Field(None, description="Dataset description and purpose")
    cases: List[EvaluationCase] = Field(default_factory=list, description="List of evaluation cases")
    created_at: Optional[str] = Field(None, description="Creation ISO timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Dataset metadata")


class QualityMetrics(BaseModel):
    """Retrieval, reranking, and evidence quality metrics."""
    status: MetricStatus = Field(MetricStatus.EVALUATED, description="Metric evaluation state")
    precision_at_k: Dict[int, float] = Field(default_factory=dict, description="Precision at cutoff K (e.g. @1, @3, @5, @10)")
    recall_at_k: Dict[int, float] = Field(default_factory=dict, description="Recall at cutoff K")
    hit_rate_at_k: Dict[int, float] = Field(default_factory=dict, description="Hit Rate at cutoff K")
    mrr: float = Field(0.0, ge=0.0, le=1.0, description="Mean Reciprocal Rank")
    ndcg_at_k: Dict[int, float] = Field(default_factory=dict, description="nDCG at cutoff K")
    total_cases_evaluated: int = Field(0, ge=0, description="Count of evaluated cases")
    not_evaluable_cases: int = Field(0, ge=0, description="Count of cases lacking ground truth")
    details: Dict[str, Any] = Field(default_factory=dict, description="Metric computation details and notes")


class PerformanceMetrics(BaseModel):
    """Latency, throughput, and resource usage metrics."""
    status: MetricStatus = Field(MetricStatus.EVALUATED, description="Metric evaluation state")
    total_e2e_latency_ms: float = Field(0.0, ge=0.0, description="Total latency across all cases")
    avg_e2e_latency_ms: float = Field(0.0, ge=0.0, description="Average E2E latency per case in ms")
    p50_latency_ms: float = Field(0.0, ge=0.0, description="50th percentile latency in ms")
    p90_latency_ms: float = Field(0.0, ge=0.0, description="90th percentile latency in ms")
    p99_latency_ms: float = Field(0.0, ge=0.0, description="99th percentile latency in ms")
    stage_latencies_ms: Dict[str, float] = Field(default_factory=dict, description="Average latency per stage (R9, R7, R8, R11, R12, R13)")
    queries_per_second: float = Field(0.0, ge=0.0, description="Overall QPS throughput")
    successful_qps: float = Field(0.0, ge=0.0, description="Successful QPS throughput")
    resource_usage: Dict[str, Any] = Field(default_factory=dict, description="Measured CPU, memory, GPU resource indicators or UNAVAILABLE")


class ReliabilityMetrics(BaseModel):
    """Execution outcome rates and reliability statistics."""
    status: MetricStatus = Field(MetricStatus.EVALUATED, description="Metric evaluation state")
    total_cases: int = Field(0, ge=0, description="Total execution attempts")
    success_count: int = Field(0, ge=0, description="Successful cases count")
    success_rate: float = Field(0.0, ge=0.0, le=1.0, description="Success rate fraction")
    failure_count: int = Field(0, ge=0, description="Failed cases count")
    failure_rate: float = Field(0.0, ge=0.0, le=1.0, description="Failure rate fraction")
    timeout_count: int = Field(0, ge=0, description="Timeout cases count")
    timeout_rate: float = Field(0.0, ge=0.0, le=1.0, description="Timeout rate fraction")
    empty_result_count: int = Field(0, ge=0, description="Valid empty results count")
    empty_result_rate: float = Field(0.0, ge=0.0, le=1.0, description="Empty result rate fraction")
    partial_result_count: int = Field(0, ge=0, description="Partial results count")
    partial_result_rate: float = Field(0.0, ge=0.0, le=1.0, description="Partial result rate fraction")
    outcome_counts: Dict[str, int] = Field(default_factory=dict, description="Count per EvaluationOutcome state")


class BaselineResult(BaseModel):
    """Baseline measurement container for controlled pipeline mode benchmarking."""
    baseline_id: str = Field(..., description="Baseline identifier")
    baseline_name: str = Field(..., description="Baseline configuration name (e.g. 'Dense-Only', 'Hybrid+Reranker')")
    configuration_snapshot: Dict[str, Any] = Field(default_factory=dict, description="Configuration settings snapshot")
    dataset_id: str = Field(..., description="Dataset identifier used for baseline")
    dataset_version: str = Field("1.0.0", description="Dataset version")
    quality_metrics: QualityMetrics = Field(..., description="Baseline quality metrics")
    performance_metrics: PerformanceMetrics = Field(..., description="Baseline performance metrics")
    reliability_metrics: ReliabilityMetrics = Field(..., description="Baseline reliability metrics")
    timestamp: str = Field(..., description="Execution timestamp")
    traceability: Dict[str, Any] = Field(default_factory=dict, description="Baseline execution trace details")


class RegressionResult(BaseModel):
    """Run-to-run regression comparison report."""
    comparison_id: str = Field(..., description="Unique comparison ID")
    base_run_id: str = Field(..., description="Baseline run ID")
    target_run_id: str = Field(..., description="Target run ID evaluated against baseline")
    metrics_diff: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Metric diff details")
    regressions_detected: List[str] = Field(default_factory=list, description="List of degraded metrics")
    improvements_detected: List[str] = Field(default_factory=list, description="List of improved metrics")
    overall_status: str = Field("NO_REGRESSION", description="Overall comparison status (NO_REGRESSION, REGRESSION_DETECTED, IMPROVEMENT_DETECTED)")


class EvaluationReport(BaseModel):
    """Master evaluation report output payload from R15 Evaluation Runner."""
    evaluation_run_id: str = Field(..., description="Unique evaluation run identifier")
    timestamp: str = Field(..., description="Execution timestamp ISO string")
    status: EvaluationRunStatus = Field(EvaluationRunStatus.COMPLETED, description="Evaluation run status")
    dataset_info: Dict[str, Any] = Field(default_factory=dict, description="Dataset metadata and version info")
    system_versions: Dict[str, Any] = Field(default_factory=dict, description="System components versions snapshot")
    environment_info: Dict[str, Any] = Field(default_factory=dict, description="Host/runtime environment info without secrets")
    quality_metrics: QualityMetrics = Field(..., description="Aggregated quality metrics")
    rerank_quality_metrics: Optional[QualityMetrics] = Field(None, description="Pre vs post rerank metrics")
    performance_metrics: PerformanceMetrics = Field(..., description="Aggregated performance metrics")
    reliability_metrics: ReliabilityMetrics = Field(..., description="Aggregated reliability metrics")
    multilingual_breakdown: Dict[str, QualityMetrics] = Field(default_factory=dict, description="Metrics grouped by ISO language code")
    agricultural_domain_breakdown: Dict[str, QualityMetrics] = Field(default_factory=dict, description="Metrics grouped by agri domain category")
    baseline_comparison: Optional[List[BaselineResult]] = Field(None, description="Comparative baseline benchmarking results")
    regression_comparison: Optional[RegressionResult] = Field(None, description="Regression evaluation against previous run")
    failure_summary: List[Dict[str, Any]] = Field(default_factory=list, description="Summary of failed or edge cases")
    limitations: List[str] = Field(default_factory=list, description="Explicit evaluation limitations and boundaries")
    not_evaluable_reasons: Dict[str, str] = Field(default_factory=dict, description="Reasons for NOT_EVALUABLE metric states")
