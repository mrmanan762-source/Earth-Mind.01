"""Stage R15 Quality & Performance Evaluation Interfaces."""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from core.schemas.evaluation import (
    BaselineResult,
    EvaluationCase,
    EvaluationDataset,
    EvaluationMeasurement,
    EvaluationReport,
    EvaluationRun,
    PerformanceMetrics,
    QualityMetrics,
    RegressionResult,
    ReliabilityMetrics,
)


@runtime_checkable
class IEvaluationDatasetRepository(Protocol):
    """Interface for managing and retrieving evaluation datasets."""

    def get_dataset(self, dataset_id: str) -> Optional[EvaluationDataset]:
        """Retrieves an evaluation dataset by ID."""
        ...

    def list_datasets(self) -> List[EvaluationDataset]:
        """Lists all available evaluation datasets."""
        ...

    def save_dataset(self, dataset: EvaluationDataset) -> None:
        """Saves or updates an evaluation dataset."""
        ...


@runtime_checkable
class IQualityEvaluator(Protocol):
    """Interface for evaluating retrieval, reranking, and evidence quality."""

    def evaluate_quality(
        self,
        cases: List[EvaluationCase],
        measurements: List[EvaluationMeasurement],
        k_values: Optional[List[int]] = None,
    ) -> QualityMetrics:
        """Calculates quality metrics across evaluation cases and measurements."""
        ...


@runtime_checkable
class IPerformanceEvaluator(Protocol):
    """Interface for measuring stage latencies, throughput, and resource usage."""

    def evaluate_performance(
        self,
        measurements: List[EvaluationMeasurement],
        total_time_seconds: float,
        execution_mode: str = "sequential",
    ) -> PerformanceMetrics:
        """Calculates performance metrics from case measurements."""
        ...


@runtime_checkable
class IReliabilityEvaluator(Protocol):
    """Interface for evaluating system reliability and error rates."""

    def evaluate_reliability(
        self,
        measurements: List[EvaluationMeasurement],
    ) -> ReliabilityMetrics:
        """Calculates reliability metrics from case measurements."""
        ...


@runtime_checkable
class IBaselineComparator(Protocol):
    """Interface for executing baseline benchmark comparisons."""

    def compare_baselines(
        self,
        baseline_results: List[BaselineResult],
    ) -> Dict[str, Any]:
        """Compares multiple baseline results."""
        ...


@runtime_checkable
class IRegressionEvaluator(Protocol):
    """Interface for detecting regressions between evaluation runs."""

    def compare_runs(
        self,
        previous_run: EvaluationRun,
        current_run: EvaluationRun,
        threshold_pct: float = 5.0,
    ) -> List[RegressionResult]:
        """Compares two evaluation runs to detect performance/quality regressions."""
        ...


@runtime_checkable
class IEvaluationRunner(Protocol):
    """Interface for executing evaluation runs against production harness."""

    def run_evaluation(
        self,
        dataset: EvaluationDataset,
        max_results: int = 10,
        enable_web_search: bool = False,
    ) -> EvaluationRun:
        """Executes an evaluation run over a dataset."""
        ...


@runtime_checkable
class IEvaluationReportGenerator(Protocol):
    """Interface for generating structured evaluation reports."""

    def generate_report(
        self,
        evaluation_run: EvaluationRun,
        baseline_results: Optional[List[BaselineResult]] = None,
        regression_results: Optional[List[RegressionResult]] = None,
    ) -> EvaluationReport:
        """Generates a structured EvaluationReport from run results."""
        ...
