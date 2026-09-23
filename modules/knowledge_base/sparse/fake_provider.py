"""Fake/Mock Sparse Representation Provider for EarthMind C.2 Knowledge Base."""

import hashlib
import math
import time
from typing import List, Optional, Dict, Any

from core.interfaces.sparse import ISparseRepresentationProvider
from core.schemas.embedding import (
    SparseVector,
    ProviderMetadata,
    ModelMetadata,
    EmbeddingMetadata,
    EmbeddingStatus,
)
from core.schemas.sparse import (
    SparseRepresentationRequest,
    SparseRepresentationResponse,
)
from core.errors.exceptions import (
    InvalidSparseInputError,
    SparseProviderUnavailableError,
    SparseConfigurationError,
    EmbeddingRateLimitError,
    EmbeddingTimeoutError,
    SparseExecutionError,
)


class FakeSparseProvider(ISparseRepresentationProvider):
    """Fake/Mock sparse provider implementation for tests, offline execution, and development.

    Supports simulating both lexical (BM25-like) and learned (SPLADE-like) sparse representations.
    Produces deterministic, index-ordered sparse vectors.
    """

    def __init__(
        self,
        provider_name: str = "fake_sparse",
        model_name: str = "earthmind-sparse-v1",
        model_version: str = "1.0.0",
        vocabulary_id: str = "agri-vocab-30k",
        vocabulary_size: int = 30000,
        license: str = "Apache-2.0",
        provenance: str = "EarthMind Synthetic Sparse Vector Generator",
        mode: str = "lexical",  # "lexical" or "learned"
        available: bool = True,
        endpoint: Optional[str] = None,
        credential_reference: Optional[str] = None,
        simulated_error: Optional[str] = None,
    ):
        self.provider_name = provider_name
        self.model_name = model_name
        self.model_version = model_version
        self.vocabulary_id = vocabulary_id
        self.vocabulary_size = vocabulary_size
        self.license = license
        self.provenance = provenance
        self.mode = mode
        self._available = available
        self.endpoint = endpoint
        self.credential_reference = credential_reference
        self.simulated_error = simulated_error

    def is_available(self) -> bool:
        return self._available

    def validate_config(self) -> bool:
        if self.vocabulary_size <= 0:
            raise SparseConfigurationError(f"Invalid vocabulary size {self.vocabulary_size}. Must be > 0.")
        return True

    def get_provider_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_name=self.provider_name,
            provider_type="fake_mock_sparse",
            is_mock=True,
            endpoint=self.endpoint,
            credential_reference=self.credential_reference,
            extra={"mode": self.mode},
        )

    def get_model_metadata(self) -> ModelMetadata:
        return ModelMetadata(
            model_name=self.model_name,
            model_version=self.model_version,
            dimension=self.vocabulary_size,
            license=self.license,
            provenance=self.provenance,
            commercial_use_allowed=True,
            extra={
                "vocabulary_id": self.vocabulary_id,
                "vocabulary_size": self.vocabulary_size,
                "sparse_type": self.mode,
            },
        )

    def get_vocabulary_id(self) -> Optional[str]:
        return self.vocabulary_id

    def get_vocabulary_size(self) -> Optional[int]:
        return self.vocabulary_size

    def _generate_synthetic_sparse(self, text: str) -> SparseVector:
        """Generate deterministic, index-sorted sparse vector from input text."""
        words = [w.lower().strip() for w in text.split() if w.strip()]
        term_map: Dict[int, tuple[float, str]] = {}

        for idx, word in enumerate(words):
            # Deterministic index within vocabulary size
            md5_hash = hashlib.md5(word.encode("utf-8")).hexdigest()
            index_val = int(md5_hash[:6], 16) % self.vocabulary_size

            if self.mode == "learned":
                # Simulated learned sparse weight (e.g., Log 1 + TF * term length)
                weight = round(math.log(1 + (len(word) / (idx + 1))), 4)
            else:
                # Lexical BM25-like weight (term frequency contribution)
                existing_weight = term_map[index_val][0] if index_val in term_map else 0.0
                weight = round(existing_weight + (1.0 / (idx + 1)), 4)

            term_map[index_val] = (weight, word)

        # Deterministic sorting by index (ascending)
        sorted_indices = sorted(term_map.keys())
        indices = sorted_indices
        values = [term_map[i][0] for i in sorted_indices]
        terms = {term_map[i][1]: term_map[i][0] for i in sorted_indices}

        return SparseVector(
            indices=indices,
            values=values,
            terms=terms,
            dimension=self.vocabulary_size,
        )

    def generate_sparse(
        self, request: SparseRepresentationRequest
    ) -> SparseRepresentationResponse:
        start_time = time.time()

        if not self.is_available():
            raise SparseProviderUnavailableError(self.provider_name, "Fake sparse provider set to unavailable.")

        self.validate_config()

        try:
            request.validate_request()
        except ValueError as e:
            raise InvalidSparseInputError(str(e))

        if self.simulated_error == "rate_limit":
            raise EmbeddingRateLimitError(self.provider_name, "Simulated sparse rate limit error.")
        elif self.simulated_error == "timeout":
            raise EmbeddingTimeoutError(self.provider_name, 30.0)
        elif self.simulated_error == "execution_error":
            raise SparseExecutionError(self.provider_name, "Simulated internal sparse execution error.")
        elif self.simulated_error == "invalid_indices":
            # Produce invalid negative index
            return SparseRepresentationResponse(
                sparse_vectors=[SparseVector(indices=[-1], values=[1.0], terms={"invalid": 1.0})],
                status=EmbeddingStatus.SUCCESS,
                provider_metadata=self.get_provider_metadata(),
                model_metadata=self.get_model_metadata(),
                vocabulary_id=self.vocabulary_id,
                vocabulary_size=self.vocabulary_size,
                metadata=EmbeddingMetadata(
                    provider=self.provider_name,
                    model=self.model_name,
                    model_version=self.model_version,
                    dimension=self.vocabulary_size,
                ),
            )
        elif self.simulated_error == "invalid_weights":
            # Produce invalid NaN weight
            return SparseRepresentationResponse(
                sparse_vectors=[SparseVector(indices=[10], values=[float("nan")], terms={"nan": float("nan")})],
                status=EmbeddingStatus.SUCCESS,
                provider_metadata=self.get_provider_metadata(),
                model_metadata=self.get_model_metadata(),
                vocabulary_id=self.vocabulary_id,
                vocabulary_size=self.vocabulary_size,
                metadata=EmbeddingMetadata(
                    provider=self.provider_name,
                    model=self.model_name,
                    model_version=self.model_version,
                    dimension=self.vocabulary_size,
                ),
            )
        elif self.simulated_error == "mismatched_alignment":
            # Produce mismatched indices and values length
            return SparseRepresentationResponse(
                sparse_vectors=[SparseVector(indices=[10, 20], values=[1.0], terms={"err": 1.0})],
                status=EmbeddingStatus.SUCCESS,
                provider_metadata=self.get_provider_metadata(),
                model_metadata=self.get_model_metadata(),
                vocabulary_id=self.vocabulary_id,
                vocabulary_size=self.vocabulary_size,
                metadata=EmbeddingMetadata(
                    provider=self.provider_name,
                    model=self.model_name,
                    model_version=self.model_version,
                    dimension=self.vocabulary_size,
                ),
            )

        sparse_vectors: List[SparseVector] = []
        for text in request.texts:
            sparse_vectors.append(self._generate_synthetic_sparse(text))

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        return SparseRepresentationResponse(
            sparse_vectors=sparse_vectors,
            status=EmbeddingStatus.SUCCESS,
            provider_metadata=self.get_provider_metadata(),
            model_metadata=self.get_model_metadata(),
            vocabulary_id=self.vocabulary_id,
            vocabulary_size=self.vocabulary_size,
            metadata=EmbeddingMetadata(
                provider=self.provider_name,
                model=self.model_name,
                model_version=self.model_version,
                dimension=self.vocabulary_size,
                processing_time_ms=elapsed_ms,
                source_id=request.source_id,
            ),
        )
