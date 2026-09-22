import time
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class EmbeddingStatus(str, Enum):
    """Operational status of embedding response or provider."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"
    PARTIAL = "PARTIAL"


class ProviderMetadata(BaseModel):
    """Metadata describing the embedding provider."""
    provider_name: str = Field(..., description="Name of the embedding provider")
    provider_type: str = Field("adapter", description="Provider type e.g. adapter, remote_api, local_model")
    is_mock: bool = Field(False, description="Whether this is a mock or fake provider")
    endpoint: Optional[str] = Field(None, description="Optional endpoint URL or API route")
    credential_reference: Optional[str] = Field(None, description="Optional non-secret credential key reference")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Additional provider metadata")


class ModelMetadata(BaseModel):
    """Metadata describing the embedding model, version, and license."""
    model_name: str = Field(..., description="Name of the embedding model")
    model_version: str = Field("1.0.0", description="Version string of the embedding model")
    dimension: Optional[int] = Field(None, description="Embedding vector dimension")
    license: str = Field("Apache-2.0", description="Model license terms")
    provenance: Optional[str] = Field(None, description="Model origin and provenance details")
    commercial_use_allowed: Optional[bool] = Field(True, description="Whether model is safe for commercial use")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Additional model metadata")


class DenseEmbeddingVector(BaseModel):
    """Container for a single dense embedding vector."""
    vector: List[float] = Field(..., description="Dense embedding float values")
    dimension: int = Field(..., description="Dimension of the vector")
    index: int = Field(0, description="Position index corresponding to input text in request")


class SparseVector(BaseModel):
    """Abstraction boundary for sparse vector representations (e.g., BM25/SPLADE term weights)."""
    indices: List[int] = Field(default_factory=list, description="Sparse feature or term indices")
    values: List[float] = Field(default_factory=list, description="Sparse weights corresponding to indices")
    terms: Dict[str, float] = Field(default_factory=dict, description="Sparse term-to-weight dictionary")
    dimension: Optional[int] = Field(None, description="Optional sparse space dimension")


class EmbeddingMetadata(BaseModel):
    """Generation and traceability metadata for an embedding result."""
    provider: str = Field(..., description="Provider name")
    model: str = Field(..., description="Model name")
    model_version: str = Field(..., description="Model version")
    dimension: int = Field(..., description="Vector dimension")
    config_version: str = Field("1.0.0", description="Embedding configuration version")
    timestamp: float = Field(default_factory=lambda: time.time(), description="Epoch timestamp of generation")
    processing_time_ms: Optional[float] = Field(None, description="Latency in milliseconds")
    input_tokens: Optional[int] = Field(None, description="Token count if available")
    chunk_id: Optional[str] = Field(None, description="Optional source chunk identifier")
    source_id: Optional[str] = Field(None, description="Optional source document identifier")
    custom_metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional generation metadata")


class EmbeddingRequest(BaseModel):
    """Request payload for generating embeddings."""
    texts: List[str] = Field(..., description="List of input text strings to embed")
    chunk_ids: Optional[List[str]] = Field(None, description="Optional chunk identifiers matching texts")
    source_id: Optional[str] = Field(None, description="Optional parent source identifier")
    include_sparse: bool = Field(False, description="Whether to request sparse representations if supported")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific runtime parameters")

    def validate_request(self) -> bool:
        if not self.texts:
            raise ValueError("Embedding request must contain at least one text string.")
        for idx, text in enumerate(self.texts):
            if not isinstance(text, str):
                raise ValueError(f"Input text at index {idx} must be a string.")
        if self.chunk_ids and len(self.chunk_ids) != len(self.texts):
            raise ValueError("When provided, chunk_ids count must match texts count.")
        return True


class EmbeddingResponse(BaseModel):
    """Response structure containing generated dense and optional sparse embeddings."""
    embeddings: List[List[float]] = Field(default_factory=list, description="List of dense vectors as float arrays")
    dense_vectors: List[DenseEmbeddingVector] = Field(default_factory=list, description="List of structured dense vector objects")
    sparse_vectors: Optional[List[SparseVector]] = Field(None, description="Optional list of sparse vector representations")
    status: EmbeddingStatus = Field(EmbeddingStatus.SUCCESS, description="Operation execution status")
    provider_metadata: ProviderMetadata = Field(..., description="Provider metadata")
    model_metadata: ModelMetadata = Field(..., description="Model metadata")
    dimension: int = Field(..., description="Vector dimension")
    metadata: EmbeddingMetadata = Field(..., description="Generation traceability metadata")
    error_message: Optional[str] = Field(None, description="Error description if operation failed")
