from typing import Dict, List, Any
from core.logging.logger import get_logger
from modules.context.schemas import ContextItem, ContextRequest, ContextResult, ContextState

logger = get_logger("modules.context.builder")


class ContextBuilder:
    """
    Constructs model-ready structured context payload from validated, filtered, and prioritized
    ContextItems.
    Does NOT perform reasoning or make agricultural decisions.
    """

    @staticmethod
    def build_context_result(
        request: ContextRequest,
        items: List[ContextItem],
        state: ContextState = ContextState.COMPLETED,
        warnings: List[str] = None,
        errors: List[str] = None,
        metrics: Dict[str, Any] = None,
    ) -> ContextResult:
        warnings = warnings or []
        errors = errors or []
        metrics = metrics or {}

        # Build structured context dictionary for direct LLM / model consumption
        structured_context: Dict[str, Any] = {
            "scope": {
                "farmer_id": request.farmer_id,
                "farm_id": request.farm_id,
                "field_id": request.field_id,
                "crop_cycle_id": request.crop_cycle_id,
                "session_id": request.session_id,
            },
            "task": request.task,
            "items": [],
            "conflicts_present": any(item.conflict_status.value == "CONFLICTED" for item in items),
        }

        total_tokens = 0
        is_compressed = False

        for item in items:
            total_tokens += item.token_count
            if item.is_compressed:
                is_compressed = True

            item_dict = {
                "context_id": item.context_id,
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "data_type": item.data_type,
                "content": item.content,
                "source": item.source,
                "event_time": item.event_time or item.recorded_at,
                "confidence": item.confidence,
                "conflict_status": item.conflict_status.value,
                "privacy_level": item.privacy_level.value,
                "priority": item.priority.value,
                "relevance_score": item.relevance_score,
                "is_compressed": item.is_compressed,
                "provenance": {
                    "source_id": item.source_id,
                    "transformations": [t.model_dump() for t in item.transformation_history],
                },
                "trace_id": item.trace_id or request.trace_id,
                "source_type": item.source_type.value if item.source_type else None,
                "ownership": item.ownership.value if item.ownership else None,
                "classification": item.classification.value if item.classification else None,
                "scope": item.scope.value if item.scope else None,
                "persistence_intent": item.persistence_intent.value if item.persistence_intent else None,
                "boundary_metadata": item.boundary_metadata,
            }
            structured_context["items"].append(item_dict)

        exec_metadata = {
            "b2_version": metrics.get("b2_version", "1.0.0"),
            "context_version": metrics.get("context_version", "1.0.0"),
            "items_received": metrics.get("items_received", len(items)),
            "items_retained": len(items),
            "items_filtered": metrics.get("items_filtered", 0),
            "items_dropped_budget": metrics.get("items_dropped_budget", 0),
            "provider_statuses": metrics.get("provider_statuses", {}),
            "execution_latency_ms": metrics.get("execution_latency_ms", 0.0),
            "validation_status": metrics.get("validation_status", "PASSED" if not errors else "FAILED"),
            "prioritization_summary": {
                "HIGH": sum(1 for item in items if getattr(item.priority, "value", str(item.priority)) == "HIGH"),
                "MEDIUM": sum(1 for item in items if getattr(item.priority, "value", str(item.priority)) == "MEDIUM"),
                "LOW": sum(1 for item in items if getattr(item.priority, "value", str(item.priority)) == "LOW"),
            },
        }

        result = ContextResult(
            request_id=request.request_id,
            state=state,
            items=items,
            structured_context=structured_context,
            total_tokens=total_tokens,
            is_compressed=is_compressed,
            trace_id=request.trace_id,
            warnings=warnings,
            errors=errors,
            metadata=exec_metadata,
        )

        return result
