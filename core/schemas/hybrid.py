"""Data Contracts for EarthMind Stage R7 Hybrid Retrieval.

Defines Pydantic models for:
- HybridRetrievalRequest: Incoming retrieval query, dense/sparse vectors, limits, filters
- CandidateRetrievalSource: Individual retrieval branch contribution (DENSE, SPARSE)
- HybridCandidate: Unified candidate record with merged dense/sparse scores, ranks, and metadata
- HybridRetrievalStatus: Execution status enum (SUCCESS, PARTIAL, FAILED, TIMEOUT, UNAVAILABLE)
- HybridRetrievalResponse: Complete response payload returned to downstream stages (R8 Reranker)
"""

from enum import Enum
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from modules.knowledge_base.index.record import IndexRecord


class HybridRetrievalStatus(str, Enum):
    """Execution status for hybrid retrieval operation."""
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"


class RetrievalSourceType(str, Enum):
    """Source branch that contributed a candidate."""
    DENSE = "DENSE"
    SPARSE = "SPARSE"
    HYBRID = "HYBRID"


class CandidateRetrievalSource(BaseModel):
    """Details of a candidate's contribution from a specific retrieval branch."""
    source_type: RetrievalSourceType = Field(..., description="Retrieval branch type (DENSE or SPARSE)")
    rank: int = Field(..., description="1-based rank within that retrieval branch")
    score: float = Field(..., description="Raw score returned by the branch engine")
    provider_name: Optional[str] = Field(None, description="Provider/adapter name")
    model_name: Optional[str] = Field(None, description="Model identifier")


class HybridCandidate(BaseModel):
    """Unified candidate record representing a Knowledge Unit or Chunk."""
    candidate_id: str = Field(..., description="Unique candidate identifier (derived from chunk_id / knowledge_unit_id / record_id)")
    record_id: str = Field(..., description="Physical IndexRecord ID")
    chunk_id: Optional[str] = Field(None, description="Canonical Chunk ID")
    knowledge_unit_id: Optional[str] = Field(None, description="Canonical Knowledge Unit ID")
    source_id: str = Field(..., description="Source identifier")
    document_id: str = Field(..., description="Document identifier")
    version_id: str = Field(..., description="Document version identifier")
    fused_score: float = Field(..., description="Final combined score computed by fusion strategy")
    fused_rank: int = Field(..., description="1-based position in final fused ranking")
    retrieval_sources: List[CandidateRetrievalSource] = Field(default_factory=list, description="List of retrieval branches that returned this candidate")
    dense_rank: Optional[int] = Field(None, description="1-based rank in dense retrieval (if present)")
    dense_score: Optional[float] = Field(None, description="Raw score in dense retrieval (if present)")
    sparse_rank: Optional[int] = Field(None, description="1-based rank in sparse retrieval (if present)")
    sparse_score: Optional[float] = Field(None, description="Raw score in sparse retrieval (if present)")
    payload_metadata: Dict[str, Any] = Field(default_factory=dict, description="Domain and administrative metadata")
    provenance: Optional[Any] = Field(None, description="Lineage provenance chain")
    record: Optional[IndexRecord] = Field(None, description="Optional full IndexRecord payload")


class HybridRetrievalRequest(BaseModel):
    """Incoming request for hybrid retrieval."""
    query_text: str = Field(..., description="Original query string")
    dense_vector: Optional[List[float]] = Field(None, description="Pre-computed dense query vector (R4 model)")
    sparse_indices: Optional[List[int]] = Field(None, description="Pre-computed sparse term indices (R6 BM25)")
    sparse_values: Optional[List[float]] = Field(None, description="Pre-computed sparse term weights (R6 BM25)")
    collection_name: str = Field("earthmind_knowledge", description="Target collection name")
    top_k: int = Field(10, description="Final number of top candidates requested")
    dense_top_k: int = Field(20, description="Number of candidates requested from dense branch")
    sparse_top_k: int = Field(20, description="Number of candidates requested from sparse branch")
    filters: Optional[Dict[str, Any]] = Field(None, description="Metadata filters to apply")
    fusion_strategy: str = Field("RRF", description="Fusion algorithm identifier (e.g., RRF, RELATIVE_SCORE)")
    rrf_k: int = Field(60, description="RRF smoothing constant k")
    enable_dense: bool = Field(True, description="Whether dense retrieval branch is active")
    enable_sparse: bool = Field(True, description="Whether sparse retrieval branch is active")
    timeout: float = Field(10.0, description="Timeout in seconds")
    request_id: Optional[str] = Field(None, description="Correlation / request tracing ID")


class HybridRetrievalResponse(BaseModel):
    """Output payload from R7 Hybrid Retrieval, ready for R8 Reranking."""
    request_id: Optional[str] = Field(None, description="Correlation / request tracing ID")
    query_text: str = Field(..., description="Original input query")
    status: HybridRetrievalStatus = Field(HybridRetrievalStatus.SUCCESS, description="Execution status")
    candidates: List[HybridCandidate] = Field(default_factory=list, description="Fused, ranked hybrid candidates")
    total_dense_candidates: int = Field(0, description="Total candidates returned by dense branch")
    total_sparse_candidates: int = Field(0, description="Total candidates returned by sparse branch")
    total_fused_candidates: int = Field(0, description="Total unique candidates after fusion")
    fusion_strategy_used: str = Field("RRF", description="Fusion algorithm used")
    processing_time_ms: float = Field(0.0, description="Latency in milliseconds")
    warnings: List[str] = Field(default_factory=list, description="Partial failure or operational warnings")
    error_message: Optional[str] = Field(None, description="Error details if status is FAILED")
