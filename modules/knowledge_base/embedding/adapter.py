from typing import List, Optional, Any
from core.interfaces.embedding import IEmbeddingProvider
from core.config.settings import EmbeddingConfig
from core.schemas.embedding import (
    EmbeddingRequest,
    EmbeddingResponse,
    ProviderMetadata,
    ModelMetadata,
    EmbeddingStatus,
)
from core.errors.exceptions import (
    InvalidEmbeddingInputError,
    EmbeddingDimensionMismatchError,
    InvalidEmbeddingResponseError,
    EmbeddingProviderUnavailableError,
)
from modules.knowledge_base.embedding.fake_provider import FakeEmbeddingProvider
from modules.knowledge_base.embedding.self_hosted import SelfHostedEmbeddingProvider
from modules.knowledge_base.embedding.api_provider import APIEmbeddingProvider


class EmbeddingAdapter:
    """Adapter wrapping an IEmbeddingProvider implementation.

    Decouples C.2 Knowledge Base domain logic from provider SDKs and concrete models.
    Enforces validation and strict provider replacement contracts.
    """

    def __init__(self, provider: IEmbeddingProvider):
        if not isinstance(provider, IEmbeddingProvider):
            raise InvalidEmbeddingInputError("Provided object does not implement IEmbeddingProvider interface.")
        self._provider = provider

    @classmethod
    def from_config(cls, config: EmbeddingConfig) -> "EmbeddingAdapter":
        """Factory method creating an EmbeddingAdapter from EmbeddingConfig."""
        prov_name = config.provider.lower()

        if prov_name in ("self_hosted", "sentence_transformers", "huggingface", "local"):
            provider = SelfHostedEmbeddingProvider(
                provider_name=config.provider,
                model_name_or_path=config.model,
                model_version=config.model_version,
                dimension=config.dimension,
                license=config.license,
                provenance=config.provenance or "https://huggingface.co/" + config.model,
                device=config.device,
                batch_size=config.batch_size,
                max_length=config.max_length,
                normalize_embeddings=config.normalize,
                execution_mode=config.execution_mode,
                allow_download=config.allow_download,
            )
        elif prov_name in ("api", "remote_api", "jina", "openai", "cohere"):
            provider = APIEmbeddingProvider(
                provider_name=config.provider,
                model_name=config.model,
                model_version=config.model_version,
                dimension=config.dimension,
                endpoint=config.endpoint,
                credential_reference=config.credential_reference,
                timeout=config.timeout,
            )
        elif prov_name in ("fake", "mock", "dummy"):
            provider = FakeEmbeddingProvider(
                provider_name=config.provider,
                model_name=config.model,
                model_version=config.model_version,
                dimension=config.dimension,
                endpoint=config.endpoint,
                credential_reference=config.credential_reference,
                license=config.license,
                provenance=config.provenance or "EarthMind Prototype Embedding Standard",
            )
        else:
            # Fallback or generic self-hosted default
            provider = SelfHostedEmbeddingProvider(
                provider_name=config.provider,
                model_name_or_path=config.model,
                model_version=config.model_version,
                dimension=config.dimension,
                license=config.license,
                provenance=f"Adapter wrapper for {config.provider}",
            )
        return cls(provider)

    @property
    def provider(self) -> IEmbeddingProvider:
        return self._provider

    def set_provider(self, new_provider: IEmbeddingProvider) -> None:
        """Replace active embedding provider dynamically without modifying domain logic."""
        if not isinstance(new_provider, IEmbeddingProvider):
            raise InvalidEmbeddingInputError("New provider does not implement IEmbeddingProvider interface.")
        self._provider = new_provider

    def is_available(self) -> bool:
        return self._provider.is_available()

    def get_dimension(self) -> int:
        return self._provider.get_dimension()

    def get_provider_metadata(self) -> ProviderMetadata:
        return self._provider.get_provider_metadata()

    def get_model_metadata(self) -> ModelMetadata:
        return self._provider.get_model_metadata()

    def validate_response(self, response: EmbeddingResponse, expected_count: int) -> bool:
        """Validate returned embedding response for dimension and item consistency."""
        if not response:
            raise InvalidEmbeddingResponseError("Embedding response object is None.")

        if response.status != EmbeddingStatus.SUCCESS:
            return False

        if len(response.embeddings) != expected_count:
            raise InvalidEmbeddingResponseError(
                f"Embedding count mismatch: requested {expected_count}, received {len(response.embeddings)}."
            )

        expected_dim = self.get_dimension()
        for idx, vec in enumerate(response.embeddings):
            if len(vec) != expected_dim:
                raise EmbeddingDimensionMismatchError(
                    expected_dim=expected_dim,
                    actual_dim=len(vec),
                    details=f"Vector at index {idx} failed dimension check.",
                )

        return True

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate embeddings via active provider adapter with validation."""
        if not self.is_available():
            raise EmbeddingProviderUnavailableError(
                self.get_provider_metadata().provider_name,
                "Embedding adapter provider is unavailable.",
            )

        response = self._provider.embed(request)
        self.validate_response(response, len(request.texts))
        return response

    def embed_texts(
        self,
        texts: List[str],
        chunk_ids: Optional[List[str]] = None,
        source_id: Optional[str] = None,
        include_sparse: bool = False,
    ) -> EmbeddingResponse:
        """Convenience wrapper for embedding a list of raw text strings."""
        request = EmbeddingRequest(
            texts=texts,
            chunk_ids=chunk_ids,
            source_id=source_id,
            include_sparse=include_sparse,
        )
        return self.embed(request)
