from typing import List, Optional, Tuple
from core.logging.logger import get_logger
from modules.context.schemas import (
    ContextItem,
    ContextRequest,
    ContextResult,
    PrivacyLevel,
)

logger = get_logger("modules.context.validator")


class ItemValidator:
    """Validates individual incoming ContextItem instances before pipeline processing."""

    @staticmethod
    def validate_item(item: ContextItem) -> Tuple[bool, Optional[str]]:
        if not item.context_id or not item.context_id.strip():
            return False, "Context item missing context_id."
        if not item.entity_type or not item.entity_type.strip():
            return False, f"Item '{item.context_id}' missing entity_type."
        if not item.entity_id or not item.entity_id.strip():
            return False, f"Item '{item.context_id}' missing entity_id."
        if not item.data_type or not item.data_type.strip():
            return False, f"Item '{item.context_id}' missing data_type."
        if not item.source or not item.source.strip():
            return False, f"Item '{item.context_id}' missing source provenance."
        if item.content is None:
            return False, f"Item '{item.context_id}' contains null content."
        if not (0.0 <= item.confidence <= 1.0):
            return False, f"Item '{item.context_id}' has invalid confidence score {item.confidence}."
        if not (0.0 <= item.relevance_score <= 1.0):
            return False, f"Item '{item.context_id}' has invalid relevance score {item.relevance_score}."
        if item.token_count < 0:
            return False, f"Item '{item.context_id}' has negative token count."
        return True, None


class OutputValidator:
    """Validates final prepared ContextResult prior to delivery to downstream model execution."""

    @staticmethod
    def validate_result(result: ContextResult, request: ContextRequest) -> Tuple[bool, List[str]]:
        errors: List[str] = []

        # 1. Scope Validation
        for item in result.items:
            if request.farmer_id and item.farmer_id and item.farmer_id != request.farmer_id:
                errors.append(f"Scope leakage: Item '{item.context_id}' farmer_id '{item.farmer_id}' != request '{request.farmer_id}'.")
            if request.farm_id and item.farm_id and item.farm_id != request.farm_id:
                errors.append(f"Scope leakage: Item '{item.context_id}' farm_id '{item.farm_id}' != request '{request.farm_id}'.")
            if request.field_id and item.field_id and item.field_id != request.field_id:
                errors.append(f"Scope leakage: Item '{item.context_id}' field_id '{item.field_id}' != request '{request.field_id}'.")
            if request.session_id and item.session_id and item.session_id != request.session_id:
                errors.append(f"Scope leakage: Item '{item.context_id}' session_id '{item.session_id}' != request '{request.session_id}'.")

        # 2. Privacy Validation
        if request.policy and not request.policy.allow_pii:
            for item in result.items:
                if item.privacy_level == PrivacyLevel.FARMER_PII or item.is_pii:
                    errors.append(f"Privacy violation: Item '{item.context_id}' contains FARMER_PII but policy disables PII.")

        # 3. Duplicate Check
        seen_ids = set()
        for item in result.items:
            if item.context_id in seen_ids:
                errors.append(f"Duplicate context_id detected in output: '{item.context_id}'.")
            seen_ids.add(item.context_id)

        # 4. Mandatory Rules Check
        if request.policy:
            for mandatory_id in request.policy.mandatory_item_ids:
                if mandatory_id not in seen_ids:
                    errors.append(f"Mandatory context item ID '{mandatory_id}' missing from output.")
            for mandatory_type in request.policy.mandatory_context_types:
                if not any(item.entity_type == mandatory_type for item in result.items):
                    errors.append(f"Mandatory context type '{mandatory_type}' missing from output.")

        # 5. Token Budget Check
        effective_limit = request.policy.max_tokens if (request.policy and request.policy.max_tokens) else request.token_limit
        if result.total_tokens > effective_limit:
            errors.append(f"Token budget exceeded: total {result.total_tokens} > limit {effective_limit}.")

        is_valid = len(errors) == 0
        return is_valid, errors
