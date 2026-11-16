"""Bridge providers that feed tool results into the B2 Context Manager.

Tool output reaches B2 through the same ``ContextProvider`` interface used by the
RAG, Memory and Satellite providers. This keeps B5 from duplicating the Tool
Dispatcher and keeps B2 as the single place where context is prepared.

Boundary rules:
- The provider reads request-scoped results from the shared ``ToolEvidenceBuffer``
  only. It performs no tool execution and no reasoning.
- Tool results are marked as ``EXTERNAL_SERVICE`` / ``EXTERNAL_OWNED`` so
  downstream reasoning can distinguish live tool data from verified RAG corpus.
"""

from __future__ import annotations

from typing import Any, List, Optional

from core.logging.logger import get_logger
from core.schemas.tools import ToolCallResult, ToolCallStatus
from modules.context.boundary.enums import (
    ContextOwnership,
    ContextSourceType,
    KnowledgeClassification,
    PersistenceIntent,
    ContextScope,
)
from modules.context.schemas import ContextItem, ContextRequest, PrivacyLevel

logger = get_logger("app.integration.tool_evidence_provider")


class ToolEvidenceProvider:
    """ContextProvider that surfaces request-scoped tool results to B2."""

    provider_name = "tool_provider"

    def __init__(self, buffer: Any, trace_id: Optional[str] = None) -> None:
        self._buffer = buffer

    def get_context(self, request: ContextRequest) -> List[ContextItem]:
        results: List[ToolCallResult] = self._buffer.get_results(request.request_id)
        items: List[ContextItem] = []

        for result in results:
            if result.status not in (ToolCallStatus.SUCCESS, ToolCallStatus.PARTIAL):
                continue

            content = result.payload if result.payload is not None else {}
            items.append(
                ContextItem(
                    context_id=f"tool_{result.tool_id}_{request.request_id}",
                    entity_type="tool_result",
                    entity_id=result.tool_id,
                    data_type=f"tool:{result.tool_id}",
                    content=content,
                    farmer_id=request.farmer_id,
                    farm_id=request.farm_id,
                    field_id=request.field_id,
                    crop_cycle_id=request.crop_cycle_id,
                    session_id=request.session_id,
                    source=f"tool:{result.tool_id}",
                    source_id=result.tool_id,
                    confidence=0.8 if result.status == ToolCallStatus.SUCCESS else 0.5,
                    privacy_level=PrivacyLevel.PUBLIC,
                    is_pii=False,
                    relevance_score=0.6,
                    source_type=ContextSourceType.EXTERNAL_SERVICE,
                    ownership=ContextOwnership.EXTERNAL_OWNED,
                    classification=KnowledgeClassification.EXTERNAL_CURRENT_DATA,
                    scope=ContextScope.GLOBAL,
                    persistence_intent=PersistenceIntent.TEMPORARY,
                    boundary_metadata={
                        "tool_id": result.tool_id,
                        "tool_status": result.status.value,
                        "sources": [s.model_dump() for s in result.sources],
                    },
                    trace_id=request.trace_id,
                    metadata={
                        "tool_id": result.tool_id,
                        "tool_status": result.status.value,
                        "sources": [s.model_dump() for s in result.sources],
                        "warnings": list(result.warnings),
                    },
                )
            )

        if items:
            logger.debug(
                "ToolEvidenceProvider surfaced %d tool result(s) for request %s",
                len(items),
                request.request_id,
            )
        return items
