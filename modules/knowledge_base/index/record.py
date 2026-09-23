"""Index Record and Batch Result Domain Models for C.2 Knowledge Base.

Defines storage-independent index records derived from canonical knowledge and representations:
- IndexRecord
- IndexBatchResult

Index records are DERIVED artifacts, NOT canonical knowledge.
The canonical KnowledgeUnit/Chunk remains the authoritative source of truth.
Deleting or rebuilding an index leaves canonical knowledge intact.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator

from core.schemas.embedding import SparseVector
from core.schemas.sparse import validate_sparse_vector
from core.errors.exceptions import InvalidIndexRecordError, SparseVectorValidationError
from modules.knowledge_base.enums import (
    IndexStatus,
    KnowledgeContentType,
    KnowledgeLifecycleState,
)
from modules.knowledge_base.metadata import CanonicalMetadata
from modules.knowledge_base.provenance import Provenance


def _validate_non_empty_str(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{field_name}' must be a non-empty string.")
    return value.strip()


class IndexRecord(BaseModel):
    """Domain record representing an index-ready searchable record.

    Traceable back to parent canonical source, artifact, document, version, and chunk/knowledge_unit,
    as well as upstream dense and sparse representations.
    """

    index_record_id: str = Field(..., description="Unique index record identifier (e.g. 'idx_...')")

    # Upstream Canonical Lineage References
    source_id: str = Field(..., description="Origin source identifier")
    artifact_id: Optional[str] = Field(None, description="Raw artifact identifier if applicable")
    document_id: str = Field(..., description="Logical document identifier")
    version_id: str = Field(..., description="Document version identifier")
    section_id: Optional[str] = Field(None, description="Section identifier if applicable")
    knowledge_unit_id: Optional[str] = Field(None, description="Associated knowledge unit identifier")
    chunk_id: Optional[str] = Field(None, description="Associated retrieval chunk identifier")

    # Upstream Representation Lineage & Models
    dense_embedding_id: Optional[str] = Field(None, description="Dense embedding record identifier")
    sparse_representation_id: Optional[str] = Field(None, description="Sparse representation record identifier")
    dense_provider: Optional[str] = Field(None, description="Dense provider name (e.g. 'fake', 'openai')")
    dense_model: Optional[str] = Field(None, description="Dense model identifier")
    dense_model_version: Optional[str] = Field("1.0.0", description="Dense model version")
    sparse_provider: Optional[str] = Field(None, description="Sparse provider name (e.g. 'bm25', 'splade')")
    sparse_model: Optional[str] = Field(None, description="Sparse model identifier")
    sparse_model_version: Optional[str] = Field("1.0.0", description="Sparse model version")

    # Vector Payload
    dense_dimension: Optional[int] = Field(None, ge=1, description="Dense vector dimension")
    dense_vector: Optional[List[float]] = Field(None, description="Dense embedding vector array")
    sparse_vector: Optional[SparseVector] = Field(None, description="Sparse vector payload")

    # Filterable Payload & Metadata
    payload_metadata: Dict[str, Any] = Field(default_factory=dict, description="Provider-neutral filterable metadata payload")
    metadata: Union[CanonicalMetadata, Dict[str, Any]] = Field(default_factory=dict, description="Extensible canonical metadata or dict")
    provenance: Optional[Provenance] = Field(None, description="Processing provenance chain")

    # Collection & Operational State
    knowledge_collection: Optional[str] = Field(None, description="Logical knowledge collection name")
    physical_collection_name: Optional[str] = Field(None, description="Mapped physical collection name")
    content_type: KnowledgeContentType = Field(KnowledgeContentType.TEXT, description="Original content type")
    lifecycle_state: Optional[KnowledgeLifecycleState] = Field(KnowledgeLifecycleState.INDEXED, description="Canonical publication lifecycle state")
    status: IndexStatus = Field(IndexStatus.PENDING, description="Index record operational status")
    index_version: str = Field("1.0.0", description="Index schema version")
    error_message: Optional[str] = Field(None, description="Error message if index record construction or persistence failed")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Last update timestamp")

    @field_validator("index_record_id", "source_id", "document_id", "version_id")
    @classmethod
    def validate_required_strings(cls, v: str, info) -> str:
        return _validate_non_empty_str(info.field_name, v)

    @field_validator("artifact_id", "section_id", "knowledge_unit_id", "chunk_id", "dense_embedding_id", "sparse_representation_id")
    @classmethod
    def validate_optional_strings(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None:
            return _validate_non_empty_str(info.field_name, v)
        return None

    @model_validator(mode="after")
    def validate_index_record(self) -> "IndexRecord":
        # 1. Require at least chunk_id or knowledge_unit_id for granular canonical traceability
        if not self.chunk_id and not self.knowledge_unit_id:
            raise InvalidIndexRecordError("IndexRecord must reference at least one of 'chunk_id' or 'knowledge_unit_id'.")

        # 2. Require at least one vector representation (dense or sparse)
        if self.dense_vector is None and self.sparse_vector is None:
            raise InvalidIndexRecordError("IndexRecord must contain at least a dense_vector or sparse_vector.")

        # 3. Dense vector validation
        if self.dense_vector is not None:
            if not isinstance(self.dense_vector, list) or len(self.dense_vector) == 0:
                raise InvalidIndexRecordError("IndexRecord dense_vector must be a non-empty list of float values.")
            for idx, val in enumerate(self.dense_vector):
                if not isinstance(val, (int, float)):
                    raise InvalidIndexRecordError(f"Dense vector element at position {idx} must be numeric float, got '{val}'.")

            actual_dim = len(self.dense_vector)
            if self.dense_dimension is not None and actual_dim != self.dense_dimension:
                raise InvalidIndexRecordError(
                    f"IndexRecord dimension mismatch: explicit dense_dimension is {self.dense_dimension}, "
                    f"but dense_vector length is {actual_dim}."
                )
            elif self.dense_dimension is None:
                self.dense_dimension = actual_dim

        # 4. Sparse vector validation
        if self.sparse_vector is not None:
            try:
                validate_sparse_vector(self.sparse_vector)
            except ValueError as e:
                raise SparseVectorValidationError(f"Sparse vector validation failed: {str(e)}")

        return self


class IndexBatchResult(BaseModel):
    """Result object detailing batch indexing outcome."""

    total_records: int = Field(0, description="Total number of records in batch")
    successful_records: List[IndexRecord] = Field(default_factory=list, description="List of successfully indexed records")
    failed_records: List[Dict[str, Any]] = Field(default_factory=list, description="List of failed record failure details")
    status: IndexStatus = Field(IndexStatus.PENDING, description="Overall batch execution status")
    processing_time_ms: Optional[float] = Field(None, description="Processing latency in milliseconds")
    error_message: Optional[str] = Field(None, description="Optional error message summarizing overall batch failure")
