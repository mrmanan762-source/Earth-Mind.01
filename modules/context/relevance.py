from typing import List
from core.logging.logger import get_logger
from modules.context.schemas import ContextItem, ContextRequest

logger = get_logger("modules.context.relevance")


class RelevanceEvaluator:
    """Evaluates context item relevance against task objectives, requested types, and policies."""

    @staticmethod
    def evaluate_and_filter(items: List[ContextItem], request: ContextRequest) -> List[ContextItem]:
        filtered: List[ContextItem] = []
        threshold = request.relevance_threshold

        mandatory_ids = set(request.policy.mandatory_item_ids) if request.policy else set()
        mandatory_types = set(request.policy.mandatory_context_types) if request.policy else set()

        for item in items:
            score = RelevanceEvaluator.calculate_relevance(item, request)
            item.relevance_score = score

            is_mandatory = (item.context_id in mandatory_ids) or (item.entity_type in mandatory_types)

            if score >= threshold or is_mandatory:
                filtered.append(item)
            else:
                logger.debug(
                    f"Relevance filter excluded item '{item.context_id}': score {score:.2f} < threshold {threshold:.2f}"
                )

        return filtered

    @staticmethod
    def calculate_relevance(item: ContextItem, request: ContextRequest) -> float:
        """
        Calculates a relevance score from 0.0 to 1.0 using task keywords, requested context types,
        entity matching, and item confidence.
        """
        # If item has a custom pre-evaluated relevance_score (not default 1.0), use it as base
        score = item.relevance_score if item.relevance_score != 1.0 else 0.5

        # Requested context types match
        if request.requested_context_types:
            if item.entity_type in request.requested_context_types or item.data_type in request.requested_context_types:
                score += 0.3
            else:
                score -= 0.2

        # Task keywords overlap match
        if request.task and isinstance(item.content, str):
            task_words = set(request.task.lower().split())
            content_words = set(item.content.lower().split())
            overlap = task_words.intersection(content_words)
            if overlap:
                score += min(0.2, 0.05 * len(overlap))

        # Scope direct alignment bonus
        if request.field_id and item.field_id == request.field_id:
            score += 0.1

        # Bound score between 0.0 and 1.0
        return max(0.0, min(1.0, score))
