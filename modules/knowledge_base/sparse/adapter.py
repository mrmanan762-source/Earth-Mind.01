"""Sparse Representation Adapter for EarthMind C.2 Knowledge Base."""

from typing import List, Optional
from core.interfaces.sparse import ISparseRepresentationProvider
from core.schemas.embedding import (
    ProviderMetadata,
    ModelMetadata,
    EmbeddingStatus,
)
from core.schemas.sparse import (
    SparseRepresentationRequest,
    SparseRepresentationResponse,
    validate_sparse_vector,
)
from core.errors.exceptions import (
    InvalidSparseInputError,
    SparseProviderUnavailableError,
    InvalidSparseResponseError,
    SparseVectorValidationError,
)
from modules.knowledge_base.sparse.fake_provider import FakeSparseProvider


class SparseRepresentationAdapter:
    """Adapter wrapping an ISparseRepresentationProvider implementation.

    Decouples C.2 Knowledge Base domain logic from concrete sparse models (BM25, SPLADE, etc.).
    Enforces response structure validation and strict provider replacement contracts.
    """

    def __init__(self, provider: ISparseRepresentationProvider):
        if not isinstance(provider, ISparseRepresentationProvider):
            raise InvalidSparseInputError("Provided object does not implement ISparseRepresentationProvider interface.")
        self._provider = provider

    @classmethod
    def default_adapter(cls) -> "SparseRepresentationAdapter":
        """Factory method creating default adapter with FakeSparseProvider."""
        return cls(FakeSparseProvider())

    @property
    def provider(self) -> ISparseRepresentationProvider:
        return self._provider

    def set_provider(self, new_provider: ISparseRepresentationProvider) -> None:
        """Replace active sparse provider dynamically without modifying domain logic."""
        if not isinstance(new_provider, ISparseRepresentationProvider):
            raise InvalidSparseInputError("New provider does not implement ISparseRepresentationProvider interface.")
        self._provider = new_provider

    def is_available(self) -> bool:
        return self._provider.is_available()

    def get_vocabulary_id(self) -> Optional[str]:
        return self._provider.get_vocabulary_id()

    def get_vocabulary_size(self) -> Optional[int]:
        return self._provider.get_vocabulary_size()

    def get_provider_metadata(self) -> ProviderMetadata:
        return self._provider.get_provider_metadata()

    def get_model_metadata(self) -> ModelMetadata:
        return self._provider.get_model_metadata()

    def validate_response(self, response: SparseRepresentationResponse, expected_count: int) -> bool:
        """Validate returned sparse response for count and sparse vector alignment/weights."""
        if not response:
            raise InvalidSparseResponseError("Sparse response object is None.")

        if response.status != EmbeddingStatus.SUCCESS:
            return False

        if len(response.sparse_vectors) != expected_count:
            raise InvalidSparseResponseError(
                f"Sparse vector count mismatch: requested {expected_count}, received {len(response.sparse_vectors)}."
            )

        vocab_size = self.get_vocabulary_size()
        for idx, sparse_vec in enumerate(response.sparse_vectors):
            try:
                validate_sparse_vector(sparse_vec, vocabulary_size=vocab_size)
            except ValueError as e:
                raise SparseVectorValidationError(
                    f"Sparse vector at index {idx} failed validation: {str(e)}"
                )

        return True

    def generate_sparse(self, request: SparseRepresentationRequest) -> SparseRepresentationResponse:
        """Generate sparse vectors via active provider adapter with validation."""
        if not self.is_available():
            raise SparseProviderUnavailableError(
                self.get_provider_metadata().provider_name,
                "Sparse adapter provider is unavailable.",
            )

        response = self._provider.generate_sparse(request)
        self.validate_response(response, len(request.texts))
        return response

    def generate_sparse_texts(
        self,
        texts: List[str],
        chunk_ids: Optional[List[str]] = None,
        source_id: Optional[str] = None,
        vocabulary_id: Optional[str] = None,
    ) -> SparseRepresentationResponse:
        """Convenience wrapper for generating sparse representations from raw text strings."""
        request = SparseRepresentationRequest(
            texts=texts,
            chunk_ids=chunk_ids,
            source_id=source_id,
            vocabulary_id=vocabulary_id,
        )
        return self.generate_sparse(request)
