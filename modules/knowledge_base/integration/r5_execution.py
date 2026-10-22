"""R5 — Qdrant Indexing Execution Engine for EarthMind C.2 Knowledge Base.

Ingests canonical real corpus (53 chunks and 53 knowledge units), generates real 1024-dimensional
BAAI/bge-m3 dense embeddings for all 106 records, constructs searchable chunk-level IndexRecords
with stable IDs and complete source/agricultural metadata, indexes chunk records into Qdrant, and
runs a real dense retrieval smoke test for soil fertility and wheat cultivation.
"""

from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from core.config.settings import QdrantConfig, settings
from core.schemas.embedding import EmbeddingRequest
from modules.knowledge_base.canonical_models import Chunk, KnowledgeUnit
from modules.knowledge_base.embedding.pipeline import R4EmbeddingPipeline
from modules.knowledge_base.embedding.record import EmbeddingRecord
from modules.knowledge_base.embedding.repository import CanonicalEmbeddingRepository
from modules.knowledge_base.embedding.self_hosted import SelfHostedEmbeddingProvider
from modules.knowledge_base.enums import IndexStatus, KnowledgeContentType, KnowledgeLifecycleState
from modules.knowledge_base.index.engine import KnowledgeIndexEngine
from modules.knowledge_base.index.qdrant_adapter import QdrantIndexAdapter, _to_qdrant_point_id
from modules.knowledge_base.index.record import IndexRecord, IndexBatchResult
from modules.knowledge_base.ingestion import CorpusIngestionEngine, IngestionPipelineSummary
from modules.knowledge_base.query_processing.metadata_extractor import AgriculturalMetadataExtractor
from modules.knowledge_base.sparse.bm25_provider import BM25SparseProvider


class R5ExecutionResult(BaseModel):
    """Structured report of R5 Qdrant Indexing Execution."""

    status: str = Field("COMPLETED", description="Execution status ('COMPLETED', 'FAILED')")
    total_canonical_chunks: int = Field(53, description="Total canonical chunks ingested")
    total_canonical_units: int = Field(53, description="Total canonical knowledge units ingested")
    total_embedding_records: int = Field(106, description="Total BGE-M3 embedding records generated")
    embedding_dimension: int = Field(1024, description="Vector dimension")
    is_fallback_vector: bool = Field(False, description="Whether fallback vector generation was used")
    model_name: str = Field("BAAI/bge-m3", description="Embedding model identifier")
    total_indexed_chunks: int = Field(0, description="Total chunk IndexRecords indexed in Qdrant")
    skipped_records: int = Field(0, description="Records skipped during indexing")
    failed_records: int = Field(0, description="Records failed during indexing")
    collection_name: str = Field("earthmind_knowledge", description="Physical Qdrant collection name")
    distance_metric: str = Field("COSINE", description="Configured distance metric")
    smoke_test_query: str = Field(..., description="Smoke test query string")
    smoke_test_hits: List[Dict[str, Any]] = Field(default_factory=list, description="Top retrieval hits from smoke test")
    sparse_smoke_test_hits: List[Dict[str, Any]] = Field(default_factory=list, description="Top sparse retrieval hits from smoke test")

    model_config = {"arbitrary_types_allowed": True}


class R5QdrantIndexingEngine:
    """Orchestrates R5 real BGE-M3 embedding generation and Qdrant indexing."""

    def __init__(
        self,
        collection_name: str = "earthmind_knowledge",
        qdrant_location: Optional[str] = ":memory:",
        qdrant_config: Optional[QdrantConfig] = None,
    ):
        self.collection_name = collection_name
        if qdrant_config:
            self.qdrant_config = qdrant_config
        else:
            self.qdrant_config = QdrantConfig(
                location=qdrant_location,
                default_collection_name=collection_name,
                distance_metric="COSINE",
            )
        self.adapter = QdrantIndexAdapter(config=self.qdrant_config)
        self.index_engine = KnowledgeIndexEngine(adapter=self.adapter)

    def execute_pipeline(self) -> R5ExecutionResult:
        """Executes full R5 indexing pipeline using real 1024D BGE-M3 embeddings."""
        # 1. Ingest Canonical Corpus (53 chunks, 53 units)
        ingestion_engine = CorpusIngestionEngine()
        summary = ingestion_engine.ingest_corpus()
        chunks = ingestion_engine.get_ingested_chunks()
        units = ingestion_engine.get_ingested_knowledge_units()

        if not chunks:
            raise RuntimeError("Corpus ingestion produced zero chunks.")

        # 2. Instantiate Real BGE-M3 Embedding Provider (1024D)
        embedding_provider = SelfHostedEmbeddingProvider(
            provider_name="self_hosted",
            model_name_or_path="BAAI/bge-m3",
            model_version="1.0.0",
            dimension=1024,
            allow_download=True,
            execution_mode="self_hosted",
        )

        # Generate embeddings for 53 chunks and 53 knowledge units (106 total)
        chunk_texts = [str(c.content) for c in chunks]
        unit_texts = [str(u.content) for u in units]

        chunk_emb_resp = embedding_provider.embed(EmbeddingRequest(texts=chunk_texts))
        unit_emb_resp = embedding_provider.embed(EmbeddingRequest(texts=unit_texts))

        chunk_vectors = [dv.vector for dv in chunk_emb_resp.dense_vectors]
        unit_vectors = [dv.vector for dv in unit_emb_resp.dense_vectors]

        total_embeddings = len(chunk_vectors) + len(unit_vectors)
        is_fallback = embedding_provider.get_provider_metadata().extra.get("is_fallback_vector", False)

        # Validate numerical integrity of all generated vectors
        for vec in chunk_vectors + unit_vectors:
            assert len(vec) == 1024, f"Vector length mismatch: expected 1024, got {len(vec)}"
            assert all(isinstance(v, float) and not (v != v) for v in vec), "Vector contains NaN or non-float"

        # 3. Build Searchable Chunk-Level IndexRecords (53 chunks) with dual Dense + Sparse vectors
        ag_extractor = AgriculturalMetadataExtractor()
        sparse_provider = BM25SparseProvider()
        index_records: List[IndexRecord] = []

        for idx, chunk in enumerate(chunks):
            dense_vec = chunk_vectors[idx]
            sparse_vec = sparse_provider.generate_sparse_vector(str(chunk.content))

            payload = dict(chunk.metadata or {})
            if chunk.provenance:
                payload.update(chunk.provenance.model_dump(exclude_none=True))

            source_id = getattr(chunk.provenance, "source_id", None) if chunk.provenance else None
            if not source_id:
                source_id = payload.get("source_id", f"src_{chunk.document_id}")

            ag_meta = ag_extractor.extract(str(chunk.content))
            if ag_meta.crop and not payload.get("crop"):
                payload["crop"] = ag_meta.crop
            if ag_meta.disease_pest and not payload.get("disease_pest"):
                payload["disease_pest"] = ag_meta.disease_pest
            if ag_meta.soil_type and not payload.get("soil_type"):
                payload["soil_type"] = ag_meta.soil_type
            if ag_meta.region and not payload.get("region"):
                payload["region"] = ag_meta.region
            if ag_meta.season and not payload.get("season"):
                payload["season"] = ag_meta.season

            payload.update({
                "content": chunk.content,
                "text": chunk.content,
                "title": payload.get("document_title") or payload.get("title") or chunk.chunk_id,
                "source_id": source_id,
                "document_id": chunk.document_id,
                "version_id": chunk.version_id,
                "chunk_id": chunk.chunk_id,
                "knowledge_unit_id": chunk.knowledge_unit_id,
            })

            record = IndexRecord(
                index_record_id=f"idx_{chunk.chunk_id}",
                source_id=source_id,
                document_id=chunk.document_id,
                version_id=chunk.version_id,
                section_id=chunk.parent_section_id,
                knowledge_unit_id=chunk.knowledge_unit_id,
                chunk_id=chunk.chunk_id,
                dense_provider="self_hosted",
                dense_model="BAAI/bge-m3",
                dense_model_version="1.0.0",
                dense_dimension=1024,
                dense_vector=dense_vec,
                sparse_provider="bm25_sparse",
                sparse_model="earthmind-bm25-agri-v1",
                sparse_model_version="1.0.0",
                sparse_vector=sparse_vec,
                payload_metadata=payload,
                knowledge_collection=self.collection_name,
                content_type=KnowledgeContentType.TEXT,
                lifecycle_state=KnowledgeLifecycleState.INDEXED,
                status=IndexStatus.PENDING,
            )
            index_records.append(record)

        # 4. Confirm Collection Dimension & Upsert into Qdrant in Controlled Batches
        self.adapter.ensure_collection_exists(
            collection_name=self.collection_name,
            dense_dim=1024,
            config={"distance_metric": "COSINE"},
        )

        batch_result = self.index_engine.index_batch(records=index_records, logical_collection=self.collection_name)

        indexed_count = len(batch_result.successful_records)
        failed_count = len(batch_result.failed_records)

        # Verify collection status
        col_status = self.adapter.get_status(self.collection_name)
        assert col_status["record_count"] == indexed_count, f"Collection count mismatch: {col_status['record_count']} vs {indexed_count}"

        # 5. Real Retrieval Smoke Test
        smoke_query = "improving soil fertility before planting wheat"
        query_emb_resp = embedding_provider.embed(EmbeddingRequest(texts=[smoke_query]))
        query_vector = query_emb_resp.dense_vectors[0].vector

        search_hits = self.adapter.search_dense(
            collection_name=self.collection_name,
            query_vector=query_vector,
            top_k=5,
            with_record=True,
        )

        hit_reports = []
        for hit in search_hits:
            hit_payload = hit.payload or {}
            hit_reports.append({
                "record_id": hit.record_id,
                "score": round(hit.score, 4),
                "chunk_id": hit_payload.get("chunk_id"),
                "document_id": hit_payload.get("document_id"),
                "crop": hit_payload.get("crop"),
                "title": hit_payload.get("title"),
                "content_snippet": (hit_payload.get("content") or "")[:120] + "...",
            })

        # Real Sparse Retrieval Smoke Test
        sparse_query_vec = sparse_provider.generate_sparse_vector(smoke_query)
        sparse_search_hits = self.adapter.search_sparse(
            collection_name=self.collection_name,
            query_indices=sparse_query_vec.indices,
            query_values=sparse_query_vec.values,
            top_k=5,
            with_record=True,
        )

        sparse_hit_reports = []
        for hit in sparse_search_hits:
            hit_payload = hit.payload or {}
            sparse_hit_reports.append({
                "record_id": hit.record_id,
                "score": round(hit.score, 4),
                "chunk_id": hit_payload.get("chunk_id"),
                "document_id": hit_payload.get("document_id"),
                "crop": hit_payload.get("crop"),
                "title": hit_payload.get("title"),
                "content_snippet": (hit_payload.get("content") or "")[:120] + "...",
            })

        return R5ExecutionResult(
            status="COMPLETED" if failed_count == 0 else "COMPLETED_WITH_ERRORS",
            total_canonical_chunks=len(chunks),
            total_canonical_units=len(units),
            total_embedding_records=total_embeddings,
            embedding_dimension=1024,
            is_fallback_vector=is_fallback,
            model_name="BAAI/bge-m3",
            total_indexed_chunks=indexed_count,
            skipped_records=0,
            failed_records=failed_count,
            collection_name=self.collection_name,
            distance_metric="COSINE",
            smoke_test_query=smoke_query,
            smoke_test_hits=hit_reports,
            sparse_smoke_test_hits=sparse_hit_reports,
        )
