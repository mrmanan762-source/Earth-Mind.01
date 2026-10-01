"""Evidence Quality Evaluator for Stage R15 (Completeness, Provenance, Source Type)."""

from typing import Any, Dict, List
from core.schemas.evaluation import MetricStatus, QualityMetrics


class EvidenceEvaluator:
    """Evaluates evidence package structural validity, completeness, provenance preservation, and source types."""

    def evaluate_evidence_quality(self, results: List[Any]) -> Dict[str, Any]:
        if not results:
            return {
                "status": MetricStatus.NOT_EVALUABLE.value,
                "reason": "No evaluation results provided.",
            }

        total_results = len(results)
        valid_evidence_packages = 0
        total_evidence_items = 0
        items_with_provenance = 0
        source_type_counts: Dict[str, int] = {}

        for res in results:
            items = getattr(res, "final_context_items", []) or []
            if items:
                valid_evidence_packages += 1

            for item in items:
                total_evidence_items += 1
                st = getattr(item, "source_type", None) or getattr(item, "source", None)
                st_val = getattr(st, "value", str(st)) if st else "UNKNOWN"
                source_type_counts[st_val] = source_type_counts.get(st_val, 0) + 1

                prov = getattr(item, "provenance", None) or getattr(item, "metadata", {})
                if prov:
                    items_with_provenance += 1

        provenance_rate = round(items_with_provenance / float(total_evidence_items), 4) if total_evidence_items > 0 else 1.0

        return {
            "status": MetricStatus.EVALUATED.value,
            "total_packages_evaluated": total_results,
            "valid_packages_count": valid_evidence_packages,
            "total_evidence_items": total_evidence_items,
            "items_with_provenance": items_with_provenance,
            "provenance_preservation_rate": provenance_rate,
            "source_type_breakdown": source_type_counts,
        }
