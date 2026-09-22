"""Generic IEmbeddingProvider Interface for EarthMind C.2 Knowledge Base."""

from typing import Protocol, runtime_checkable
from core.schemas.embedding import (
    EmbeddingRequest,
    EmbeddingResponse,
    ProviderMetadata,
    ModelMetadata,
)


@runtime_checkable
class IEmbeddingProvider(Protocol):
    """Generic, provider-agnostic interface for generating vector embeddings."""

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate dense and optional sparse embeddings for the given request."""
        ...

    def get_provider_metadata(self) -> ProviderMetadata:
        """Return provider identification and configuration metadata."""
        ...

    def get_model_metadata(self) -> ModelMetadata:
        """Return model metadata including identifier, version, license, and dimension."""
        ...

    def get_dimension(self) -> int:
        """Return vector dimension for the active provider configuration."""
        ...

    def is_available(self) -> bool:
        """Return operational availability status of the embedding provider."""
        ...

    def validate_config(self) -> bool:
        """Validate embedding provider configuration and dependencies."""
        ...
