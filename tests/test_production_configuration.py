import os
import pytest
from core.config.settings import Settings, EmbeddingConfig, QdrantConfig, RerankConfig, SparseConfig, FusionConfig
from core.errors.exceptions import ConfigurationError, CollectionOperationError
from modules.knowledge_base.index.qdrant_adapter import QdrantIndexAdapter


def test_valid_development_configuration():
    """Verify default development configuration validates successfully."""
    s = Settings()
    assert s.environment == "development"
    assert s.embedding.dimension == 1024
    assert s.embedding.model == "BAAI/bge-m3"
    assert s.qdrant.default_collection_name == "earthmind_knowledge"
    assert s.validate_config() is True


def test_valid_production_configuration(monkeypatch):
    """Verify valid production configuration passes validation."""
    monkeypatch.setenv("EARTHMIND_ENV", "production")
    monkeypatch.setenv("EARTHMIND_EMBEDDING_PROVIDER", "self_hosted")
    monkeypatch.setenv("EARTHMIND_RERANK_PROVIDER", "cross_encoder")
    monkeypatch.setenv("EARTHMIND_QDRANT_MODE", "remote")
    monkeypatch.setenv("EARTHMIND_QDRANT_URL", "https://qdrant.internal.earthmind.org:6333")

    s = Settings()
    assert s.environment == "production"
    assert s.validate_config() is True


def test_production_rejects_fake_embedding_provider(monkeypatch):
    """Verify production mode rejects fake embedding provider."""
    monkeypatch.setenv("EARTHMIND_ENV", "production")
    monkeypatch.setenv("EARTHMIND_EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("EARTHMIND_RERANK_PROVIDER", "cross_encoder")
    monkeypatch.setenv("EARTHMIND_QDRANT_MODE", "remote")
    monkeypatch.setenv("EARTHMIND_QDRANT_URL", "https://qdrant.internal.earthmind.org:6333")

    s = Settings()
    with pytest.raises(ConfigurationError) as exc_info:
        s.validate_config()

    assert "Fake embedding provider is prohibited in production mode" in str(exc_info.value)
    assert exc_info.value.error_contract.error_code == "CONFIGURATION_ERROR"


def test_production_rejects_fake_reranker_provider(monkeypatch):
    """Verify production mode rejects fake reranker provider."""
    monkeypatch.setenv("EARTHMIND_ENV", "production")
    monkeypatch.setenv("EARTHMIND_EMBEDDING_PROVIDER", "self_hosted")
    monkeypatch.setenv("EARTHMIND_RERANK_PROVIDER", "fake")
    monkeypatch.setenv("EARTHMIND_QDRANT_MODE", "remote")
    monkeypatch.setenv("EARTHMIND_QDRANT_URL", "https://qdrant.internal.earthmind.org:6333")

    s = Settings()
    with pytest.raises(ConfigurationError) as exc_info:
        s.validate_config()

    assert "Fake reranker provider is prohibited in production mode" in str(exc_info.value)


def test_production_rejects_in_memory_qdrant(monkeypatch):
    """Verify production mode rejects :memory: Qdrant storage."""
    monkeypatch.setenv("EARTHMIND_ENV", "production")
    monkeypatch.setenv("EARTHMIND_EMBEDDING_PROVIDER", "self_hosted")
    monkeypatch.setenv("EARTHMIND_RERANK_PROVIDER", "cross_encoder")
    monkeypatch.setenv("EARTHMIND_QDRANT_LOCATION", ":memory:")

    s = Settings()
    with pytest.raises(ConfigurationError) as exc_info:
        s.validate_config()

    assert "In-memory Qdrant storage (location=':memory:') is prohibited in production mode" in str(exc_info.value)


def test_invalid_negative_timeout(monkeypatch):
    """Verify invalid negative timeout raises ConfigurationError."""
    monkeypatch.setenv("EARTHMIND_EMBEDDING_TIMEOUT", "-5.0")

    s = Settings()
    with pytest.raises(ConfigurationError) as exc_info:
        s.validate_config()

    assert "timeout must be greater than 0" in str(exc_info.value)


def test_invalid_device_selection(monkeypatch):
    """Verify invalid hardware device selection raises ConfigurationError."""
    monkeypatch.setenv("EARTHMIND_EMBEDDING_DEVICE", "invalid_device_xyz")

    s = Settings()
    with pytest.raises(ConfigurationError) as exc_info:
        s.validate_config()

    assert "Invalid embedding device 'invalid_device_xyz'" in str(exc_info.value)


def test_qdrant_mode_resolution():
    """Verify Qdrant mode resolution logic."""
    cfg_mem = QdrantConfig(location=":memory:")
    assert cfg_mem.get_mode() == "memory"

    cfg_local = QdrantConfig(location="/data/qdrant")
    assert cfg_local.get_mode() == "local_persistent"

    cfg_remote = QdrantConfig(url="https://qdrant.example.com:6333")
    assert cfg_remote.get_mode() == "remote"

    cfg_explicit = QdrantConfig(mode="remote", location="/data/qdrant")
    assert cfg_explicit.get_mode() == "remote"


def test_qdrant_api_key_masking():
    """Verify Qdrant API key masking prevents credential leaks."""
    cfg = QdrantConfig(api_key="sk_production_secret_key_123456789")
    masked = cfg.get_masked_api_key()
    assert masked == "sk_***789"
    assert "production_secret" not in masked

    cfg_short = QdrantConfig(api_key="12345")
    assert cfg_short.get_masked_api_key() == "***"


def test_settings_to_safe_dict_masking(monkeypatch):
    """Verify Settings.to_safe_dict() masks secrets across all components."""
    monkeypatch.setenv("EARTHMIND_QDRANT_API_KEY", "qdrant_secret_api_key_999")
    monkeypatch.setenv("EARTHMIND_WEB_SEARCH_API_KEY", "web_search_secret_key_888")

    s = Settings()
    safe_dict = s.to_safe_dict()

    assert safe_dict["qdrant"]["api_key"] == "qdr***999"
    assert safe_dict["web_search"]["api_key"] == "web***888"
    assert "qdrant_secret" not in str(safe_dict)


def test_auto_create_collection_disabled_in_production(monkeypatch):
    """Verify auto_create_collection=False prevents silent collection creation when missing."""
    q_cfg = QdrantConfig(location=":memory:", auto_create_collection=False)
    adapter = QdrantIndexAdapter(config=q_cfg)

    with pytest.raises(CollectionOperationError) as exc_info:
        adapter.ensure_collection_exists("non_existent_collection_123", dense_dim=1024)

    assert "automatic creation is disabled" in str(exc_info.value)


def test_model_cache_directory_configuration(monkeypatch):
    """Verify custom model cache directory configuration."""
    monkeypatch.setenv("EARTHMIND_MODEL_CACHE_DIR", "/custom/cache/dir")

    s = Settings()
    assert s.embedding.cache_dir == "/custom/cache/dir"
    assert s.rerank.cache_dir == "/custom/cache/dir"


def test_sparse_and_fusion_configuration():
    """Verify SparseConfig and FusionConfig default values."""
    s = Settings()
    assert isinstance(s.sparse, SparseConfig)
    assert s.sparse.provider == "bm25"
    assert s.sparse.model == "earthmind-bm25-v1"

    assert isinstance(s.fusion, FusionConfig)
    assert s.fusion.strategy == "rrf"
    assert s.fusion.rrf_k == 60
    assert s.fusion.dense_weight == 0.5
    assert s.fusion.sparse_weight == 0.5
