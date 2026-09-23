"""Knowledge Index Engine for C.2 Knowledge Base.

Coordinates converting validated derived representations (dense and sparse) into
searchable IndexRecords, preserving canonical lineage and provenance, and persisting
records via a generic IKnowledgeIndexAdapter.
"""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional, Union

from core.errors.exceptions import (
    IndexExecutionError,
    InvalidIndexRecordError,
)
from core.interfaces.index import IKnowledgeIndexAdapter
from modules.knowledge_base.enums import (
    IndexStatus,
    KnowledgeContentType,
    KnowledgeLifecycleState,
)
from modules.knowledge_base.embedding.record import EmbeddingRecord
from modules.knowledge_base.index.collection_strategy import KnowledgeCollectionMapper
from modules.knowledge_base.index.record import IndexBatchResult, IndexRecord
from modules.knowledge_base.metadata import CanonicalMetadata
from modules.knowledge_base.provenance import Provenance
from modules.knowledge_base.sparse.record import SparseRepresentationRecord

# States that cannot be indexed as published retrievable knowledge
FORBIDDEN_INDEX_LIFECYCLE_STATES = {
    KnowledgeLifecycleState.FAILED,
    KnowledgeLifecycleState.REJECTED,
    KnowledgeLifecycleState.INVALID,
    KnowledgeLifecycleState.RETIRED,
    KnowledgeLifecycleState.SUPERSEDED,
}


class KnowledgeIndexEngine:
    """Engine responsible for building index records and coordinating index persistence."""

    def __init__(
        self,
        adapter: IKnowledgeIndexAdapter,
        collection_mapper: Optional[KnowledgeCollectionMapper] = None,
        enforce_publication_lifecycle: bool = True,
    ):
        self.adapter = adapter
        self.collection_mapper = collection_mapper or KnowledgeCollectionMapper()
        self.enforce_publication_lifecycle = enforce_publication_lifecycle

    def extract_filterable_payload(
        self,
        metadata: Union[CanonicalMetadata, Dict[str, Any]],
        source_id: str,
        document_id: str,
        version_id: str,
        chunk_id: Optional[str] = None,
        knowledge_unit_id: Optional[str] = None,
        section_id: Optional[str] = None,
        knowledge_collection: Optional[str] = None,
        lifecycle_state: Optional[Union[KnowledgeLifecycleState, str]] = None,
        content_type: Optional[Union[KnowledgeContentType, str]] = None,
    ) -> Dict[str, Any]:
        """Extract provider-neutral filterable metadata payload for retrieval indexing."""
        payload: Dict[str, Any] = {
            "source_id": source_id,
            "document_id": document_id,
            "version_id": version_id,
        }

        if chunk_id:
            payload["chunk_id"] = chunk_id
        if knowledge_unit_id:
            payload["knowledge_unit_id"] = knowledge_unit_id
        if section_id:
            payload["section_id"] = section_id
        if knowledge_collection:
            payload["knowledge_collection"] = knowledge_collection
        if lifecycle_state:
            payload["lifecycle_state"] = str(lifecycle_state)
        if content_type:
            payload["content_type"] = str(content_type)

        meta_dict = metadata.model_dump() if isinstance(metadata, CanonicalMetadata) else (metadata or {})

        # Extract domain & filterable attributes from canonical metadata
        for field in [
            "language", "region", "crop", "crop_stage", "season", "topic", "domain",
            "quality_status", "review_status", "access_policy", "visibility",
            "publication_status", "timestamp"
        ]:
            val = meta_dict.get(field)
            if val is not None:
                payload[field] = str(val) if isinstance(val, (KnowledgeLifecycleState, KnowledgeContentType)) else val

        return payload

    def build_index_record(
        self,
        dense_record: Optional[EmbeddingRecord] = None,
        sparse_record: Optional[SparseRepresentationRecord] = None,
        index_record_id: Optional[str] = None,
        knowledge_collection: Optional[str] = None,
        metadata: Optional[Union[CanonicalMetadata, Dict[str, Any]]] = None,
        provenance: Optional[Provenance] = None,
        lifecycle_state: Optional[KnowledgeLifecycleState] = None,
    ) -> IndexRecord:
        """Build a validated, traceable IndexRecord from dense and/or sparse representation records."""
        if dense_record is None and sparse_record is None:
            raise InvalidIndexRecordError("Cannot build IndexRecord: at least one of dense_record or sparse_record is required.")

        # Determine lineage reference fields from records
        ref = dense_record or sparse_record
        source_id = ref.source_id
        document_id = ref.document_id
        version_id = ref.version_id
        chunk_id = ref.chunk_id
        knowledge_unit_id = ref.knowledge_unit_id

        # Verify lineage consistency if both dense and sparse are provided
        if dense_record and sparse_record:
            if dense_record.source_id != sparse_record.source_id or dense_record.document_id != sparse_record.document_id:
                raise InvalidIndexRecordError("Dense and sparse representation records have mismatched canonical lineage.")

        # Determine index record ID deterministically if not explicitly passed
        if not index_record_id:
            target_id = chunk_id or knowledge_unit_id or "rec"
            index_record_id = f"idx_{target_id}"

        # Combine or fallback metadata/provenance
        record_metadata = metadata or (dense_record.metadata if dense_record else sparse_record.metadata)
        record_provenance = provenance or (dense_record.provenance if dense_record else sparse_record.provenance)

        active_lifecycle_state = lifecycle_state or KnowledgeLifecycleState.INDEXED

        # Enforce publication lifecycle check if enabled
        if self.enforce_publication_lifecycle and active_lifecycle_state in FORBIDDEN_INDEX_LIFECYCLE_STATES:
            raise InvalidIndexRecordError(
                f"Cannot index record with lifecycle state '{active_lifecycle_state}'. "
                "Only non-failed, valid knowledge can be indexed."
            )

        payload_meta = self.extract_filterable_payload(
            metadata=record_metadata,
            source_id=source_id,
            document_id=document_id,
            version_id=version_id,
            chunk_id=chunk_id,
            knowledge_unit_id=knowledge_unit_id,
            knowledge_collection=knowledge_collection,
            lifecycle_state=active_lifecycle_state,
            content_type=ref.content_type,
        )

        return IndexRecord(
            index_record_id=index_record_id,
            source_id=source_id,
            document_id=document_id,
            version_id=version_id,
            chunk_id=chunk_id,
            knowledge_unit_id=knowledge_unit_id,
            dense_embedding_id=dense_record.embedding_id if dense_record else None,
            sparse_representation_id=sparse_record.representation_id if sparse_record else None,
            dense_provider=dense_record.provider if dense_record else None,
            dense_model=dense_record.model if dense_record else None,
            dense_model_version=dense_record.model_version if dense_record else None,
            sparse_provider=sparse_record.provider if sparse_record else None,
            sparse_model=sparse_record.model if sparse_record else None,
            sparse_model_version=sparse_record.model_version if sparse_record else None,
            dense_dimension=dense_record.dimension if dense_record else None,
            dense_vector=dense_record.dense_vector if dense_record else None,
            sparse_vector=sparse_record.sparse_vector if sparse_record else None,
            payload_metadata=payload_meta,
            metadata=record_metadata,
            provenance=record_provenance,
            knowledge_collection=knowledge_collection,
            content_type=ref.content_type,
            lifecycle_state=active_lifecycle_state,
            status=IndexStatus.PENDING,
        )

    def index_record(
        self, record: IndexRecord, logical_collection: Optional[str] = None
    ) -> IndexRecord:
        """Persist a single IndexRecord using the configured adapter."""
        target_collection = logical_collection or record.knowledge_collection
        physical_name = self.collection_mapper.get_physical_collection_name(target_collection)

        if record.dense_dimension:
            self.adapter.ensure_collection_exists(physical_name, dense_dim=record.dense_dimension)
        else:
            self.adapter.create_collection(physical_name)

        return self.adapter.index_record(physical_name, record)

    def index_batch(
        self, records: List[IndexRecord], logical_collection: Optional[str] = None
    ) -> IndexBatchResult:
        """Persist a batch of IndexRecords with structured result tracking."""
        if not records:
            return IndexBatchResult(total_records=0, status=IndexStatus.INDEXED)

        start_time = time.time()
        target_collection = logical_collection or records[0].knowledge_collection
        physical_name = self.collection_mapper.get_physical_collection_name(target_collection)

        dense_dim = next((r.dense_dimension for r in records if r.dense_dimension), None)
        if dense_dim:
            self.adapter.ensure_collection_exists(physical_name, dense_dim=dense_dim)
        else:
            self.adapter.create_collection(physical_name)

        result = self.adapter.index_batch(physical_name, records)
        elapsed_ms = (time.time() - start_time) * 1000.0
        result.processing_time_ms = round(elapsed_ms, 2)
        return result

    def update_record(
        self, record: IndexRecord, logical_collection: Optional[str] = None
    ) -> IndexRecord:
        """Update an existing IndexRecord."""
        target_collection = logical_collection or record.knowledge_collection
        physical_name = self.collection_mapper.get_physical_collection_name(target_collection)
        return self.adapter.update_record(physical_name, record)

    def delete_record(
        self, record_id: str, logical_collection: Optional[str] = None
    ) -> bool:
        """Delete an index record by ID."""
        physical_name = self.collection_mapper.get_physical_collection_name(logical_collection)
        return self.adapter.delete_record(physical_name, record_id)

    def get_record(
        self, record_id: str, logical_collection: Optional[str] = None
    ) -> Optional[IndexRecord]:
        """Retrieve an index record by ID."""
        physical_name = self.collection_mapper.get_physical_collection_name(logical_collection)
        return self.adapter.get_record(physical_name, record_id)

    def rebuild_index(
        self, records: List[IndexRecord], logical_collection: Optional[str] = None
    ) -> IndexBatchResult:
        """Rebuild index for a collection from canonical records & representations."""
        return self.index_batch(records, logical_collection=logical_collection)
