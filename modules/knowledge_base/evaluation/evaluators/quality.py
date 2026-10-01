"""Quality Evaluator for Stage R15 (Precision, Recall, HitRate, MRR, nDCG)."""

import math
from typing import Any, Dict, List, Optional, Set

from core.interfaces.evaluation import IQualityEvaluator
from core.schemas.evaluation import EvaluationCase, MetricStatus, QualityMetrics


class QualityEvaluator(IQualityEvaluator):
    """
    Computes deterministic retrieval quality metrics (Precision@K, Recall@K, Hit Rate@K, MRR, nDCG@K).
    Handles missing ground truth safely using MetricStatus.NOT_EVALUABLE without fabricating scores.
    """

    DEFAULT_K_VALUES = [1, 3, 5, 10]

    def evaluate_quality(
        self,
        cases: List[EvaluationCase],
        results: List[Any],
        k_values: Optional[List[int]] = None,
    ) -> QualityMetrics:
        ks = k_values or self.DEFAULT_K_VALUES
        if not cases or not results or len(cases) != len(results):
            return QualityMetrics(
                status=MetricStatus.INSUFFICIENT_DATA,
                total_cases_evaluated=len(cases),
                not_evaluable_cases=len(cases),
                details={"reason": "Cases or results list is empty or length mismatched."},
            )

        precisions: Dict[int, List[float]] = {k: [] for k in ks}
        recalls: Dict[int, List[float]] = {k: [] for k in ks}
        hit_rates: Dict[int, List[float]] = {k: [] for k in ks}
        ndcgs: Dict[int, List[float]] = {k: [] for k in ks}
        mrr_scores: List[float] = []

        evaluable_count = 0
        not_evaluable_count = 0

        for case, res in zip(cases, results):
            # Extract retrieved IDs from result payload (RAGContextContract, ContextItem, or dict)
            retrieved_ids = self._extract_retrieved_ids(res)

            # Ground truth targets
            expected_ids = set(case.expected_chunk_ids + case.expected_document_ids + case.expected_evidence_ids)

            if not expected_ids:
                # Handle negative/empty cases
                if not retrieved_ids:
                    # Correct empty retrieval
                    for k in ks:
                        precisions[k].append(1.0)
                        recalls[k].append(1.0)
                        hit_rates[k].append(1.0)
                        ndcgs[k].append(1.0)
                    mrr_scores.append(1.0)
                    evaluable_count += 1
                else:
                    # Retrieved items when none expected -> Precision = 0
                    for k in ks:
                        precisions[k].append(0.0)
                        recalls[k].append(0.0)
                        hit_rates[k].append(0.0)
                        ndcgs[k].append(0.0)
                    mrr_scores.append(0.0)
                    evaluable_count += 1
                continue

            evaluable_count += 1

            # Precision, Recall, Hit Rate at K
            for k in ks:
                retrieved_at_k = retrieved_ids[:k]
                relevant_at_k = [r for r in retrieved_at_k if r in expected_ids]

                prec = len(relevant_at_k) / float(k) if k > 0 else 0.0
                rec = len(relevant_at_k) / float(len(expected_ids)) if len(expected_ids) > 0 else 0.0
                hr = 1.0 if len(relevant_at_k) > 0 else 0.0

                precisions[k].append(prec)
                recalls[k].append(rec)
                hit_rates[k].append(hr)

                # nDCG@K
                rel_judgments = case.relevance_judgments or {eid: 1.0 for eid in expected_ids}
                ndcg_val = self._compute_ndcg(retrieved_at_k, rel_judgments, k)
                ndcgs[k].append(ndcg_val)

            # MRR
            first_rank = 0
            for idx, r_id in enumerate(retrieved_ids, start=1):
                if r_id in expected_ids:
                    first_rank = idx
                    break
            mrr_val = 1.0 / first_rank if first_rank > 0 else 0.0
            mrr_scores.append(mrr_val)

        if evaluable_count == 0:
            return QualityMetrics(
                status=MetricStatus.NOT_EVALUABLE,
                total_cases_evaluated=len(cases),
                not_evaluable_cases=not_evaluable_count,
            )

        avg_precision = {k: round(sum(precisions[k]) / float(len(precisions[k])), 4) for k in ks}
        avg_recall = {k: round(sum(recalls[k]) / float(len(recalls[k])), 4) for k in ks}
        avg_hit_rate = {k: round(sum(hit_rates[k]) / float(len(hit_rates[k])), 4) for k in ks}
        avg_ndcg = {k: round(sum(ndcgs[k]) / float(len(ndcgs[k])), 4) for k in ks}
        avg_mrr = round(sum(mrr_scores) / float(len(mrr_scores)), 4) if mrr_scores else 0.0

        return QualityMetrics(
            status=MetricStatus.EVALUATED,
            precision_at_k=avg_precision,
            recall_at_k=avg_recall,
            hit_rate_at_k=avg_hit_rate,
            mrr=avg_mrr,
            ndcg_at_k=avg_ndcg,
            total_cases_evaluated=evaluable_count,
            not_evaluable_cases=not_evaluable_count,
        )

    def _extract_retrieved_ids(self, result: Any) -> List[str]:
        """Extracts candidate/chunk/document/evidence IDs from result payload."""
        ids: List[str] = []
        if not result:
            return ids

        items = []
        if hasattr(result, "final_context_items") and result.final_context_items is not None:
            items = result.final_context_items
        elif isinstance(result, list):
            items = result
        elif hasattr(result, "candidates") and result.candidates is not None:
            items = result.candidates

        for item in items:
            entity_id = getattr(item, "entity_id", None) or getattr(item, "contract_id", None) or getattr(item, "candidate_id", None)
            chunk_id = getattr(item, "chunk_id", None)
            doc_id = getattr(item, "document_id", None)
            payload = getattr(item, "payload", {}) or getattr(item, "metadata", {}) or {}

            if isinstance(payload, dict):
                p_chunk = payload.get("chunk_id")
                p_doc = payload.get("document_id")
                if p_chunk:
                    ids.append(p_chunk)
                if p_doc:
                    ids.append(p_doc)

            if chunk_id:
                ids.append(chunk_id)
            if doc_id:
                ids.append(doc_id)
            if entity_id:
                ids.append(entity_id)

        # Retain order while removing duplicates
        seen = set()
        unique_ids = []
        for i in ids:
            if i not in seen:
                seen.add(i)
                unique_ids.append(i)

        return unique_ids

    def _compute_ndcg(
        self,
        retrieved_ids: List[str],
        relevance_judgments: Dict[str, float],
        k: int,
    ) -> float:
        """Computes Normalized Discounted Cumulative Gain (nDCG) at cutoff K."""
        dcg = 0.0
        for idx, item_id in enumerate(retrieved_ids[:k], start=1):
            rel = relevance_judgments.get(item_id, 0.0)
            if rel > 0.0:
                dcg += (2.0 ** rel - 1.0) / math.log2(idx + 1)

        # Ideal DCG
        ideal_rels = sorted(relevance_judgments.values(), reverse=True)[:k]
        idcg = 0.0
        for idx, rel in enumerate(ideal_rels, start=1):
            if rel > 0.0:
                idcg += (2.0 ** rel - 1.0) / math.log2(idx + 1)

        if idcg <= 0.0:
            return 1.0 if dcg == 0.0 else 0.0

        return round(dcg / idcg, 4)
