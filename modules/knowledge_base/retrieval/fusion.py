"""Candidate Fusion Engine and Strategies for EarthMind R7 Hybrid Retrieval.

Implements:
- IFusionStrategy protocol
- ReciprocalRankFusionStrategy (RRF): RRF score = sum(1 / (k + rank))
- RelativeScoreFusionStrategy: Min-Max score normalization and weighted sum
- CandidateFusionEngine: Unified candidate identity matching, duplicate merging, and strategy application
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from pydantic import BaseModel, Field

from core.interfaces.index import DenseSearchResult
from core.schemas.hybrid import CandidateRetrievalSource, HybridCandidate, RetrievalSourceType
from modules.knowledge_base.index.sparse_index import SparseSearchResult


def resolve_candidate_identity(record_id: str, payload: Dict[str, Any]) -> str:
    """Resolve a stable candidate identity from payload metadata or record ID.

    Prioritizes canonical chunk_id or knowledge_unit_id over raw index record_id.
    """
    chunk_id = payload.get("chunk_id") or payload.get("_chunk_id")
    if chunk_id:
        return str(chunk_id)

    unit_id = payload.get("knowledge_unit_id") or payload.get("_knowledge_unit_id")
    if unit_id:
        return str(unit_id)

    return str(record_id)


@runtime_checkable
class IFusionStrategy(Protocol):
    """Protocol for candidate fusion algorithms."""

    def fuse(
        self,
        dense_results: List[DenseSearchResult],
        sparse_results: List[SparseSearchResult],
        top_k: int = 10,
        **kwargs: Any,
    ) -> List[HybridCandidate]:
        """Combine dense and sparse search results into a unified candidate list."""
        ...


class ReciprocalRankFusionStrategy:
    """Reciprocal Rank Fusion (RRF) algorithm.

    RRF score = sum(1.0 / (k + rank)) across retrieval branches where candidate appears.
    Uses configurable smoothing parameter k (default 60).
    """

    def __init__(self, k: int = 60):
        self.k = k

    def fuse(
        self,
        dense_results: List[DenseSearchResult],
        sparse_results: List[SparseSearchResult],
        top_k: int = 10,
        **kwargs: Any,
    ) -> List[HybridCandidate]:
        rrf_k = kwargs.get("rrf_k", self.k)

        # Map candidate_id -> accumulated candidate data
        candidates_map: Dict[str, Dict[str, Any]] = {}

        # Process Dense Branch
        for rank, res in enumerate(dense_results, start=1):
            payload = res.payload or {}
            c_id = resolve_candidate_identity(res.record_id, payload)
            rrf_score = 1.0 / (rrf_k + rank)

            if c_id not in candidates_map:
                candidates_map[c_id] = {
                    "candidate_id": c_id,
                    "record_id": res.record_id,
                    "chunk_id": payload.get("chunk_id") or payload.get("_chunk_id"),
                    "knowledge_unit_id": payload.get("knowledge_unit_id") or payload.get("_knowledge_unit_id"),
                    "source_id": payload.get("source_id") or payload.get("_source_id") or "unknown",
                    "document_id": payload.get("document_id") or payload.get("_document_id") or "unknown",
                    "version_id": payload.get("version_id") or payload.get("_version_id") or "unknown",
                    "fused_score": 0.0,
                    "dense_rank": rank,
                    "dense_score": res.score,
                    "sparse_rank": None,
                    "sparse_score": None,
                    "retrieval_sources": [],
                    "payload_metadata": payload,
                    "record": res.record,
                }

            candidates_map[c_id]["fused_score"] += rrf_score
            candidates_map[c_id]["retrieval_sources"].append(
                CandidateRetrievalSource(
                    source_type=RetrievalSourceType.DENSE,
                    rank=rank,
                    score=res.score,
                )
            )

        # Process Sparse Branch
        for rank, res in enumerate(sparse_results, start=1):
            payload = res.payload or {}
            c_id = resolve_candidate_identity(res.record_id, payload)
            rrf_score = 1.0 / (rrf_k + rank)

            if c_id not in candidates_map:
                candidates_map[c_id] = {
                    "candidate_id": c_id,
                    "record_id": res.record_id,
                    "chunk_id": payload.get("chunk_id") or payload.get("_chunk_id"),
                    "knowledge_unit_id": payload.get("knowledge_unit_id") or payload.get("_knowledge_unit_id"),
                    "source_id": payload.get("source_id") or payload.get("_source_id") or "unknown",
                    "document_id": payload.get("document_id") or payload.get("_document_id") or "unknown",
                    "version_id": payload.get("version_id") or payload.get("_version_id") or "unknown",
                    "fused_score": 0.0,
                    "dense_rank": None,
                    "dense_score": None,
                    "sparse_rank": rank,
                    "sparse_score": res.score,
                    "retrieval_sources": [],
                    "payload_metadata": payload,
                    "record": res.record,
                }
            else:
                candidates_map[c_id]["sparse_rank"] = rank
                candidates_map[c_id]["sparse_score"] = res.score
                if not candidates_map[c_id]["record"] and res.record:
                    candidates_map[c_id]["record"] = res.record

            candidates_map[c_id]["fused_score"] += rrf_score
            candidates_map[c_id]["retrieval_sources"].append(
                CandidateRetrievalSource(
                    source_type=RetrievalSourceType.SPARSE,
                    rank=rank,
                    score=res.score,
                )
            )

        # Sort candidates deterministically by fused_score descending, then candidate_id ascending for stable tie handling
        sorted_candidates = sorted(
            candidates_map.values(),
            key=lambda x: (-x["fused_score"], x["candidate_id"]),
        )

        fused_list: List[HybridCandidate] = []
        for fused_rank, item in enumerate(sorted_candidates[:top_k], start=1):
            fused_list.append(
                HybridCandidate(
                    candidate_id=item["candidate_id"],
                    record_id=item["record_id"],
                    chunk_id=item["chunk_id"],
                    knowledge_unit_id=item["knowledge_unit_id"],
                    source_id=item["source_id"],
                    document_id=item["document_id"],
                    version_id=item["version_id"],
                    fused_score=round(item["fused_score"], 6),
                    fused_rank=fused_rank,
                    retrieval_sources=item["retrieval_sources"],
                    dense_rank=item["dense_rank"],
                    dense_score=item["dense_score"],
                    sparse_rank=item["sparse_rank"],
                    sparse_score=item["sparse_score"],
                    payload_metadata=item["payload_metadata"],
                    record=item["record"],
                )
            )

        return fused_list


class RelativeScoreFusionStrategy:
    """Relative Min-Max Score Normalization Fusion strategy."""

    def __init__(self, dense_weight: float = 0.5, sparse_weight: float = 0.5):
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight

    def fuse(
        self,
        dense_results: List[DenseSearchResult],
        sparse_results: List[SparseSearchResult],
        top_k: int = 10,
        **kwargs: Any,
    ) -> List[HybridCandidate]:
        d_weight = kwargs.get("dense_weight", self.dense_weight)
        s_weight = kwargs.get("sparse_weight", self.sparse_weight)

        # Helper for min-max normalization
        def _normalize_scores(scores: List[float]) -> List[float]:
            if not scores:
                return []
            min_s = min(scores)
            max_s = max(scores)
            if max_s == min_s:
                return [1.0 for _ in scores]
            return [(s - min_s) / (max_s - min_s) for s in scores]

        norm_dense = _normalize_scores([r.score for r in dense_results])
        norm_sparse = _normalize_scores([r.score for r in sparse_results])

        candidates_map: Dict[str, Dict[str, Any]] = {}

        for rank, (res, norm_score) in enumerate(zip(dense_results, norm_dense), start=1):
            payload = res.payload or {}
            c_id = resolve_candidate_identity(res.record_id, payload)
            if c_id not in candidates_map:
                candidates_map[c_id] = {
                    "candidate_id": c_id,
                    "record_id": res.record_id,
                    "chunk_id": payload.get("chunk_id") or payload.get("_chunk_id"),
                    "knowledge_unit_id": payload.get("knowledge_unit_id") or payload.get("_knowledge_unit_id"),
                    "source_id": payload.get("source_id") or payload.get("_source_id") or "unknown",
                    "document_id": payload.get("document_id") or payload.get("_document_id") or "unknown",
                    "version_id": payload.get("version_id") or payload.get("_version_id") or "unknown",
                    "fused_score": 0.0,
                    "dense_rank": rank,
                    "dense_score": res.score,
                    "sparse_rank": None,
                    "sparse_score": None,
                    "retrieval_sources": [],
                    "payload_metadata": payload,
                    "record": res.record,
                }
            candidates_map[c_id]["fused_score"] += norm_score * d_weight
            candidates_map[c_id]["retrieval_sources"].append(
                CandidateRetrievalSource(
                    source_type=RetrievalSourceType.DENSE,
                    rank=rank,
                    score=res.score,
                )
            )

        for rank, (res, norm_score) in enumerate(zip(sparse_results, norm_sparse), start=1):
            payload = res.payload or {}
            c_id = resolve_candidate_identity(res.record_id, payload)
            if c_id not in candidates_map:
                candidates_map[c_id] = {
                    "candidate_id": c_id,
                    "record_id": res.record_id,
                    "chunk_id": payload.get("chunk_id") or payload.get("_chunk_id"),
                    "knowledge_unit_id": payload.get("knowledge_unit_id") or payload.get("_knowledge_unit_id"),
                    "source_id": payload.get("source_id") or payload.get("_source_id") or "unknown",
                    "document_id": payload.get("document_id") or payload.get("_document_id") or "unknown",
                    "version_id": payload.get("version_id") or payload.get("_version_id") or "unknown",
                    "fused_score": 0.0,
                    "dense_rank": None,
                    "dense_score": None,
                    "sparse_rank": rank,
                    "sparse_score": res.score,
                    "retrieval_sources": [],
                    "payload_metadata": payload,
                    "record": res.record,
                }
            else:
                candidates_map[c_id]["sparse_rank"] = rank
                candidates_map[c_id]["sparse_score"] = res.score

            candidates_map[c_id]["fused_score"] += norm_score * s_weight
            candidates_map[c_id]["retrieval_sources"].append(
                CandidateRetrievalSource(
                    source_type=RetrievalSourceType.SPARSE,
                    rank=rank,
                    score=res.score,
                )
            )

        sorted_candidates = sorted(
            candidates_map.values(),
            key=lambda x: (-x["fused_score"], x["candidate_id"]),
        )

        fused_list: List[HybridCandidate] = []
        for fused_rank, item in enumerate(sorted_candidates[:top_k], start=1):
            fused_list.append(
                HybridCandidate(
                    candidate_id=item["candidate_id"],
                    record_id=item["record_id"],
                    chunk_id=item["chunk_id"],
                    knowledge_unit_id=item["knowledge_unit_id"],
                    source_id=item["source_id"],
                    document_id=item["document_id"],
                    version_id=item["version_id"],
                    fused_score=round(item["fused_score"], 6),
                    fused_rank=fused_rank,
                    retrieval_sources=item["retrieval_sources"],
                    dense_rank=item["dense_rank"],
                    dense_score=item["dense_score"],
                    sparse_rank=item["sparse_rank"],
                    sparse_score=item["sparse_score"],
                    payload_metadata=item["payload_metadata"],
                    record=item["record"],
                )
            )

        return fused_list


class CandidateFusionEngine:
    """Engine responsible for candidate fusion registry and execution."""

    def __init__(self, default_strategy: Optional[IFusionStrategy] = None):
        self.strategies: Dict[str, IFusionStrategy] = {
            "RRF": ReciprocalRankFusionStrategy(),
            "RELATIVE_SCORE": RelativeScoreFusionStrategy(),
        }
        self.default_strategy = default_strategy or self.strategies["RRF"]

    def register_strategy(self, name: str, strategy: IFusionStrategy) -> None:
        """Register a new replaceable fusion strategy."""
        self.strategies[name.upper().strip()] = strategy

    def fuse(
        self,
        dense_results: List[DenseSearchResult],
        sparse_results: List[SparseSearchResult],
        top_k: int = 10,
        strategy_name: Optional[str] = None,
        **kwargs: Any,
    ) -> List[HybridCandidate]:
        """Execute candidate fusion using specified or default fusion strategy."""
        s_name = (strategy_name or "RRF").upper().strip()
        strategy = self.strategies.get(s_name, self.default_strategy)
        return strategy.fuse(
            dense_results=dense_results,
            sparse_results=sparse_results,
            top_k=top_k,
            **kwargs,
        )
