"""Reranking Quality Evaluator for Stage R15 (Pre vs Post Reranking Comparison)."""

from typing import Any, Dict, List, Optional
from core.schemas.evaluation import MetricStatus, QualityMetrics
from modules.knowledge_base.evaluation.evaluators.quality import QualityEvaluator


class RerankEvaluator:
    """Evaluates candidate rank changes and quality gains introduced by Stage R8 Reranker."""

    def __init__(self, quality_evaluator: Optional[QualityEvaluator] = None):
        self.quality_evaluator = quality_evaluator or QualityEvaluator()

    def evaluate_reranking_gain(
        self,
        cases: List[Any],
        pre_rerank_responses: List[Any],
        post_rerank_responses: List[Any],
    ) -> Dict[str, Any]:
        """
        Compares quality metrics before and after reranking to measure actual reranking gain.
        """
        if not pre_rerank_responses or not post_rerank_responses:
            return {
                "status": MetricStatus.NOT_EVALUABLE.value,
                "reason": "Missing pre or post rerank responses.",
            }

        pre_metrics = self.quality_evaluator.evaluate_quality(cases, pre_rerank_responses)
        post_metrics = self.quality_evaluator.evaluate_quality(cases, post_rerank_responses)

        mrr_gain = round(post_metrics.mrr - pre_metrics.mrr, 4)
        ndcg5_pre = pre_metrics.ndcg_at_k.get(5, 0.0)
        ndcg5_post = post_metrics.ndcg_at_k.get(5, 0.0)
        ndcg5_gain = round(ndcg5_post - ndcg5_pre, 4)

        return {
            "status": MetricStatus.EVALUATED.value,
            "pre_rerank_metrics": pre_metrics.model_dump(),
            "post_rerank_metrics": post_metrics.model_dump(),
            "mrr_gain": mrr_gain,
            "ndcg5_gain": ndcg5_gain,
            "is_reranker_beneficial": post_metrics.mrr >= pre_metrics.mrr,
        }
