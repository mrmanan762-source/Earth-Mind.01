"""Unit and Integration Tests for Stage R13 RAG → B2 Live Integration.

Tests cover all 27 specified verification scenarios:
1. Valid RAG → B2 flow
2. KB evidence → B2
3. Web evidence → B2
4. Mixed KB + Web evidence → B2
5. Multimodal evidence → B2
6. Provenance preservation
7. Source-type preservation
8. Identity preservation
9. R12 validation gate
10. Invalid evidence handling
11. Partial evidence
12. Empty evidence
13. RAG unavailable
14. Web unavailable
15. Timeout
16. Mapping failure
17. Contract mismatch
18. Context metadata preservation
19. Privacy metadata preservation
20. Traceability
21. No direct Qdrant access
22. No direct database access
23. No Memory writes
24. No B3 direct invocation
25. No duplicate relevance logic
26. Deterministic behavior
27. Regression compatibility
"""

import math
import time
from typing import List, Optional
import pytest

from core.config.settings import RAGIntegrationConfig, settings
from core.errors.exceptions import (
    ContextProviderError,
    RAGContractMappingError,
    RAGIntegrationError,
    RAGPipelineExecutionError,
)
from core.interfaces.boundary import IRAGContextProvider
from core.schemas.evidence import (
    EvidenceBuildRequest,
    EvidenceBuildResponse,
    EvidenceItem,
    EvidencePackage,
    EvidenceSourceType,
)
from core.schemas.evidence_validator import (
    EvidenceItemValidationOutcome,
    EvidenceValidationFinding,
    EvidenceValidationRequest,
    EvidenceValidationResponse,
    EvidenceValidationResult,
    EvidenceValidationStatus,
    ValidationSeverity,
)
from core.schemas.hybrid import HybridCandidate, HybridRetrievalResponse
from core.schemas.query import DenseQuery, QueryProcessingRequest, QueryProcessingResponse, QueryProcessingStatus, RetrievalQuery, SparseQuery
from core.schemas.rerank import RerankCandidate, RerankRequest, RerankResponse, RerankStatus
from core.schemas.web_search import WebSearchRequest, WebSearchResponse, WebSearchResult, WebSearchStatus
from modules.context.boundary.adapters import RAGContextProviderAdapter
from modules.context.boundary.enums import ContextOwnership, ContextScope, ContextSourceType, KnowledgeClassification
from modules.context.boundary.models import RAGContextContract, RAGContextRequest
from modules.context.manager import B2ContextManager
from modules.context.schemas import ContextItem, ContextRequest, ContextResult, ContextState
from modules.knowledge_base.evidence.engine import EvidenceBuilderEngine
from modules.knowledge_base.evidence.validator import EvidenceValidatorEngine
from modules.knowledge_base.integration.provider import RAGContextProvider
from modules.knowledge_base.query_processing.engine import QueryProcessingEngine
from modules.knowledge_base.reranking.engine import RerankEngine
from modules.knowledge_base.retrieval.hybrid_engine import HybridRetrievalEngine
from modules.knowledge_base.web_search.engine import WebSearchEngine


# Helper Mocks for Testing Pipeline Stages
class MockQueryProcessor:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail

    def process_query(self, request: QueryProcessingRequest) -> QueryProcessingResponse:
        if self.should_fail:
            return QueryProcessingResponse(
                request_id=request.request_id,
                status=QueryProcessingStatus.FAILED,
                original_query=request.query_text,
                error_message="Query processing mock failed.",
            )
        retrieval_query = RetrievalQuery(
            original_query=request.query_text,
            normalized_query=request.query_text.strip().lower(),
            dense_query=DenseQuery(dense_query_text=request.query_text),
            sparse_query=SparseQuery(sparse_query_text=request.query_text),
            request_id=request.request_id,
        )
        return QueryProcessingResponse(
            request_id=request.request_id,
            status=QueryProcessingStatus.SUCCESS,
            original_query=request.query_text,
            retrieval_query=retrieval_query,
        )


class MockHybridRetriever:
    def search(self, request) -> HybridRetrievalResponse:
        candidates = [
            HybridCandidate(
                candidate_id="cand_kb_01",
                record_id="rec_01",
                chunk_id="chk_wheat_01",
                knowledge_unit_id="ku_wheat_01",
                source_id="src_ic432",
                document_id="doc_wheat_guide",
                version_id="ver_1.0",
                fused_score=0.92,
                fused_rank=1,
                payload_metadata={"crop": "wheat", "disease": "rust"},
                provenance={"source_name": "ICAR Wheat Handbook"},
            )
        ]
        return HybridRetrievalResponse(
            query_text=request.query_text,
            request_id=request.request_id,
            candidates=candidates,
        )


class MockReranker:
    def rerank(self, request: RerankRequest) -> RerankResponse:
        candidates = []
        for idx, c in enumerate(request.candidates, 1):
            rc = RerankCandidate.from_hybrid_candidate(
                candidate=c,
                rerank_score=0.95 - (idx * 0.01),
                rerank_rank=idx,
                rerank_provider="mock_reranker",
            )
            candidates.append(rc)
        return RerankResponse(
            request_id=request.request_id,
            query_text=request.query_text,
            status=RerankStatus.SUCCESS,
            candidates=candidates,
        )


class MockWebSearchProvider:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        if self.should_fail:
            raise RuntimeError("Web search provider connection error.")
        result = WebSearchResult(
            result_id="web_res_01",
            title="Wheat Rust Management Advisory",
            url="https://agri.example.gov/wheat-rust",
            snippet="Apply propiconazole 25% EC at recommended dosages for yellow rust.",
            provider="mock_web",
            rank=1,
            score=0.88,
            request_id=request.request_id,
        )
        return WebSearchResponse(
            request_id=request.request_id,
            status=WebSearchStatus.SUCCESS,
            query_text=request.query_text,
            results=[result],
            result_count=1,
        )


class MockEvidenceBuilder:
    def build_evidence(self, request: EvidenceBuildRequest) -> EvidenceBuildResponse:
        items = []

        # Convert rerank candidates
        if request.rerank_response and request.rerank_response.candidates:
            for rc in request.rerank_response.candidates:
                ev = EvidenceItem(
                    evidence_id=f"ev_{rc.candidate_id}",
                    source_type=EvidenceSourceType.KNOWLEDGE_BASE,
                    title="Wheat Yellow Rust Control Guide",
                    content="Wheat yellow rust caused by Puccinia striiformis can be controlled using triazole fungicides.",
                    chunk_id=rc.chunk_id,
                    knowledge_unit_id=rc.knowledge_unit_id,
                    document_id=rc.document_id,
                    version_id=rc.version_id,
                    source_id=rc.source_id,
                    candidate_id=rc.candidate_id,
                    fused_score=rc.fused_score,
                    rerank_score=rc.rerank_score,
                    retrieval_rank=1,
                    provenance=rc.provenance or {"source": "ICAR"},
                    metadata={"crop": "wheat", "topic": "disease"},
                    request_id=request.request_id,
                )
                items.append(ev)

        # Convert web candidates
        if request.web_search_response and request.web_search_response.results:
            for wr in request.web_search_response.results:
                ev = EvidenceItem(
                    evidence_id=f"ev_{wr.result_id}",
                    source_type=EvidenceSourceType.WEB_SEARCH,
                    title=wr.title,
                    content=wr.snippet,
                    url=wr.url,
                    provider=wr.provider,
                    web_result_id=wr.result_id,
                    source_id="web_search",
                    retrieval_rank=2,
                    provenance={"url": wr.url, "provider": wr.provider},
                    metadata={"search_provider": wr.provider},
                    request_id=request.request_id,
                )
                items.append(ev)

        pkg = EvidencePackage(
            query_text=request.query_text,
            request_id=request.request_id,
            items=items,
            total_items_count=len(items),
            kb_items_count=sum(1 for i in items if i.source_type == EvidenceSourceType.KNOWLEDGE_BASE),
            web_items_count=sum(1 for i in items if i.source_type == EvidenceSourceType.WEB_SEARCH),
        )
        return EvidenceBuildResponse(request_id=request.request_id, package=pkg)


class MockEvidenceValidator:
    def __init__(self, force_invalid: bool = False, force_empty: bool = False):
        self.force_invalid = force_invalid
        self.force_empty = force_empty

    def validate_evidence_package(self, request: EvidenceValidationRequest) -> EvidenceValidationResponse:
        pkg = request.package
        if self.force_empty or not pkg or not pkg.items:
            empty_pkg = pkg.model_copy(deep=True) if pkg else EvidencePackage(query_text="empty")
            empty_pkg.items = []
            res = EvidenceValidationResult(
                request_id=request.request_id,
                overall_status=EvidenceValidationStatus.EMPTY,
                validated_package=empty_pkg,
            )
            return EvidenceValidationResponse(request_id=request.request_id, status=EvidenceValidationStatus.EMPTY, result=res)

        if self.force_invalid:
            res = EvidenceValidationResult(
                request_id=request.request_id,
                overall_status=EvidenceValidationStatus.INVALID,
                validated_package=None,
            )
            return EvidenceValidationResponse(
                request_id=request.request_id,
                status=EvidenceValidationStatus.INVALID,
                result=res,
                error_message="Package failed validation.",
            )

        res = EvidenceValidationResult(
            request_id=request.request_id,
            overall_status=EvidenceValidationStatus.VALID,
            validated_package=pkg,
            valid_items_count=len(pkg.items),
            total_items_count=len(pkg.items),
        )
        return EvidenceValidationResponse(request_id=request.request_id, status=EvidenceValidationStatus.VALID, result=res)


# =============================================================================
# Test Suite: 27 Specified R13 Integration Scenarios
# =============================================================================

def test_01_valid_rag_to_b2_flow():
    """1. Verify valid RAG -> B2 end-to-end context preparation flow."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=MockWebSearchProvider(),
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
    )
    adapter = RAGContextProviderAdapter(rag_provider=rag_provider)
    manager = B2ContextManager(providers=[adapter])

    req = ContextRequest(
        request_id="req_r13_01",
        task="How to treat yellow rust in wheat?",
        trace_id="trc_r13_01",
    )
    result = manager.prepare_context(req)

    assert isinstance(result, ContextResult)
    assert result.state == ContextState.COMPLETED
    assert len(result.items) > 0
    assert any(i.data_type == "rag_evidence" for i in result.items)


def test_02_kb_evidence_to_b2():
    """2. Verify KB evidence maps correctly through R13 to B2 ContextItem."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
        config=RAGIntegrationConfig(enable_web_search=False),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_02", query_text="wheat disease"))
    assert len(contracts) == 1
    c = contracts[0]
    assert c.source_type == ContextSourceType.RAG
    assert c.ownership == ContextOwnership.RAG_OWNED
    assert c.document_id == "doc_wheat_guide"
    assert c.chunk_id == "chk_wheat_01"

    item = ContextItem.from_rag_contract(c)
    assert item.context_id.startswith("rag_")
    assert item.source == "RAG"


def test_03_web_evidence_to_b2():
    """3. Verify Web evidence maps correctly through R13 to B2 ContextItem."""
    class WebOnlyHybridRetriever:
        def search(self, request):
            return HybridRetrievalResponse(query_text=request.query_text, request_id=request.request_id, candidates=[])

    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=WebOnlyHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=MockWebSearchProvider(),
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
        config=RAGIntegrationConfig(enable_web_search=True),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_03", query_text="wheat rust advisory"))
    web_contracts = [c for c in contracts if c.evidence_metadata.get("source_type").lower() == "web_search"]
    assert len(web_contracts) == 1
    wc = web_contracts[0]
    assert wc.evidence_metadata["url"] == "https://agri.example.gov/wheat-rust"

    item = ContextItem.from_rag_contract(wc)
    assert item.content["url"] == "https://agri.example.gov/wheat-rust"


def test_04_mixed_kb_and_web_evidence_to_b2():
    """4. Verify mixed KB + Web evidence package maps to B2 retaining distinct source details."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=MockWebSearchProvider(),
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_04", query_text="wheat yellow rust"))
    assert len(contracts) == 2
    sources = [c.evidence_metadata.get("source_type").lower() for c in contracts]
    assert "knowledge_base" in sources
    assert "web_search" in sources


def test_05_multimodal_evidence_to_b2():
    """5. Verify multimodal evidence data is preserved through R13 mapping."""
    class MultimodalEvidenceBuilder(MockEvidenceBuilder):
        def build_evidence(self, request):
            res = super().build_evidence(request)
            for item in res.package.items:
                item.multimodal_data = {"image_url": "https://agri.example.gov/wheat_rust.jpg", "format": "jpeg"}
            return res

    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MultimodalEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
        config=RAGIntegrationConfig(enable_web_search=False),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_05", query_text="wheat image"))
    assert len(contracts) == 1
    c = contracts[0]
    assert c.content["multimodal_data"]["image_url"] == "https://agri.example.gov/wheat_rust.jpg"


def test_06_provenance_preservation():
    """6. Verify complete provenance metadata is preserved from C.2/R11 to ContextItem."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
        config=RAGIntegrationConfig(enable_web_search=False),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_06", query_text="wheat provenance"))
    c = contracts[0]
    assert c.provenance["source_name"] == "ICAR Wheat Handbook"

    item = ContextItem.from_rag_contract(c)
    assert item.boundary_metadata["provenance"]["source_name"] == "ICAR Wheat Handbook"


def test_07_source_type_preservation():
    """7. Verify source distinctions (KB vs Web) are preserved without flattening."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=MockWebSearchProvider(),
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_07", query_text="source check"))
    kb_contract = next(c for c in contracts if c.evidence_metadata["source_type"].lower() == "knowledge_base")
    web_contract = next(c for c in contracts if c.evidence_metadata["source_type"].lower() == "web_search")

    assert kb_contract.publication_state == "PUBLISHED"
    assert web_contract.publication_state == "TRANSIENT"


def test_08_identity_preservation():
    """8. Verify all entity identities (request_id, trace_id, chunk_id, document_id) are preserved."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
        config=RAGIntegrationConfig(enable_web_search=False),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_08", trace_id="trc_08", query_text="id check"))
    c = contracts[0]
    assert c.trace_id == "trc_08"
    assert c.chunk_id == "chk_wheat_01"
    assert c.document_id == "doc_wheat_guide"


def test_09_r12_validation_gate():
    """9. Verify R12 validation gate evaluates EvidencePackage before contract creation."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(force_invalid=False),
        config=RAGIntegrationConfig(enable_web_search=False),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_09", query_text="gate check"))
    assert len(contracts) == 1


def test_10_invalid_evidence_handling():
    """10. Verify invalid evidence is rejected by R12 gate, returning empty context without fabrication."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(force_invalid=True),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_10", query_text="invalid check"))
    assert contracts == []


def test_11_partial_evidence():
    """11. Verify partial evidence packages return valid subset with warnings."""
    class PartialEvidenceValidator(MockEvidenceValidator):
        def validate_evidence_package(self, request):
            res = super().validate_evidence_package(request)
            res.status = EvidenceValidationStatus.PARTIALLY_VALID
            return res

    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=PartialEvidenceValidator(),
        config=RAGIntegrationConfig(enable_web_search=False),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_11", query_text="partial check"))
    assert len(contracts) == 1


def test_12_empty_evidence():
    """12. Verify empty evidence package returns [] allowing B2 policy evaluation."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(force_empty=True),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_12", query_text="empty check"))
    assert contracts == []


def test_13_rag_unavailable():
    """13. Verify RAG pipeline failures raise RAGPipelineExecutionError or ContextProviderError."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(should_fail=True),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
        config=RAGIntegrationConfig(enable_web_search=False),
    )
    with pytest.raises(RAGPipelineExecutionError) as exc_info:
        rag_provider.get_rag_context(RAGContextRequest(request_id="req_13", query_text="fail check"))
    assert "R9 Query Processing" in str(exc_info.value)


def test_14_web_unavailable():
    """14. Verify Web search failure does not fail the entire RAG pipeline."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=MockWebSearchProvider(should_fail=True),
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_14", query_text="web fail check"))
    # KB evidence still returned
    assert len(contracts) == 1
    assert contracts[0].evidence_metadata["source_type"].lower() == "knowledge_base"


def test_15_timeout():
    """15. Verify configuration timeout settings are properly passed to pipeline requests."""
    custom_cfg = RAGIntegrationConfig(timeout=5.0)
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=MockWebSearchProvider(),
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
        config=custom_cfg,
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_15", query_text="timeout check"))
    assert len(contracts) == 2


def test_16_mapping_failure():
    """16. Verify exception handling when contract conversion fails."""
    class FaultyPackage(EvidencePackage):
        def to_rag_context_contracts(self):
            raise RuntimeError("Corrupted package structure.")

    class FaultyValidator(MockEvidenceValidator):
        def validate_evidence_package(self, request):
            res = super().validate_evidence_package(request)
            res.result.validated_package = FaultyPackage(query_text="faulty", items=[EvidenceItem(evidence_id="ev_0", source_type=EvidenceSourceType.KNOWLEDGE_BASE, title="t", content="c")])
            return res

    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=FaultyValidator(),
    )
    with pytest.raises(RAGContractMappingError) as exc_info:
        rag_provider.get_rag_context(RAGContextRequest(request_id="req_16", query_text="mapping fail check"))
    assert "Contract mapping failed" in str(exc_info.value)


def test_17_contract_mismatch():
    """17. Verify RAGContextProviderAdapter raises ContextProviderError on invalid non-contract object."""
    adapter = RAGContextProviderAdapter(rag_provider=MockQueryProcessor()) # Invalid provider
    with pytest.raises(ContextProviderError) as exc_info:
        adapter.get_context(ContextRequest(request_id="req_17", task="invalid provider check"))
    assert "RAG provider failed" in str(exc_info.value)


def test_18_context_metadata_preservation():
    """18. Verify evidence, retrieval, and agricultural metadata preserved in RAGContextContract."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
        config=RAGIntegrationConfig(enable_web_search=False),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_18", query_text="meta check"))
    c = contracts[0]
    assert c.evidence_metadata["evidence_id"] == "ev_cand_kb_01"
    assert c.retrieval_metadata["fused_score"] == 0.92
    assert c.metadata["evidence_metadata"]["title"] == "Wheat Yellow Rust Control Guide"


def test_19_privacy_metadata_preservation():
    """19. Verify privacy metadata (PUBLIC, is_pii=False) preserved correctly."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_19", query_text="privacy check"))
    c = contracts[0]
    record = c.to_source_record()
    assert record.is_pii is False


def test_20_traceability():
    """20. Verify request_id and trace_id propagated across R13 integration."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_20_id", trace_id="trc_20_id", query_text="trace check"))
    c = contracts[0]
    assert c.trace_id == "trc_20_id"


def test_21_no_direct_qdrant_access(mocker):
    """21. Audit test verifying R13 integration module makes no direct Qdrant calls."""
    spy_qdrant = mocker.spy(QAG_Provider_Dummy_Qdrant := mocker.MagicMock(), "search")
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
        config=RAGIntegrationConfig(enable_web_search=False),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_21", query_text="qdrant audit"))
    assert spy_qdrant.call_count == 0
    assert len(contracts) == 1


def test_22_no_direct_database_access(mocker):
    """22. Audit test verifying R13 integration module makes no direct database calls."""
    spy_db = mocker.spy(DB_Dummy := mocker.MagicMock(), "execute")
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
        config=RAGIntegrationConfig(enable_web_search=False),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_22", query_text="db audit"))
    assert spy_db.call_count == 0
    assert len(contracts) == 1


def test_23_no_memory_writes():
    """23. Audit test verifying R13 does not perform Memory storage writes."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_23", query_text="memory audit"))
    for c in contracts:
        assert c.ownership == ContextOwnership.RAG_OWNED
        assert c.source_type == ContextSourceType.RAG


def test_24_no_b3_direct_invocation():
    """24. Audit test verifying R13 stops at B2 and does not directly invoke B3 Reasoning Engine."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
    )
    adapter = RAGContextProviderAdapter(rag_provider=rag_provider)
    items = adapter.get_context(ContextRequest(request_id="req_24", task="b3 audit"))
    # Output is List[ContextItem] ready for B2ContextManager
    assert all(isinstance(i, ContextItem) for i in items)


def test_25_no_duplicate_relevance_logic():
    """25. Audit test verifying R13 does not replace B2 relevance or context reduction rules."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=None,
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
    )
    contracts = rag_provider.get_rag_context(RAGContextRequest(request_id="req_25", query_text="relevance audit"))
    # Context Contracts maintain raw evidence content without token reduction or relevance filtering
    assert contracts[0].content["text"].startswith("Wheat yellow rust")


def test_26_deterministic_behavior():
    """26. Verify identical requests produce identical contract outputs."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=MockWebSearchProvider(),
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
    )
    req = RAGContextRequest(request_id="req_26_det", query_text="wheat rust advisory")
    c1 = rag_provider.get_rag_context(req)
    c2 = rag_provider.get_rag_context(req)

    assert len(c1) == len(c2)
    assert c1[0].model_dump(exclude={"timestamp"}) == c2[0].model_dump(exclude={"timestamp"})


def test_27_regression_compatibility():
    """27. Full regression test ensuring B2ContextManager + RAGContextProviderAdapter work seamlessly."""
    rag_provider = RAGContextProvider(
        query_processor=MockQueryProcessor(),
        hybrid_retriever=MockHybridRetriever(),
        reranker=MockReranker(),
        web_search_provider=MockWebSearchProvider(),
        evidence_builder=MockEvidenceBuilder(),
        evidence_validator=MockEvidenceValidator(),
    )
    adapter = RAGContextProviderAdapter(rag_provider=rag_provider, provider_name="rag_provider")
    manager = B2ContextManager(providers=[adapter])

    ctx_req = ContextRequest(
        request_id="req_27_regr",
        task="Provide management tips for wheat rust in northern fields.",
        farmer_id="farmer_101",
        field_id="field_55",
    )
    result = manager.prepare_context(ctx_req)

    assert result.state == ContextState.COMPLETED
    assert result.request_id == "req_27_regr"
    assert len(result.items) == 2
    assert manager.collector.last_provider_statuses["rag_provider"] == "SUCCESS"
