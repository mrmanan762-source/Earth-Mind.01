"""Hybrid Retrieval Engine Coordinator for EarthMind Stage R7.

Orchestrates R5 Dense Retrieval and R6 Sparse Retrieval, performs candidate identity
resolution and duplicate candidate merging, enforces top-k candidate limits, coordinates
filtering, handles partial result states (SUCCESS, PARTIAL, FAILED, TIMEOUT), and builds
unified HybridRetrievalResponse payloads ready for downstream R8 Reranking.
"""

import time
from typing import Any, Dict, List, Optional
from core.errors.exceptions import (
    IndexExecutionError,
    IndexProviderUnavailableError,
    InvalidIndexRecordError,
)
from core.interfaces.index import DenseSearchResult, IKnowledgeIndexAdapter
from core.schemas.hybrid import (
    HybridCandidate,
    HybridRetrievalRequest,
    HybridRetrievalResponse,
    HybridRetrievalStatus,
)
from modules.knowledge_base.index.sparse_index import ISparseIndexAdapter, SparseSearchResult
from modules.knowledge_base.retrieval.fusion import CandidateFusionEngine


class HybridRetrievalEngine:
    """Coordinator for Stage R7 Hybrid Retrieval."""

    def __init__(
        self,
        dense_adapter: Optional[IKnowledgeIndexAdapter] = None,
        sparse_adapter: Optional[ISparseIndexAdapter] = None,
        fusion_engine: Optional[CandidateFusionEngine] = None,
    ):
        self.dense_adapter = dense_adapter
        self.sparse_adapter = sparse_adapter
        self.fusion_engine = fusion_engine or CandidateFusionEngine()

    def retrieve(self, request: HybridRetrievalRequest) -> HybridRetrievalResponse:
        """Execute hybrid retrieval over dense and sparse branches and return fused candidates."""
        start_time = time.time()
        warnings: List[str] = []

        dense_results: List[DenseSearchResult] = []
        sparse_results: List[SparseSearchResult] = []

        dense_success = False
        sparse_success = False

        # --- 1. Execute Dense Retrieval Branch ---
        if request.enable_dense and self.dense_adapter and request.dense_vector:
            try:
                if self.dense_adapter.is_available():
                    dense_results = self.dense_adapter.search_dense(
                        collection_name=request.collection_name,
                        query_vector=request.dense_vector,
                        top_k=request.dense_top_k,
                        filters=request.filters,
                        with_record=True,
                    )
                    dense_success = True
                else:
                    warnings.append("Dense index adapter is currently unavailable.")
            except Exception as e:
                warnings.append(f"Dense retrieval branch failed: {str(e)}")
        elif request.enable_dense and not request.dense_vector:
            warnings.append("Dense retrieval enabled but no dense query vector provided.")
        elif request.enable_dense and not self.dense_adapter:
            warnings.append("Dense retrieval enabled but no dense index adapter configured.")

        # --- 2. Execute Sparse Retrieval Branch ---
        if request.enable_sparse and self.sparse_adapter and request.sparse_indices and request.sparse_values:
            try:
                if self.sparse_adapter.is_available():
                    sparse_results = self.sparse_adapter.search_sparse(
                        collection_name=request.collection_name,
                        query_indices=request.sparse_indices,
                        query_values=request.sparse_values,
                        top_k=request.sparse_top_k,
                        filters=request.filters,
                        with_record=True,
                    )
                    sparse_success = True
                else:
                    warnings.append("Sparse index adapter is currently unavailable.")
            except Exception as e:
                warnings.append(f"Sparse retrieval branch failed: {str(e)}")
        elif request.enable_sparse and (not request.sparse_indices or not request.sparse_values):
            warnings.append("Sparse retrieval enabled but sparse query indices/values missing.")
        elif request.enable_sparse and not self.sparse_adapter:
            warnings.append("Sparse retrieval enabled but no sparse index adapter configured.")

        # --- 3. Determine Overall Hybrid Status ---
        if dense_success and sparse_success:
            status = HybridRetrievalStatus.SUCCESS
        elif dense_success or sparse_success:
            status = HybridRetrievalStatus.PARTIAL
        else:
            status = HybridRetrievalStatus.FAILED
            elapsed_ms = (time.time() - start_time) * 1000.0
            return HybridRetrievalResponse(
                request_id=request.request_id,
                query_text=request.query_text,
                status=HybridRetrievalStatus.FAILED,
                candidates=[],
                total_dense_candidates=0,
                total_sparse_candidates=0,
                total_fused_candidates=0,
                fusion_strategy_used=request.fusion_strategy,
                processing_time_ms=round(elapsed_ms, 2),
                warnings=warnings,
                error_message="Both dense and sparse retrieval branches failed or were unavailable.",
            )

        # --- 4. Execute Candidate Fusion & Identity Resolution ---
        fused_candidates = self.fusion_engine.fuse(
            dense_results=dense_results,
            sparse_results=sparse_results,
            top_k=request.top_k,
            strategy_name=request.fusion_strategy,
            rrf_k=request.rrf_k,
        )

        elapsed_ms = (time.time() - start_time) * 1000.0

        return HybridRetrievalResponse(
            request_id=request.request_id,
            query_text=request.query_text,
            status=status,
            candidates=fused_candidates,
            total_dense_candidates=len(dense_results),
            total_sparse_candidates=len(sparse_results),
            total_fused_candidates=len(fused_candidates),
            fusion_strategy_used=request.fusion_strategy,
            processing_time_ms=round(elapsed_ms, 2),
            warnings=warnings,
            error_message=None if status != HybridRetrievalStatus.FAILED else "Retrieval failed.",
        )
