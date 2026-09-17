from typing import Dict, List, Tuple
from core.logging.logger import get_logger
from modules.context.schemas import ConflictStatus, ContextItem

logger = get_logger("modules.context.conflict")


class ConflictDetector:
    """
    Detects conflicting observations across context items referring to the same logical entity,
    property, and temporal period.
    Marks items as CONFLICTED without dropping any items.
    """

    @staticmethod
    def detect_and_mark_conflicts(items: List[ContextItem]) -> List[ContextItem]:
        # Group items by (entity_type, entity_id, data_type, event_time/recorded_at)
        grouped: Dict[Tuple[str, str, str, str], List[ContextItem]] = {}

        for item in items:
            key = (
                item.entity_type,
                item.entity_id,
                item.data_type,
                item.event_time or item.recorded_at or "undated"
            )
            grouped.setdefault(key, []).append(item)

        for key, group in grouped.items():
            if len(group) > 1:
                # Check if values differ across items in the same logical observation bucket
                values = [item.content for item in group]
                first_val = values[0]
                has_conflict = any(v != first_val for v in values[1:])

                if has_conflict:
                    logger.warning(
                        f"Conflict detected for entity '{key[0]}/{key[1]}' property '{key[2]}' at time '{key[3]}' across {len(group)} sources."
                    )
                    for item in group:
                        item.conflict_status = ConflictStatus.CONFLICTED

        return items
