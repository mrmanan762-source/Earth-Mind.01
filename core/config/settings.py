import os
from typing import Dict, Optional, Any
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    identifier: str = Field(..., description="Unique model identifier within EarthMind")
    version: str = Field("1.0.0", description="Model version string")
    family: str = Field("sarvam", description="Model family name")
    provider: str = Field("huggingface", description="Model provider or host platform")
    repo_id: str = Field(..., description="Hugging Face repository ID")
    revision: str = Field(..., description="Exact pinned commit SHA or revision")
    model_type: str = Field("causal_lm", description="Architecture/type metadata")
    license: str = Field("Apache-2.0", description="Model license terms")
    provenance: str = Field("upstream: sarvamai/sarvam-105b", description="Model provenance information")
    is_main_model: bool = Field(False, description="Whether this is the primary EarthMind model")
    lifecycle_state: str = Field("ACTIVE", description="Current lifecycle state string")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata dictionary")

    def validate_config(self) -> bool:
        if not self.identifier or not self.identifier.strip():
            raise ValueError("Model identifier cannot be empty.")
        if not self.repo_id or "/" not in self.repo_id:
            raise ValueError(f"Invalid repo_id '{self.repo_id}'. Must be in format 'owner/repo'.")
        if not self.revision or len(self.revision.strip()) < 8:
            raise ValueError(f"Invalid revision '{self.revision}'. Must be a valid pinned commit SHA.")
        return True


class EmbeddingConfig(BaseModel):
    """Configuration for C.2 Knowledge Base embedding providers."""
    provider: str = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_PROVIDER", "fake"), description="Embedding provider name")
    model: str = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_MODEL", "earthmind-embed-v1"), description="Embedding model name")
    model_version: str = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_MODEL_VERSION", "1.0.0"), description="Embedding model version")
    dimension: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_EMBEDDING_DIMENSION", "384")), description="Embedding dimension")
    endpoint: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_ENDPOINT"), description="Provider API endpoint if applicable")
    credential_reference: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_CREDENTIAL_REFERENCE"), description="Credential key reference string")
    batch_size: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_EMBEDDING_BATCH_SIZE", "32")), description="Default batch size")
    max_length: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_EMBEDDING_MAX_LENGTH", "512")), description="Maximum sequence input token length")
    device: str = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_DEVICE", "cpu"), description="Execution device (cpu, cuda, mps, auto)")
    normalize: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_NORMALIZE", "true").lower() == "true", description="Normalize embeddings to unit L2 length")
    allow_download: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_ALLOW_DOWNLOAD", "false").lower() == "true", description="Allow downloading model weights from remote repository")
    execution_mode: str = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_EXECUTION_MODE", "self_hosted"), description="Execution mode string")
    timeout: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_EMBEDDING_TIMEOUT", "30.0")), description="Request timeout in seconds")
    license: str = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_LICENSE", "Apache-2.0"), description="Embedding model license")
    provenance: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_PROVENANCE", "EarthMind Prototype Vector Standard"), description="Model provenance information")


class QdrantConfig(BaseModel):
    """Configuration settings for Qdrant Index Adapter."""
    url: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_QDRANT_URL"), description="Qdrant server URL")
    host: str = Field(default_factory=lambda: os.getenv("EARTHMIND_QDRANT_HOST", "localhost"), description="Qdrant host name")
    port: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_QDRANT_PORT", "6333")), description="Qdrant HTTP port")
    grpc_port: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_QDRANT_GRPC_PORT", "6334")), description="Qdrant gRPC port")
    api_key: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_QDRANT_API_KEY"), description="Qdrant API key")
    location: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_QDRANT_LOCATION"), description="Optional location e.g. ':memory:' for unit tests")
    prefer_grpc: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_QDRANT_PREFER_GRPC", "false").lower() == "true", description="Prefer gRPC connection")
    default_collection_name: str = Field(default_factory=lambda: os.getenv("EARTHMIND_QDRANT_COLLECTION", "earthmind_knowledge"), description="Default physical Qdrant collection name")
    distance_metric: str = Field(default_factory=lambda: os.getenv("EARTHMIND_QDRANT_DISTANCE", "COSINE"), description="Distance metric for vector search (COSINE, DOT, EUCLID)")
    timeout: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_QDRANT_TIMEOUT", "30.0")), description="Request timeout in seconds")


class RerankConfig(BaseModel):
    """Configuration settings for Stage R8 Reranking Engine."""
    provider: str = Field(default_factory=lambda: os.getenv("EARTHMIND_RERANK_PROVIDER", "fake"), description="Reranker provider identifier")
    model: str = Field(default_factory=lambda: os.getenv("EARTHMIND_RERANK_MODEL", "BAAI/bge-reranker-base"), description="Reranker model identifier")
    model_version: str = Field(default_factory=lambda: os.getenv("EARTHMIND_RERANK_MODEL_VERSION", "1.0.0"), description="Reranker model version string")
    batch_size: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_RERANK_BATCH_SIZE", "32")), description="Batch size for model evaluation")
    max_candidate_count: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_RERANK_MAX_CANDIDATE_COUNT", "100")), description="Maximum candidate limit accepted for reranking")
    max_input_length: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_RERANK_MAX_INPUT_LENGTH", "512")), description="Maximum sequence input token/character length")
    timeout: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_RERANK_TIMEOUT", "10.0")), description="Request timeout in seconds")
    candidate_limit: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_RERANK_CANDIDATE_LIMIT", "10")), description="Default top-k reranked output limit")
    fallback_policy: str = Field(default_factory=lambda: os.getenv("EARTHMIND_RERANK_FALLBACK_POLICY", "PRESERVE_FUSED_ORDER"), description="Fallback policy on provider failure ('PRESERVE_FUSED_ORDER', 'FAIL')")
    score_normalization_policy: str = Field(default_factory=lambda: os.getenv("EARTHMIND_RERANK_SCORE_NORMALIZATION", "NONE"), description="Score normalization policy ('NONE', 'MIN_MAX', 'SIGMOID')")
    deterministic_ordering_policy: str = Field(default_factory=lambda: os.getenv("EARTHMIND_RERANK_DETERMINISTIC_ORDERING", "HIGHER_SCORE_FIRST"), description="Deterministic score ordering policy")
    allow_download: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_RERANK_ALLOW_DOWNLOAD", "false").lower() == "true", description="Allow downloading model weights from remote repository")
    device: str = Field(default_factory=lambda: os.getenv("EARTHMIND_RERANK_DEVICE", "cpu"), description="Execution device (cpu, cuda, mps, auto)")


class Settings(BaseModel):
    app_name: str = "EarthMind"
    environment: str = os.getenv("EARTHMIND_ENV", "development")
    version: str = "0.1.0"
    db_path: str = os.getenv("EARTHMIND_DB_PATH", "earthmind.db")
    log_level: str = os.getenv("EARTHMIND_LOG_LEVEL", "INFO")
    main_model: ModelConfig = Field(
        default_factory=lambda: ModelConfig(
            identifier="sarvam-105b",
            provider="huggingface",
            repo_id=os.getenv("EARTHMIND_MAIN_MODEL_REPO", "mrmanan762/EarthMind"),
            revision=os.getenv("EARTHMIND_MAIN_MODEL_REVISION", "fb187764dbad56ed8b26742a802909e858e9bb72"),
            model_type="causal_lm",
            license="Apache-2.0",
            provenance="upstream: sarvamai/sarvam-105b",
            is_main_model=True
        )
    )
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    rerank: RerankConfig = Field(default_factory=RerankConfig)
    ulpu: Dict[str, Any] = Field(
        default_factory=lambda: {
            "supported_languages": ["en", "hi", "mr", "pa", "te", "ta", "gu", "bn", "kn", "ml"],
            "default_source_language": "hi",
            "default_canonical_language": "en",
            "stt_provider": "mock_stt",
            "translation_provider": "mock_translation",
            "tts_provider": "mock_tts",
            "language_detection_provider": "mock_detection",
            "timeout_seconds": 15.0,
            "confidence_threshold": 0.6,
        }
    )


settings = Settings()
