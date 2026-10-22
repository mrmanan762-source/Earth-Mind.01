"""Qdrant Concrete Index Adapter for C.2 Knowledge Base.

Implements IKnowledgeIndexAdapter using the qdrant-client SDK.
Encapsulates all Qdrant-specific SDK interactions behind the provider-neutral Index Interface.
No Qdrant types or SDK details leak beyond this module.
"""

import uuid
from typing import Any, Dict, List, Optional
from core.config.settings import QdrantConfig, settings
from core.errors.exceptions import (
    CollectionOperationError,
    IndexDimensionMismatchError,
    IndexExecutionError,
    IndexProviderUnavailableError,
    InvalidIndexRecordError,
    QdrantAdapterError,
)
from core.interfaces.index import DenseSearchResult, SparseSearchResult, IKnowledgeIndexAdapter
from core.schemas.embedding import SparseVector
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


def _to_qdrant_point_id(record_id: str) -> str:
    """Convert an arbitrary string index record ID into a valid Qdrant UUID v5 string."""
    try:
        # Check if already a valid UUID
        parsed = uuid.UUID(record_id)
        return str(parsed)
    except ValueError:
        # Generate deterministic UUID v5 from record_id
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, record_id))


class QdrantIndexAdapter(IKnowledgeIndexAdapter):
    """Concrete implementation of IKnowledgeIndexAdapter for Qdrant vector database."""

    def __init__(
        self,
        config: Optional[QdrantConfig] = None,
        client: Optional[Any] = None,
    ):
        if not QDRANT_SDK_AVAILABLE:  # pragma: no cover
            raise IndexProviderUnavailableError("qdrant", "qdrant-client Python SDK is not installed.")

        self.config = config or getattr(settings, "qdrant", QdrantConfig())

        if client is not None:
            self.client = client
        else:
            self.client = self._init_client(self.config)

    def _init_client(self, cfg: QdrantConfig) -> Any:
        """Initialize QdrantClient based on configuration."""
        try:
            if cfg.location:
                if cfg.location == ":memory:":
                    return qdrant_client.QdrantClient(location=":memory:")
                elif cfg.location.startswith("http://") or cfg.location.startswith("https://"):
                    return qdrant_client.QdrantClient(url=cfg.location, api_key=cfg.api_key, timeout=cfg.timeout)
                else:
                    return qdrant_client.QdrantClient(path=cfg.location)
            elif cfg.url:
                return qdrant_client.QdrantClient(
                    url=cfg.url,
                    api_key=cfg.api_key,
                    timeout=cfg.timeout,
                )
            else:
                return qdrant_client.QdrantClient(
                    host=cfg.host,
                    port=cfg.port,
                    grpc_port=cfg.grpc_port,
                    api_key=cfg.api_key,
                    prefer_grpc=cfg.prefer_grpc,
                    timeout=cfg.timeout,
                )
        except Exception as e:
            raise IndexProviderUnavailableError("qdrant", f"Failed to initialize QdrantClient: {str(e)}")

    def _get_distance_metric(self, metric_str: str) -> Any:
        """Map distance metric string to Qdrant Distance enum."""
        m = (metric_str or "COSINE").upper().strip()
        if m == "DOT":
            return models.Distance.DOT
        elif m in ("EUCLID", "EUCLIDEAN"):
            return models.Distance.EUCLID
        return models.Distance.COSINE

    def is_available(self) -> bool:
        """Return operational status of Qdrant connection."""
        if hasattr(self, "_override_available") and self._override_available is not None:
            return self._override_available
        try:
            return self.health_check()
        except Exception:
            return False

    def set_availability(self, available: bool) -> None:
        """Set availability override status for testing and branch isolation."""
        self._override_available = available

    def close(self) -> None:
        """Close underlying client connection and release file locks."""
        if hasattr(self, "client") and self.client is not None:
            try:
                if hasattr(self.client, "close"):
                    self.client.close()
            except Exception:
                pass

    def health_check(self) -> bool:
        """Check operational health of Qdrant backend."""
        try:
            # Query collections list to check connection
            self.client.get_collections()
            return True
        except Exception as e:
            raise IndexProviderUnavailableError("qdrant", f"Health check failed: {str(e)}")

    def create_collection(
        self, collection_name: str, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Create a Qdrant collection."""
        if not collection_name or not collection_name.strip():
            raise CollectionOperationError(collection_name or "", "create_collection", "Collection name cannot be empty.")

        name = collection_name.strip()
        cfg = config or {}
        dense_dim = cfg.get("dense_dimension", 384)
        distance_str = cfg.get("distance_metric", self.config.distance_metric)
        distance = self._get_distance_metric(distance_str)

        try:
            vectors_config = {
                "dense": models.VectorParams(size=dense_dim, distance=distance)
            }
            sparse_vectors_config = {
                "sparse": models.SparseVectorParams()
            }

            self.client.create_collection(
                collection_name=name,
                vectors_config=vectors_config,
                sparse_vectors_config=sparse_vectors_config,
            )
            return True
        except Exception as e:
            raise CollectionOperationError(name, "create_collection", str(e))

    def validate_collection_config(self, collection_name: str, required_dense_dim: int) -> bool:
        """Validate an existing collection's vector configuration against required parameters."""
        name = collection_name.strip()
        try:
            info = self.client.get_collection(collection_name=name)
            vectors_cfg = getattr(info.config.params, "vectors", None)
            existing_dim = None

            if isinstance(vectors_cfg, dict):
                dense_params = vectors_cfg.get("dense")
                if dense_params and hasattr(dense_params, "size"):
                    existing_dim = dense_params.size
            elif hasattr(vectors_cfg, "size"):
                existing_dim = vectors_cfg.size

            if existing_dim is not None and existing_dim != required_dense_dim:
                raise IndexDimensionMismatchError(
                    expected_dim=required_dense_dim,
                    actual_dim=existing_dim,
                    details=f"Collection '{name}' vector dimension configuration mismatch.",
                )
            return True
        except IndexDimensionMismatchError:
            raise
        except Exception as e:
            raise CollectionOperationError(name, "validate_collection_config", str(e))

    def ensure_collection_exists(
        self, collection_name: str, dense_dim: int, config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Ensure collection exists with required dense vector parameters and validates dimension."""
        if not collection_name or not collection_name.strip():
            raise CollectionOperationError(collection_name or "", "ensure_collection_exists", "Collection name cannot be empty.")

        name = collection_name.strip()
        try:
            if not self.client.collection_exists(name):
                cfg = dict(config or {})
                cfg["dense_dimension"] = dense_dim
                return self.create_collection(name, cfg)
            else:
                self.validate_collection_config(name, required_dense_dim=dense_dim)
            return True
        except (CollectionOperationError, IndexDimensionMismatchError):
            raise
        except Exception as e:
            raise CollectionOperationError(name, "ensure_collection_exists", str(e))

    def _convert_record_to_point(self, record: IndexRecord) -> Any:
        """Convert an IndexRecord to a Qdrant PointStruct."""
        point_id = _to_qdrant_point_id(record.index_record_id)

        vector_dict: Dict[str, Any] = {}
        if record.dense_vector:
            vector_dict["dense"] = record.dense_vector

        if record.sparse_vector:
            vector_dict["sparse"] = models.SparseVector(
                indices=record.sparse_vector.indices,
                values=record.sparse_vector.values,
            )

        payload = dict(record.payload_metadata or {})
        # Attach reserved lineage and record metadata fields to payload
        payload.update({
            "_index_record_id": record.index_record_id,
            "_source_id": record.source_id,
            "_document_id": record.document_id,
            "_version_id": record.version_id,
            "_chunk_id": record.chunk_id,
            "_knowledge_unit_id": record.knowledge_unit_id,
            "_section_id": record.section_id,
            "_artifact_id": record.artifact_id,
            "_dense_embedding_id": record.dense_embedding_id,
            "_sparse_representation_id": record.sparse_representation_id,
            "_dense_provider": record.dense_provider,
            "_dense_model": record.dense_model,
            "_dense_model_version": record.dense_model_version,
            "_sparse_provider": record.sparse_provider,
            "_sparse_model": record.sparse_model,
            "_sparse_model_version": record.sparse_model_version,
            "_knowledge_collection": record.knowledge_collection,
            "_content_type": record.content_type.value if hasattr(record.content_type, "value") else str(record.content_type),
            "_lifecycle_state": record.lifecycle_state.value if (record.lifecycle_state and hasattr(record.lifecycle_state, "value")) else str(record.lifecycle_state) if record.lifecycle_state else None,
            "_status": str(record.status),
            "_index_version": record.index_version,
        })

        return models.PointStruct(
            id=point_id,
            vector=vector_dict,
            payload=payload,
        )

    def _convert_point_to_record(self, point: Any) -> IndexRecord:
        """Convert a Qdrant point back to a provider-neutral IndexRecord."""
        payload = point.payload or {}
        record_id = payload.get("_index_record_id", str(point.id))

        vectors = point.vector or {}
        dense_vec = None
        if isinstance(vectors, dict) and "dense" in vectors:
            dense_vec = vectors["dense"]

        sparse_vec = None
        if isinstance(vectors, dict) and "sparse" in vectors:
            sp = vectors["sparse"]
            if hasattr(sp, "indices") and hasattr(sp, "values"):
                sparse_vec = SparseVector(indices=list(sp.indices), values=list(sp.values))

        # Reconstruct clean user payload metadata without internal reserved underscore keys
        clean_payload = {k: v for k, v in payload.items() if not k.startswith("_")}

        return IndexRecord(
            index_record_id=record_id,
            source_id=payload.get("_source_id", "unknown"),
            artifact_id=payload.get("_artifact_id"),
            document_id=payload.get("_document_id", "unknown"),
            version_id=payload.get("_version_id", "unknown"),
            section_id=payload.get("_section_id"),
            knowledge_unit_id=payload.get("_knowledge_unit_id"),
            chunk_id=payload.get("_chunk_id"),
            dense_embedding_id=payload.get("_dense_embedding_id"),
            sparse_representation_id=payload.get("_sparse_representation_id"),
            dense_provider=payload.get("_dense_provider"),
            dense_model=payload.get("_dense_model"),
            dense_model_version=payload.get("_dense_model_version"),
            sparse_provider=payload.get("_sparse_provider"),
            sparse_model=payload.get("_sparse_model"),
            sparse_model_version=payload.get("_sparse_model_version"),
            dense_dimension=len(dense_vec) if dense_vec else None,
            dense_vector=dense_vec,
            sparse_vector=sparse_vec,
            payload_metadata=clean_payload,
            knowledge_collection=payload.get("_knowledge_collection"),
            content_type=payload.get("_content_type", KnowledgeContentType.TEXT),
            lifecycle_state=payload.get("_lifecycle_state", KnowledgeLifecycleState.INDEXED),
            status=IndexStatus.INDEXED,
            index_version=payload.get("_index_version", "1.0.0"),
        )

    def index_record(self, collection_name: str, record: IndexRecord) -> IndexRecord:
        """Index a single record into Qdrant."""
        if not isinstance(record, IndexRecord):
            raise InvalidIndexRecordError("Record must be an instance of IndexRecord.")

        name = collection_name.strip()
        point = self._convert_record_to_point(record)

        try:
            self.client.upsert(
                collection_name=name,
                points=[point],
            )
            indexed = record.model_copy(
                update={
                    "physical_collection_name": name,
                    "status": IndexStatus.INDEXED,
                    "error_message": None,
                }
            )
            return indexed
        except Exception as e:
            raise QdrantAdapterError(f"Failed to index record '{record.index_record_id}' in collection '{name}': {str(e)}")

    def index_batch(self, collection_name: str, records: List[IndexRecord]) -> IndexBatchResult:
        """Index a batch of records into Qdrant with partial failure handling."""
        name = collection_name.strip()
        successful: List[IndexRecord] = []
        failed: List[Dict[str, Any]] = []

        points_to_upsert: List[Any] = []
        records_to_upsert: List[IndexRecord] = []

        for record in records:
            try:
                if not isinstance(record, IndexRecord):
                    raise InvalidIndexRecordError("Record must be an instance of IndexRecord.")
                point = self._convert_record_to_point(record)
                points_to_upsert.append(point)
                records_to_upsert.append(record)
            except Exception as e:
                failed.append({
                    "index_record_id": getattr(record, "index_record_id", "unknown"),
                    "error": str(e),
                    "code": getattr(e, "error_code", "INVALID_RECORD"),
                    "retryable": False,
                })

        if points_to_upsert:
            try:
                self.client.upsert(
                    collection_name=name,
                    points=points_to_upsert,
                )
                for rec in records_to_upsert:
                    indexed = rec.model_copy(
                        update={
                            "physical_collection_name": name,
                            "status": IndexStatus.INDEXED,
                            "error_message": None,
                        }
                    )
                    successful.append(indexed)
            except Exception as e:
                # If batch upsert failed, attempt individual point upserts to isolate partial failures
                for rec, pt in zip(records_to_upsert, points_to_upsert):
                    try:
                        self.client.upsert(
                            collection_name=name,
                            points=[pt],
                        )
                        indexed = rec.model_copy(
                            update={
                                "physical_collection_name": name,
                                "status": IndexStatus.INDEXED,
                                "error_message": None,
                            }
                        )
                        successful.append(indexed)
                    except Exception as single_err:
                        failed.append({
                            "index_record_id": rec.index_record_id,
                            "error": str(single_err),
                            "code": "QDRANT_UPSERT_FAILURE",
                            "retryable": True,
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
        """Delete an index record from Qdrant by ID."""
        name = collection_name.strip()
        point_id = _to_qdrant_point_id(record_id)
        try:
            self.client.delete(
                collection_name=name,
                points_selector=models.PointIdsList(points=[point_id]),
            )
            return True
        except Exception as e:
            raise QdrantAdapterError(f"Failed to delete record '{record_id}' from collection '{name}': {str(e)}")

    def get_record(self, collection_name: str, record_id: str) -> Optional[IndexRecord]:
        """Retrieve an index record from Qdrant by ID."""
        name = collection_name.strip()
        point_id = _to_qdrant_point_id(record_id)
        try:
            res = self.client.retrieve(
                collection_name=name,
                ids=[point_id],
                with_payload=True,
                with_vectors=True,
            )
            if res and len(res) > 0:
                return self._convert_point_to_record(res[0])
            return None
        except Exception as e:
            raise QdrantAdapterError(f"Failed to retrieve record '{record_id}' from collection '{name}': {str(e)}")

    def search_dense(
        self,
        collection_name: str,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        with_record: bool = True,
    ) -> List[DenseSearchResult]:
        """Perform dense vector search in Qdrant."""
        name = collection_name.strip()
        try:
            filter_conditions = None
            if filters:
                must_clauses = [
                    models.FieldCondition(key=k, match=models.MatchValue(value=v))
                    for k, v in filters.items()
                ]
                filter_conditions = models.Filter(must=must_clauses)

            if hasattr(self.client, "query_points"):
                q_res = self.client.query_points(
                    collection_name=name,
                    query=query_vector,
                    using="dense",
                    limit=top_k,
                    query_filter=filter_conditions,
                    with_payload=True,
                )
                hits = q_res.points
            else:
                hits = self.client.search(
                    collection_name=name,
                    query_vector=models.NamedVector(name="dense", vector=query_vector),
                    limit=top_k,
                    query_filter=filter_conditions,
                    with_payload=True,
                )

            results: List[DenseSearchResult] = []
            for hit in hits:
                payload = hit.payload or {}
                rec_id = payload.get("_index_record_id", str(hit.id))
                rec = None
                if with_record:
                    rec = self.get_record(name, rec_id)

                results.append(
                    DenseSearchResult(
                        record_id=rec_id,
                        score=hit.score,
                        record=rec,
                        payload={k: v for k, v in payload.items() if not k.startswith("_")},
                    )
                )
            return results
        except Exception as e:
            raise QdrantAdapterError(f"Dense search failed in '{name}': {str(e)}")

    def search_sparse(
        self,
        collection_name: str,
        query_indices: List[int],
        query_values: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        with_record: bool = True,
    ) -> List[SparseSearchResult]:
        """Perform sparse vector search in Qdrant against the 'sparse' vector index."""
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

            if hasattr(self.client, "query_points"):
                q_res = self.client.query_points(
                    collection_name=name,
                    query=sparse_query,
                    using="sparse",
                    limit=top_k,
                    query_filter=filter_conditions,
                    with_payload=True,
                )
                hits = q_res.points
            else:
                hits = self.client.search(
                    collection_name=name,
                    query_vector=models.NamedSparseVector(name="sparse", vector=sparse_query),
                    limit=top_k,
                    query_filter=filter_conditions,
                    with_payload=True,
                )

            results: List[SparseSearchResult] = []
            for hit in hits:
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

    def get_status(self, collection_name: str) -> Dict[str, Any]:
        """Return collection status and count metrics."""
        name = collection_name.strip()
        try:
            info = self.client.get_collection(collection_name=name)
            count_res = self.client.count(collection_name=name)
            return {
                "collection_name": name,
                "status": str(info.status),
                "record_count": count_res.count if hasattr(count_res, "count") else 0,
                "vectors_count": getattr(info, "vectors_count", None),
                "points_count": getattr(info, "points_count", None),
            }
        except Exception as e:
            raise QdrantAdapterError(f"Failed to get collection status for '{name}': {str(e)}")
