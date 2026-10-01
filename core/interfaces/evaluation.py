"""
Protocol Interfaces for EarthMind Stage R15 RAG Quality & Performance Evaluation.

Defines runtime protocols for:
- IEvaluationDatasetLoader
- IQualityEvaluator
- IPerformanceEvaluator
- IReliabilityEvaluator
- IBaselineComparator
- IRegressionEvaluator
- IEvaluationRunner
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from core.schemas.evaluation import (
    BaselineResult,
    EvaluationCase,
    EvaluationDataset,
    EvaluationReport,
    PerformanceMetrics,
    QualityMetrics,
    RegressionResult,
    ReliabilityMetrics,
)


@runtime_checkable
class IEvaluationDatasetLoader(Protocol):
    """Interface for loading evaluation datasets from file or registry."""

    def load_dataset(self, dataset_path_or_id: str) -> EvaluationDataset:
        """Load an EvaluationDataset given a file path or dataset ID."""
        ...


@runtime_checkable
class IQualityEvaluator(Protocol):
    """Interface for evaluating retrieval, reranking, and evidence quality metrics."""

    def evaluate_quality(
        self,
        cases: List[EvaluationCase],
        results: List[Any],
        k_values: Optional[List[int]] = None,
    ) -> QualityMetrics:
        """Compute Precision@K, Recall@K, Hit Rate@K, MRR, nDCG@K for cases and results."""
        ...


@runtime_checkable
class IPerformanceEvaluator(Protocol):
    """Interface for evaluating latency, throughput, and resource usage."""

    def evaluate_performance(
        self,
        execution_times_ms: List[float],
        stage_times_ms: List[Dict[str, float]],
        total_time_ms: float,
    ) -> PerformanceMetrics:
        """Compute average, p50, p90, p99 latencies, QPS throughput, and resource usage."""
        ...


@runtime_checkable
class IReliabilityEvaluator(Protocol):
    """Interface for evaluating reliability rates and failure classifications."""

    def evaluate_reliability(
        self,
        outcomes: List[Any],
    ) -> ReliabilityMetrics:
        """Compute success, failure, timeout, empty, and partial result rates."""
        ...


@runtime_checkable
class IBaselineComparator(Protocol):
    """Interface for running baseline comparisons across retrieval modes."""

    def compare_baselines(
        self,
        dataset: EvaluationDataset,
        baselines: Optional[List[str]] = None,
    ) -> List[BaselineResult]:
        """Run evaluation over controlled baselines and return benchmark results."""
        ...


@runtime_checkable
class IRegressionEvaluator(Protocol):
    """Interface for evaluating regressions between two evaluation runs."""

    def evaluate_regression(
        self,
        base_report: EvaluationReport,
        target_report: EvaluationReport,
    ) -> RegressionResult:
        """Compare two reports and produce a RegressionResult report."""
        ...


@runtime_checkable
class IEvaluationRunner(Protocol):
    """Master orchestrator interface for executing R15 evaluation runs."""

    def run_evaluation(
        self,
        dataset_path_or_id: str,
        k_values: Optional[List[int]] = None,
        compare_baselines: bool = False,
    ) -> EvaluationReport:
        """Run full evaluation suite over dataset and return EvaluationReport."""
        ...
