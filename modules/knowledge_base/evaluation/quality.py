"""Stage R15 Retrieval, Reranking, Evidence, and E2E Quality Evaluator."""

import math
from typing import Any, Dict, List, Optional, Set
from core.schemas.evaluation import (
    EvaluationCase,
    EvaluationMeasurement,
    QualityMetrics,
    QualityStatus,
)


class QualityEvaluator:
    """Evaluates retrieval, reranking, and evidence quality using ground-truth labels."""

    def __init__(self, default_k_values: Optional[List[int]] = None):
        self.default_k_values = default_k_values or [1, 3, 5, 10]

    def evaluate_quality(
        self,
        cases: List[EvaluationCase],
        measurements: List[EvaluationMeasurement],
        k_values: Optional[List[int]] = None,
    ) -> QualityMetrics:
        """
        Calculates Precision@K, Recall@K, Hit Rate@K, MRR, nDCG@K, rerank movement, and evidence quality.

        Returns:
            QualityMetrics with explicit QualityStatus handling when ground truth is missing.
        """
        k_list = sorted(list(set(k_values or self.default_k_values)))
        meas_map = {m.case_id: m for m in measurements}

        evaluable_cases = [c for c in cases if c.expected_relevant_chunk_ids or c.expected_relevant_doc_ids]
        if not cases or not evaluable_cases:
            return QualityMetrics(
                precision_at_k={k: None for k in k_list},
                recall_at_k={k: None for k in k_list},
                hit_rate_at_k={k: None for k in k_list},
                mrr=None,
                ndcg_at_k={k: None for k in k_list},
                rerank_movement={},
                evidence_metrics={},
                status=QualityStatus.NOT_EVALUABLE,
                status_reason="No ground truth labels available for quality evaluation.",
            )

        prec_sums: Dict[int, float] = {k: 0.0 for k in k_list}
        rec_sums: Dict[int, float] = {k: 0.0 for k in k_list}
        hit_sums: Dict[int, float] = {k: 0.0 for k in k_list}
        mrr_sum: float = 0.0
        ndcg_sums: Dict[int, float] = {k: 0.0 for k in k_list}
        eval_count = 0

        rerank_improvements = 0
        rerank_comparisons = 0

        valid_evidence_count = 0
        total_evidence_count = 0

        for case in evaluable_cases:
            meas = meas_map.get(case.case_id)
            if not meas:
                continue

            eval_count += 1
            # Relevant item set (chunks or documents)
            rel_chunks: Set[str] = set(case.expected_relevant_chunk_ids)
            rel_docs: Set[str] = set(case.expected_relevant_doc_ids)

            retrieved = meas.reranked_chunk_ids or meas.retrieved_chunk_ids

            # Calculate MRR
            first_hit_rank: Optional[int] = None
            for idx, item in enumerate(retrieved):
                if item in rel_chunks or any(doc_id in item for doc_id in rel_docs):
                    first_hit_rank = idx + 1
                    break
            if first_hit_rank is not None:
                mrr_sum += 1.0 / first_hit_rank

            # Per K metrics
            for k in k_list:
                top_k = retrieved[:k]
                hits = sum(1 for item in top_k if item in rel_chunks or any(doc_id in item for doc_id in rel_docs))

                prec_sums[k] += hits / float(k)

                total_rel = len(rel_chunks) if rel_chunks else len(rel_docs)
                if total_rel > 0:
                    rec_sums[k] += hits / float(total_rel)

                hit_sums[k] += 1.0 if hits > 0 else 0.0

                # nDCG calculation
                dcg = sum((1.0 if (item in rel_chunks or any(doc_id in item for doc_id in rel_docs)) else 0.0) / math.log2(i + 2) for i, item in enumerate(top_k))
                idcg = sum(1.0 / math.log2(i + 2) for i in range(min(k, max(total_rel, 1))))
                ndcg_sums[k] += (dcg / idcg) if idcg > 0 else 0.0

            # Rerank comparison (R7 vs R8)
            if meas.retrieved_chunk_ids and meas.reranked_chunk_ids:
                pre_rank = None
                post_rank = None
                for idx, item in enumerate(meas.retrieved_chunk_ids):
                    if item in rel_chunks or any(doc_id in item for doc_id in rel_docs):
                        pre_rank = idx + 1
                        break
                for idx, item in enumerate(meas.reranked_chunk_ids):
                    if item in rel_chunks or any(doc_id in item for doc_id in rel_docs):
                        post_rank = idx + 1
                        break

                if pre_rank is not None and post_rank is not None:
                    rerank_comparisons += 1
                    if post_rank < pre_rank:
                        rerank_improvements += 1

            if meas.validation_status == "VALID":
                valid_evidence_count += 1
            total_evidence_count += 1

        if eval_count == 0:
            return QualityMetrics(
                precision_at_k={k: None for k in k_list},
                recall_at_k={k: None for k in k_list},
                hit_rate_at_k={k: None for k in k_list},
                mrr=None,
                ndcg_at_k={k: None for k in k_list},
                rerank_movement={},
                evidence_metrics={},
                status=QualityStatus.INSUFFICIENT_DATA,
                status_reason="No measurements with retrieved candidates matched the evaluation dataset.",
            )

        return QualityMetrics(
            precision_at_k={k: round(prec_sums[k] / eval_count, 4) for k in k_list},
            recall_at_k={k: round(rec_sums[k] / eval_count, 4) for k in k_list},
            hit_rate_at_k={k: round(hit_sums[k] / eval_count, 4) for k in k_list},
            mrr=round(mrr_sum / eval_count, 4),
            ndcg_at_k={k: round(ndcg_sums[k] / eval_count, 4) for k in k_list},
            rerank_movement={
                "comparisons_count": rerank_comparisons,
                "improvements_count": rerank_improvements,
                "improvement_rate": round(rerank_improvements / float(rerank_comparisons), 4) if rerank_comparisons > 0 else None,
            },
            evidence_metrics={
                "valid_evidence_rate": round(valid_evidence_count / float(total_evidence_count), 4) if total_evidence_count > 0 else 0.0,
                "total_evaluated": total_evidence_count,
            },
            status=QualityStatus.EVALUATED,
            status_reason="Quality metrics calculated successfully over ground-truth evaluation cases.",
        )
