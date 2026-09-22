import hashlib
import time
from typing import List, Optional, Dict, Any

from core.interfaces.embedding import IEmbeddingProvider
from core.schemas.embedding import (
    EmbeddingRequest,
    EmbeddingResponse,
    DenseEmbeddingVector,
    SparseVector,
    ProviderMetadata,
    ModelMetadata,
    EmbeddingMetadata,
    EmbeddingStatus,
)
from core.errors.exceptions import (
    InvalidEmbeddingInputError,
    EmbeddingProviderUnavailableError,
    EmbeddingConfigurationError,
    EmbeddingRateLimitError,
    EmbeddingTimeoutError,
    EmbeddingExecutionError,
    EmbeddingDimensionMismatchError,
)


class FakeEmbeddingProvider(IEmbeddingProvider):
    """Fake/Mock embedding provider implementation for tests and offline execution."""

    def __init__(
        self,
        provider_name: str = "fake",
        model_name: str = "earthmind-embed-v1",
        model_version: str = "1.0.0",
        dimension: int = 384,
        license: str = "Apache-2.0",
        provenance: str = "EarthMind Synthetic Vector Generator",
        available: bool = True,
        endpoint: Optional[str] = None,
        credential_reference: Optional[str] = None,
        require_credential: bool = False,
        simulated_error: Optional[str] = None,
    ):
        self.provider_name = provider_name
        self.model_name = model_name
        self.model_version = model_version
        self.dimension = dimension
        self.license = license
        self.provenance = provenance
        self._available = available
        self.endpoint = endpoint
        self.credential_reference = credential_reference
        self.require_credential = require_credential
        self.simulated_error = simulated_error

    def is_available(self) -> bool:
        return self._available

    def validate_config(self) -> bool:
        if self.dimension <= 0:
            raise EmbeddingConfigurationError(f"Invalid dimension {self.dimension}. Must be > 0.")
        if self.require_credential and not self.credential_reference:
            raise EmbeddingConfigurationError("Missing required credential reference for provider.")
        return True

    def get_provider_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_name=self.provider_name,
            provider_type="fake_mock",
            is_mock=True,
            endpoint=self.endpoint,
            credential_reference=self.credential_reference,
            extra={"require_credential": self.require_credential},
        )

    def get_model_metadata(self) -> ModelMetadata:
        return ModelMetadata(
            model_name=self.model_name,
            model_version=self.model_version,
            dimension=self.dimension,
            license=self.license,
            provenance=self.provenance,
            commercial_use_allowed=True,
        )

    def get_dimension(self) -> int:
        return self.dimension

    def _generate_synthetic_vector(self, text: str, index: int) -> List[float]:
        """Generate deterministic pseudo-random float vector based on sha256 hash of text."""
        vector = []
        # Create base seed from text and index
        seed = f"{text}_{index}".encode("utf-8")
        hash_bytes = hashlib.sha256(seed).digest()

        for i in range(self.dimension):
            # Deterministically produce values in range [-1.0, 1.0]
            byte_val = hash_bytes[(i + index) % len(hash_bytes)]
            val = ((byte_val / 255.0) * 2.0) - 1.0
            vector.append(round(val, 6))

        return vector

    def _generate_synthetic_sparse(self, text: str) -> SparseVector:
        """Generate synthetic sparse vector representation (terms and indices)."""
        words = [w.lower().strip() for w in text.split() if w.strip()]
        terms: Dict[str, float] = {}
        indices: List[int] = []
        values: List[float] = []

        for idx, word in enumerate(words):
            if word not in terms:
                # Term weight based on frequency / length
                weight = round(1.0 / (idx + 1), 4)
                terms[word] = weight
                term_idx = int(hashlib.md5(word.encode("utf-8")).hexdigest()[:4], 16) % 10000
                indices.append(term_idx)
                values.append(weight)

        return SparseVector(
            indices=indices,
            values=values,
            terms=terms,
            dimension=10000,
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        start_time = time.time()

        if not self.is_available():
            raise EmbeddingProviderUnavailableError(self.provider_name, "Fake provider set to unavailable.")

        self.validate_config()

        # Check request validity
        try:
            request.validate_request()
        except ValueError as e:
            raise InvalidEmbeddingInputError(str(e))

        # Check for simulated errors
        if self.simulated_error == "rate_limit":
            raise EmbeddingRateLimitError(self.provider_name, "Simulated rate limit error.")
        elif self.simulated_error == "timeout":
            raise EmbeddingTimeoutError(self.provider_name, 30.0)
        elif self.simulated_error == "execution_error":
            raise EmbeddingExecutionError(self.provider_name, "Simulated internal execution error.")
        elif self.simulated_error == "dimension_mismatch":
            # Intentionally produce incorrect dimension vector to test validation
            invalid_response_dim = self.dimension + 10
            embeddings = [[0.1] * invalid_response_dim for _ in request.texts]
            dense_vectors = [
                DenseEmbeddingVector(vector=[0.1] * invalid_response_dim, dimension=invalid_response_dim, index=i)
                for i in range(len(request.texts))
            ]
            return EmbeddingResponse(
                embeddings=embeddings,
                dense_vectors=dense_vectors,
                status=EmbeddingStatus.SUCCESS,
                provider_metadata=self.get_provider_metadata(),
                model_metadata=self.get_model_metadata(),
                dimension=invalid_response_dim,
                metadata=EmbeddingMetadata(
                    provider=self.provider_name,
                    model=self.model_name,
                    model_version=self.model_version,
                    dimension=invalid_response_dim,
                    timestamp=time.time(),
                ),
            )

        embeddings: List[List[float]] = []
        dense_vectors: List[DenseEmbeddingVector] = []
        sparse_vectors: Optional[List[SparseVector]] = [] if request.include_sparse else None

        for idx, text in enumerate(request.texts):
            vec = self._generate_synthetic_vector(text, idx)
            embeddings.append(vec)
            chunk_id = request.chunk_ids[idx] if request.chunk_ids else None
            dense_vectors.append(
                DenseEmbeddingVector(
                    vector=vec,
                    dimension=self.dimension,
                    index=idx,
                )
            )
            if request.include_sparse and sparse_vectors is not None:
                sparse_vectors.append(self._generate_synthetic_sparse(text))

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        return EmbeddingResponse(
            embeddings=embeddings,
            dense_vectors=dense_vectors,
            sparse_vectors=sparse_vectors,
            status=EmbeddingStatus.SUCCESS,
            provider_metadata=self.get_provider_metadata(),
            model_metadata=self.get_model_metadata(),
            dimension=self.dimension,
            metadata=EmbeddingMetadata(
                provider=self.provider_name,
                model=self.model_name,
                model_version=self.model_version,
                dimension=self.dimension,
                processing_time_ms=elapsed_ms,
                source_id=request.source_id,
            ),
        )
