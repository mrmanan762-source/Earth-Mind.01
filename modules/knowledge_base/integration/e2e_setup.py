"""Real Knowledge Ingestion and Index Setup Helper for EarthMind Stage R14.

Loads the real agricultural knowledge corpus from `data/knowledge/raw/` using
CorpusIngestionEngine, generates real dense embeddings using SelfHostedEmbeddingProvider,
generates real sparse representations using BM25SparseProvider, and indexes all
IndexRecord objects into QdrantIndexAdapter and InvertedSparseIndexAdapter with complete
provenance, lineage, and metadata preservation.
"""

from typing import Any, Dict, List, Optional, NamedTuple
from pydantic import BaseModel, Field

from core.config.settings import QdrantConfig, settings
from core.interfaces.embedding import IEmbeddingProvider
from core.interfaces.sparse import ISparseRepresentationProvider
from core.schemas.embedding import EmbeddingRequest
from core.schemas.sparse import SparseRepresentationRequest
from modules.knowledge_base.canonical_models import Chunk
from modules.knowledge_base.embedding.self_hosted import SelfHostedEmbeddingProvider
from modules.knowledge_base.enums import IndexStatus, KnowledgeContentType, KnowledgeLifecycleState
from modules.knowledge_base.index.qdrant_adapter import QdrantIndexAdapter
from modules.knowledge_base.index.record import IndexRecord
from modules.knowledge_base.index.sparse_index import InvertedSparseIndexAdapter, ISparseIndexAdapter
from modules.knowledge_base.ingestion import CorpusIngestionEngine, IngestionPipelineSummary
from modules.knowledge_base.query_processing.metadata_extractor import AgriculturalMetadataExtractor
from modules.knowledge_base.sparse.bm25_provider import BM25SparseProvider


class RealIndexContainer(BaseModel):
    """Container holding initialized real index adapters, providers, and corpus summary."""
    dense_adapter: Any = Field(..., description="Initialized dense index adapter (QdrantIndexAdapter)")
    sparse_adapter: Any = Field(..., description="Initialized sparse index adapter (InvertedSparseIndexAdapter)")
    embedding_provider: Any = Field(..., description="Real dense embedding provider")
    sparse_provider: Any = Field(..., description="Real sparse representation provider")
    ingestion_summary: IngestionPipelineSummary = Field(..., description="Corpus ingestion report")
    total_indexed_records: int = Field(0, description="Total count of records indexed")
    collection_name: str = Field("earthmind_knowledge", description="Target collection name")

    model_config = {"arbitrary_types_allowed": True}


def ingest_and_index_real_corpus(
    collection_name: str = "earthmind_knowledge",
    qdrant_location: Optional[str] = ":memory:",
    batch_size: int = 32,
) -> RealIndexContainer:
    """
    Ingests the complete R3 real agricultural corpus and indexes all chunks into dense and sparse adapters.

    Returns:
        RealIndexContainer holding initialized adapters, providers, and metrics.
    """
    # 1. Ingest Real Agricultural Knowledge Corpus
    ingestion_engine = CorpusIngestionEngine()
    summary = ingestion_engine.ingest_corpus()
    chunks = ingestion_engine.get_ingested_chunks()

    if not chunks:
        raise RuntimeError("Real corpus ingestion produced zero chunks.")

    # 2. Instantiate Real Embedding & Sparse Providers
    embedding_provider = SelfHostedEmbeddingProvider(
        execution_mode="self_hosted",
        allow_download=False,
    )
    sparse_provider = BM25SparseProvider()

    chunk_texts = [c.content for c in chunks]

    # 3. Generate Real Dense Vectors
    emb_response = embedding_provider.embed(EmbeddingRequest(texts=chunk_texts))
    dense_vectors = [dv.vector for dv in emb_response.dense_vectors]

    # 4. Generate Real Sparse Representations
    sparse_response = sparse_provider.generate_sparse(SparseRepresentationRequest(texts=chunk_texts))
    sparse_vectors = sparse_response.sparse_vectors

    # 5. Build IndexRecords with Complete Lineage & Metadata
    ag_extractor = AgriculturalMetadataExtractor()
    index_records: List[IndexRecord] = []
    for idx, chunk in enumerate(chunks):
        dense_vec = dense_vectors[idx]
        sparse_vec = sparse_vectors[idx]

        # Extract payload metadata from chunk and canonical fields
        payload = dict(chunk.metadata or {})
        if chunk.provenance:
            payload.update(chunk.provenance.model_dump(exclude_none=True))

        source_id = getattr(chunk.provenance, "source_id", None) if chunk.provenance else None
        if not source_id:
            source_id = payload.get("source_id", f"src_{chunk.document_id}")

        # Extract agricultural metadata from chunk content to populate filterable metadata
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
        })

        record = IndexRecord(
            index_record_id=f"rec_{chunk.chunk_id}",
            source_id=source_id,
            document_id=chunk.document_id,
            version_id=chunk.version_id,
            section_id=chunk.parent_section_id,
            knowledge_unit_id=chunk.knowledge_unit_id,
            chunk_id=chunk.chunk_id,
            dense_provider="self_hosted",
            dense_model=embedding_provider.model_name_or_path,
            dense_model_version=embedding_provider.model_version,
            sparse_provider="bm25_sparse",
            sparse_model=sparse_provider.model_name,
            sparse_model_version=sparse_provider.model_version,
            dense_dimension=embedding_provider.dimension,
            dense_vector=dense_vec,
            sparse_vector=sparse_vec,
            payload_metadata=payload,
            knowledge_collection=collection_name,
            content_type=KnowledgeContentType.TEXT,
            lifecycle_state=KnowledgeLifecycleState.INDEXED,
            status=IndexStatus.INDEXED,
        )
        index_records.append(record)

    # 6. Initialize Dense Qdrant Index Adapter
    q_config = QdrantConfig(location=qdrant_location)
    dense_adapter = QdrantIndexAdapter(config=q_config)
    dense_adapter.ensure_collection_exists(
        collection_name=collection_name,
        dense_dim=embedding_provider.dimension,
    )
    dense_batch_res = dense_adapter.index_batch(collection_name=collection_name, records=index_records)

    # 7. Initialize Sparse Inverted Index Adapter
    sparse_adapter = InvertedSparseIndexAdapter()
    sparse_adapter.create_collection(collection_name=collection_name)
    sparse_batch_res = sparse_adapter.index_batch(collection_name=collection_name, records=index_records)

    indexed_count = len(dense_batch_res.successful_records)

    return RealIndexContainer(
        dense_adapter=dense_adapter,
        sparse_adapter=sparse_adapter,
        embedding_provider=embedding_provider,
        sparse_provider=sparse_provider,
        ingestion_summary=summary,
        total_indexed_records=indexed_count,
        collection_name=collection_name,
    )
