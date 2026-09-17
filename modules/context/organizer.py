from typing import Dict, List, Any
from core.logging.logger import get_logger
from modules.context.schemas import (
    ConflictStatus,
    ContextItem,
    ContextRequest,
    PriorityLevel,
)

logger = get_logger("modules.context.organizer")


class Prioritizer:
    """Assigns policy-driven priority levels (HIGH, MEDIUM, LOW) to context items."""

    @staticmethod
    def assign_priorities(items: List[ContextItem], request: ContextRequest) -> List[ContextItem]:
        mandatory_ids = set(request.policy.mandatory_item_ids) if request.policy else set()
        mandatory_types = set(request.policy.mandatory_context_types) if request.policy else set()

        for item in items:
            # Policy Signals
            is_mandatory = (item.context_id in mandatory_ids) or (item.entity_type in mandatory_types)
            is_conflicted = item.conflict_status == ConflictStatus.CONFLICTED
            is_high_relevance = item.relevance_score >= 0.8
            is_low_relevance = item.relevance_score < 0.4

            if is_mandatory or (is_high_relevance and not is_conflicted):
                item.priority = PriorityLevel.HIGH
            elif is_low_relevance:
                item.priority = PriorityLevel.LOW
            else:
                item.priority = PriorityLevel.MEDIUM

        return items


class ContextOrganizer:
    """
    Organizes and sorts context items deterministically by dimensions such as entity, priority,
    type, time, and source.
    """

    @staticmethod
    def organize_and_sort(items: List[ContextItem]) -> List[ContextItem]:
        # Priority mapping for deterministic ordering
        priority_map = {
            PriorityLevel.HIGH: 1,
            PriorityLevel.MEDIUM: 2,
            PriorityLevel.LOW: 3,
        }

        # Deterministic multi-key sort: priority -> relevance_score (desc) -> entity_type -> entity_id -> context_id
        sorted_items = sorted(
            items,
            key=lambda x: (
                priority_map.get(x.priority, 2),
                -x.relevance_score,
                x.entity_type,
                x.entity_id,
                x.context_id,
            ),
        )

        return sorted_items

    @staticmethod
    def group_by_dimension(items: List[ContextItem], dimension: str = "entity_type") -> Dict[str, List[ContextItem]]:
        grouped: Dict[str, List[ContextItem]] = {}
        for item in items:
            key_val = str(getattr(item, dimension, "other"))
            grouped.setdefault(key_val, []).append(item)
        return grouped
