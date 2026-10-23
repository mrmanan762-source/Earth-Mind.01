import os
from typing import Dict, Optional, Any, List
from pydantic import BaseModel, Field
from core.errors.exceptions import ConfigurationError


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
    provider: str = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_PROVIDER", "self_hosted"), description="Embedding provider name")
    model: str = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_MODEL", "BAAI/bge-m3"), description="Embedding model name")
    model_version: str = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_MODEL_VERSION", "1.0.0"), description="Embedding model version")
    dimension: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_EMBEDDING_DIMENSION", "1024")), description="Embedding dimension")
    endpoint: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_ENDPOINT"), description="Provider API endpoint if applicable")
    credential_reference: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_CREDENTIAL_REFERENCE"), description="Credential key reference string")
    batch_size: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_EMBEDDING_BATCH_SIZE", "32")), description="Default batch size")
    max_length: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_EMBEDDING_MAX_LENGTH", "8192")), description="Maximum sequence input token length")
    device: str = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_DEVICE", "cpu"), description="Execution device (cpu, cuda, mps, auto)")
    normalize: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_NORMALIZE", "true").lower() == "true", description="Normalize embeddings to unit L2 length")
    allow_download: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_ALLOW_DOWNLOAD", "true").lower() == "true", description="Allow downloading model weights from remote repository")
    execution_mode: str = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_EXECUTION_MODE", "self_hosted"), description="Execution mode string")
    timeout: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_EMBEDDING_TIMEOUT", "30.0")), description="Request timeout in seconds")
    license: str = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_LICENSE", "MIT"), description="Embedding model license")
    provenance: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_EMBEDDING_PROVENANCE", "https://huggingface.co/BAAI/bge-m3"), description="Model provenance information")
    cache_dir: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_MODEL_CACHE_DIR") or os.getenv("HF_HOME"), description="Model weights cache directory")

    @classmethod
    def bge_m3(
        cls,
        provider: str = "self_hosted",
        device: str = "cpu",
        allow_download: bool = True,
        execution_mode: str = "self_hosted",
    ) -> "EmbeddingConfig":
        """Factory method returning a standard 1024-dimensional BAAI/bge-m3 EmbeddingConfig profile."""
        return cls(
            provider=provider,
            model="BAAI/bge-m3",
            model_version="1.0.0",
            dimension=1024,
            batch_size=32,
            max_length=8192,
            device=device,
            normalize=True,
            allow_download=allow_download,
            execution_mode=execution_mode,
            license="MIT",
            provenance="https://huggingface.co/BAAI/bge-m3",
        )


class SparseConfig(BaseModel):
    """Configuration for C.2 Knowledge Base sparse vector representation / BM25 provider."""
    provider: str = Field(default_factory=lambda: os.getenv("EARTHMIND_SPARSE_PROVIDER", "bm25"), description="Sparse provider identifier ('bm25', 'fake')")
    model: str = Field(default_factory=lambda: os.getenv("EARTHMIND_SPARSE_MODEL", "earthmind-bm25-v1"), description="Sparse model identifier")
    timeout: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_SPARSE_TIMEOUT", "10.0")), description="Sparse retrieval timeout in seconds")


class FusionConfig(BaseModel):
    """Configuration for Stage R7 Hybrid Retrieval Fusion."""
    strategy: str = Field(default_factory=lambda: os.getenv("EARTHMIND_FUSION_STRATEGY", "rrf"), description="Fusion strategy ('rrf', 'relative_score')")
    rrf_k: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_FUSION_RRF_K", "60")), description="Reciprocal Rank Fusion k constant parameter")
    dense_weight: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_FUSION_DENSE_WEIGHT", "0.5")), description="Dense result weight for score fusion")
    sparse_weight: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_FUSION_SPARSE_WEIGHT", "0.5")), description="Sparse result weight for score fusion")
    timeout: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_FUSION_TIMEOUT", "10.0")), description="Fusion timeout in seconds")


class QdrantConfig(BaseModel):
    """Configuration settings for Qdrant Index Adapter."""
    mode: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_QDRANT_MODE"), description="Explicit Qdrant mode: 'remote', 'local_persistent', or 'memory'")
    url: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_QDRANT_URL"), description="Qdrant server URL")
    host: str = Field(default_factory=lambda: os.getenv("EARTHMIND_QDRANT_HOST", "localhost"), description="Qdrant host name")
    port: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_QDRANT_PORT", "6333")), description="Qdrant HTTP port")
    grpc_port: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_QDRANT_GRPC_PORT", "6334")), description="Qdrant gRPC port")
    api_key: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_QDRANT_API_KEY"), description="Qdrant API key")
    location: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_QDRANT_LOCATION"), description="Optional location e.g. ':memory:' or filesystem path for local storage")
    prefer_grpc: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_QDRANT_PREFER_GRPC", "false").lower() == "true", description="Prefer gRPC connection")
    default_collection_name: str = Field(default_factory=lambda: os.getenv("EARTHMIND_QDRANT_COLLECTION", "earthmind_knowledge"), description="Default physical Qdrant collection name")
    distance_metric: str = Field(default_factory=lambda: os.getenv("EARTHMIND_QDRANT_DISTANCE", "COSINE"), description="Distance metric for vector search (COSINE, DOT, EUCLID)")
    timeout: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_QDRANT_TIMEOUT", "30.0")), description="Request timeout in seconds")
    auto_create_collection: bool = Field(
        default_factory=lambda: os.getenv(
            "EARTHMIND_QDRANT_AUTO_CREATE",
            "true" if os.getenv("EARTHMIND_ENV", "development").lower() in ("development", "dev", "test") else "false"
        ).lower() == "true",
        description="Allow automatic creation of non-existent Qdrant collection"
    )

    def get_mode(self) -> str:
        """Determine effective Qdrant storage/connection mode."""
        if self.mode and self.mode.strip():
            return self.mode.strip().lower()

        if self.location == ":memory:":
            return "memory"
        elif self.location and self.location.strip() != ":memory:":
            return "local_persistent"
        elif self.url or (self.host and self.port):
            return "remote"
        return "remote"

    def get_masked_api_key(self) -> Optional[str]:
        """Return masked API key string for logging/diagnostics without exposing secret."""
        if not self.api_key:
            return None
        key = self.api_key.strip()
        if len(key) <= 6:
            return "***"
        return f"{key[:3]}***{key[-3:]}"


class RerankConfig(BaseModel):
    """Configuration settings for Stage R8 Reranking Engine."""
    provider: str = Field(default_factory=lambda: os.getenv("EARTHMIND_RERANK_PROVIDER", "cross_encoder"), description="Reranker provider identifier")
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
    allow_download: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_RERANK_ALLOW_DOWNLOAD", "true").lower() == "true", description="Allow downloading model weights from remote repository")
    device: str = Field(default_factory=lambda: os.getenv("EARTHMIND_RERANK_DEVICE", "cpu"), description="Execution device (cpu, cuda, mps, auto)")
    cache_dir: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_MODEL_CACHE_DIR") or os.getenv("HF_HOME"), description="Model weights cache directory")


class QueryProcessingConfig(BaseModel):
    """Configuration settings for Stage R9 Query Processing Engine."""
    max_query_length: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_QUERY_MAX_LENGTH", "1000")), description="Maximum character length for queries")
    min_query_length: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_QUERY_MIN_LENGTH", "1")), description="Minimum character length for queries")
    expansion_enabled: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_QUERY_EXPANSION_ENABLED", "true").lower() == "true", description="Enable query expansion by default")
    max_expansions: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_QUERY_MAX_EXPANSIONS", "3")), description="Maximum expansions per query")
    normalization_policy: str = Field(default_factory=lambda: os.getenv("EARTHMIND_QUERY_NORMALIZATION_POLICY", "STANDARD"), description="Normalization strategy identifier")
    default_language: str = Field(default_factory=lambda: os.getenv("EARTHMIND_QUERY_DEFAULT_LANG", "hi"), description="Default language code")
    supported_languages: List[str] = Field(default_factory=lambda: ["en", "hi", "mr", "pa", "te", "ta", "gu", "bn", "kn", "ml"], description="Supported language list")
    default_top_k: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_QUERY_DEFAULT_TOP_K", "10")), description="Default fused top-k")
    default_dense_top_k: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_QUERY_DEFAULT_DENSE_TOP_K", "20")), description="Default dense top-k")
    default_sparse_top_k: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_QUERY_DEFAULT_SPARSE_TOP_K", "20")), description="Default sparse top-k")
    collection_name: str = Field(default_factory=lambda: os.getenv("EARTHMIND_QUERY_COLLECTION", "earthmind_knowledge"), description="Default target collection")
    timeout: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_QUERY_TIMEOUT", "10.0")), description="Query processing timeout in seconds")
    deterministic_mode: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_QUERY_DETERMINISTIC", "true").lower() == "true", description="Enforce deterministic normalization and expansion")
    processing_version: str = Field(default_factory=lambda: os.getenv("EARTHMIND_QUERY_PROCESSING_VERSION", "1.0.0"), description="R9 pipeline version tag")


class WebSearchConfig(BaseModel):
    """Configuration settings for Stage R10 Web Search Engine."""
    provider: str = Field(default_factory=lambda: os.getenv("EARTHMIND_WEB_SEARCH_PROVIDER", "fake"), description="Web search provider name")
    api_key: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_WEB_SEARCH_API_KEY"), description="Web search provider API key")
    endpoint: Optional[str] = Field(default_factory=lambda: os.getenv("EARTHMIND_WEB_SEARCH_ENDPOINT"), description="Web search provider API endpoint URL")
    timeout: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_WEB_SEARCH_TIMEOUT", "10.0")), description="Web search execution timeout in seconds")
    max_results: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_WEB_SEARCH_MAX_RESULTS", "10")), description="Default maximum results returned per query")
    safe_search: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_WEB_SEARCH_SAFE_SEARCH", "true").lower() == "true", description="Enable safe search filtering")
    user_agent: str = Field(default_factory=lambda: os.getenv("EARTHMIND_WEB_SEARCH_USER_AGENT", "EarthMind-RAG/1.0"), description="Custom User-Agent header for HTTP requests")


class EvidenceBuilderConfig(BaseModel):
    """Configuration settings for Stage R11 Evidence Builder Engine."""
    max_items: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_EVIDENCE_MAX_ITEMS", "20")), description="Maximum total evidence items allowed in package")
    max_content_length: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_EVIDENCE_MAX_CONTENT_LENGTH", "2000")), description="Maximum character length per evidence content string")
    deduplicate: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_EVIDENCE_DEDUPLICATE", "true").lower() == "true", description="Enable conservative deduplication across sources")
    deterministic_ordering: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_EVIDENCE_DETERMINISTIC", "true").lower() == "true", description="Enforce deterministic evidence ordering")
    package_version: str = Field(default_factory=lambda: os.getenv("EARTHMIND_EVIDENCE_PACKAGE_VERSION", "1.0.0"), description="Evidence Package schema version string")


class EvidenceValidatorConfig(BaseModel):
    """Configuration settings for Stage R12 Evidence Validator Engine."""
    strict_mode: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_VALIDATOR_STRICT_MODE", "false").lower() == "true", description="Enforce strict package invalidation on error")
    max_items_limit: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_VALIDATOR_MAX_ITEMS", "100")), description="Maximum allowed evidence items per validation request")
    require_identity: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_VALIDATOR_REQUIRE_IDENTITY", "true").lower() == "true", description="Require valid evidence_id on items")
    require_provenance: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_VALIDATOR_REQUIRE_PROVENANCE", "true").lower() == "true", description="Require provenance dictionary on items")
    require_content: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_VALIDATOR_REQUIRE_CONTENT", "true").lower() == "true", description="Require non-empty content string on items")
    validator_version: str = Field(default_factory=lambda: os.getenv("EARTHMIND_VALIDATOR_VERSION", "1.0.0"), description="Evidence Validator implementation version string")


class RAGIntegrationConfig(BaseModel):
    """Configuration settings for Stage R13 RAG → B2 Integration Engine."""
    enable_web_search: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_RAG_ENABLE_WEB_SEARCH", "true").lower() == "true", description="Enable Stage R10 Web Search in RAG pipeline")
    max_results: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_RAG_MAX_RESULTS", "10")), description="Default maximum result count requested from RAG pipeline")
    strict_validation: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_RAG_STRICT_VALIDATION", "false").lower() == "true", description="Strict mode for R12 Evidence Validator gate")
    timeout: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_RAG_TIMEOUT", "15.0")), description="Overall RAG pipeline execution timeout in seconds")
    provider_name: str = Field(default_factory=lambda: os.getenv("EARTHMIND_RAG_PROVIDER_NAME", "rag_provider"), description="RAG Context Provider identifier name")


class ContextConfig(BaseModel):
    """Configuration settings for B2 Context Manager Engine."""
    default_token_limit: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_CONTEXT_DEFAULT_TOKEN_LIMIT", "4096")), description="Default token limit budget")
    default_relevance_threshold: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_CONTEXT_RELEVANCE_THRESHOLD", "0.5")), description="Default relevance threshold")
    default_timeout: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_CONTEXT_TIMEOUT", "5.0")), description="Default provider collection timeout in seconds")
    allow_pii_default: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_CONTEXT_ALLOW_PII", "false").lower() == "true", description="Default allow PII flag")
    b2_version: str = Field(default_factory=lambda: os.getenv("EARTHMIND_CONTEXT_B2_VERSION", "1.0.0"), description="B2 Context Manager engine version string")
    context_version: str = Field(default_factory=lambda: os.getenv("EARTHMIND_CONTEXT_VERSION", "1.0.0"), description="Context package schema version string")
    enable_cache: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_CONTEXT_ENABLE_CACHE", "true").lower() == "true", description="Enable context cache by default")
    strict_output_validation: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_CONTEXT_STRICT_OUTPUT_VALIDATION", "true").lower() == "true", description="Enforce strict output validation")


class EvaluationConfig(BaseModel):
    """Configuration settings for Stage R15 Quality & Performance Evaluation."""
    k_values: List[int] = Field(default_factory=lambda: [1, 3, 5, 10], description="K values for evaluation metrics")
    default_dataset_id: str = Field(default_factory=lambda: os.getenv("EARTHMIND_EVAL_DEFAULT_DATASET", "ds_earthmind_agri_v1"), description="Default benchmark dataset ID")
    max_concurrency: int = Field(default_factory=lambda: int(os.getenv("EARTHMIND_EVAL_MAX_CONCURRENCY", "4")), description="Max concurrency for concurrent evaluation runs")
    timeout_per_case: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_EVAL_CASE_TIMEOUT", "30.0")), description="Timeout in seconds per evaluation case")
    collect_resource_usage: bool = Field(default_factory=lambda: os.getenv("EARTHMIND_EVAL_COLLECT_RESOURCES", "true").lower() == "true", description="Collect CPU/Memory process indicators")
    regression_threshold_pct: float = Field(default_factory=lambda: float(os.getenv("EARTHMIND_EVAL_REGRESSION_THRESHOLD_PCT", "5.0")), description="Threshold percentage for regression flags")
    eval_version: str = Field(default_factory=lambda: os.getenv("EARTHMIND_EVAL_VERSION", "1.0.0"), description="Evaluation pipeline implementation version")


class Settings(BaseModel):
    app_name: str = "EarthMind"
    environment: str = Field(default_factory=lambda: os.getenv("EARTHMIND_ENV", "development"), description="Application execution environment ('development', 'production', 'test', 'staging')")
    version: str = "0.1.0"
    db_path: str = Field(default_factory=lambda: os.getenv("EARTHMIND_DB_PATH", "earthmind.db"), description="SQLite database file path")
    log_level: str = Field(default_factory=lambda: os.getenv("EARTHMIND_LOG_LEVEL", "INFO"), description="Logging level")
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
    sparse: SparseConfig = Field(default_factory=SparseConfig)
    fusion: FusionConfig = Field(default_factory=FusionConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    rerank: RerankConfig = Field(default_factory=RerankConfig)
    query_processing: QueryProcessingConfig = Field(default_factory=QueryProcessingConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    evidence_builder: EvidenceBuilderConfig = Field(default_factory=EvidenceBuilderConfig)
    evidence_validator: EvidenceValidatorConfig = Field(default_factory=EvidenceValidatorConfig)
    rag_integration: RAGIntegrationConfig = Field(default_factory=RAGIntegrationConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
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

    def validate_config(self) -> bool:
        """Validate EarthMind configuration parameters based on environment rules.

        Raises ConfigurationError for missing or invalid parameters.
        Returns True on success.
        """
        env = (self.environment or "development").lower().strip()
        is_prod = env in ("production", "prod")

        # --- 1. Timeout Validations ---
        timeouts = {
            "qdrant.timeout": self.qdrant.timeout,
            "embedding.timeout": self.embedding.timeout,
            "sparse.timeout": self.sparse.timeout,
            "fusion.timeout": self.fusion.timeout,
            "rerank.timeout": self.rerank.timeout,
            "query_processing.timeout": self.query_processing.timeout,
            "web_search.timeout": self.web_search.timeout,
            "rag_integration.timeout": self.rag_integration.timeout,
            "context.default_timeout": self.context.default_timeout,
        }
        for name, t_val in timeouts.items():
            if t_val <= 0:
                raise ConfigurationError(
                    f"Invalid configuration for '{name}': timeout must be greater than 0. Got {t_val}.",
                    details={"setting": name, "value": t_val}
                )

        # --- 2. Device Validations ---
        valid_devices = {"cpu", "cuda", "mps", "auto"}
        if self.embedding.device.lower() not in valid_devices:
            raise ConfigurationError(
                f"Invalid embedding device '{self.embedding.device}'. Allowed: {sorted(list(valid_devices))}.",
                details={"setting": "embedding.device", "value": self.embedding.device}
            )
        if self.rerank.device.lower() not in valid_devices:
            raise ConfigurationError(
                f"Invalid reranker device '{self.rerank.device}'. Allowed: {sorted(list(valid_devices))}.",
                details={"setting": "rerank.device", "value": self.rerank.device}
            )

        # --- 3. Dimension & Collection Name Validations ---
        if self.embedding.dimension <= 0:
            raise ConfigurationError(
                f"Embedding dimension must be positive. Got {self.embedding.dimension}.",
                details={"setting": "embedding.dimension", "value": self.embedding.dimension}
            )
        if not self.qdrant.default_collection_name or not self.qdrant.default_collection_name.strip():
            raise ConfigurationError(
                "Default Qdrant collection name cannot be empty.",
                details={"setting": "qdrant.default_collection_name"}
            )

        # --- 4. Qdrant Mode Consistency Checks ---
        q_mode = self.qdrant.get_mode()
        if q_mode == "remote":
            if not self.qdrant.url and not (self.qdrant.host and self.qdrant.port):
                raise ConfigurationError(
                    "Qdrant configured in 'remote' mode but neither EARTHMIND_QDRANT_URL nor EARTHMIND_QDRANT_HOST/PORT is set.",
                    details={"mode": q_mode}
                )
        elif q_mode == "local_persistent":
            if not self.qdrant.location or self.qdrant.location.strip() == ":memory:":
                raise ConfigurationError(
                    "Qdrant configured in 'local_persistent' mode but EARTHMIND_QDRANT_LOCATION persistent path is missing or invalid.",
                    details={"mode": q_mode, "location": self.qdrant.location}
                )

        # --- 5. Production Constraints Enforcement ---
        if is_prod:
            # Prohibit fake embedding provider in production
            if self.embedding.provider.lower() in ("fake", "mock", "dummy"):
                raise ConfigurationError(
                    "Production mode violation: Fake embedding provider is prohibited in production mode. "
                    "Set EARTHMIND_EMBEDDING_PROVIDER to 'self_hosted' (or an active non-fake provider).",
                    details={"setting": "embedding.provider", "value": self.embedding.provider}
                )

            # Prohibit fake reranker provider in production
            if self.rerank.provider.lower() in ("fake", "mock", "dummy"):
                raise ConfigurationError(
                    "Production mode violation: Fake reranker provider is prohibited in production mode. "
                    "Set EARTHMIND_RERANK_PROVIDER to 'cross_encoder' (or an active non-fake provider).",
                    details={"setting": "rerank.provider", "value": self.rerank.provider}
                )

            # Prohibit in-memory Qdrant storage in production
            if q_mode == "memory":
                raise ConfigurationError(
                    "Production mode violation: In-memory Qdrant storage (location=':memory:') is prohibited in production mode. "
                    "Configure EARTHMIND_QDRANT_URL or a persistent path EARTHMIND_QDRANT_LOCATION.",
                    details={"setting": "qdrant.location", "value": self.qdrant.location}
                )

        return True

    def to_safe_dict(self) -> Dict[str, Any]:
        """Export settings as a dictionary with all secrets and credentials masked."""
        raw = self.model_dump()

        # Mask Qdrant API key
        if raw.get("qdrant", {}).get("api_key"):
            raw["qdrant"]["api_key"] = self.qdrant.get_masked_api_key()

        # Mask Web Search API key
        if raw.get("web_search", {}).get("api_key"):
            ws_key = raw["web_search"]["api_key"]
            raw["web_search"]["api_key"] = f"{ws_key[:3]}***{ws_key[-3:]}" if len(ws_key) > 6 else "***"

        # Mask Embedding credential reference if contains secret
        if raw.get("embedding", {}).get("credential_reference"):
            cred = raw["embedding"]["credential_reference"]
            if "key" in cred.lower() or "secret" in cred.lower() or "token" in cred.lower():
                raw["embedding"]["credential_reference"] = "***masked_ref***"

        return raw


settings = Settings()
