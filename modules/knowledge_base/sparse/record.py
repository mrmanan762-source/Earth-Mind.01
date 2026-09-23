"""Sparse Representation Record Domain Model for C.2 Knowledge Base.

Defines storage-independent derived sparse vector representations of canonical knowledge:
- SparseRepresentationRecord

Sparse representations are DERIVED representations, NOT canonical knowledge.
The canonical KnowledgeUnit/Chunk remains the authoritative source of truth.
Deleting or regenerating a sparse representation leaves original canonical knowledge intact.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator

from core.schemas.embedding import SparseVector
from core.schemas.sparse import validate_sparse_vector
from core.errors.exceptions import SparseVectorValidationError
from modules.knowledge_base.enums import KnowledgeContentType
from modules.knowledge_base.metadata import CanonicalMetadata
from modules.knowledge_base.provenance import Provenance


def _validate_non_empty_str(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{field_name}' must be a non-empty string.")
    return value.strip()


class SparseRepresentationRecord(BaseModel):
    """Domain record representing a derived sparse vector representation for canonical knowledge.

    Traceable to parent canonical source, document, version, and chunk/knowledge_unit.
    """

    representation_id: str = Field(..., description="Unique sparse representation identifier (e.g. 'sp_...')")

    # Upstream Canonical Lineage References
    source_id: str = Field(..., description="Origin source identifier")
    document_id: str = Field(..., description="Logical document identifier")
    version_id: str = Field(..., description="Document version identifier")
    chunk_id: Optional[str] = Field(None, description="Associated retrieval chunk identifier")
    knowledge_unit_id: Optional[str] = Field(None, description="Associated knowledge unit identifier")

    # Provider, Model & Index-Space Traceability
    representation_type: str = Field("SPARSE", description="Type of representation (SPARSE, LEXICAL, LEARNED_SPARSE)")
    provider: str = Field(..., description="Sparse representation provider name (e.g. 'bm25', 'splade', 'fake')")
    model: str = Field(..., description="Sparse model identifier (e.g. 'earthmind-sparse-v1')")
    model_version: str = Field("1.0.0", description="Sparse model version")
    vocabulary_id: Optional[str] = Field(None, description="Vocabulary or index-space identifier where applicable")
    vocabulary_size: Optional[int] = Field(None, ge=1, description="Vocabulary size or feature dimension where applicable")

    # Vector Payload
    sparse_vector: SparseVector = Field(..., description="Sparse vector payload (indices, values, terms)")

    # Content Classification & State
    content_type: KnowledgeContentType = Field(KnowledgeContentType.TEXT, description="Original content type")
    status: str = Field("ACTIVE", description="Sparse record status ('ACTIVE', 'SUPERSEDED', 'DEPRECATED', 'FAILED')")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")

    # Metadata & Provenance
    metadata: Union[CanonicalMetadata, Dict[str, Any]] = Field(default_factory=dict, description="Extensible metadata or dict")
    provenance: Optional[Provenance] = Field(None, description="Processing provenance chain")

    @field_validator("representation_id", "source_id", "document_id", "version_id", "provider", "model", "model_version")
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
    def validate_canonical_reference_and_sparse_vector(self) -> "SparseRepresentationRecord":
        # 1. Require at least chunk_id or knowledge_unit_id for granular canonical traceability
        if not self.chunk_id and not self.knowledge_unit_id:
            raise ValueError("SparseRepresentationRecord must reference at least one of 'chunk_id' or 'knowledge_unit_id'.")

        # 2. Validate sparse_vector index/value alignment, valid indices, and numeric weights
        try:
            validate_sparse_vector(self.sparse_vector, vocabulary_size=self.vocabulary_size)
        except ValueError as e:
            raise SparseVectorValidationError(str(e))

        return self
