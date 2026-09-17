import json
from typing import List, Optional
from core.errors.exceptions import InsufficientContextError
from core.logging.logger import get_logger
from modules.context.interfaces import CompressionProvider
from modules.context.schemas import ContextItem, ContextRequest, PriorityLevel

logger = get_logger("modules.context.limit_manager")


class LimitManager:
    """
    Manages context token budget enforcing policy-driven reduction steps when total token count
    exceeds budget.
    """

    @staticmethod
    def estimate_item_tokens(item: ContextItem) -> int:
        if item.token_count > 0:
            return item.token_count

        # Fallback estimation based on content representation
        if isinstance(item.content, str):
            length = len(item.content)
        else:
            length = len(json.dumps(item.content, default=str))

        # Rough token approximation ~ 4 characters per token
        estimated = max(1, length // 4)
        item.token_count = estimated
        return estimated

    @classmethod
    def calculate_total_tokens(cls, items: List[ContextItem]) -> int:
        return sum(cls.estimate_item_tokens(item) for item in items)

    @classmethod
    def enforce_limits(
        cls,
        items: List[ContextItem],
        request: ContextRequest,
        compression_provider: Optional[CompressionProvider] = None,
    ) -> List[ContextItem]:
        limit = request.policy.max_tokens if (request.policy and request.policy.max_tokens) else request.token_limit
        total_tokens = cls.calculate_total_tokens(items)

        if total_tokens <= limit:
            return items

        logger.info(f"Context total tokens ({total_tokens}) exceeds budget ({limit}). Applying policy-driven reduction.")

        mandatory_ids = set(request.policy.mandatory_item_ids) if request.policy else set()
        mandatory_types = set(request.policy.mandatory_context_types) if request.policy else set()

        def is_mandatory(item: ContextItem) -> bool:
            return (item.context_id in mandatory_ids) or (item.entity_type in mandatory_types)

        current_items = list(items)

        # Step 1: Remove clearly irrelevant optional items (relevance < 0.3)
        if cls.calculate_total_tokens(current_items) > limit:
            current_items = [
                item for item in current_items
                if is_mandatory(item) or item.relevance_score >= 0.3
            ]

        # Step 2: Remove below-threshold optional items (relevance < request.relevance_threshold)
        if cls.calculate_total_tokens(current_items) > limit:
            current_items = [
                item for item in current_items
                if is_mandatory(item) or item.relevance_score >= request.relevance_threshold
            ]

        # Step 3: Remove lower-priority optional items (LOW priority)
        if cls.calculate_total_tokens(current_items) > limit:
            current_items = [
                item for item in current_items
                if is_mandatory(item) or item.priority != PriorityLevel.LOW
            ]

        # Step 4: Remove MEDIUM priority optional items if still over budget
        if cls.calculate_total_tokens(current_items) > limit:
            current_items = [
                item for item in current_items
                if is_mandatory(item) or item.priority == PriorityLevel.HIGH
            ]

        # Step 5: Compress/condense if compression provider available
        if cls.calculate_total_tokens(current_items) > limit and compression_provider:
            logger.info("Invoking compression provider to reduce token count.")
            current_items = compression_provider.compress(current_items, limit)

        # Step 6: Verify if preserved mandatory/high-priority items fit budget
        final_tokens = cls.calculate_total_tokens(current_items)
        if final_tokens > limit:
            msg = f"Cannot reduce context within token budget {limit} (final total: {final_tokens}) without dropping mandatory context."
            logger.error(msg)
            raise InsufficientContextError(request.request_id, msg)

        return current_items
