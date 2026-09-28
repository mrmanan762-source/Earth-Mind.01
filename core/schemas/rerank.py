"""Data Contracts for EarthMind Stage R8 Reranking.

Defines Pydantic models for:
- RerankStatus: Execution status enum (SUCCESS, PARTIAL, FAILED, TIMEOUT, UNAVAILABLE, FALLBACK)
- RerankScoreResult: Single document/candidate reranking score payload from provider
- RerankCandidate: Unified reranked candidate preserving all upstream R7 properties and adding R8 scores
- RerankRequest: Incoming request payload for candidate reranking
- RerankResponse: Output payload ready for Stage R11 Evidence Builder
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.schemas.hybrid import CandidateRetrievalSource, HybridCandidate, HybridRetrievalResponse
from modules.knowledge_base.index.record import IndexRecord


class RerankStatus(str, Enum):
    """Execution status for R8 reranking operation."""
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    FALLBACK = "FALLBACK"


class RerankScoreResult(BaseModel):
    """Output score produced by IRerankerProvider for a single candidate."""
    candidate_id: str = Field(..., description="Unique candidate identifier matching HybridCandidate.candidate_id")
    score: float = Field(..., description="Raw relevance score assigned by reranker provider")


class RerankCandidate(BaseModel):
    """Reranked candidate representation preserving complete upstream R7 lineage and adding R8 metrics."""
    candidate_id: str = Field(..., description="Unique candidate identifier")
    record_id: str = Field(..., description="Physical IndexRecord ID")
    chunk_id: Optional[str] = Field(None, description="Canonical Chunk ID")
    knowledge_unit_id: Optional[str] = Field(None, description="Canonical Knowledge Unit ID")
    source_id: str = Field(..., description="Source identifier")
    document_id: str = Field(..., description="Document identifier")
    version_id: str = Field(..., description="Document version identifier")

    # Upstream R7 Hybrid Retrieval scores and ranks
    fused_score: float = Field(..., description="Final combined score computed by R7 fusion strategy")
    fused_rank: int = Field(..., description="1-based position in R7 fused ranking")
    dense_rank: Optional[int] = Field(None, description="1-based rank in dense retrieval")
    dense_score: Optional[float] = Field(None, description="Raw score in dense retrieval")
    sparse_rank: Optional[int] = Field(None, description="1-based rank in sparse retrieval")
    sparse_score: Optional[float] = Field(None, description="Raw score in sparse retrieval")

    # Stage R8 Reranking scores and ranks
    rerank_score: Optional[float] = Field(None, description="Independent relevance score computed by R8 reranker")
    rerank_rank: Optional[int] = Field(None, description="Final 1-based ordering position after R8 reranking")
    rerank_provider: Optional[str] = Field(None, description="Reranker provider identifier")
    rerank_model: Optional[str] = Field(None, description="Reranker model identifier/version")
    is_fallback: bool = Field(False, description="Whether this candidate ordering relies on fallback strategy")

    # Traceability, Metadata & Provenance Preservation
    retrieval_sources: List[CandidateRetrievalSource] = Field(default_factory=list, description="Retrieval branches from R7")
    payload_metadata: Dict[str, Any] = Field(default_factory=dict, description="Domain and administrative metadata")
    provenance: Optional[Any] = Field(None, description="Lineage provenance chain")
    record: Optional[IndexRecord] = Field(None, description="Optional full IndexRecord payload")

    @classmethod
    def from_hybrid_candidate(
        cls,
        candidate: HybridCandidate,
        rerank_score: Optional[float] = None,
        rerank_rank: Optional[int] = None,
        rerank_provider: Optional[str] = None,
        rerank_model: Optional[str] = None,
        is_fallback: bool = False,
    ) -> "RerankCandidate":
        """Factory method to convert an upstream R7 HybridCandidate into an R8 RerankCandidate."""
        return cls(
            candidate_id=candidate.candidate_id,
            record_id=candidate.record_id,
            chunk_id=candidate.chunk_id,
            knowledge_unit_id=candidate.knowledge_unit_id,
            source_id=candidate.source_id,
            document_id=candidate.document_id,
            version_id=candidate.version_id,
            fused_score=candidate.fused_score,
            fused_rank=candidate.fused_rank,
            dense_rank=candidate.dense_rank,
            dense_score=candidate.dense_score,
            sparse_rank=candidate.sparse_rank,
            sparse_score=candidate.sparse_score,
            rerank_score=rerank_score,
            rerank_rank=rerank_rank,
            rerank_provider=rerank_provider,
            rerank_model=rerank_model,
            is_fallback=is_fallback,
            retrieval_sources=list(candidate.retrieval_sources),
            payload_metadata=dict(candidate.payload_metadata),
            provenance=candidate.provenance,
            record=candidate.record,
        )


class RerankRequest(BaseModel):
    """Incoming request for Stage R8 Reranking."""
    query_text: str = Field(..., description="Original query string")
    candidates: List[HybridCandidate] = Field(..., description="List of unified candidates from Stage R7")
    top_k: int = Field(10, description="Final number of reranked top candidates requested")
    request_id: Optional[str] = Field(None, description="Correlation / request tracing ID")
    timeout: float = Field(10.0, description="Execution timeout in seconds")
    allow_fallback: bool = Field(True, description="Whether to fall back to R7 fused ordering on reranker failure")

    @classmethod
    def from_hybrid_response(
        cls,
        response: HybridRetrievalResponse,
        top_k: Optional[int] = None,
        allow_fallback: bool = True,
        timeout: float = 10.0,
    ) -> "RerankRequest":
        """Factory method to build a RerankRequest directly from an R7 HybridRetrievalResponse."""
        k = top_k if top_k is not None else len(response.candidates)
        return cls(
            query_text=response.query_text,
            candidates=response.candidates,
            top_k=k,
            request_id=response.request_id,
            timeout=timeout,
            allow_fallback=allow_fallback,
        )


class RerankResponse(BaseModel):
    """Output payload from Stage R8 Reranking, ready for Stage R11 Evidence Builder."""
    request_id: Optional[str] = Field(None, description="Correlation / request tracing ID")
    query_text: str = Field(..., description="Original input query string")
    status: RerankStatus = Field(RerankStatus.SUCCESS, description="Reranking execution status")
    candidates: List[RerankCandidate] = Field(default_factory=list, description="Relevance-ranked candidate set")
    total_candidates_received: int = Field(0, description="Total candidates received from R7")
    total_candidates_reranked: int = Field(0, description="Total candidates successfully reranked")
    provider_used: Optional[str] = Field(None, description="Reranker provider identifier used")
    model_used: Optional[str] = Field(None, description="Reranker model identifier used")
    is_fallback: bool = Field(False, description="True if output relies on fallback ordering")
    processing_time_ms: float = Field(0.0, description="Execution latency in milliseconds")
    warnings: List[str] = Field(default_factory=list, description="Partial failure or operational warnings")
    error_message: Optional[str] = Field(None, description="Error details if status is FAILED")
