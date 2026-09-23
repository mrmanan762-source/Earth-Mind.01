"""Comprehensive Unit Tests for C.2 Knowledge Base Index Layer & Qdrant Adapter."""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from core.config.settings import QdrantConfig
from core.errors.exceptions import (
    CollectionOperationError,
    IndexExecutionError,
    InvalidIndexRecordError,
    SparseVectorValidationError,
)
from core.interfaces.index import IKnowledgeIndexAdapter
from core.schemas.embedding import SparseVector
from modules.knowledge_base.enums import (
    IndexStatus,
    KnowledgeContentType,
    KnowledgeLifecycleState,
    QualityStatus,
    ReviewStatus,
)
from modules.knowledge_base.embedding.record import EmbeddingRecord
from modules.knowledge_base.sparse.record import SparseRepresentationRecord
from modules.knowledge_base.metadata import CanonicalMetadata
from modules.knowledge_base.provenance import Provenance
from modules.knowledge_base.index.record import IndexRecord, IndexBatchResult
from modules.knowledge_base.index.collection_strategy import KnowledgeCollectionMapper
from modules.knowledge_base.index.fake_adapter import FakeIndexAdapter
from modules.knowledge_base.index.engine import KnowledgeIndexEngine
from modules.knowledge_base.index.qdrant_adapter import QdrantIndexAdapter


# ==============================================================================
# 1. INDEX RECORD VALIDATION TESTS
# ==============================================================================

def test_index_record_dense_only():
    record = IndexRecord(
        index_record_id="idx_001",
        source_id="src_001",
        document_id="doc_001",
        version_id="ver_1.0",
        chunk_id="chk_001",
        dense_embedding_id="emb_001",
        dense_provider="fake",
        dense_model="test-model",
        dense_dimension=4,
        dense_vector=[0.1, 0.2, 0.3, 0.4],
    )
    assert record.index_record_id == "idx_001"
    assert record.dense_dimension == 4
    assert record.dense_vector == [0.1, 0.2, 0.3, 0.4]
    assert record.sparse_vector is None


def test_index_record_sparse_only():
    record = IndexRecord(
        index_record_id="idx_002",
        source_id="src_001",
        document_id="doc_001",
        version_id="ver_1.0",
        knowledge_unit_id="ku_001",
        sparse_representation_id="sp_001",
        sparse_provider="bm25",
        sparse_model="bm25-v1",
        sparse_vector=SparseVector(indices=[10, 20], values=[0.5, 0.8]),
    )
    assert record.index_record_id == "idx_002"
    assert record.dense_vector is None
    assert record.sparse_vector.indices == [10, 20]
    assert record.sparse_vector.values == [0.5, 0.8]


def test_index_record_dense_and_sparse():
    record = IndexRecord(
        index_record_id="idx_003",
        source_id="src_001",
        document_id="doc_001",
        version_id="ver_1.0",
        chunk_id="chk_001",
        knowledge_unit_id="ku_001",
        dense_vector=[0.1, 0.2],
        sparse_vector=SparseVector(indices=[1], values=[0.9]),
    )
    assert record.dense_dimension == 2
    assert record.dense_vector == [0.1, 0.2]
    assert record.sparse_vector.indices == [1]


def test_index_record_missing_canonical_references():
    with pytest.raises(InvalidIndexRecordError) as exc_info:
        IndexRecord(
            index_record_id="idx_004",
            source_id="src_001",
            document_id="doc_001",
            version_id="ver_1.0",
            # missing chunk_id AND knowledge_unit_id
            dense_vector=[0.1, 0.2],
        )
    assert "at least one of 'chunk_id' or 'knowledge_unit_id'" in str(exc_info.value)


def test_index_record_missing_vectors():
    with pytest.raises(InvalidIndexRecordError) as exc_info:
        IndexRecord(
            index_record_id="idx_005",
            source_id="src_001",
            document_id="doc_001",
            version_id="ver_1.0",
            chunk_id="chk_001",
            # missing both dense_vector and sparse_vector
        )
    assert "must contain at least a dense_vector or sparse_vector" in str(exc_info.value)


def test_index_record_dimension_mismatch():
    with pytest.raises(InvalidIndexRecordError) as exc_info:
        IndexRecord(
            index_record_id="idx_006",
            source_id="src_001",
            document_id="doc_001",
            version_id="ver_1.0",
            chunk_id="chk_001",
            dense_dimension=5,  # Explicit dim 5 vs vector length 2
            dense_vector=[0.1, 0.2],
        )
    assert "dimension mismatch" in str(exc_info.value)


def test_index_record_non_numeric_dense_vector():
    with pytest.raises((InvalidIndexRecordError, ValidationError)):
        IndexRecord(
            index_record_id="idx_007",
            source_id="src_001",
            document_id="doc_001",
            version_id="ver_1.0",
            chunk_id="chk_001",
            dense_vector=[0.1, "invalid_val"],  # type: ignore
        )


def test_index_record_invalid_sparse_vector():
    with pytest.raises(SparseVectorValidationError) as exc_info:
        IndexRecord(
            index_record_id="idx_008",
            source_id="src_001",
            document_id="doc_001",
            version_id="ver_1.0",
            chunk_id="chk_001",
            sparse_vector=SparseVector(indices=[1, 2], values=[0.5]),  # Length mismatch
        )
    assert "SparseVector index/value count mismatch" in str(exc_info.value)


# ==============================================================================
# 2. COLLECTION STRATEGY TESTS
# ==============================================================================

def test_collection_mapper_defaults():
    mapper = KnowledgeCollectionMapper()
    assert mapper.get_physical_collection_name() == "earthmind_knowledge"
    assert mapper.get_physical_collection_name("Crops") == "earthmind_knowledge"


def test_collection_mapper_explicit_and_prefix():
    mapper = KnowledgeCollectionMapper(default_physical_collection="default_kb", collection_prefix="kb_")
    mapper.register_mapping("Diseases", "physical_diseases_v1")

    assert mapper.get_physical_collection_name("Diseases") == "physical_diseases_v1"
    assert mapper.get_physical_collection_name("Soil") == "kb_soil"
    assert mapper.get_physical_collection_name(None) == "default_kb"


# ==============================================================================
# 3. KNOWLEDGE INDEX ENGINE TESTS
# ==============================================================================

def test_engine_build_index_record_from_dense_record():
    adapter = FakeIndexAdapter()
    engine = KnowledgeIndexEngine(adapter)

    dense_rec = EmbeddingRecord(
        embedding_id="emb_100",
        source_id="src_100",
        document_id="doc_100",
        version_id="v1.0",
        chunk_id="chk_100",
        provider="fake",
        model="fake-embed-v1",
        dimension=3,
        dense_vector=[0.1, 0.2, 0.3],
        metadata={"crop": "Wheat", "region": "Punjab"},
    )

    idx_rec = engine.build_index_record(
        dense_record=dense_rec,
        knowledge_collection="Crops",
    )

    assert idx_rec.index_record_id == "idx_chk_100"
    assert idx_rec.source_id == "src_100"
    assert idx_rec.chunk_id == "chk_100"
    assert idx_rec.dense_embedding_id == "emb_100"
    assert idx_rec.dense_vector == [0.1, 0.2, 0.3]
    assert idx_rec.payload_metadata["crop"] == "Wheat"
    assert idx_rec.payload_metadata["region"] == "Punjab"
    assert idx_rec.payload_metadata["knowledge_collection"] == "Crops"


def test_engine_build_index_record_from_sparse_record():
    adapter = FakeIndexAdapter()
    engine = KnowledgeIndexEngine(adapter)

    sparse_rec = SparseRepresentationRecord(
        representation_id="sp_100",
        source_id="src_100",
        document_id="doc_100",
        version_id="v1.0",
        knowledge_unit_id="ku_100",
        provider="bm25",
        model="bm25-v1",
        sparse_vector=SparseVector(indices=[5, 15], values=[1.2, 2.5]),
        metadata={"topic": "Pest Control"},
    )

    idx_rec = engine.build_index_record(
        sparse_record=sparse_rec,
    )

    assert idx_rec.index_record_id == "idx_ku_100"
    assert idx_rec.knowledge_unit_id == "ku_100"
    assert idx_rec.sparse_representation_id == "sp_100"
    assert idx_rec.sparse_vector.indices == [5, 15]
    assert idx_rec.payload_metadata["topic"] == "Pest Control"


def test_engine_lifecycle_enforcement():
    adapter = FakeIndexAdapter()
    engine = KnowledgeIndexEngine(adapter, enforce_publication_lifecycle=True)

    dense_rec = EmbeddingRecord(
        embedding_id="emb_200",
        source_id="src_200",
        document_id="doc_200",
        version_id="v1.0",
        chunk_id="chk_200",
        provider="fake",
        model="fake-embed-v1",
        dimension=2,
        dense_vector=[0.1, 0.2],
    )

    with pytest.raises(InvalidIndexRecordError) as exc_info:
        engine.build_index_record(
            dense_record=dense_rec,
            lifecycle_state=KnowledgeLifecycleState.REJECTED,
        )
    assert "Cannot index record with lifecycle state" in str(exc_info.value)


def test_engine_indexing_and_batch():
    adapter = FakeIndexAdapter()
    engine = KnowledgeIndexEngine(adapter)

    rec1 = IndexRecord(
        index_record_id="idx_b1",
        source_id="src_b",
        document_id="doc_b",
        version_id="v1",
        chunk_id="chk_b1",
        dense_vector=[0.1, 0.2],
        knowledge_collection="Soil",
    )
    rec2 = IndexRecord(
        index_record_id="idx_b2",
        source_id="src_b",
        document_id="doc_b",
        version_id="v1",
        chunk_id="chk_b2",
        dense_vector=[0.3, 0.4],
        knowledge_collection="Soil",
    )

    # Index single
    indexed_rec1 = engine.index_record(rec1)
    assert indexed_rec1.status == IndexStatus.INDEXED
    assert adapter.get_record("earthmind_knowledge", "idx_b1") is not None

    # Index batch
    batch_res = engine.index_batch([rec1, rec2])
    assert batch_res.total_records == 2
    assert batch_res.status == IndexStatus.INDEXED
    assert len(batch_res.successful_records) == 2
    assert batch_res.processing_time_ms is not None


# ==============================================================================
# 4. FAKE INDEX ADAPTER TESTS
# ==============================================================================

def test_fake_adapter_crud():
    adapter = FakeIndexAdapter()
    assert adapter.is_available() is True
    assert adapter.health_check() is True

    adapter.create_collection("test_col")
    rec = IndexRecord(
        index_record_id="idx_f1",
        source_id="src_f",
        document_id="doc_f",
        version_id="v1",
        chunk_id="chk_f1",
        dense_vector=[0.1, 0.2],
    )

    indexed = adapter.index_record("test_col", rec)
    assert indexed.status == IndexStatus.INDEXED

    retrieved = adapter.get_record("test_col", "idx_f1")
    assert retrieved is not None
    assert retrieved.index_record_id == "idx_f1"

    status = adapter.get_status("test_col")
    assert status["record_count"] == 1

    deleted = adapter.delete_record("test_col", "idx_f1")
    assert deleted is True
    assert adapter.get_record("test_col", "idx_f1") is None


def test_fake_adapter_unavailability_error():
    adapter = FakeIndexAdapter()
    adapter.set_availability(False)

    rec = IndexRecord(
        index_record_id="idx_f2",
        source_id="src_f",
        document_id="doc_f",
        version_id="v1",
        chunk_id="chk_f2",
        dense_vector=[0.1, 0.2],
    )

    with pytest.raises(IndexExecutionError):
        adapter.index_record("test_col", rec)


# ==============================================================================
# 5. QDRANT ADAPTER TESTS (IN-MEMORY)
# ==============================================================================

def test_qdrant_adapter_in_memory_full_lifecycle():
    config = QdrantConfig(location=":memory:", distance_metric="COSINE")
    adapter = QdrantIndexAdapter(config=config)

    assert isinstance(adapter, IKnowledgeIndexAdapter)
    assert adapter.is_available() is True
    assert adapter.health_check() is True

    col_name = "test_qdrant_col"
    adapter.ensure_collection_exists(col_name, dense_dim=3)

    rec1 = IndexRecord(
        index_record_id="idx_q1",
        source_id="src_q1",
        document_id="doc_q1",
        version_id="v1.0",
        chunk_id="chk_q1",
        dense_embedding_id="emb_q1",
        dense_provider="fake",
        dense_model="embed-v1",
        dense_dimension=3,
        dense_vector=[1.0, 0.0, 0.0],
        sparse_vector=SparseVector(indices=[10, 20], values=[0.4, 0.8]),
        payload_metadata={"crop": "Corn", "season": "Kharif"},
        knowledge_collection="Crops",
    )

    rec2 = IndexRecord(
        index_record_id="idx_q2",
        source_id="src_q1",
        document_id="doc_q1",
        version_id="v1.0",
        chunk_id="chk_q2",
        dense_dimension=3,
        dense_vector=[0.0, 1.0, 0.0],
        payload_metadata={"crop": "Rice", "season": "Rabi"},
        knowledge_collection="Crops",
    )

    # 1. Index single record
    indexed1 = adapter.index_record(col_name, rec1)
    assert indexed1.status == IndexStatus.INDEXED
    assert indexed1.physical_collection_name == col_name

    # 2. Retrieve record
    retrieved1 = adapter.get_record(col_name, "idx_q1")
    assert retrieved1 is not None
    assert retrieved1.index_record_id == "idx_q1"
    assert retrieved1.source_id == "src_q1"
    assert retrieved1.document_id == "doc_q1"
    assert retrieved1.chunk_id == "chk_q1"
    assert retrieved1.dense_vector == pytest.approx([1.0, 0.0, 0.0], abs=1e-3)
    assert retrieved1.sparse_vector.indices == [10, 20]
    assert retrieved1.payload_metadata["crop"] == "Corn"

    # 3. Index batch
    batch_res = adapter.index_batch(col_name, [rec2])
    assert batch_res.total_records == 1
    assert batch_res.status == IndexStatus.INDEXED
    assert len(batch_res.successful_records) == 1

    # 4. Get collection status
    stats = adapter.get_status(col_name)
    assert stats["record_count"] == 2

    # 5. Delete record
    deleted = adapter.delete_record(col_name, "idx_q1")
    assert deleted is True
    assert adapter.get_record(col_name, "idx_q1") is None


# ==============================================================================
# 6. ARCHITECTURAL ISOLATION TEST
# ==============================================================================

def test_architectural_isolation_no_qdrant_imports():
    """Verify that non-adapter Index Layer modules contain zero Qdrant SDK dependencies."""
    import inspect
    import modules.knowledge_base.index.record as record_mod
    import modules.knowledge_base.index.engine as engine_mod
    import modules.knowledge_base.index.collection_strategy as strat_mod
    import core.interfaces.index as iface_mod

    for mod in [record_mod, engine_mod, strat_mod, iface_mod]:
        src = inspect.getsource(mod)
        assert "qdrant" not in src.lower(), f"Qdrant import or leakage found in module {mod.__name__}"
