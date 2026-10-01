"""Data Contracts for EarthMind Stage R11 Evidence Builder.

Defines Pydantic models for:
- EvidenceSourceType: Category enum (KNOWLEDGE_BASE, WEB_SEARCH)
- EvidenceBuildStatus: Execution status enum (SUCCESS, PARTIAL, EMPTY, INVALID, FAILED, UNAVAILABLE)
- EvidenceItem: Unified traceable evidence item preserving upstream R8 reranked candidates and R10 web search results
- EvidencePackage: Normalized, provider-independent evidence container ready for B2 Context Manager
- EvidenceBuildRequest: Incoming request payload for evidence package construction
- EvidenceBuildResponse: Execution output payload containing constructed EvidencePackage
"""

from enum import Enum
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.schemas.rerank import RerankCandidate, RerankResponse
from core.schemas.web_search import WebSearchResult, WebSearchResponse

if TYPE_CHECKING:
    from modules.context.boundary.models import RAGContextContract


class EvidenceSourceType(str, Enum):
    """Source origin categories for R11 evidence items."""
    KNOWLEDGE_BASE = "KNOWLEDGE_BASE"
    WEB_SEARCH = "WEB_SEARCH"


class EvidenceBuildStatus(str, Enum):
    """Execution status for R11 Evidence Builder operation."""
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    EMPTY = "EMPTY"
    INVALID = "INVALID"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


class EvidenceItem(BaseModel):
    """
    Unified, traceable evidence item representation preserving upstream R8/R10 properties,
    scoring, ranking, C.2 lineage, and provenance without inventing data.
    """
    evidence_id: str = Field(
        default_factory=lambda: f"ev_{uuid.uuid4().hex[:12]}",
        description="Unique evidence item identifier"
    )
    source_type: EvidenceSourceType = Field(..., description="Origin source system category (KNOWLEDGE_BASE or WEB_SEARCH)")
    source_id: Optional[str] = Field(None, description="Source or publisher identifier")
    document_id: Optional[str] = Field(None, description="Document identifier for KB evidence")
    version_id: Optional[str] = Field(None, description="Document version identifier for KB evidence")
    section_id: Optional[str] = Field(None, description="Section identifier where available")
    knowledge_unit_id: Optional[str] = Field(None, description="Knowledge unit identifier for KB evidence")
    chunk_id: Optional[str] = Field(None, description="Canonical Chunk identifier for KB evidence")
    candidate_id: Optional[str] = Field(None, description="R8 candidate identifier where applicable")
    web_result_id: Optional[str] = Field(None, description="R10 web search result identifier where applicable")

    title: Optional[str] = Field(None, description="Document, page, or section title")
    content: str = Field(..., description="Content text excerpt or snippet")
    url: Optional[str] = Field(None, description="Canonical URL reference for web evidence or source location")
    provider: Optional[str] = Field(None, description="Provider identifier (e.g. reranker or search engine provider)")

    # Ranking information preserved from upstream stages
    retrieval_rank: Optional[int] = Field(None, description="Primary output rank in evidence list")
    dense_rank: Optional[int] = Field(None, description="1-based rank in R5 dense vector retrieval")
    sparse_rank: Optional[int] = Field(None, description="1-based rank in R6 sparse retrieval")
    fused_rank: Optional[int] = Field(None, description="1-based rank in R7 hybrid fusion")
    rerank_rank: Optional[int] = Field(None, description="1-based rank in R8 reranking")

    # Score information preserved from upstream stages
    dense_score: Optional[float] = Field(None, description="Dense retrieval score")
    sparse_score: Optional[float] = Field(None, description="Sparse retrieval score")
    fused_score: Optional[float] = Field(None, description="Hybrid fusion score")
    rerank_score: Optional[float] = Field(None, description="Reranker score")

    # Timestamps & Request identity
    publication_timestamp: Optional[str] = Field(None, description="Publication or last updated ISO timestamp string")
    retrieval_timestamp: float = Field(default_factory=time.time, description="Unix timestamp when evidence was retrieved")
    request_id: Optional[str] = Field(None, description="Correlation / request tracing ID")

    # Domain metadata, provenance, assessment & multimodal structures
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Domain metadata (e.g. crop, disease, region, state)")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Complete origin provenance chain")
    source_assessment: Optional[Dict[str, Any]] = Field(None, description="Source quality or reliability assessment signals")
    multimodal_data: Optional[Dict[str, Any]] = Field(None, description="Preserved multimodal references or structured objects")
    conflict_indicators: List[str] = Field(default_factory=list, description="Preserved conflict indicators or warnings")

    # Bounded truncation state
    is_truncated: bool = Field(False, description="Whether content was truncated to fit character limits")
    truncation_reason: Optional[str] = Field(None, description="Explanation if content was truncated")

    @classmethod
    def from_rerank_candidate(
        cls,
        candidate: RerankCandidate,
        request_id: Optional[str] = None,
        retrieval_rank: Optional[int] = None,
    ) -> "EvidenceItem":
        """Factory method to construct a KB EvidenceItem from an R8 RerankCandidate."""
        # Extract content text from record or metadata
        content_str = ""
        title_str = None
        multimodal_obj = None

        if candidate.record and getattr(candidate.record, "text", None):
            content_str = candidate.record.text
        elif "content" in candidate.payload_metadata:
            content_str = str(candidate.payload_metadata["content"])
        elif "snippet" in candidate.payload_metadata:
            content_str = str(candidate.payload_metadata["snippet"])
        elif "text" in candidate.payload_metadata:
            content_str = str(candidate.payload_metadata["text"])

        if candidate.record and getattr(candidate.record, "payload", None):
            title_str = candidate.record.payload.get("title") or candidate.payload_metadata.get("title")
            multimodal_obj = candidate.record.payload.get("multimodal_data") or candidate.payload_metadata.get("multimodal_data")
        else:
            title_str = candidate.payload_metadata.get("title")
            multimodal_obj = candidate.payload_metadata.get("multimodal_data")

        section_id_val = candidate.payload_metadata.get("section_id")
        if candidate.record and getattr(candidate.record, "payload", None) and not section_id_val:
            section_id_val = candidate.record.payload.get("section_id")

        source_assess = candidate.payload_metadata.get("source_assessment")
        conflicts = candidate.payload_metadata.get("conflict_indicators") or []

        # Convert provenance object to dict if present
        prov_dict: Dict[str, Any] = {}
        if isinstance(candidate.provenance, dict):
            prov_dict = dict(candidate.provenance)
        elif hasattr(candidate.provenance, "model_dump"):
            prov_dict = candidate.provenance.model_dump()
        elif candidate.record and getattr(candidate.record, "provenance", None):
            prov_dict = dict(candidate.record.provenance)

        return cls(
            evidence_id=f"ev_kb_{candidate.candidate_id}",
            source_type=EvidenceSourceType.KNOWLEDGE_BASE,
            source_id=candidate.source_id,
            document_id=candidate.document_id,
            version_id=candidate.version_id,
            section_id=section_id_val,
            knowledge_unit_id=candidate.knowledge_unit_id,
            chunk_id=candidate.chunk_id,
            candidate_id=candidate.candidate_id,
            title=title_str,
            content=content_str,
            provider=candidate.rerank_provider,
            retrieval_rank=retrieval_rank or candidate.rerank_rank or candidate.fused_rank,
            dense_rank=candidate.dense_rank,
            sparse_rank=candidate.sparse_rank,
            fused_rank=candidate.fused_rank,
            rerank_rank=candidate.rerank_rank,
            dense_score=candidate.dense_score,
            sparse_score=candidate.sparse_score,
            fused_score=candidate.fused_score,
            rerank_score=candidate.rerank_score,
            request_id=request_id,
            metadata=dict(candidate.payload_metadata),
            provenance=prov_dict,
            source_assessment=source_assess if isinstance(source_assess, dict) else None,
            multimodal_data=multimodal_obj if isinstance(multimodal_obj, dict) else None,
            conflict_indicators=list(conflicts),
        )

    @classmethod
    def from_web_search_result(
        cls,
        result: WebSearchResult,
        request_id: Optional[str] = None,
        retrieval_rank: Optional[int] = None,
    ) -> "EvidenceItem":
        """Factory method to construct a Web EvidenceItem from an R10 WebSearchResult."""
        content_str = result.content if result.content else result.snippet
        prov_dict = dict(result.provenance) if result.provenance else {
            "source_type": "WEB_SEARCH",
            "provider": result.provider,
            "url": result.url,
            "result_id": result.result_id,
            "retrieval_timestamp": result.retrieval_timestamp,
        }

        return cls(
            evidence_id=f"ev_web_{result.result_id}",
            source_type=EvidenceSourceType.WEB_SEARCH,
            source_id=result.source or result.provider,
            web_result_id=result.result_id,
            title=result.title,
            content=content_str,
            url=result.url,
            provider=result.provider,
            retrieval_rank=retrieval_rank or result.rank,
            rerank_score=result.score,
            publication_timestamp=result.publication_date or result.last_updated_date,
            retrieval_timestamp=result.retrieval_timestamp,
            request_id=request_id or result.request_id,
            metadata=dict(result.metadata),
            provenance=prov_dict,
        )


class EvidencePackage(BaseModel):
    """
    Structured, traceable, provider-independent Evidence Package produced by R11.
    Delivers evidence to B2 Context Manager without executing agricultural reasoning.
    """
    package_id: str = Field(
        default_factory=lambda: f"pkg_{uuid.uuid4().hex[:12]}",
        description="Unique evidence package identifier"
    )
    request_id: Optional[str] = Field(None, description="Correlation / request tracing ID")
    query_text: str = Field(..., description="Original input query string")
    status: EvidenceBuildStatus = Field(EvidenceBuildStatus.SUCCESS, description="Execution status")
    items: List[EvidenceItem] = Field(default_factory=list, description="Ordered evidence items")
    kb_items_count: int = Field(0, description="Count of Knowledge Base evidence items")
    web_items_count: int = Field(0, description="Count of Web Search evidence items")
    total_items_count: int = Field(0, description="Total count of evidence items")
    is_partial: bool = Field(False, description="True if one or more upstream retrieval sources failed or partial")
    warnings: List[str] = Field(default_factory=list, description="Warning messages during construction")
    errors: List[str] = Field(default_factory=list, description="Error messages from partial failures")
    execution_time_ms: float = Field(0.0, description="Construction latency in milliseconds")
    created_at: float = Field(default_factory=time.time, description="Unix timestamp of package creation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Package processing metadata")

    def to_rag_context_contracts(self) -> List["RAGContextContract"]:
        """
        Convert EvidencePackage items into B2 Context Manager compatible RAGContextContract objects.
        Enforces C.3 boundary standards and RAG_OWNED context ownership.
        """
        from modules.context.boundary.enums import ContextOwnership, ContextScope, ContextSourceType, KnowledgeClassification, PersistenceIntent
        from modules.context.boundary.models import RAGContextContract

        contracts: List[RAGContextContract] = []
        for item in self.items:
            classification = KnowledgeClassification.GENERAL_KNOWLEDGE

            contract = RAGContextContract(
                source_type=ContextSourceType.RAG,
                ownership=ContextOwnership.RAG_OWNED,
                classification=classification,
                scope=ContextScope.GLOBAL,
                persistence_intent=PersistenceIntent.TEMPORARY if item.source_type == EvidenceSourceType.WEB_SEARCH else PersistenceIntent.PERSISTENT,
                content={
                    "evidence_id": item.evidence_id,
                    "title": item.title,
                    "text": item.content,
                    "url": item.url,
                    "source_type": item.source_type.value,
                    "provider": item.provider,
                    "multimodal_data": item.multimodal_data,
                    "conflict_indicators": item.conflict_indicators,
                },
                document_id=item.document_id,
                document_version_id=item.version_id,
                knowledge_unit_id=item.knowledge_unit_id,
                chunk_id=item.chunk_id,
                publication_state="PUBLISHED" if item.source_type == EvidenceSourceType.KNOWLEDGE_BASE else "TRANSIENT",
                evidence_metadata={
                    "evidence_id": item.evidence_id,
                    "source_type": item.source_type.value,
                    "title": item.title,
                    "url": item.url,
                    "is_truncated": item.is_truncated,
                    "truncation_reason": item.truncation_reason,
                    "source_assessment": item.source_assessment,
                    "agricultural_metadata": item.metadata,
                },
                retrieval_metadata={
                    "retrieval_rank": item.retrieval_rank,
                    "dense_rank": item.dense_rank,
                    "sparse_rank": item.sparse_rank,
                    "fused_rank": item.fused_rank,
                    "rerank_rank": item.rerank_rank,
                    "dense_score": item.dense_score,
                    "sparse_score": item.sparse_score,
                    "fused_score": item.fused_score,
                    "rerank_score": item.rerank_score,
                    "provider": item.provider,
                },
                provenance=dict(item.provenance),
                trace_id=self.request_id,
                source_id=item.source_id or item.candidate_id or item.web_result_id,
                metadata={
                    **dict(item.metadata),
                    "evidence_metadata": {
                        "evidence_id": item.evidence_id,
                        "source_type": item.source_type.value,
                        "title": item.title,
                        "url": item.url,
                        "is_truncated": item.is_truncated,
                        "truncation_reason": item.truncation_reason,
                        "source_assessment": item.source_assessment,
                        "agricultural_metadata": item.metadata,
                    },
                    "retrieval_metadata": {
                        "retrieval_rank": item.retrieval_rank,
                        "dense_rank": item.dense_rank,
                        "sparse_rank": item.sparse_rank,
                        "fused_rank": item.fused_rank,
                        "rerank_rank": item.rerank_rank,
                        "dense_score": item.dense_score,
                        "sparse_score": item.sparse_score,
                        "fused_score": item.fused_score,
                        "rerank_score": item.rerank_score,
                        "provider": item.provider,
                    },
                    "provenance": dict(item.provenance),
                },
            )
            contracts.append(contract)
        return contracts


class EvidenceBuildRequest(BaseModel):
    """Incoming request for Stage R11 Evidence Builder Engine."""
    query_text: str = Field(..., description="Original input query string")
    request_id: Optional[str] = Field(None, description="Correlation / request tracing ID")
    rerank_response: Optional[RerankResponse] = Field(None, description="Stage R8 RerankResponse output payload")
    web_search_response: Optional[WebSearchResponse] = Field(None, description="Stage R10 WebSearchResponse output payload")
    max_items: Optional[int] = Field(None, description="Maximum total evidence items requested")
    max_content_length: Optional[int] = Field(None, description="Maximum character limit per evidence content string")
    deduplicate: bool = Field(True, description="Whether to perform conservative deduplication across sources")
    user_context: Optional[Dict[str, Any]] = Field(None, description="Upstream user context")


class EvidenceBuildResponse(BaseModel):
    """Output payload from Stage R11 Evidence Builder Engine."""
    request_id: Optional[str] = Field(None, description="Correlation / request tracing ID")
    status: EvidenceBuildStatus = Field(EvidenceBuildStatus.SUCCESS, description="Overall execution status")
    package: Optional[EvidencePackage] = Field(None, description="Constructed EvidencePackage container")
    warnings: List[str] = Field(default_factory=list, description="Construction warnings")
    error_message: Optional[str] = Field(None, description="Error details if status is FAILED")
    execution_time_ms: float = Field(0.0, description="Latency in milliseconds")
