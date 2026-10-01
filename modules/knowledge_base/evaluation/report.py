"""Report Generator for Stage R15 (JSON and Markdown Formats)."""

import json
from pathlib import Path
from typing import Optional
from core.schemas.evaluation import EvaluationReport


class EvaluationReportGenerator:
    """Formats EvaluationReport objects into structured JSON and clean Markdown reports."""

    @staticmethod
    def to_json(report: EvaluationReport, indent: int = 2) -> str:
        """Converts EvaluationReport into formatted JSON string."""
        return report.model_dump_json(indent=indent)

    @staticmethod
    def to_markdown(report: EvaluationReport) -> str:
        """Converts EvaluationReport into a Markdown report."""
        lines = []
        lines.append(f"# EarthMind Stage R15 RAG Evaluation Report")
        lines.append(f"**Run ID:** `{report.evaluation_run_id}` | **Timestamp:** `{report.timestamp}` | **Status:** `{report.status.value}`")
        lines.append("")
        lines.append("## 1. Dataset & Environment Summary")
        lines.append(f"- **Dataset:** `{report.dataset_info.get('dataset_name', 'Unknown')}` (`{report.dataset_info.get('dataset_id')}` v`{report.dataset_info.get('dataset_version')}`)")
        lines.append(f"- **Total Test Cases:** {report.dataset_info.get('total_cases', 0)}")
        lines.append(f"- **RAG Pipeline:** {report.system_versions.get('rag_pipeline', 'Unknown')}")
        lines.append("")
        lines.append("## 2. Retrieval Quality Metrics")
        qm = report.quality_metrics
        lines.append(f"- **MRR (Mean Reciprocal Rank):** `{qm.mrr}`")
        lines.append(f"- **Precision@K:** {qm.precision_at_k}")
        lines.append(f"- **Recall@K:** {qm.recall_at_k}")
        lines.append(f"- **Hit Rate@K:** {qm.hit_rate_at_k}")
        lines.append(f"- **nDCG@K:** {qm.ndcg_at_k}")
        lines.append("")
        lines.append("## 3. Performance Metrics")
        pm = report.performance_metrics
        lines.append(f"- **Average Latency:** `{pm.avg_e2e_latency_ms} ms`")
        lines.append(f"- **P50 Latency:** `{pm.p50_latency_ms} ms` | **P90 Latency:** `{pm.p90_latency_ms} ms` | **P99 Latency:** `{pm.p99_latency_ms} ms`")
        lines.append(f"- **Throughput (QPS):** `{pm.queries_per_second} queries/sec`")
        lines.append("")
        lines.append("## 4. Reliability & Outcome Rates")
        rm = report.reliability_metrics
        lines.append(f"- **Success Rate:** `{rm.success_rate * 100:.1f}%` ({rm.success_count}/{rm.total_cases})")
        lines.append(f"- **Failure Rate:** `{rm.failure_rate * 100:.1f}%` ({rm.failure_count}/{rm.total_cases})")
        lines.append(f"- **Empty Result Rate:** `{rm.empty_result_rate * 100:.1f}%` ({rm.empty_result_count}/{rm.total_cases})")
        lines.append("")
        lines.append("## 5. Multilingual Breakdown")
        for lang, l_qm in report.multilingual_breakdown.items():
            lines.append(f"- **Language `{lang}`:** MRR=`{l_qm.mrr}`, Precision@5=`{l_qm.precision_at_k.get(5, 0.0)}`, Recall@5=`{l_qm.recall_at_k.get(5, 0.0)}`")
        lines.append("")
        lines.append("## 6. Agricultural Domain Breakdown")
        for dom, d_qm in report.agricultural_domain_breakdown.items():
            lines.append(f"- **Domain `{dom}`:** MRR=`{d_qm.mrr}`, Precision@5=`{d_qm.precision_at_k.get(5, 0.0)}`, Recall@5=`{d_qm.recall_at_k.get(5, 0.0)}`")
        lines.append("")

        if report.baseline_comparison:
            lines.append("## 7. Baseline Comparison")
            for b_res in report.baseline_comparison:
                lines.append(f"- **Mode `{b_res.baseline_name}`:** MRR=`{b_res.quality_metrics.mrr}`, Avg Latency=`{b_res.performance_metrics.avg_e2e_latency_ms} ms`")
            lines.append("")

        if report.regression_comparison:
            lines.append("## 8. Regression Comparison")
            rc = report.regression_comparison
            lines.append(f"- **Comparison ID:** `{rc.comparison_id}` | **Status:** `{rc.overall_status}`")
            lines.append(f"- **Regressions:** {rc.regressions_detected or 'None'}")
            lines.append(f"- **Improvements:** {rc.improvements_detected or 'None'}")
            lines.append("")

        lines.append("## 9. Limitations & Boundaries")
        for lim in report.limitations:
            lines.append(f"- {lim}")

        return "\n".join(lines)

    @staticmethod
    def save_report(
        report: EvaluationReport,
        output_dir: Optional[str] = None,
    ) -> tuple[Path, Path]:
        """Saves JSON and Markdown reports to output_dir."""
        out_path = Path(output_dir) if output_dir else Path(__file__).resolve().parents[3] / "docs"
        out_path.mkdir(parents=True, exist_ok=True)

        json_path = out_path / f"r15_eval_report_{report.evaluation_run_id}.json"
        md_path = out_path / f"r15_eval_report_{report.evaluation_run_id}.md"

        with open(json_path, "w", encoding="utf-8") as f:
            f.write(EvaluationReportGenerator.to_json(report))

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(EvaluationReportGenerator.to_markdown(report))

        return json_path, md_path
