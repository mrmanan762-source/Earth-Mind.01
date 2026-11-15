"""KnowledgeBaseModule — application lifecycle wiring for the EarthMind RAG system.

Owns the RAG retrieval stack (embedding, sparse representation, dense/sparse index
adapters, hybrid retriever, reranker, evidence builder/validator, and the R13
RAGContextProvider) and exposes it to the application through the module lifecycle
and through the B2 Context Manager boundary.

The module deliberately does NOT perform agricultural reasoning or orchestration:
it only prepares validated, traceable evidence for B2, in line with the Phase 2
architectural boundary (RAG prepares evidence; B2/B3/B4/B5 reason over it).
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config.settings import QdrantConfig, RAGIntegrationConfig, settings
from core.errors.exceptions import EarthMindException, RAGIntegrationError
from core.interfaces.module import ModuleInterface
from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest, ApplicationResponse
from modules.knowledge_base.embedding.self_hosted import SelfHostedEmbeddingProvider
from modules.knowledge_base.index.qdrant_adapter import QdrantIndexAdapter
from modules.knowledge_base.index.sparse_index import InvertedSparseIndexAdapter
from modules.knowledge_base.integration.e2e_setup import build_index_records
from modules.knowledge_base.integration.provider import RAGContextProvider
from modules.knowledge_base.ingestion import CorpusIngestionEngine
from modules.knowledge_base.reranking.engine import RerankEngine
from modules.knowledge_base.retrieval.hybrid_engine import HybridRetrievalEngine
from modules.knowledge_base.sparse.bm25_provider import BM25SparseProvider

logger = get_logger("modules.knowledge_base.kb_module")

DEFAULT_COLLECTION = "earthmind_knowledge"


class KnowledgeBaseModule(ModuleInterface):
    """Module wrapping the RAG retrieval stack for application lifecycle integration."""

    module_name = "knowledge_base"

    def __init__(
        self,
        collection_name: Optional[str] = None,
        persist_dir: Optional[str] = None,
        qdrant_location: Optional[str] = None,
        allow_download: Optional[bool] = None,
        ingest_on_startup: Optional[bool] = None,
        enable_web_search: bool = False,
        context_module: Optional[Any] = None,
    ):
        self.collection_name = collection_name or settings.qdrant.default_collection_name or DEFAULT_COLLECTION
        self.persist_dir = persist_dir or os.getenv("EARTHMIND_KB_PERSIST_DIR")
        self.qdrant_location = qdrant_location if qdrant_location is not None else settings.qdrant.location
        self.allow_download = (
            allow_download
            if allow_download is not None
            else settings.embedding.allow_download
        )
        self.ingest_on_startup = (
            ingest_on_startup
            if ingest_on_startup is not None
            else os.getenv("EARTHMIND_KB_INGEST_ON_STARTUP", "false").lower() == "true"
        )
        self.enable_web_search = enable_web_search
        self._context_module = context_module

        self.embedding_provider: Optional[SelfHostedEmbeddingProvider] = None
        self.sparse_provider: Optional[BM25SparseProvider] = None
        self.dense_adapter: Optional[QdrantIndexAdapter] = None
        self.sparse_adapter: Optional[InvertedSparseIndexAdapter] = None
        self.hybrid_retriever: Optional[HybridRetrievalEngine] = None
        self.reranker: Optional[RerankEngine] = None
        self.rag_provider: Optional[RAGContextProvider] = None

        self._initialized = False
        self._ready = False
        self._readiness_reason = "NOT_INITIALIZED"
        self._indexed_records = 0

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------
    def _resolve_qdrant_config(self) -> QdrantConfig:
        """Resolve the effective Qdrant config, honouring a persistent store dir."""
        persist_dir = self.persist_dir
        env = (settings.environment or "development").lower()
        is_prod = env in ("production", "prod")

        # Operational-by-default: when no explicit Qdrant target is configured and we are
        # not in production, fall back to a durable local store so RAG actually works.
        if (
            not persist_dir
            and not is_prod
            and settings.qdrant.mode is None
            and not settings.qdrant.url
            and not settings.qdrant.location
        ):
            persist_dir = os.getenv("EARTHMIND_KB_PERSIST_DIR", os.path.join("data", "rag_store"))
            self.persist_dir = persist_dir

        if persist_dir:
            qdrant_path = Path(persist_dir) / "qdrant"
            qdrant_path.mkdir(parents=True, exist_ok=True)
            return QdrantConfig(
                mode="local_persistent",
                location=str(qdrant_path),
                default_collection_name=self.collection_name,
                distance_metric=settings.qdrant.distance_metric,
                timeout=settings.qdrant.timeout,
            )
        return QdrantConfig(
            mode=settings.qdrant.mode,
            url=settings.qdrant.url,
            host=settings.qdrant.host,
            port=settings.qdrant.port,
            grpc_port=settings.qdrant.grpc_port,
            api_key=settings.qdrant.api_key,
            location=self.qdrant_location,
            default_collection_name=self.collection_name,
            distance_metric=settings.qdrant.distance_metric,
            timeout=settings.qdrant.timeout,
            auto_create_collection=settings.qdrant.auto_create_collection,
        )

    def _resolve_sparse_index_path(self) -> Optional[str]:
        if self.persist_dir:
            return str(Path(self.persist_dir) / "sparse_index.json")
        return settings.sparse.index_path

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def initialize(self) -> None:
        if self._initialized:
            return
        logger.info(f"Initializing Knowledge Base (RAG) module for collection '{self.collection_name}'")

        try:
            self._build_stack()
            # Operational-by-default: in non-production environments an empty index is
            # populated from the canonical corpus so RAG can actually serve evidence.
            # Production never auto-ingests; it relies on the explicit ingestion path.
            env = (settings.environment or "development").lower()
            if self.ingest_on_startup or (env not in ("production", "prod") and self._index_is_empty()):
                try:
                    self.ingest_corpus()
                except Exception as ingest_exc:
                    logger.warning(f"Automatic corpus ingestion failed: {ingest_exc}")
            if self._context_module is not None and self.rag_provider is not None:
                self._context_module.register_rag_provider(self.rag_provider)
            self._initialized = True
        except Exception as exc:
            # Degrade gracefully: the module reports NOT ready instead of crashing the
            # application, and B2 will simply receive no RAG evidence.
            logger.error(f"Knowledge Base module initialization failed: {exc}")
            self._initialized = False
            self._ready = False
            self._readiness_reason = f"INIT_FAILED: {exc}"

        self._evaluate_readiness()
        logger.info(
            f"Knowledge Base module initialized. ready={self._ready} reason={self._readiness_reason} "
            f"indexed_records={self._indexed_records}"
        )

    def _index_is_empty(self) -> bool:
        """True when the dense collection currently holds no records."""
        try:
            status = self.dense_adapter.get_status(self.collection_name)
            return int(status.get("record_count", 0)) == 0
        except Exception:
            return True

    def _build_stack(self) -> None:
        """Construct the RAG provider stack (embedding, sparse, indexes, retriever, reranker)."""
        self.embedding_provider = SelfHostedEmbeddingProvider(
            provider_name=settings.embedding.provider,
            model_name_or_path=settings.embedding.model,
            model_version=settings.embedding.model_version,
            dimension=settings.embedding.dimension,
            device=settings.embedding.device,
            batch_size=settings.embedding.batch_size,
            max_length=settings.embedding.max_length,
            normalize_embeddings=settings.embedding.normalize,
            license=settings.embedding.license,
            provenance=settings.embedding.provenance or SelfHostedEmbeddingProvider.DEFAULT_PROVENANCE,
            execution_mode=settings.embedding.execution_mode,
            allow_download=self.allow_download,
        )
        self.sparse_provider = BM25SparseProvider()
        self.reranker = RerankEngine()

        qdrant_cfg = self._resolve_qdrant_config()
        self.dense_adapter = QdrantIndexAdapter(config=qdrant_cfg)
        self.dense_adapter.ensure_collection_exists(
            collection_name=self.collection_name,
            dense_dim=self.embedding_provider.dimension,
        )

        self.sparse_adapter = InvertedSparseIndexAdapter(
            persist_path=self._resolve_sparse_index_path()
        )

        self.hybrid_retriever = HybridRetrievalEngine(
            dense_adapter=self.dense_adapter,
            sparse_adapter=self.sparse_adapter,
        )

        self.rag_provider = RAGContextProvider(
            hybrid_retriever=self.hybrid_retriever,
            embedding_provider=self.embedding_provider,
            sparse_provider=self.sparse_provider,
            reranker=self.reranker,
            config=self._resolve_rag_config(),
        )

    def _resolve_rag_config(self) -> RAGIntegrationConfig:
        """Build a per-module RAG config so toggling web search never mutates the shared
        ``settings.rag_integration`` singleton (which other components rely on)."""
        base = settings.rag_integration
        return RAGIntegrationConfig(
            enable_web_search=self.enable_web_search,
            max_results=base.max_results,
            strict_validation=base.strict_validation,
            timeout=base.timeout,
            provider_name=base.provider_name,
        )

    def ingest_corpus(self) -> int:
        """Ingest and index the canonical agricultural corpus into dense + sparse stores."""
        if not (self.embedding_provider and self.sparse_provider and self.dense_adapter):
            raise RAGIntegrationError("Knowledge Base module must be initialized before ingestion.")

        from core.schemas.embedding import EmbeddingRequest
        from core.schemas.sparse import SparseRepresentationRequest

        ingestion_engine = CorpusIngestionEngine()
        ingestion_engine.ingest_corpus()
        chunks = ingestion_engine.get_ingested_chunks()
        if not chunks:
            raise RAGIntegrationError("Corpus ingestion produced zero chunks; cannot build the index.")

        texts = [c.content for c in chunks]
        dense_resp = self.embedding_provider.embed(EmbeddingRequest(texts=texts))
        sparse_resp = self.sparse_provider.generate_sparse(SparseRepresentationRequest(texts=texts))

        records = build_index_records(
            chunks=chunks,
            dense_vectors=[dv.vector for dv in dense_resp.dense_vectors],
            sparse_vectors=sparse_resp.sparse_vectors,
            embedding_provider=self.embedding_provider,
            sparse_provider=self.sparse_provider,
            collection_name=self.collection_name,
        )

        self.dense_adapter.ensure_collection_exists(
            collection_name=self.collection_name,
            dense_dim=self.embedding_provider.dimension,
        )
        self.dense_adapter.index_batch(collection_name=self.collection_name, records=records)

        self.sparse_adapter.create_collection(self.collection_name)
        self.sparse_adapter.index_batch(self.collection_name, records)

        self._indexed_records = len(records)
        self._evaluate_readiness()
        logger.info(f"Indexed {self._indexed_records} records into '{self.collection_name}'.")
        return self._indexed_records

    def _evaluate_readiness(self) -> None:
        """Determine honest readiness: RAG is ready only when its vector store holds records."""
        try:
            status = self.dense_adapter.get_status(self.collection_name)
            count = int(status.get("record_count", 0))
        except Exception as exc:  # pragma: no cover - defensive
            self._ready = False
            self._readiness_reason = f"VECTOR_STORE_ERROR: {exc}"
            return

        self._indexed_records = count
        if count > 0:
            self._ready = True
            self._readiness_reason = "READY"
        else:
            self._ready = False
            self._readiness_reason = "INDEX_EMPTY"

    @property
    def is_ready(self) -> bool:
        return self._ready

    def get_health(self) -> Dict[str, Any]:
        """Return a structured RAG health snapshot without claiming false readiness."""
        return {
            "module": self.module_name,
            "initialized": self._initialized,
            "ready": self._ready,
            "readiness_reason": self._readiness_reason,
            "collection_name": self.collection_name,
            "indexed_records": self._indexed_records,
            "embedding_model": getattr(self.embedding_provider, "model_name_or_path", None),
            "embedding_dimension": getattr(self.embedding_provider, "dimension", None),
            "web_search_enabled": self.enable_web_search,
        }

    # ------------------------------------------------------------------
    # Request handling
    # ------------------------------------------------------------------
    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        operation = (request.operation or "").lower()
        payload = request.payload if isinstance(request.payload, dict) else {}

        if operation not in ("rag_query", "retrieve", "retrieve_context"):
            return ApplicationResponse(
                request_id=request.request_id,
                status="UNSUPPORTED_OPERATION",
                response=None,
                warnings=[f"KnowledgeBaseModule does not handle operation '{request.operation}'."],
            )

        if not self._initialized or self.rag_provider is None:
            return ApplicationResponse(
                request_id=request.request_id,
                status="RAG_UNAVAILABLE",
                response=None,
                warnings=["RAG services are not initialized."],
            )

        query = payload.get("query") or payload.get("task") or payload.get("prompt")
        if not query:
            return ApplicationResponse(
                request_id=request.request_id,
                status="INVALID_REQUEST",
                response=None,
                warnings=["A non-empty 'query' is required for RAG retrieval."],
            )

        try:
            contracts = self.rag_provider.get_rag_context(
                {
                    "request_id": request.request_id,
                    "query_text": query,
                    "max_results": payload.get("max_results", settings.rag_integration.max_results),
                    "trace_id": request.metadata.get("trace_id"),
                }
            )
        except EarthMindException as exc:
            logger.error(f"RAG retrieval failed for request {request.request_id}: {exc}")
            return ApplicationResponse(
                request_id=request.request_id,
                status="RAG_ERROR",
                response=None,
                warnings=[str(exc)],
            )

        return ApplicationResponse(
            request_id=request.request_id,
            status="SUCCESS",
            response=[c.model_dump() if hasattr(c, "model_dump") else c for c in contracts],
            metadata={
                "contracts_count": len(contracts),
                "ready": self._ready,
                "readiness_reason": self._readiness_reason,
            },
        )

    def shutdown(self) -> None:
        logger.info("Shutting down Knowledge Base (RAG) module...")
        # Persist the sparse index and release the dense client so local storage
        # locks are freed and a restart can reopen the same durable store.
        if self.sparse_adapter is not None:
            try:
                self.sparse_adapter._persist()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"Failed to persist sparse index on shutdown: {exc}")
        if self.dense_adapter is not None:
            try:
                self.dense_adapter.close()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"Failed to close dense index adapter on shutdown: {exc}")
        self._initialized = False
        self._ready = False
        logger.info("Knowledge Base module shut down cleanly.")
