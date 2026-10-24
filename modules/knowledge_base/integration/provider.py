"""Stage R13 RAG Context Provider implementation for EarthMind.

Connects the completed RAG retrieval pipeline (R9 Query Processing -> R7 Hybrid Retrieval ->
R8 Reranking -> R10 Web Search -> R11 Evidence Builder -> R12 Evidence Validator) to B2
Context Manager via IRAGContextProvider protocol and RAGContextContract interface.

Enforces:
- R12 Validation Gate (filtering invalid or malformed evidence)
- Source-type and provenance preservation (Knowledge Base, Web Search, Multimodal)
- B2 context compatibility without performing agricultural reasoning or direct storage/Qdrant access
- Traceability (request_id, correlation_id, trace_id, evidence_id)
- Zero memory writes or direct reasoning engine invocations
- Structured telemetry and observability instrumentation
"""

import time
from typing import Any, Dict, List, Optional

from core.config.settings import RAGIntegrationConfig, settings
from core.errors.exceptions import (
    RAGContractMappingError,
    RAGIntegrationError,
    RAGPipelineExecutionError,
)
from core.interfaces.boundary import IRAGContextProvider
from core.interfaces.embedding import IEmbeddingProvider
from core.interfaces.evidence import IEvidenceBuilderEngine
from core.interfaces.evidence_validator import IEvidenceValidatorEngine
from core.interfaces.query_processor import IQueryProcessorEngine
from core.interfaces.sparse import ISparseRepresentationProvider
from core.interfaces.web_search import IWebSearchProvider
from core.logging.logger import get_logger
from core.observability.metrics import metrics_collector
from core.schemas.embedding import EmbeddingRequest
from core.schemas.evidence import EvidenceBuildRequest, EvidenceBuildResponse, EvidencePackage
from core.schemas.evidence_validator import (
    EvidenceValidationRequest,
    EvidenceValidationResponse,
    EvidenceValidationStatus,
)
from core.schemas.query import QueryProcessingRequest, QueryProcessingStatus, RetrievalQuery
from core.schemas.rerank import RerankRequest, RerankResponse, RerankStatus
from core.schemas.sparse import SparseRepresentationRequest
from core.schemas.web_search import WebSearchRequest, WebSearchResponse, WebSearchStatus
from modules.context.boundary.models import RAGContextContract, RAGContextRequest
from modules.context.schemas import ContextRequest
from modules.knowledge_base.embedding.self_hosted import SelfHostedEmbeddingProvider
from modules.knowledge_base.evidence.engine import EvidenceBuilderEngine
from modules.knowledge_base.evidence.validator import EvidenceValidatorEngine
from modules.knowledge_base.query_processing.engine import QueryProcessingEngine
from modules.knowledge_base.reranking.engine import RerankEngine
from modules.knowledge_base.retrieval.hybrid_engine import HybridRetrievalEngine
from modules.knowledge_base.sparse.bm25_provider import BM25SparseProvider
from modules.knowledge_base.web_search.engine import WebSearchEngine

logger = get_logger("modules.knowledge_base.integration.provider")


class RAGContextProvider(IRAGContextProvider):
    """
    Production-grade Stage R13 RAG Context Provider.
    Implements IRAGContextProvider protocol to connect RAG retrieval pipeline to B2 Context Manager.
    """

    def __init__(
        self,
        query_processor: Optional[IQueryProcessorEngine] = None,
        hybrid_retriever: Optional[HybridRetrievalEngine] = None,
        reranker: Optional[Any] = None,
        web_search_provider: Optional[IWebSearchProvider] = None,
        evidence_builder: Optional[IEvidenceBuilderEngine] = None,
        evidence_validator: Optional[IEvidenceValidatorEngine] = None,
        embedding_provider: Optional[IEmbeddingProvider] = None,
        sparse_provider: Optional[ISparseRepresentationProvider] = None,
        config: Optional[RAGIntegrationConfig] = None,
        provider_name: Optional[str] = None,
    ):
        """
        Initialize RAGContextProvider with pipeline engines or default components.
        """
        self.config = config or settings.rag_integration
        self.provider_name = provider_name or self.config.provider_name

        self.query_processor = query_processor or QueryProcessingEngine()
        self.hybrid_retriever = hybrid_retriever or HybridRetrievalEngine()
        self.reranker = reranker or RerankEngine()
        self.web_search_provider = web_search_provider if web_search_provider is not None else WebSearchEngine()
        self.evidence_builder = evidence_builder or EvidenceBuilderEngine()
        self.evidence_validator = evidence_validator or EvidenceValidatorEngine()
        self.embedding_provider = embedding_provider or SelfHostedEmbeddingProvider(
            execution_mode="self_hosted", allow_download=False
        )
        self.sparse_provider = sparse_provider or BM25SparseProvider()

    def get_rag_context(self, request: Any) -> List[RAGContextContract]:
        """
        Retrieve validated RAG context contracts for B2 Context Manager.

        Args:
            request: Incoming RAGContextRequest, ContextRequest, or dictionary payload.

        Returns:
            List of validated RAGContextContract objects.
        """
        start_time = time.time()
        metrics_collector.record_request_start()

        # Parse request fields
        query_text, request_id, trace_id, max_results, user_context = self._parse_request(request)

        q_len = len(query_text) if query_text else 0
        logger.info(f"RAGContextProvider '{self.provider_name}' processing query (len={q_len}) for request_id={request_id}")

        if not query_text or not query_text.strip():
            logger.warning(f"Empty query text received in RAGContextProvider for request_id={request_id}")
            metrics_collector.record_request_completion(
                latency_ms=(time.time() - start_time) * 1000.0,
                status="CONTROLLED_ABSTENTION",
                citation_present=False,
                has_evidence=False,
            )
            return []

        try:
            # Step 1: Stage R9 Query Processing
            retrieval_query = self._execute_query_processing(query_text, request_id, user_context)

            # Step 2: Stage R7 Hybrid Retrieval
            hybrid_start = time.time()
            hybrid_response = self._execute_hybrid_retrieval(retrieval_query, max_results, request_id)
            hybrid_lat_ms = (time.time() - hybrid_start) * 1000.0

            fused_candidates_count = len(getattr(hybrid_response, "candidates", [])) if hybrid_response else 0
            is_hybrid_degraded = getattr(hybrid_response, "status", None) == "PARTIAL"
            metrics_collector.record_retrieval_stage(
                "hybrid",
                latency_ms=hybrid_lat_ms,
                candidate_count=fused_candidates_count,
                success=getattr(hybrid_response, "status", None) != "FAILED",
                degraded=is_hybrid_degraded,
            )

            # Step 3: Stage R8 Reranking
            rerank_start = time.time()
            rerank_response = self._execute_reranking(hybrid_response, max_results, request_id)
            rerank_lat_ms = (time.time() - rerank_start) * 1000.0

            rerank_candidates_count = len(getattr(rerank_response, "candidates", [])) if rerank_response else 0
            is_rerank_degraded = getattr(rerank_response, "fallback_used", False)
            metrics_collector.record_retrieval_stage(
                "rerank",
                latency_ms=rerank_lat_ms,
                candidate_count=rerank_candidates_count,
                success=getattr(rerank_response, "status", None) in (RerankStatus.SUCCESS, "SUCCESS"),
                degraded=is_rerank_degraded,
            )

            # Step 4: Stage R10 Web Search (Optional / Configurable)
            web_search_response = self._execute_web_search(retrieval_query, max_results, request_id)

            # Step 5: Stage R11 Evidence Builder
            assembly_start = time.time()
            evidence_package = self._execute_evidence_builder(
                query_text=query_text,
                request_id=request_id,
                rerank_response=rerank_response,
                web_search_response=web_search_response,
                max_results=max_results,
            )

            # Step 6: Stage R12 Evidence Validator Gate
            validated_contracts = self._execute_evidence_validator_gate(
                package=evidence_package,
                request_id=request_id,
                trace_id=trace_id,
            )
            assembly_lat_ms = (time.time() - assembly_start) * 1000.0

            evidence_items_count = len(getattr(evidence_package, "items", []))
            metrics_collector.record_evidence_context(
                assembly_latency_ms=assembly_lat_ms,
                evidence_count=evidence_items_count,
                context_count=len(validated_contracts),
            )

            has_citations = any(bool(c.citation) for c in validated_contracts if hasattr(c, "citation") and c.citation)

            # Determine request outcome status
            if not validated_contracts:
                final_status = "CONTROLLED_ABSTENTION"
            elif is_hybrid_degraded or is_rerank_degraded:
                final_status = "DEGRADED"
            else:
                final_status = "SUCCESS"

            total_exec_time_ms = (time.time() - start_time) * 1000.0
            metrics_collector.record_request_completion(
                latency_ms=total_exec_time_ms,
                status=final_status,
                citation_present=has_citations,
                has_evidence=len(validated_contracts) > 0,
            )

            logger.info(
                f"RAGContextProvider '{self.provider_name}' completed request_id={request_id} "
                f"returning {len(validated_contracts)} RAGContextContracts in {total_exec_time_ms:.2f}ms "
                f"(status={final_status})"
            )

            return validated_contracts

        except RAGIntegrationError:
            metrics_collector.record_request_completion(
                latency_ms=(time.time() - start_time) * 1000.0,
                status="FAILED",
                citation_present=False,
                has_evidence=False,
            )
            raise
        except Exception as e:
            metrics_collector.record_request_completion(
                latency_ms=(time.time() - start_time) * 1000.0,
                status="FAILED",
                citation_present=False,
                has_evidence=False,
            )
            msg = f"RAG integration pipeline failed for request_id={request_id}: {str(e)}"
            logger.error(msg)
            raise RAGPipelineExecutionError("pipeline", str(e), request_id=request_id) from e

    # -------------------------------------------------------------------------
    # Internal Pipeline Stage Helper Methods
    # -------------------------------------------------------------------------

    def _parse_request(self, request: Any) -> tuple[str, Optional[str], Optional[str], int, Optional[Dict[str, Any]]]:
        """Extract standardized query_text, request_id, trace_id, max_results, user_context."""
        query_text = ""
        request_id = None
        trace_id = None
        max_results = self.config.max_results
        user_context = None

        if isinstance(request, RAGContextRequest):
            query_text = request.query_text
            request_id = request.request_id
            trace_id = request.trace_id or request.request_id
            if request.maximum_result_count:
                max_results = request.maximum_result_count
            user_context = request.metadata
        elif isinstance(request, ContextRequest):
            query_text = request.task
            request_id = request.request_id
            trace_id = request.trace_id or request.request_id
            user_context = request.metadata
        elif isinstance(request, dict):
            query_text = request.get("query_text") or request.get("query") or request.get("task") or ""
            request_id = request.get("request_id")
            trace_id = request.get("trace_id") or request_id
            max_results = request.get("max_results") or request.get("maximum_result_count") or max_results
            user_context = request.get("user_context") or request.get("metadata")
        elif isinstance(request, str):
            query_text = request

        return query_text, request_id, trace_id, max_results, user_context

    def _execute_query_processing(
        self, query_text: str, request_id: Optional[str], user_context: Optional[Dict[str, Any]]
    ) -> RetrievalQuery:
        """Stage R9: Process raw input query into structured RetrievalQuery."""
        qp_request = QueryProcessingRequest(
            query_text=query_text,
            request_id=request_id,
            user_context=user_context or {},
        )
        qp_response = self.query_processor.process_query(qp_request)

        if qp_response.status == QueryProcessingStatus.FAILED or not qp_response.retrieval_query:
            err = qp_response.error_message or "Query processing produced no retrieval query."
            logger.error(f"Stage R9 Query Processing failed for request_id={request_id}: {err}")
            raise RAGPipelineExecutionError("R9 Query Processing", err, request_id=request_id)

        return qp_response.retrieval_query

    def _execute_hybrid_retrieval(
        self, retrieval_query: RetrievalQuery, max_results: int, request_id: Optional[str]
    ) -> Any:
        """Stage R7: Execute hybrid dense + sparse vector retrieval with channel timing."""
        if max_results:
            retrieval_query.top_k = max_results

        # Dense representation generation & metric tracking
        dense_start = time.time()
        dense_success = True
        q_text = retrieval_query.normalized_query or retrieval_query.original_query
        if retrieval_query.dense_query.dense_vector is None and self.embedding_provider and self.embedding_provider.is_available():
            try:
                emb_res = self.embedding_provider.embed(EmbeddingRequest(texts=[q_text]))
                if emb_res and emb_res.dense_vectors:
                    retrieval_query.dense_query.dense_vector = emb_res.dense_vectors[0].vector
            except Exception as e:
                dense_success = False
                logger.warning(f"Dense query embedding generation failed: {str(e)}")
                metrics_collector.record_dependency_event("embedding", operation_success=False)

        dense_lat_ms = (time.time() - dense_start) * 1000.0

        # Sparse representation generation & metric tracking
        sparse_start = time.time()
        sparse_success = True
        if (
            (retrieval_query.sparse_query.sparse_indices is None or retrieval_query.sparse_query.sparse_values is None)
            and self.sparse_provider
            and self.sparse_provider.is_available()
        ):
            try:
                sp_res = self.sparse_provider.generate_sparse(SparseRepresentationRequest(texts=[q_text]))
                if sp_res and sp_res.sparse_vectors:
                    retrieval_query.sparse_query.sparse_indices = sp_res.sparse_vectors[0].indices
                    retrieval_query.sparse_query.sparse_values = sp_res.sparse_vectors[0].values
            except Exception as e:
                sparse_success = False
                logger.warning(f"Sparse query representation generation failed: {str(e)}")
                metrics_collector.record_dependency_event("sparse", operation_success=False)

        sparse_lat_ms = (time.time() - sparse_start) * 1000.0

        hybrid_request = retrieval_query.to_hybrid_retrieval_request(timeout=self.config.timeout)
        if request_id:
            hybrid_request.request_id = request_id

        hybrid_response = self.hybrid_retriever.search(hybrid_request)

        # Record branch specific retrieval metrics
        dense_cand_count = getattr(hybrid_response, "total_dense_candidates", 0)
        sparse_cand_count = getattr(hybrid_response, "total_sparse_candidates", 0)

        metrics_collector.record_retrieval_stage("dense", dense_lat_ms, dense_cand_count, success=dense_success)
        metrics_collector.record_retrieval_stage("sparse", sparse_lat_ms, sparse_cand_count, success=sparse_success)

        # Fallback to search without hard filters if strict metadata filters produced 0 candidates
        if (not hybrid_response or not getattr(hybrid_response, "candidates", None)) and hybrid_request.filters:
            logger.info(f"Hybrid retrieval with filters {hybrid_request.filters} produced 0 candidates for request_id={request_id}. Retrying without hard filters.")
            hybrid_request_unfiltered = hybrid_request.model_copy(update={"filters": None})
            hybrid_response = self.hybrid_retriever.search(hybrid_request_unfiltered)

        return hybrid_response

    def _execute_reranking(
        self, hybrid_response: Any, max_results: int, request_id: Optional[str]
    ) -> Optional[RerankResponse]:
        """Stage R8: Rerank candidates produced by Stage R7."""
        if not hybrid_response or not getattr(hybrid_response, "candidates", None):
            return RerankResponse(
                request_id=request_id,
                query_text=getattr(hybrid_response, "query_text", ""),
                status=RerankStatus.SUCCESS,
                candidates=[],
            )

        rerank_request = RerankRequest.from_hybrid_response(
            response=hybrid_response,
            top_k=max_results,
            allow_fallback=True,
            timeout=self.config.timeout,
        )
        if request_id:
            rerank_request.request_id = request_id

        try:
            return self.reranker.rerank(rerank_request)
        except Exception as e:
            logger.warning(f"Reranker invocation failed for request_id={request_id}: {str(e)}")
            metrics_collector.record_dependency_event("reranker", operation_success=False)
            metrics_collector.set_degraded_status("reranker", True)
            raise

    def _execute_web_search(
        self, retrieval_query: RetrievalQuery, max_results: int, request_id: Optional[str]
    ) -> Optional[WebSearchResponse]:
        """Stage R10: Perform web search if enabled in configuration."""
        if not self.config.enable_web_search or not self.web_search_provider:
            return None

        ws_start = time.time()
        try:
            ws_request = WebSearchRequest.from_retrieval_query(
                retrieval_query=retrieval_query,
                max_results=max_results,
                timeout=self.config.timeout,
            )
            if request_id:
                ws_request.request_id = request_id

            res = self.web_search_provider.search(ws_request)
            metrics_collector.record_dependency_event("web_search", operation_success=True)
            return res
        except Exception as e:
            logger.warning(f"Stage R10 Web Search failed for request_id={request_id}: {str(e)}. Continuing without web evidence.")
            metrics_collector.record_dependency_event("web_search", operation_success=False)
            return WebSearchResponse(
                request_id=request_id,
                status=WebSearchStatus.PROVIDER_ERROR,
                query_text=retrieval_query.normalized_query or retrieval_query.original_query,
                error_message=str(e),
            )

    def _execute_evidence_builder(
        self,
        query_text: str,
        request_id: Optional[str],
        rerank_response: Optional[RerankResponse],
        web_search_response: Optional[WebSearchResponse],
        max_results: int,
    ) -> EvidencePackage:
        """Stage R11: Build EvidencePackage from reranked KB candidates and web search candidates."""
        eb_request = EvidenceBuildRequest(
            query_text=query_text,
            request_id=request_id,
            rerank_response=rerank_response,
            web_search_response=web_search_response,
            max_items=max_results,
            deduplicate=True,
        )

        eb_response = self.evidence_builder.build_evidence(eb_request)
        if not eb_response.package:
            logger.warning(f"Stage R11 Evidence Builder returned no package for request_id={request_id}")
            return EvidencePackage(
                query_text=query_text,
                request_id=request_id,
                items=[],
                total_items_count=0,
            )

        return eb_response.package

    def _execute_evidence_validator_gate(
        self,
        package: EvidencePackage,
        request_id: Optional[str],
        trace_id: Optional[str],
    ) -> List[RAGContextContract]:
        """
        Stage R12: Evidence Validator Gate.
        Validates EvidencePackage and maps valid items into RAGContextContracts.
        """
        val_request = EvidenceValidationRequest(
            package=package,
            request_id=request_id,
            strict_mode=self.config.strict_validation,
        )

        val_response = self.evidence_validator.validate_evidence_package(val_request)

        if not val_response.result or not val_response.result.validated_package:
            logger.warning(f"Stage R12 Evidence Validator gate returned no package for request_id={request_id}")
            return []

        # Check overall validation status
        if val_response.status in (EvidenceValidationStatus.INVALID, EvidenceValidationStatus.MALFORMED):
            logger.warning(
                f"Stage R12 Evidence Validator gate rejected package for request_id={request_id} "
                f"with status '{val_response.status}'"
            )
            return []

        sanitized_pkg = val_response.result.validated_package
        if not sanitized_pkg.items:
            return []

        try:
            contracts = sanitized_pkg.to_rag_context_contracts()
            # Ensure trace_id preservation across all contracts
            for contract in contracts:
                if trace_id:
                    contract.trace_id = trace_id
                elif request_id:
                    contract.trace_id = request_id
            return contracts
        except Exception as e:
            logger.error(f"Failed to convert EvidencePackage to RAGContextContracts: {str(e)}")
            raise RAGContractMappingError(f"Contract mapping failed: {str(e)}", request_id=request_id) from e
