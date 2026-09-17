from typing import List, Optional, Dict, Any
from core.logging.logger import get_logger
from modules.context.schemas import ContextItem, ContextRequest, PrivacyLevel

logger = get_logger("modules.context.filter")


class ScopeFilter:
    """Filters context items to prevent cross-farmer, farm, field, or session data leakage."""

    @staticmethod
    def filter(items: List[ContextItem], request: ContextRequest) -> List[ContextItem]:
        filtered: List[ContextItem] = []
        for item in items:
            if request.farmer_id and item.farmer_id and item.farmer_id != request.farmer_id:
                logger.warning(f"Scope mismatch (farmer_id): Item '{item.context_id}' ({item.farmer_id}) != Request ({request.farmer_id})")
                continue
            if request.farm_id and item.farm_id and item.farm_id != request.farm_id:
                logger.warning(f"Scope mismatch (farm_id): Item '{item.context_id}' ({item.farm_id}) != Request ({request.farm_id})")
                continue
            if request.field_id and item.field_id and item.field_id != request.field_id:
                logger.warning(f"Scope mismatch (field_id): Item '{item.context_id}' ({item.field_id}) != Request ({request.field_id})")
                continue
            if request.crop_cycle_id and item.crop_cycle_id and item.crop_cycle_id != request.crop_cycle_id:
                logger.warning(f"Scope mismatch (crop_cycle_id): Item '{item.context_id}' ({item.crop_cycle_id}) != Request ({request.crop_cycle_id})")
                continue
            if request.session_id and item.session_id and item.session_id != request.session_id:
                logger.warning(f"Scope mismatch (session_id): Item '{item.context_id}' ({item.session_id}) != Request ({request.session_id})")
                continue
            filtered.append(item)
        return filtered


class PrivacyFilter:
    """Enforces data privacy policies on context items."""

    @staticmethod
    def filter(items: List[ContextItem], request: ContextRequest) -> List[ContextItem]:
        allow_pii = request.policy.allow_pii if request.policy else False
        filtered: List[ContextItem] = []
        for item in items:
            if not allow_pii and (item.privacy_level == PrivacyLevel.FARMER_PII or item.is_pii):
                logger.info(f"Privacy filter excluded PII item '{item.context_id}'")
                continue
            filtered.append(item)
        return filtered


class TimeFilter:
    """Filters context items according to structured event_time, recorded_at, valid_from, valid_until."""

    @staticmethod
    def filter(items: List[ContextItem], request: ContextRequest) -> List[ContextItem]:
        if not request.time_range:
            return items

        start_time = request.time_range.get("start_time")
        end_time = request.time_range.get("end_time")

        filtered: List[ContextItem] = []
        for item in items:
            # Use event_time primarily, fallback to recorded_at
            t_str = item.event_time or item.recorded_at
            if t_str:
                if start_time and t_str < start_time:
                    logger.debug(f"Time filter excluded item '{item.context_id}': timestamp {t_str} < start {start_time}")
                    continue
                if end_time and t_str > end_time:
                    logger.debug(f"Time filter excluded item '{item.context_id}': timestamp {t_str} > end {end_time}")
                    continue

            # Check validity window if specified in item and request time range
            if item.valid_until and end_time and item.valid_until < start_time if start_time else False:
                continue

            filtered.append(item)
        return filtered
