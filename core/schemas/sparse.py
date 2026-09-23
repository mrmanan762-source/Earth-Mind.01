"""Sparse Representation Schemas for EarthMind C.2 Knowledge Base."""

import math
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator, model_validator

from core.schemas.embedding import (
    SparseVector,
    EmbeddingStatus,
    ProviderMetadata,
    ModelMetadata,
    EmbeddingMetadata,
)


def validate_sparse_vector(
    sparse_vec: SparseVector, vocabulary_size: Optional[int] = None
) -> None:
    """Validate sparse vector index/value alignment, index values, and numeric weights."""
    if len(sparse_vec.indices) != len(sparse_vec.values):
        raise ValueError(
            f"SparseVector index/value count mismatch: {len(sparse_vec.indices)} indices vs {len(sparse_vec.values)} values."
        )

    for idx, index_val in enumerate(sparse_vec.indices):
        if not isinstance(index_val, int) or index_val < 0:
            raise ValueError(f"SparseVector index at position {idx} must be a non-negative integer, got '{index_val}'.")
        if vocabulary_size is not None and index_val >= vocabulary_size:
            raise ValueError(
                f"SparseVector index {index_val} at position {idx} exceeds vocabulary size limit of {vocabulary_size}."
            )

    for idx, weight in enumerate(sparse_vec.values):
        if not isinstance(weight, (int, float)) or math.isnan(weight) or math.isinf(weight):
            raise ValueError(f"SparseVector weight at position {idx} must be a finite real number, got '{weight}'.")


class SparseRepresentationRequest(BaseModel):
    """Request payload for generating sparse representations."""

    texts: List[str] = Field(..., description="List of input text strings to represent sparsely")
    chunk_ids: Optional[List[str]] = Field(None, description="Optional chunk identifiers matching texts")
    source_id: Optional[str] = Field(None, description="Optional parent source identifier")
    vocabulary_id: Optional[str] = Field(None, description="Optional vocabulary or index-space identifier")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific runtime parameters")

    def validate_request(self) -> bool:
        """Validate request input parameters."""
        if not self.texts:
            raise ValueError("Sparse representation request must contain at least one text string.")
        for idx, text in enumerate(self.texts):
            if not isinstance(text, str):
                raise ValueError(f"Input text at index {idx} must be a string.")
        if self.chunk_ids and len(self.chunk_ids) != len(self.texts):
            raise ValueError("When provided, chunk_ids count must match texts count.")
        return True


class SparseRepresentationResponse(BaseModel):
    """Response structure containing generated sparse vectors."""

    sparse_vectors: List[SparseVector] = Field(
        default_factory=list, description="List of generated sparse vector representations"
    )
    status: EmbeddingStatus = Field(EmbeddingStatus.SUCCESS, description="Operation execution status")
    provider_metadata: ProviderMetadata = Field(..., description="Provider metadata")
    model_metadata: ModelMetadata = Field(..., description="Model metadata")
    vocabulary_id: Optional[str] = Field(None, description="Active vocabulary or index-space identifier")
    vocabulary_size: Optional[int] = Field(None, description="Active vocabulary size or dimension")
    metadata: EmbeddingMetadata = Field(..., description="Generation traceability metadata")
    error_message: Optional[str] = Field(None, description="Error description if operation failed")
