"""Generic ISparseRepresentationProvider Interface for EarthMind C.2 Knowledge Base."""

from typing import Protocol, Optional, runtime_checkable
from core.schemas.embedding import ProviderMetadata, ModelMetadata
from core.schemas.sparse import SparseRepresentationRequest, SparseRepresentationResponse


@runtime_checkable
class ISparseRepresentationProvider(Protocol):
    """Generic, provider-agnostic interface for generating sparse representations."""

    def generate_sparse(
        self, request: SparseRepresentationRequest
    ) -> SparseRepresentationResponse:
        """Generate sparse representations for the given request."""
        ...

    def get_provider_metadata(self) -> ProviderMetadata:
        """Return provider identification and configuration metadata."""
        ...

    def get_model_metadata(self) -> ModelMetadata:
        """Return model metadata including identifier, version, license, and vocabulary details."""
        ...

    def get_vocabulary_id(self) -> Optional[str]:
        """Return vocabulary/index-space identifier if applicable."""
        ...

    def get_vocabulary_size(self) -> Optional[int]:
        """Return vocabulary/index-space size or dimension if applicable."""
        ...

    def is_available(self) -> bool:
        """Return operational availability status of the sparse provider."""
        ...

    def validate_config(self) -> bool:
        """Validate sparse provider configuration and dependencies."""
        ...
