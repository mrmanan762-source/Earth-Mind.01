"""Embedding Representation Domain Model for C.2 Knowledge Base.

Defines storage-independent derived embedding representations of canonical knowledge:
- EmbeddingRecord / EmbeddingRepresentation

Embeddings are DERIVED representations, NOT canonical knowledge.
The canonical KnowledgeUnit/Chunk remains the authoritative source of truth.
Deleting or regenerating an embedding leaves original canonical knowledge intact.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator

from core.schemas.embedding import DenseEmbeddingVector, SparseVector
from modules.knowledge_base.enums import KnowledgeContentType
from modules.knowledge_base.metadata import CanonicalMetadata
from modules.knowledge_base.provenance import Provenance


def _validate_non_empty_str(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{field_name}' must be a non-empty string.")
    return value.strip()


class EmbeddingRecord(BaseModel):
    """Domain record representing derived dense and/or sparse vector embeddings for canonical knowledge.

    Traceable to parent canonical source, document, version, and chunk/knowledge_unit.
    """

    embedding_id: str = Field(..., description="Unique embedding record identifier (e.g. 'emb_...')")

    # Upstream Canonical Lineage References
    source_id: str = Field(..., description="Origin source identifier")
    document_id: str = Field(..., description="Logical document identifier")
    version_id: str = Field(..., description="Document version identifier")
    chunk_id: Optional[str] = Field(None, description="Associated retrieval chunk identifier")
    knowledge_unit_id: Optional[str] = Field(None, description="Associated knowledge unit identifier")

    # Provider & Model Traceability
    representation_type: str = Field("DENSE", description="Type of representation (DENSE, SPARSE, HYBRID)")
    provider: str = Field(..., description="Embedding provider name (e.g. 'fake', 'openai', 'jina')")
    model: str = Field(..., description="Embedding model identifier (e.g. 'earthmind-embed-v1')")
    model_version: str = Field("1.0.0", description="Embedding model version")

    # Vector Payload
    dimension: Optional[int] = Field(None, ge=1, description="Dense vector dimension")
    dense_vector: Optional[List[float]] = Field(None, description="Dense embedding vector array")
    sparse_vector: Optional[SparseVector] = Field(None, description="Optional sparse representation")

    # Content Classification & State
    content_type: KnowledgeContentType = Field(KnowledgeContentType.TEXT, description="Original content type")
    status: str = Field("ACTIVE", description="Embedding lifecycle status ('ACTIVE', 'SUPERSEDED', 'DEPRECATED', 'FAILED')")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")

    # Metadata & Provenance
    metadata: Union[CanonicalMetadata, Dict[str, Any]] = Field(default_factory=dict, description="Extensible metadata or dict")
    provenance: Optional[Provenance] = Field(None, description="Processing provenance chain")

    @field_validator("embedding_id", "source_id", "document_id", "version_id", "provider", "model", "model_version")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        return _validate_non_empty_str(info.field_name, v)

    @field_validator("chunk_id", "knowledge_unit_id")
    @classmethod
    def validate_optional_strings(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None:
            return _validate_non_empty_str(info.field_name, v)
        return None

    @model_validator(mode="after")
    def validate_canonical_reference_and_vector(self) -> "EmbeddingRecord":
        # 1. Require at least chunk_id or knowledge_unit_id for granular canonical traceability
        if not self.chunk_id and not self.knowledge_unit_id:
            raise ValueError("EmbeddingRecord must reference at least one of 'chunk_id' or 'knowledge_unit_id'.")

        # 2. Check vector dimension consistency if dense_vector and dimension are provided
        if self.dense_vector is not None:
            actual_dim = len(self.dense_vector)
            if self.dimension is not None and actual_dim != self.dimension:
                raise ValueError(
                    f"EmbeddingRecord dimension mismatch: explicit dimension is {self.dimension}, "
                    f"but dense_vector length is {actual_dim}."
                )
            elif self.dimension is None:
                self.dimension = actual_dim

        return self
