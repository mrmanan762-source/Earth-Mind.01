"""
EarthMind Stage R11 Evidence Builder Engine Implementation.

Responsible for:
- Receiving outputs from Stage R8 Reranking and Stage R10 Web Search Integration
- Converting candidates and search results into unified, traceable EvidenceItems
- Conservative deduplication based on strongest identity signals (chunk_id, candidate_id, web_result_id, normalized URL)
- Preserving scores, ranks, C.2 lineage, and origin provenance
- Preserving source assessment signals, conflict indicators, and multimodal metadata
- Bounded content truncation and item/package limits with explicit warning tracking
- Distinguishing KB vs Web source types without auto-publishing Web evidence or writing to Memory
- Exposing stable EvidencePackage and generating B2 Context Manager compatible RAGContextContracts
"""

import logging
import time
import uuid
from typing import Dict, List, Optional, Set, Tuple

from core.config.settings import EvidenceBuilderConfig, settings
from core.errors.exceptions import InvalidEvidenceBuildRequestError
from core.interfaces.evidence import IEvidenceBuilderEngine
from core.schemas.evidence import (
    EvidenceBuildRequest,
    EvidenceBuildResponse,
    EvidenceBuildStatus,
    EvidenceItem,
    EvidencePackage,
    EvidenceSourceType,
)
from core.schemas.rerank import RerankStatus
from core.schemas.web_search import WebSearchStatus

logger = logging.getLogger(__name__)


class EvidenceBuilderEngine(IEvidenceBuilderEngine):
    """
    Implementation of Stage R11 Evidence Builder Engine adhering to EarthMind architecture
    and the 5 EarthMind Principles.
    """

    def __init__(self, config: Optional[EvidenceBuilderConfig] = None):
        self.config = config or settings.evidence_builder

    def build_evidence(self, request: EvidenceBuildRequest) -> EvidenceBuildResponse:
        """
        Constructs a structured, traceable EvidencePackage from R8 reranked candidates and/or R10 web search results.
        """
        start_time = time.time()

        if not request:
            raise InvalidEvidenceBuildRequestError("Request payload cannot be None.")

        query_text = request.query_text or ""
        if not query_text.strip():
            # Check if query text can be recovered from R8 or R10 responses
            if request.rerank_response and request.rerank_response.query_text:
                query_text = request.rerank_response.query_text
            elif request.web_search_response and request.web_search_response.query_text:
                query_text = request.web_search_response.query_text

        if not query_text.strip():
            raise InvalidEvidenceBuildRequestError("query_text cannot be empty.")

        request_id = request.request_id or (
            request.rerank_response.request_id if request.rerank_response else None
        ) or (
            request.web_search_response.request_id if request.web_search_response else None
        ) or f"req_r11_{uuid.uuid4().hex[:12]}"

        warnings: List[str] = []
        errors: List[str] = []
        raw_items: List[EvidenceItem] = []
        is_partial = False

        # Effective limits
        max_items = request.max_items if request.max_items is not None else self.config.max_items
        max_content_len = (
            request.max_content_length
            if request.max_content_length is not None
            else self.config.max_content_length
        )

        # 1. Process KB evidence from R8
        rerank_resp = request.rerank_response
        if rerank_resp:
            if rerank_resp.status in (RerankStatus.SUCCESS, RerankStatus.FALLBACK):
                for candidate in rerank_resp.candidates:
                    try:
                        item = EvidenceItem.from_rerank_candidate(
                            candidate, request_id=request_id
                        )
                        raw_items.append(item)
                    except Exception as ex:
                        warn_msg = f"Failed to parse R8 candidate '{getattr(candidate, 'candidate_id', 'unknown')}': {ex}"
                        warnings.append(warn_msg)
                        is_partial = True
                if rerank_resp.status == RerankStatus.FALLBACK:
                    is_partial = True
                    warnings.append("R8 reranker used fallback ordering.")
            else:
                is_partial = True
                err_msg = f"R8 reranking returned non-SUCCESS status: {rerank_resp.status}"
                if rerank_resp.error_message:
                    err_msg += f" ({rerank_resp.error_message})"
                errors.append(err_msg)
                warnings.extend(rerank_resp.warnings)

        # 2. Process Web evidence from R10
        web_resp = request.web_search_response
        if web_resp:
            if web_resp.status == WebSearchStatus.SUCCESS:
                for web_res in web_resp.results:
                    try:
                        item = EvidenceItem.from_web_search_result(
                            web_res, request_id=request_id
                        )
                        raw_items.append(item)
                    except Exception as ex:
                        warn_msg = f"Failed to parse R10 search result '{getattr(web_res, 'result_id', 'unknown')}': {ex}"
                        warnings.append(warn_msg)
                        is_partial = True
            else:
                is_partial = True
                err_msg = f"R10 web search returned non-SUCCESS status: {web_resp.status}"
                if web_resp.error_message:
                    err_msg += f" ({web_resp.error_message})"
                errors.append(err_msg)
                warnings.extend(web_resp.warnings)

        # 3. Conservative Deduplication
        dedup_enabled = request.deduplicate if request.deduplicate is not None else self.config.deduplicate
        processed_items: List[EvidenceItem] = []

        if dedup_enabled and raw_items:
            processed_items = self._deduplicate_items(raw_items)
        else:
            processed_items = list(raw_items)

        # 4. Truncation and Limit Enforcement
        final_items: List[EvidenceItem] = []
        for rank_idx, item in enumerate(processed_items[:max_items], start=1):
            # Assign deterministic output retrieval rank
            item.retrieval_rank = rank_idx

            # Enforce max content length
            if max_content_len and len(item.content) > max_content_len:
                item.content = item.content[:max_content_len]
                item.is_truncated = True
                item.truncation_reason = f"Exceeded max content length limit of {max_content_len} characters."

            final_items.append(item)

        if len(processed_items) > max_items:
            warnings.append(f"Evidence package items count trimmed from {len(processed_items)} to limit of {max_items}.")

        # 5. Counts and Status Determination
        kb_count = sum(1 for it in final_items if it.source_type == EvidenceSourceType.KNOWLEDGE_BASE)
        web_count = sum(1 for it in final_items if it.source_type == EvidenceSourceType.WEB_SEARCH)
        total_count = len(final_items)

        if total_count == 0:
            status = EvidenceBuildStatus.EMPTY
        elif is_partial or errors:
            status = EvidenceBuildStatus.PARTIAL
        else:
            status = EvidenceBuildStatus.SUCCESS

        elapsed_ms = (time.time() - start_time) * 1000.0

        package = EvidencePackage(
            package_id=f"pkg_{uuid.uuid4().hex[:12]}",
            request_id=request_id,
            query_text=query_text,
            status=status,
            items=final_items,
            kb_items_count=kb_count,
            web_items_count=web_count,
            total_items_count=total_count,
            is_partial=is_partial,
            warnings=warnings,
            errors=errors,
            execution_time_ms=elapsed_ms,
        )

        return EvidenceBuildResponse(
            request_id=request_id,
            status=status,
            package=package,
            warnings=warnings,
            error_message="; ".join(errors) if errors else None,
            execution_time_ms=elapsed_ms,
        )

    def _deduplicate_items(self, items: List[EvidenceItem]) -> List[EvidenceItem]:
        """
        Conservative deduplication logic.
        Deduplicates items only when explicit, definitive identity matches exist:
        - Same chunk_id for KB evidence
        - Same candidate_id for KB evidence
        - Same web_result_id for Web evidence
        - Same normalized URL for Web evidence
        Preserves distinct evidence items if uncertain.
        """
        seen_keys: Set[str] = set()
        unique_items: List[EvidenceItem] = []

        for item in items:
            key: Optional[str] = None

            if item.source_type == EvidenceSourceType.KNOWLEDGE_BASE:
                if item.chunk_id:
                    key = f"kb_chunk:{item.chunk_id}"
                elif item.candidate_id:
                    key = f"kb_candidate:{item.candidate_id}"
                elif item.document_id and item.version_id and item.content:
                    key = f"kb_doc:{item.document_id}:{item.version_id}:{hash(item.content)}"
            elif item.source_type == EvidenceSourceType.WEB_SEARCH:
                if item.web_result_id:
                    key = f"web_id:{item.web_result_id}"
                elif item.url:
                    norm_url = item.url.strip().rstrip("/").lower()
                    key = f"web_url:{norm_url}"

            if key:
                if key in seen_keys:
                    logger.debug("Deduplicated evidence item with identity key: %s", key)
                    continue
                seen_keys.add(key)

            unique_items.append(item)

        return unique_items
