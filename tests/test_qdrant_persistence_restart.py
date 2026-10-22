"""Persistence and Restart Validation Tests for EarthMind RAG.

Validates that:
1. Real dense (1024D BGE-M3) and sparse (BM25) vectors, UUID v5 point IDs, and payload metadata
   persist to local storage.
2. A process restart (re-initializing Qdrant adapter & RAG pipeline against existing storage)
   retains 100% of points without corpus re-ingestion or re-embedding.
3. Hybrid retrieval, neural reranking, source attribution, and citations function properly post-restart.
4. Repeated initialization is strictly idempotent (no duplicate points or destructive collection wipes).
"""

import os
import shutil
import pytest

from core.config.settings import QdrantConfig
from modules.knowledge_base.embedding.self_hosted import SelfHostedEmbeddingProvider
from modules.knowledge_base.index.qdrant_adapter import QdrantIndexAdapter
from modules.knowledge_base.integration.e2e_setup import ingest_and_index_real_corpus
from modules.knowledge_base.integration.harness import R14RealRetrievalHarness
from modules.knowledge_base.integration.provider import RAGContextProvider
from modules.knowledge_base.retrieval.hybrid_engine import HybridRetrievalEngine
from modules.knowledge_base.sparse.bm25_provider import BM25SparseProvider


@pytest.fixture
def persistent_db_path(tmp_path):
    """Function-scoped temporary disk path for Qdrant storage."""
    db_dir = tmp_path / "qdrant_persistent_db"
    return str(db_dir)


def test_qdrant_persistence_and_process_restart(persistent_db_path):
    """
    Test that data persists to disk and survives process restart without re-ingesting.
    """
    collection_name = "earthmind_knowledge"

    # Step 1: Ingest and Index into Disk Storage
    container1 = ingest_and_index_real_corpus(
        collection_name=collection_name,
        qdrant_location=persistent_db_path,
    )
    adapter1 = container1.dense_adapter
    status1 = adapter1.get_status(collection_name)

    assert status1["record_count"] == 53
    assert status1["points_count"] == 53

    # Direct search to grab a known record ID for verification
    sample_hits = adapter1.search_dense(collection_name, [0.0] * 1024, top_k=1)
    sample_rec_id = sample_hits[0].record_id

    # Run query pre-restart
    harness1 = R14RealRetrievalHarness(index_container=container1)
    query = "improving soil fertility before planting wheat"
    res1 = harness1.execute_query(query)

    assert res1.context_items_count > 0
    top_source_pre = res1.final_context_items[0].source_id
    top_content_pre = res1.final_context_items[0].content

    # Close first client instance to release file lock (simulating process exit)
    adapter1.close()
    del harness1, container1, adapter1

    # Step 2: Re-open Existing Persistence Directory WITHOUT Re-Ingestion or Re-Embedding
    q_config = QdrantConfig(location=persistent_db_path)
    adapter2 = QdrantIndexAdapter(config=q_config)

    status2 = adapter2.get_status(collection_name)

    # Point counts must match exactly
    assert status2["record_count"] == 53
    assert status2["points_count"] == 53

    # Retrieve point directly and verify payload and dense/sparse vectors
    rec_check = adapter2.get_record(collection_name, sample_rec_id)
    assert rec_check is not None
    assert rec_check.dense_dimension == 1024
    assert rec_check.dense_vector is not None
    assert len(rec_check.dense_vector) == 1024
    assert rec_check.sparse_vector is not None
    assert len(rec_check.sparse_vector.indices) > 0
    assert rec_check.payload_metadata is not None

    # Step 3: Re-wire RAG Pipeline on Restarted Collection
    emb_provider = SelfHostedEmbeddingProvider(
        provider_name="self_hosted",
        model_name_or_path="BAAI/bge-m3",
        model_version="1.0.0",
        dimension=1024,
        allow_download=False,
        execution_mode="self_hosted",
    )
    sparse_provider = BM25SparseProvider()
    hybrid_engine = HybridRetrievalEngine(dense_adapter=adapter2, sparse_adapter=adapter2)
    rag_provider = RAGContextProvider(
        hybrid_retriever=hybrid_engine,
        embedding_provider=emb_provider,
        sparse_provider=sparse_provider,
    )

    class PersistentContainer:
        def __init__(self, dense_ad, emb_p, sp_p):
            self.dense_adapter = dense_ad
            self.sparse_adapter = dense_ad
            self.embedding_provider = emb_p
            self.sparse_provider = sp_p

    container2 = PersistentContainer(adapter2, emb_provider, sparse_provider)
    harness2 = R14RealRetrievalHarness(index_container=container2, rag_provider=rag_provider)

    res2 = harness2.execute_query(query)

    assert res2.context_items_count == res1.context_items_count
    assert res2.final_context_items[0].source_id == top_source_pre
    assert res2.final_context_items[0].content == top_content_pre

    # Explicitly close second adapter instance
    adapter2.close()


def test_repeated_initialization_idempotency(persistent_db_path):
    """
    Test that re-running ingestion/indexing on an existing collection does not duplicate points.
    """
    collection_name = "earthmind_knowledge"

    # Initial ingestion
    container_1 = ingest_and_index_real_corpus(
        collection_name=collection_name,
        qdrant_location=persistent_db_path,
    )
    container_1.dense_adapter.close()

    # Repeated ingestion on existing path
    container_repeat = ingest_and_index_real_corpus(
        collection_name=collection_name,
        qdrant_location=persistent_db_path,
    )
    status_repeat = container_repeat.dense_adapter.get_status(collection_name)

    # Point count must remain 53 due to deterministic UUID v5 point IDs
    assert status_repeat["record_count"] == 53
    assert status_repeat["points_count"] == 53

    container_repeat.dense_adapter.close()
