"""Comprehensive Integration and Deployment Tests for R5 — Vector Database / Qdrant Deployment."""

import uuid
import pytest
from typing import Dict, Any

from core.config.settings import QdrantConfig
from core.errors.exceptions import (
    CollectionOperationError,
    IndexDimensionMismatchError,
    IndexProviderUnavailableError,
    InvalidIndexRecordError,
    QdrantAdapterError,
)
from core.interfaces.index import IKnowledgeIndexAdapter
from core.schemas.embedding import SparseVector
from modules.knowledge_base.enums import (
    IndexStatus,
    KnowledgeContentType,
    KnowledgeLifecycleState,
)
from modules.knowledge_base.embedding.record import EmbeddingRecord
from modules.knowledge_base.index.collection_strategy import KnowledgeCollectionMapper
from modules.knowledge_base.index.engine import KnowledgeIndexEngine
from modules.knowledge_base.index.qdrant_adapter import QdrantIndexAdapter, _to_qdrant_point_id
from modules.knowledge_base.index.record import IndexRecord, IndexBatchResult


# ==============================================================================
# 1. QDRANT ADAPTER LIFECYCLE TESTS (IN-MEMORY)
# ==============================================================================

def test_qdrant_adapter_initialization_and_health():
    config = QdrantConfig(location=":memory:")
    adapter = QdrantIndexAdapter(config=config)

    assert isinstance(adapter, IKnowledgeIndexAdapter)
    assert adapter.is_available() is True
    assert adapter.health_check() is True


def test_qdrant_adapter_point_id_conversion():
    # UUID v4 string
    valid_uuid = str(uuid.uuid4())
    assert _to_qdrant_point_id(valid_uuid) == valid_uuid

    # Arbitrary record ID
    record_id = "chk_wheat_rust_001"
    uuid5_str = _to_qdrant_point_id(record_id)
    assert isinstance(uuid.UUID(uuid5_str), uuid.UUID)
    # Idempotent conversion
    assert _to_qdrant_point_id(record_id) == uuid5_str


def test_qdrant_adapter_collection_creation_and_existence():
    config = QdrantConfig(location=":memory:", distance_metric="COSINE")
    adapter = QdrantIndexAdapter(config=config)

    col = "earthmind_crops"
    assert adapter.ensure_collection_exists(col, dense_dim=384) is True
    # Re-calling ensure_collection_exists on existing collection
    assert adapter.ensure_collection_exists(col, dense_dim=384) is True


def test_qdrant_adapter_dimension_mismatch_error():
    config = QdrantConfig(location=":memory:")
    adapter = QdrantIndexAdapter(config=config)

    col = "dim_test_col"
    adapter.ensure_collection_exists(col, dense_dim=384)

    # Check that ensuring existence with mismatched dimension raises IndexDimensionMismatchError
    with pytest.raises(IndexDimensionMismatchError) as exc_info:
        adapter.ensure_collection_exists(col, dense_dim=768)

    assert "384" in str(exc_info.value) or "768" in str(exc_info.value)


# ==============================================================================
# 2. R4 EMBEDDING -> R5 INDEX -> QDRANT PIPELINE TESTS
# ==============================================================================

def test_r4_to_r5_pipeline_execution():
    config = QdrantConfig(location=":memory:")
    adapter = QdrantIndexAdapter(config=config)
    engine = KnowledgeIndexEngine(adapter=adapter)

    # Simulated R4 EmbeddingRecord
    # Unit-normalized 4D vector for Cosine metric in Qdrant
    raw_vec = [0.12, 0.34, 0.56, 0.78]
    norm = sum(x**2 for x in raw_vec) ** 0.5
    unit_vec = [x / norm for x in raw_vec]

    r4_embedding = EmbeddingRecord(
        embedding_id="emb_r4_wheat_001",
        source_id="src_agri_doc_101",
        document_id="doc_wheat_guide",
        version_id="v2.0",
        chunk_id="chk_wheat_disease_p2",
        knowledge_unit_id="ku_wheat_disease_01",
        provider="self_hosted",
        model="paraphrase-multilingual-MiniLM-L12-v2",
        model_version="1.0.0",
        dimension=4,
        dense_vector=unit_vec,
        metadata={
            "crop": "Wheat",
            "region": "Punjab",
            "topic": "Disease Control",
            "season": "Rabi",
            "language": "en",
        },
    )

    # Build R5 IndexRecord from R4 EmbeddingRecord
    index_record = engine.build_index_record(
        dense_record=r4_embedding,
        knowledge_collection="PlantPathology",
    )

    assert index_record.index_record_id == "idx_chk_wheat_disease_p2"
    assert index_record.dense_dimension == 4
    assert index_record.dense_vector == unit_vec
    assert index_record.payload_metadata["crop"] == "Wheat"
    assert index_record.payload_metadata["source_id"] == "src_agri_doc_101"

    # Index into Qdrant via Engine
    indexed_res = engine.index_record(index_record)
    assert indexed_res.status == IndexStatus.INDEXED

    # Retrieve from Qdrant and verify provenance preservation
    retrieved = engine.get_record("idx_chk_wheat_disease_p2", logical_collection="PlantPathology")
    assert retrieved is not None
    assert retrieved.source_id == "src_agri_doc_101"
    assert retrieved.document_id == "doc_wheat_guide"
    assert retrieved.version_id == "v2.0"
    assert retrieved.chunk_id == "chk_wheat_disease_p2"
    assert retrieved.dense_vector == pytest.approx(unit_vec, abs=1e-3)
    assert retrieved.payload_metadata["crop"] == "Wheat"


def test_idempotent_upsert_and_update():
    config = QdrantConfig(location=":memory:")
    adapter = QdrantIndexAdapter(config=config)
    engine = KnowledgeIndexEngine(adapter=adapter)

    rec = IndexRecord(
        index_record_id="idx_idempotent_01",
        source_id="src_001",
        document_id="doc_001",
        version_id="v1.0",
        chunk_id="chk_001",
        dense_dimension=2,
        dense_vector=[0.5, 0.5],
        payload_metadata={"status": "initial"},
        knowledge_collection="SoilHealth",
    )

    # Initial upsert
    engine.index_record(rec)
    res1 = engine.get_record("idx_idempotent_01", logical_collection="SoilHealth")
    assert res1.payload_metadata["status"] == "initial"

    # Repeated upsert with updated payload
    updated_rec = rec.model_copy(update={"payload_metadata": {"status": "updated"}})
    engine.update_record(updated_rec)

    res2 = engine.get_record("idx_idempotent_01", logical_collection="SoilHealth")
    assert res2.payload_metadata["status"] == "updated"

    # Ensure total record count in Qdrant collection is still 1
    phys_col = engine.collection_mapper.get_physical_collection_name("SoilHealth")
    stats = adapter.get_status(phys_col)
    assert stats["record_count"] == 1


def test_batch_upsert_and_rebuild():
    config = QdrantConfig(location=":memory:")
    adapter = QdrantIndexAdapter(config=config)
    engine = KnowledgeIndexEngine(adapter=adapter)

    records = [
        IndexRecord(
            index_record_id=f"idx_batch_{i}",
            source_id="src_batch",
            document_id="doc_batch",
            version_id="v1.0",
            chunk_id=f"chk_batch_{i}",
            dense_dimension=3,
            dense_vector=[0.1 * i, 0.2 * i, 0.3 * i],
            payload_metadata={"idx": i},
            knowledge_collection="Irrigation",
        )
        for i in range(5)
    ]

    # Rebuild / Batch Index
    batch_res = engine.rebuild_index(records, logical_collection="Irrigation")
    assert batch_res.total_records == 5
    assert batch_res.status == IndexStatus.INDEXED
    assert len(batch_res.successful_records) == 5

    # Confirm all points exist
    for i in range(5):
        r = engine.get_record(f"idx_batch_{i}", logical_collection="Irrigation")
        assert r is not None
        assert r.payload_metadata["idx"] == i


def test_delete_and_lifecycle_retire():
    config = QdrantConfig(location=":memory:")
    adapter = QdrantIndexAdapter(config=config)
    engine = KnowledgeIndexEngine(adapter=adapter)

    rec = IndexRecord(
        index_record_id="idx_to_delete",
        source_id="src_001",
        document_id="doc_001",
        version_id="v1.0",
        chunk_id="chk_del",
        dense_dimension=2,
        dense_vector=[0.1, 0.9],
        knowledge_collection="GeneralAgri",
    )

    engine.index_record(rec)
    assert engine.get_record("idx_to_delete", logical_collection="GeneralAgri") is not None

    deleted = engine.delete_record("idx_to_delete", logical_collection="GeneralAgri")
    assert deleted is True
    assert engine.get_record("idx_to_delete", logical_collection="GeneralAgri") is None


# ==============================================================================
# 3. ARCHITECTURAL ISOLATION & SECURITY VERIFICATION
# ==============================================================================

def test_qdrant_sdk_non_leakage():
    """Verify that qdrant_client is only imported in qdrant_adapter.py within knowledge base module."""
    import sys
    import inspect
    import modules.knowledge_base.index.engine as engine_mod
    import modules.knowledge_base.index.record as record_mod
    import modules.knowledge_base.index.collection_strategy as strat_mod

    for mod in [engine_mod, record_mod, strat_mod]:
        src = inspect.getsource(mod)
        assert "qdrant_client" not in src, f"qdrant_client SDK leaked in module {mod.__name__}"
