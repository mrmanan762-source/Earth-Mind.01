from typing import List, Set, Tuple
from core.logging.logger import get_logger
from modules.context.schemas import ContextItem

logger = get_logger("modules.context.deduplicator")


class ContextDeduplicator:
    """
    Deduplicates context items using stable identity, provenance, temporal, and version signals.
    Does NOT auto-deduplicate similar text from distinct sources or observations.
    """

    @staticmethod
    def deduplicate(items: List[ContextItem]) -> List[ContextItem]:
        unique_items: List[ContextItem] = []
        seen_keys: Set[Tuple[str, str, str, str, str]] = set()

        for item in items:
            # Key built from stable signals:
            # context_id, source, source_id, event_time/recorded_at, version
            key = (
                item.context_id,
                item.source or "",
                item.source_id or "",
                item.event_time or item.recorded_at or "",
                item.version or ""
            )

            if key in seen_keys:
                logger.debug(f"Deduplicator dropped exact duplicate item '{item.context_id}' from source '{item.source}'.")
                continue

            seen_keys.add(key)
            unique_items.append(item)

        return unique_items
