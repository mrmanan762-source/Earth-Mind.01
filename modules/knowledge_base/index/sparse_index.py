"""Sparse Index Adapter Interfaces and Implementation for EarthMind R6.

Defines:
- ISparseIndexAdapter protocol for provider-agnostic sparse index CRUD & search lookup primitives
- InvertedSparseIndexAdapter: Pure Python in-memory inverted sparse index with BM25 dot-product lookup
- QdrantSparseIndexAdapter: Sparse index adapter backed by Qdrant's sparse vector engine
"""

import math
import uuid
from typing import Any, Dict, List, Optional, Protocol, Tuple, Union, runtime_checkable

from pydantic import BaseModel, Field

from core.config.settings import QdrantConfig, settings
from core.errors.exceptions import (
    CollectionOperationError,
    IndexExecutionError,
    IndexProviderUnavailableError,
    InvalidIndexRecordError,
    QdrantAdapterError,
    SparseVectorValidationError,
)
from core.schemas.sparse import validate_sparse_vector
from modules.knowledge_base.enums import IndexStatus, KnowledgeContentType, KnowledgeLifecycleState
from modules.knowledge_base.index.record import IndexBatchResult, IndexRecord

try:
    import qdrant_client
    from qdrant_client import models
    QDRANT_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    QDRANT_SDK_AVAILABLE = False
    qdrant_client = None
    models = None


class SparseSearchResult(BaseModel):
    """Result structure for sparse retrieval lookup primitives."""

    record_id: str = Field(..., description="IndexRecord identifier")
    score: float = Field(..., description="Sparse matching score (e.g., dot product / BM25 score)")
    record: Optional[IndexRecord] = Field(None, description="Full IndexRecord payload if requested")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Filterable payload metadata")


@runtime_checkable
class ISparseIndexAdapter(Protocol):
    """Generic interface for sparse index persistence, CRUD, and lookup search primitives."""

    def create_collection(
        self, collection_name: str, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Create a new sparse index collection."""
        ...

    def index_record(self, collection_name: str, record: IndexRecord) -> IndexRecord:
        """Index a single IndexRecord containing a sparse_vector."""
        ...

    def index_batch(self, collection_name: str, records: List[IndexRecord]) -> IndexBatchResult:
        """Index a batch of IndexRecords with sparse vectors."""
        ...

    def update_record(self, collection_name: str, record: IndexRecord) -> IndexRecord:
        """Update an existing sparse record."""
        ...

    def delete_record(self, collection_name: str, record_id: str) -> bool:
        """Delete a record from the sparse index by ID."""
        ...

    def get_record(self, collection_name: str, record_id: str) -> Optional[IndexRecord]:
        """Retrieve an IndexRecord from the sparse index by ID."""
        ...

    def search_sparse(
        self,
        collection_name: str,
        query_indices: List[int],
        query_values: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        with_record: bool = True,
    ) -> List[SparseSearchResult]:
        """Perform sparse lookup/search primitive given sparse query vector indices and weights."""
        ...

    def rebuild_index(
        self, collection_name: str, records: List[IndexRecord]
    ) -> IndexBatchResult:
        """Rebuild sparse index deterministically from canonical/sparse records."""
        ...

    def get_status(self, collection_name: str) -> Dict[str, Any]:
        """Return collection status and count metrics."""
        ...

    def is_available(self) -> bool:
        """Return operational health of the backend."""
        ...


class InvertedSparseIndexAdapter(ISparseIndexAdapter):
    """Pure Python Inverted Index Adapter for fast, in-memory sparse retrieval."""

    def __init__(self, is_available: bool = True):
        self._is_available = is_available
        # Storage: collection_name -> (record_id -> IndexRecord)
        self.records: Dict[str, Dict[str, IndexRecord]] = {}
        # Inverted Index: collection_name -> (term_index -> List[(record_id, term_weight)])
        self.inverted_index: Dict[str, Dict[int, List[Tuple[str, float]]]] = {}

    def is_available(self) -> bool:
        return self._is_available

    def set_availability(self, available: bool) -> None:
        self._is_available = available

    def create_collection(
        self, collection_name: str, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        if not self._is_available:
            raise IndexExecutionError("inverted_sparse", "InvertedSparseIndexAdapter is set to unavailable.")
        c_name = collection_name.strip()
        if c_name not in self.records:
            self.records[c_name] = {}
            self.inverted_index[c_name] = {}
        return True

    def index_record(self, collection_name: str, record: IndexRecord) -> IndexRecord:
        if not self._is_available:
            raise IndexExecutionError("inverted_sparse", "InvertedSparseIndexAdapter is set to unavailable.")
        if not isinstance(record, IndexRecord):
            raise InvalidIndexRecordError("Record must be an instance of IndexRecord.")
        if record.sparse_vector is None:
            raise InvalidIndexRecordError(f"Record '{record.index_record_id}' missing sparse_vector.")

        c_name = collection_name.strip()
        if c_name not in self.records:
            self.create_collection(c_name)

        # If existing record, remove old inverted index entries first
        if record.index_record_id in self.records[c_name]:
            self.delete_record(c_name, record.index_record_id)

        indexed_rec = record.model_copy(
            update={
                "physical_collection_name": c_name,
                "status": IndexStatus.INDEXED,
                "error_message": None,
            }
        )
        self.records[c_name][indexed_rec.index_record_id] = indexed_rec

        # Populate inverted index
        inv = self.inverted_index[c_name]
        sp = record.sparse_vector
        for term_idx, term_val in zip(sp.indices, sp.values):
            if term_idx not in inv:
                inv[term_idx] = []
            inv[term_idx].append((record.index_record_id, term_val))

        return indexed_rec

    def index_batch(self, collection_name: str, records: List[IndexRecord]) -> IndexBatchResult:
        if not self._is_available:
            raise IndexExecutionError("inverted_sparse", "InvertedSparseIndexAdapter is set to unavailable.")

        successful: List[IndexRecord] = []
        failed: List[Dict[str, Any]] = []

        c_name = collection_name.strip()
        if c_name not in self.records:
            self.create_collection(c_name)

        for rec in records:
            try:
                indexed = self.index_record(c_name, rec)
                successful.append(indexed)
            except Exception as e:
                failed.append({
                    "index_record_id": getattr(rec, "index_record_id", "unknown"),
                    "error": str(e),
                })

        batch_status = IndexStatus.INDEXED
        if failed and successful:
            batch_status = IndexStatus.PARTIAL
        elif failed and not successful:
            batch_status = IndexStatus.FAILED

        return IndexBatchResult(
            total_records=len(records),
            successful_records=successful,
            failed_records=failed,
            status=batch_status,
        )

    def update_record(self, collection_name: str, record: IndexRecord) -> IndexRecord:
        return self.index_record(collection_name, record)

    def delete_record(self, collection_name: str, record_id: str) -> bool:
        if not self._is_available:
            raise IndexExecutionError("inverted_sparse", "InvertedSparseIndexAdapter is set to unavailable.")
        c_name = collection_name.strip()
        if c_name not in self.records or record_id not in self.records[c_name]:
            return False

        # Remove from record map
        del self.records[c_name][record_id]

        # Remove from inverted index
        inv = self.inverted_index[c_name]
        for term_idx in list(inv.keys()):
            inv[term_idx] = [entry for entry in inv[term_idx] if entry[0] != record_id]
            if not inv[term_idx]:
                del inv[term_idx]

        return True

    def get_record(self, collection_name: str, record_id: str) -> Optional[IndexRecord]:
        if not self._is_available:
            raise IndexExecutionError("inverted_sparse", "InvertedSparseIndexAdapter is set to unavailable.")
        c_name = collection_name.strip()
        if c_name in self.records:
            return self.records[c_name].get(record_id)
        return None

    def search_sparse(
        self,
        collection_name: str,
        query_indices: List[int],
        query_values: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        with_record: bool = True,
    ) -> List[SparseSearchResult]:
        if not self._is_available:
            raise IndexExecutionError("inverted_sparse", "InvertedSparseIndexAdapter is set to unavailable.")
        c_name = collection_name.strip()
        if c_name not in self.records:
            return []

        inv = self.inverted_index[c_name]
        scores: Dict[str, float] = {}

        # Dot-product scoring over matching query term indices
        for q_idx, q_val in zip(query_indices, query_values):
            if q_idx in inv:
                for rec_id, doc_val in inv[q_idx]:
                    scores[rec_id] = scores.get(rec_id, 0.0) + (q_val * doc_val)

        # Apply metadata filters if provided
        filtered_results: List[Tuple[str, float]] = []
        for rec_id, score in scores.items():
            rec = self.records[c_name][rec_id]
            if filters:
                match = True
                payload = rec.payload_metadata or {}
                for k, v in filters.items():
                    if payload.get(k) != v:
                        match = False
                        break
                if not match:
                    continue
            filtered_results.append((rec_id, score))

        # Sort by score descending
        filtered_results.sort(key=lambda x: x[1], reverse=True)
        top_results = filtered_results[:top_k]

        results: List[SparseSearchResult] = []
        for rec_id, score in top_results:
            rec = self.records[c_name][rec_id]
            results.append(
                SparseSearchResult(
                    record_id=rec_id,
                    score=round(score, 4),
                    record=rec if with_record else None,
                    payload=rec.payload_metadata or {},
                )
            )

        return results

    def rebuild_index(
        self, collection_name: str, records: List[IndexRecord]
    ) -> IndexBatchResult:
        c_name = collection_name.strip()
        self.records[c_name] = {}
        self.inverted_index[c_name] = {}
        return self.index_batch(c_name, records)

    def get_status(self, collection_name: str) -> Dict[str, Any]:
        c_name = collection_name.strip()
        count = len(self.records.get(c_name, {}))
        vocab_terms = len(self.inverted_index.get(c_name, {}))
        return {
            "collection_name": c_name,
            "record_count": count,
            "unique_terms_indexed": vocab_terms,
            "status": "HEALTHY" if self._is_available else "UNAVAILABLE",
        }


def _to_qdrant_point_id(record_id: str) -> str:
    try:
        parsed = uuid.UUID(record_id)
        return str(parsed)
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, record_id))


class QdrantSparseIndexAdapter(ISparseIndexAdapter):
    """Concrete Sparse Index Adapter backed by Qdrant Sparse Vector Engine."""

    def __init__(
        self,
        config: Optional[QdrantConfig] = None,
        client: Optional[Any] = None,
    ):
        if not QDRANT_SDK_AVAILABLE:  # pragma: no cover
            raise IndexProviderUnavailableError("qdrant", "qdrant-client SDK not available.")

        self.config = config or getattr(settings, "qdrant", QdrantConfig())
        if client is not None:
            self.client = client
        else:
            self.client = self._init_client(self.config)

    def _init_client(self, cfg: QdrantConfig) -> Any:
        try:
            if cfg.location:
                return qdrant_client.QdrantClient(location=cfg.location)
            elif cfg.url:
                return qdrant_client.QdrantClient(
                    url=cfg.url, api_key=cfg.api_key, timeout=cfg.timeout
                )
            else:
                return qdrant_client.QdrantClient(
                    host=cfg.host, port=cfg.port, api_key=cfg.api_key, timeout=cfg.timeout
                )
        except Exception as e:
            raise IndexProviderUnavailableError("qdrant", f"Failed to init QdrantClient: {str(e)}")

    def is_available(self) -> bool:
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False

    def create_collection(
        self, collection_name: str, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        name = collection_name.strip()
        try:
            sparse_vectors_config = {
                "sparse": models.SparseVectorParams()
            }
            self.client.create_collection(
                collection_name=name,
                sparse_vectors_config=sparse_vectors_config,
            )
            return True
        except Exception as e:
            raise CollectionOperationError(name, "create_collection", str(e))

    def index_record(self, collection_name: str, record: IndexRecord) -> IndexRecord:
        if not isinstance(record, IndexRecord):
            raise InvalidIndexRecordError("Record must be an instance of IndexRecord.")
        if not record.sparse_vector:
            raise InvalidIndexRecordError(f"Record '{record.index_record_id}' missing sparse_vector.")

        name = collection_name.strip()
        point_id = _to_qdrant_point_id(record.index_record_id)

        vector_dict = {
            "sparse": models.SparseVector(
                indices=record.sparse_vector.indices,
                values=record.sparse_vector.values,
            )
        }
        if record.dense_vector:
            vector_dict["dense"] = record.dense_vector

        payload = dict(record.payload_metadata or {})
        payload.update({
            "_index_record_id": record.index_record_id,
            "_source_id": record.source_id,
            "_document_id": record.document_id,
            "_version_id": record.version_id,
            "_chunk_id": record.chunk_id,
            "_knowledge_unit_id": record.knowledge_unit_id,
            "_sparse_representation_id": record.sparse_representation_id,
            "_sparse_provider": record.sparse_provider,
            "_sparse_model": record.sparse_model,
        })

        point = models.PointStruct(id=point_id, vector=vector_dict, payload=payload)

        try:
            self.client.upsert(collection_name=name, points=[point])
            return record.model_copy(
                update={
                    "physical_collection_name": name,
                    "status": IndexStatus.INDEXED,
                    "error_message": None,
                }
            )
        except Exception as e:
            raise QdrantAdapterError(f"Failed to index sparse record '{record.index_record_id}': {str(e)}")

    def index_batch(self, collection_name: str, records: List[IndexRecord]) -> IndexBatchResult:
        name = collection_name.strip()
        successful: List[IndexRecord] = []
        failed: List[Dict[str, Any]] = []

        points: List[Any] = []
        for rec in records:
            try:
                point_id = _to_qdrant_point_id(rec.index_record_id)
                v_dict = {
                    "sparse": models.SparseVector(
                        indices=rec.sparse_vector.indices,
                        values=rec.sparse_vector.values,
                    )
                }
                payload = dict(rec.payload_metadata or {})
                payload["_index_record_id"] = rec.index_record_id
                points.append(models.PointStruct(id=point_id, vector=v_dict, payload=payload))
            except Exception as e:
                failed.append({"index_record_id": rec.index_record_id, "error": str(e)})

        if points:
            try:
                self.client.upsert(collection_name=name, points=points)
                for rec in records:
                    successful.append(rec.model_copy(update={"physical_collection_name": name, "status": IndexStatus.INDEXED}))
            except Exception as e:
                failed.append({"batch_error": str(e)})

        status = IndexStatus.INDEXED if not failed else (IndexStatus.PARTIAL if successful else IndexStatus.FAILED)
        return IndexBatchResult(
            total_records=len(records),
            successful_records=successful,
            failed_records=failed,
            status=status,
        )

    def update_record(self, collection_name: str, record: IndexRecord) -> IndexRecord:
        return self.index_record(collection_name, record)

    def delete_record(self, collection_name: str, record_id: str) -> bool:
        name = collection_name.strip()
        point_id = _to_qdrant_point_id(record_id)
        try:
            self.client.delete(
                collection_name=name,
                points_selector=models.PointIdsList(points=[point_id]),
            )
            return True
        except Exception as e:
            raise QdrantAdapterError(f"Failed to delete sparse record '{record_id}': {str(e)}")

    def get_record(self, collection_name: str, record_id: str) -> Optional[IndexRecord]:
        name = collection_name.strip()
        point_id = _to_qdrant_point_id(record_id)
        try:
            res = self.client.retrieve(collection_name=name, ids=[point_id], with_payload=True, with_vectors=True)
            if res and len(res) > 0:
                p = res[0]
                payload = p.payload or {}
                rec_id = payload.get("_index_record_id", str(p.id))
                return IndexRecord(
                    index_record_id=rec_id,
                    source_id=payload.get("_source_id", "unknown"),
                    document_id=payload.get("_document_id", "unknown"),
                    version_id=payload.get("_version_id", "unknown"),
                    chunk_id=payload.get("_chunk_id"),
                    knowledge_unit_id=payload.get("_knowledge_unit_id"),
                    sparse_representation_id=payload.get("_sparse_representation_id"),
                    payload_metadata={k: v for k, v in payload.items() if not k.startswith("_")},
                    status=IndexStatus.INDEXED,
                )
            return None
        except Exception as e:
            raise QdrantAdapterError(f"Failed to get record '{record_id}': {str(e)}")

    def search_sparse(
        self,
        collection_name: str,
        query_indices: List[int],
        query_values: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        with_record: bool = True,
    ) -> List[SparseSearchResult]:
        name = collection_name.strip()
        try:
            sparse_query = models.SparseVector(indices=query_indices, values=query_values)
            filter_conditions = None
            if filters:
                must_clauses = [
                    models.FieldCondition(key=k, match=models.MatchValue(value=v))
                    for k, v in filters.items()
                ]
                filter_conditions = models.Filter(must=must_clauses)

            res = self.client.search(
                collection_name=name,
                query_vector=models.NamedSparseVector(name="sparse", vector=sparse_query),
                limit=top_k,
                query_filter=filter_conditions,
                with_payload=True,
            )

            results: List[SparseSearchResult] = []
            for hit in res:
                payload = hit.payload or {}
                rec_id = payload.get("_index_record_id", str(hit.id))
                rec = None
                if with_record:
                    rec = self.get_record(name, rec_id)

                results.append(
                    SparseSearchResult(
                        record_id=rec_id,
                        score=hit.score,
                        record=rec,
                        payload={k: v for k, v in payload.items() if not k.startswith("_")},
                    )
                )
            return results
        except Exception as e:
            raise QdrantAdapterError(f"Sparse search failed in '{name}': {str(e)}")

    def rebuild_index(
        self, collection_name: str, records: List[IndexRecord]
    ) -> IndexBatchResult:
        return self.index_batch(collection_name, records)

    def get_status(self, collection_name: str) -> Dict[str, Any]:
        name = collection_name.strip()
        try:
            info = self.client.get_collection(collection_name=name)
            count_res = self.client.count(collection_name=name)
            return {
                "collection_name": name,
                "record_count": count_res.count if hasattr(count_res, "count") else 0,
                "status": str(info.status),
            }
        except Exception as e:
            raise QdrantAdapterError(f"Failed to get collection status for '{name}': {str(e)}")
