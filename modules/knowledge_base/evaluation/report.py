"""Stage R15 Evaluation Report Generator."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from core.schemas.evaluation import (
    BaselineResult,
    EvaluationDataset,
    EvaluationReport,
    EvaluationRun,
    QualityMetrics,
    QualityStatus,
    RegressionResult,
)
from modules.knowledge_base.evaluation.quality import QualityEvaluator


class EvaluationReportGenerator:
    """Generates comprehensive structured evaluation reports and text summaries."""

    def __init__(self, quality_evaluator: Optional[QualityEvaluator] = None):
        self.quality_evaluator = quality_evaluator or QualityEvaluator()

    def _sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Removes secrets, tokens, and API keys from dictionary trees."""
        secret_keywords = {"key", "token", "secret", "password", "credential", "auth", "api_key"}
        clean: Dict[str, Any] = {}
        for k, v in data.items():
            if any(kw in k.lower() for kw in secret_keywords):
                clean[k] = "[REDACTED]"
            elif isinstance(v, dict):
                clean[k] = self._sanitize_dict(v)
            else:
                clean[k] = v
        return clean

    def generate_report(
        self,
        evaluation_run: EvaluationRun,
        dataset: Optional[EvaluationDataset] = None,
        baseline_results: Optional[List[BaselineResult]] = None,
        regression_results: Optional[List[RegressionResult]] = None,
    ) -> EvaluationReport:
        """
        Generates structured EvaluationReport from an EvaluationRun.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # Sanitize config and environment
        clean_config = self._sanitize_dict(evaluation_run.config_snapshot)
        clean_env = self._sanitize_dict(evaluation_run.environment_metadata)

        # Build multilingual breakdown
        multilingual_breakdown: Dict[str, QualityMetrics] = {}
        agricultural_breakdown: Dict[str, QualityMetrics] = {}

        not_evaluable_fields: List[str] = []

        if dataset and dataset.cases:
            meas_map = {m.case_id: m for m in evaluation_run.measurements}

            # Multilingual breakdown
            lang_cases: Dict[str, List[Any]] = {}
            for case in dataset.cases:
                lang_cases.setdefault(case.language, []).append(case)

            for lang, cases in lang_cases.items():
                lang_meas = [meas_map[c.case_id] for c in cases if c.case_id in meas_map]
                multilingual_breakdown[lang] = self.quality_evaluator.evaluate_quality(cases, lang_meas)

            # Agricultural domain breakdown
            domain_cases: Dict[str, List[Any]] = {}
            for case in dataset.cases:
                domain_cases.setdefault(case.domain_category, []).append(case)

            for domain, cases in domain_cases.items():
                domain_meas = [meas_map[c.case_id] for c in cases if c.case_id in meas_map]
                agricultural_breakdown[domain] = self.quality_evaluator.evaluate_quality(cases, domain_meas)

        # Track NOT_EVALUABLE fields
        if evaluation_run.quality_metrics and evaluation_run.quality_metrics.status != QualityStatus.EVALUATED:
            not_evaluable_fields.append(f"quality_metrics: {evaluation_run.quality_metrics.status_reason}")

        # Sample case traces
        sample_traces: List[Dict[str, Any]] = []
        for m in evaluation_run.measurements[:5]:
            sample_traces.append({
                "case_id": m.case_id,
                "request_id": m.request_id,
                "trace_id": m.trace_id,
                "correlation_id": m.correlation_id,
                "status": m.status,
                "total_latency_ms": m.total_latency_ms,
                "retrieved_count": len(m.retrieved_chunk_ids),
                "context_item_count": m.context_item_count,
            })

        limitations = [
            "Evaluates offline corpus benchmarks; live dynamic web updates are not included.",
            "Multilingual coverage is subject to model tokenizer alignment across Indian languages.",
            "Resource usage indicators report process RSS memory and CPU times.",
        ]

        q_metrics = evaluation_run.quality_metrics or QualityMetrics(
            status=QualityStatus.NOT_EVALUABLE, status_reason="No quality metrics provided"
        )

        return EvaluationReport(
            run_id=evaluation_run.run_id,
            timestamp=now_iso,
            evaluation_metadata={
                "evaluation_run_id": evaluation_run.evaluation_run_id,
                "correlation_id": evaluation_run.correlation_id,
                "knowledge_base_version": evaluation_run.knowledge_base_version,
                "embedding_model_version": evaluation_run.embedding_model_version,
                "sparse_version": evaluation_run.sparse_version,
                "dense_index_version": evaluation_run.dense_index_version,
                "qdrant_version": evaluation_run.qdrant_version,
                "fusion_strategy_version": evaluation_run.fusion_strategy_version,
                "reranker_version": evaluation_run.reranker_version,
                "query_processing_version": evaluation_run.query_processing_version,
                "model_runtime_version": evaluation_run.model_runtime_version,
                "environment": clean_env,
            },
            dataset_info={
                "dataset_id": evaluation_run.dataset_id,
                "dataset_version": evaluation_run.dataset_version,
                "total_cases_evaluated": len(evaluation_run.measurements),
            },
            configuration_info=clean_config,
            quality_metrics=q_metrics,
            performance_metrics=evaluation_run.performance_metrics,
            reliability_metrics=evaluation_run.reliability_metrics,
            multilingual_breakdown=multilingual_breakdown,
            agricultural_breakdown=agricultural_breakdown,
            baseline_comparisons=baseline_results or [],
            regression_comparisons=regression_results or [],
            failure_summary={
                "total_failures": evaluation_run.reliability_metrics.system_failure_count if evaluation_run.reliability_metrics else 0,
                "breakdown": evaluation_run.reliability_metrics.failure_breakdown if evaluation_run.reliability_metrics else {},
            },
            traceability_samples=sample_traces,
            limitations=limitations,
            not_evaluable_fields=not_evaluable_fields,
        )

    def render_markdown_summary(self, report: EvaluationReport) -> str:
        """Renders a human-readable Markdown summary report."""
        q = report.quality_metrics
        p = report.performance_metrics
        r = report.reliability_metrics

        md = []
        md.append(f"# EarthMind RAG Evaluation Report (`{report.report_id}`)")
        md.append(f"**Run ID:** `{report.run_id}` | **Generated:** `{report.timestamp}`\n")

        md.append("## 1. Quality Metrics Summary")
        md.append(f"- **Quality Status:** `{q.status}` ({q.status_reason or 'OK'})")
        md.append(f"- **MRR:** `{q.mrr}`")
        md.append(f"- **Hit Rate@5:** `{q.hit_rate_at_k.get(5)}`")
        md.append(f"- **nDCG@5:** `{q.ndcg_at_k.get(5)}`")
        md.append(f"- **Precision@5:** `{q.precision_at_k.get(5)}`")
        md.append(f"- **Recall@5:** `{q.recall_at_k.get(5)}`\n")

        if p:
            md.append("## 2. Performance Metrics Summary")
            md.append(f"- **E2E Latency (Mean):** `{p.total_latency.mean_ms} ms`")
            md.append(f"- **E2E Latency (P50 / P90 / P99):** `{p.total_latency.p50_ms} ms` / `{p.total_latency.p90_ms} ms` / `{p.total_latency.p99_ms} ms`")
            md.append(f"- **Throughput:** `{p.throughput_qps} QPS` ({p.cases_per_second} cases/sec)\n")

        if r:
            md.append("## 3. Reliability Summary")
            md.append(f"- **Success Rate:** `{r.success_rate * 100:.1f}%` ({r.success_count}/{r.total_cases})")
            md.append(f"- **Valid Empty Rate:** `{r.empty_result_rate * 100:.1f}%` ({r.valid_empty_count})")
            md.append(f"- **System Failure Count:** `{r.system_failure_count}`\n")

        if report.multilingual_breakdown:
            md.append("## 4. Multilingual Quality Breakdown")
            for lang, lq in report.multilingual_breakdown.items():
                md.append(f"- **Language `{lang}`:** MRR=`{lq.mrr}`, HitRate@5=`{lq.hit_rate_at_k.get(5)}`")
            md.append("")

        if report.agricultural_breakdown:
            md.append("## 5. Agricultural Domain Quality Breakdown")
            for dom, dq in report.agricultural_breakdown.items():
                md.append(f"- **Domain `{dom}`:** MRR=`{dq.mrr}`, HitRate@5=`{dq.hit_rate_at_k.get(5)}`")
            md.append("")

        if report.baseline_comparisons:
            md.append("## 6. Baseline Comparisons")
            for b in report.baseline_comparisons:
                md.append(f"- **{b.baseline_name}:** MRR=`{b.quality_metrics.mrr}`, P50 Latency=`{b.performance_metrics.total_latency.p50_ms} ms`")
            md.append("")

        if report.regression_comparisons:
            md.append("## 7. Regression Comparisons")
            for reg in report.regression_comparisons:
                status_str = "REGRESSION" if reg.regression_detected else "NO REGRESSION"
                md.append(f"- **{reg.metric_name}:** Run A={reg.value_a}, Run B={reg.value_b} ({status_str})")
            md.append("")

        return "\n".join(md)
