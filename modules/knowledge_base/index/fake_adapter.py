"""Fake / In-Memory Index Adapter for C.2 Knowledge Base.

Provides an in-memory implementation of IKnowledgeIndexAdapter for:
- Testing without external services or C-extensions.
- Verifying interface isolation and adapter replaceability.
"""

import math
from typing import Any, Dict, List, Optional
from core.interfaces.index import DenseSearchResult, IKnowledgeIndexAdapter
from core.errors.exceptions import (
    CollectionOperationError,
    IndexExecutionError,
    InvalidIndexRecordError,
)
from modules.knowledge_base.enums import IndexStatus
from modules.knowledge_base.index.record import IndexBatchResult, IndexRecord


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


class FakeIndexAdapter(IKnowledgeIndexAdapter):
    """In-memory Index Adapter implementing IKnowledgeIndexAdapter."""

    def __init__(self, is_available: bool = True):
        self._is_available = is_available
        # Storage: collection_name -> (record_id -> IndexRecord)
        self.collections: Dict[str, Dict[str, IndexRecord]] = {}
        # Metadata storage per collection
        self.collection_configs: Dict[str, Dict[str, Any]] = {}

    def set_availability(self, available: bool) -> None:
        """Dynamically toggle availability for testing failure scenarios."""
        self._is_available = available

    def is_available(self) -> bool:
        """Return availability status."""
        return self._is_available

    def health_check(self) -> bool:
        """Return operational health status."""
        return self._is_available

    def create_collection(
        self, collection_name: str, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Create a new in-memory index collection."""
        if not self._is_available:
            raise IndexExecutionError("fake", "FakeIndexAdapter is set to unavailable.")
        if not collection_name or not collection_name.strip():
            raise CollectionOperationError(collection_name or "", "create_collection", "Collection name cannot be empty.")

        name = collection_name.strip()
        if name not in self.collections:
            self.collections[name] = {}
            self.collection_configs[name] = config or {}
        return True

    def ensure_collection_exists(
        self, collection_name: str, dense_dim: int, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Ensure in-memory collection exists with required dimension setting."""
        if not self._is_available:
            raise IndexExecutionError("fake", "FakeIndexAdapter is set to unavailable.")
        if dense_dim <= 0:
            raise CollectionOperationError(collection_name, "ensure_collection_exists", f"Invalid dense dimension {dense_dim}.")

        cfg = config or {}
        cfg["dense_dimension"] = dense_dim
        return self.create_collection(collection_name, cfg)

    def index_record(self, collection_name: str, record: IndexRecord) -> IndexRecord:
        """Index a single IndexRecord."""
        if not self._is_available:
            raise IndexExecutionError("fake", "FakeIndexAdapter is set to unavailable.")
        if not isinstance(record, IndexRecord):
            raise InvalidIndexRecordError("Record must be an instance of IndexRecord.")

        c_name = collection_name.strip()
        if c_name not in self.collections:
            self.create_collection(c_name)

        # Clone and update status
        indexed_record = record.model_copy(
            update={
                "physical_collection_name": c_name,
                "status": IndexStatus.INDEXED,
                "error_message": None,
            }
        )
        self.collections[c_name][indexed_record.index_record_id] = indexed_record
        return indexed_record

    def index_batch(self, collection_name: str, records: List[IndexRecord]) -> IndexBatchResult:
        """Index a batch of IndexRecords with partial batch failure handling."""
        if not self._is_available:
            raise IndexExecutionError("fake", "FakeIndexAdapter is set to unavailable.")

        successful: List[IndexRecord] = []
        failed: List[Dict[str, Any]] = []

        c_name = collection_name.strip()
        if c_name not in self.collections:
            self.create_collection(c_name)

        for record in records:
            try:
                indexed = self.index_record(c_name, record)
                successful.append(indexed)
            except Exception as e:
                failed.append({
                    "index_record_id": getattr(record, "index_record_id", "unknown"),
                    "error": str(e),
                    "code": getattr(e, "error_code", "INDEX_RECORD_FAILURE"),
                    "retryable": getattr(e, "retryable", False),
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
        """Update an existing record."""
        return self.index_record(collection_name, record)

    def delete_record(self, collection_name: str, record_id: str) -> bool:
        """Delete an index record by ID."""
        if not self._is_available:
            raise IndexExecutionError("fake", "FakeIndexAdapter is set to unavailable.")
        c_name = collection_name.strip()
        if c_name in self.collections and record_id in self.collections[c_name]:
            del self.collections[c_name][record_id]
            return True
        return False

    def get_record(self, collection_name: str, record_id: str) -> Optional[IndexRecord]:
        """Retrieve an index record by ID."""
        if not self._is_available:
            raise IndexExecutionError("fake", "FakeIndexAdapter is set to unavailable.")
        c_name = collection_name.strip()
        if c_name in self.collections:
            return self.collections[c_name].get(record_id)
        return None

    def search_dense(
        self,
        collection_name: str,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        with_record: bool = True,
    ) -> List[DenseSearchResult]:
        """Perform dense vector cosine similarity search in memory."""
        if not self._is_available:
            raise IndexExecutionError("fake", "FakeIndexAdapter is set to unavailable.")

        c_name = collection_name.strip()
        if c_name not in self.collections:
            return []

        scored: List[tuple[str, float]] = []
        for rec_id, record in self.collections[c_name].items():
            if not record.dense_vector:
                continue

            # Apply filters if provided
            if filters:
                match = True
                payload = record.payload_metadata or {}
                for k, v in filters.items():
                    if payload.get(k) != v:
                        match = False
                        break
                if not match:
                    continue

            score = _cosine_similarity(query_vector, record.dense_vector)
            scored.append((rec_id, score))

        # Sort by similarity score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        top_results = scored[:top_k]

        results: List[DenseSearchResult] = []
        for rec_id, score in top_results:
            rec = self.collections[c_name][rec_id]
            results.append(
                DenseSearchResult(
                    record_id=rec_id,
                    score=round(score, 6),
                    record=rec if with_record else None,
                    payload=rec.payload_metadata or {},
                )
            )

        return results

    def get_status(self, collection_name: str) -> Dict[str, Any]:
        """Return status metrics for the specified collection."""
        if not self._is_available:
            raise IndexExecutionError("fake", "FakeIndexAdapter is set to unavailable.")
        c_name = collection_name.strip()
        count = len(self.collections.get(c_name, {}))
        return {
            "collection_name": c_name,
            "record_count": count,
            "status": "HEALTHY" if self._is_available else "UNAVAILABLE",
            "exists": c_name in self.collections,
        }
