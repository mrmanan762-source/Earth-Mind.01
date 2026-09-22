import os
import pytest

from core.interfaces.embedding import IEmbeddingProvider
from core.config.settings import Settings, EmbeddingConfig
from core.schemas.embedding import (
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingStatus,
    ProviderMetadata,
    ModelMetadata,
    SparseVector,
)
from core.errors.exceptions import (
    EmbeddingError,
    InvalidEmbeddingInputError,
    EmbeddingProviderUnavailableError,
    EmbeddingConfigurationError,
    EmbeddingRateLimitError,
    EmbeddingTimeoutError,
    EmbeddingExecutionError,
    InvalidEmbeddingResponseError,
    EmbeddingDimensionMismatchError,
)
from modules.knowledge_base.embedding.fake_provider import FakeEmbeddingProvider
from modules.knowledge_base.embedding.adapter import EmbeddingAdapter


def test_1_interface_contract_adherence():
    """Verify FakeEmbeddingProvider adheres to IEmbeddingProvider runtime protocol."""
    provider = FakeEmbeddingProvider()
    assert isinstance(provider, IEmbeddingProvider)
    assert provider.get_dimension() == 384
    assert provider.is_available() is True
    assert provider.validate_config() is True


def test_2_request_response_behavior_single_and_batch():
    """Verify single and batch request/response processing."""
    adapter = EmbeddingAdapter(FakeEmbeddingProvider(dimension=256))

    # Single text request
    res_single = adapter.embed_texts(["Soil moisture level is optimal for wheat."])
    assert res_single.status == EmbeddingStatus.SUCCESS
    assert len(res_single.embeddings) == 1
    assert len(res_single.embeddings[0]) == 256
    assert len(res_single.dense_vectors) == 1

    # Batch request
    batch_texts = [
        "Nitrogen deficiency observed in corn leaves.",
        "Drip irrigation schedule for sandy loam soil.",
        "Pesticide application guidelines for aphid control.",
    ]
    res_batch = adapter.embed_texts(batch_texts, chunk_ids=["c1", "c2", "c3"], source_id="src_agri_1")
    assert res_batch.status == EmbeddingStatus.SUCCESS
    assert len(res_batch.embeddings) == 3
    for vec in res_batch.embeddings:
        assert len(vec) == 256
    assert res_batch.metadata.source_id == "src_agri_1"


def test_3_provider_metadata():
    """Verify provider metadata format and attributes."""
    provider = FakeEmbeddingProvider(
        provider_name="custom_provider",
        endpoint="https://api.embedding.local",
        credential_reference="ENV:LOCAL_KEY",
    )
    meta = provider.get_provider_metadata()
    assert isinstance(meta, ProviderMetadata)
    assert meta.provider_name == "custom_provider"
    assert meta.endpoint == "https://api.embedding.local"
    assert meta.credential_reference == "ENV:LOCAL_KEY"
    assert meta.is_mock is True


def test_4_model_metadata_license_provenance():
    """Verify model metadata including license, provenance, and commercial safety."""
    provider = FakeEmbeddingProvider(
        model_name="agri-embed-v2",
        model_version="2.1.0",
        license="Apache-2.0",
        provenance="EarthMind Commercial Clean Dataset",
    )
    model_meta = provider.get_model_metadata()
    assert isinstance(model_meta, ModelMetadata)
    assert model_meta.model_name == "agri-embed-v2"
    assert model_meta.model_version == "2.1.0"
    assert model_meta.license == "Apache-2.0"
    assert model_meta.commercial_use_allowed is True
    assert model_meta.provenance == "EarthMind Commercial Clean Dataset"


def test_5_dimension_validation():
    """Verify dimension validation and dimension mismatch error handling."""
    # Test valid dimension
    provider_384 = FakeEmbeddingProvider(dimension=384)
    adapter = EmbeddingAdapter(provider_384)
    res = adapter.embed_texts(["Test string"])
    assert len(res.embeddings[0]) == 384

    # Test adapter catching provider dimension mismatch
    mismatched_provider = FakeEmbeddingProvider(dimension=384, simulated_error="dimension_mismatch")
    mismatched_adapter = EmbeddingAdapter(mismatched_provider)

    with pytest.raises(EmbeddingDimensionMismatchError) as exc_info:
        mismatched_adapter.embed_texts(["Test text"])
    assert "Dimension mismatch" in str(exc_info.value)
    assert exc_info.value.error_contract.error_code == "EMBEDDING_DIMENSION_MISMATCH"


def test_6_explicit_error_handling():
    """Verify explicit custom exception handling for distinguishable failure conditions."""
    # 1. Invalid input error
    adapter = EmbeddingAdapter(FakeEmbeddingProvider())
    with pytest.raises(InvalidEmbeddingInputError):
        adapter.embed(EmbeddingRequest(texts=[]))

    with pytest.raises(InvalidEmbeddingInputError):
        adapter.embed(EmbeddingRequest(texts=["valid text"], chunk_ids=["c1", "c2"]))

    # 2. Provider unavailable error
    unavail_adapter = EmbeddingAdapter(FakeEmbeddingProvider(available=False))
    with pytest.raises(EmbeddingProviderUnavailableError) as unavail_exc:
        unavail_adapter.embed_texts(["Text"])
    assert unavail_exc.value.error_contract.retryable is True

    # 3. Rate limit error
    rate_limit_adapter = EmbeddingAdapter(FakeEmbeddingProvider(simulated_error="rate_limit"))
    with pytest.raises(EmbeddingRateLimitError) as rate_exc:
        rate_limit_adapter.embed_texts(["Text"])
    assert rate_exc.value.error_contract.retryable is True

    # 4. Timeout error
    timeout_adapter = EmbeddingAdapter(FakeEmbeddingProvider(simulated_error="timeout"))
    with pytest.raises(EmbeddingTimeoutError) as timeout_exc:
        timeout_adapter.embed_texts(["Text"])
    assert timeout_exc.value.error_contract.retryable is True

    # 5. Execution error
    exec_adapter = EmbeddingAdapter(FakeEmbeddingProvider(simulated_error="execution_error"))
    with pytest.raises(EmbeddingExecutionError):
        exec_adapter.embed_texts(["Text"])


def test_7_configuration_loading(monkeypatch):
    """Verify EmbeddingConfig initialization and env var overrides."""
    monkeypatch.setenv("EARTHMIND_EMBEDDING_PROVIDER", "custom_test_provider")
    monkeypatch.setenv("EARTHMIND_EMBEDDING_MODEL", "custom-model-v1")
    monkeypatch.setenv("EARTHMIND_EMBEDDING_DIMENSION", "512")

    cfg = EmbeddingConfig()
    assert cfg.provider == "custom_test_provider"
    assert cfg.model == "custom-model-v1"
    assert cfg.dimension == 512

    adapter = EmbeddingAdapter.from_config(cfg)
    assert adapter.get_dimension() == 512
    assert adapter.get_provider_metadata().provider_name == "custom_test_provider"


def test_8_missing_credential_and_config_validation():
    """Verify behavior when required credentials or invalid configurations are encountered."""
    # Require credential reference but pass None
    provider = FakeEmbeddingProvider(require_credential=True, credential_reference=None)
    with pytest.raises(EmbeddingConfigurationError) as exc_info:
        provider.validate_config()
    assert "Missing required credential reference" in str(exc_info.value)

    # Invalid dimension config
    invalid_dim_provider = FakeEmbeddingProvider(dimension=0)
    with pytest.raises(EmbeddingConfigurationError) as exc_info_dim:
        invalid_dim_provider.validate_config()
    assert "Invalid dimension" in str(exc_info_dim.value)


def test_9_provider_replacement_strategy():
    """Verify seamless provider replacement without modifying adapter or domain interface."""
    # Initial Provider A (dim 384)
    provider_a = FakeEmbeddingProvider(
        provider_name="Provider_A_Vendor",
        model_name="model-alpha",
        dimension=384,
    )
    adapter = EmbeddingAdapter(provider_a)

    res_a = adapter.embed_texts(["Domain text for Provider A"])
    assert res_a.provider_metadata.provider_name == "Provider_A_Vendor"
    assert res_a.dimension == 384
    assert len(res_a.embeddings[0]) == 384

    # Replace with Provider B (dim 768)
    provider_b = FakeEmbeddingProvider(
        provider_name="Provider_B_Vendor",
        model_name="model-beta",
        dimension=768,
    )
    adapter.set_provider(provider_b)

    res_b = adapter.embed_texts(["Domain text for Provider B"])
    assert res_b.provider_metadata.provider_name == "Provider_B_Vendor"
    assert res_b.dimension == 768
    assert len(res_b.embeddings[0]) == 768


def test_10_sparse_representation_boundary_and_no_sdk_leakage():
    """Verify sparse vector representation boundary and absence of provider SDK leakage."""
    provider = FakeEmbeddingProvider(dimension=384)
    adapter = EmbeddingAdapter(provider)

    request = EmbeddingRequest(
        texts=["Rice crop pest resistance analysis."],
        include_sparse=True,
    )
    response = adapter.embed(request)

    assert response.sparse_vectors is not None
    assert len(response.sparse_vectors) == 1
    sparse_vec = response.sparse_vectors[0]
    assert isinstance(sparse_vec, SparseVector)
    assert len(sparse_vec.terms) > 0

    # Ensure response types strictly use standard Python / Pydantic types, no custom SDK objects
    assert type(response).__name__ == "EmbeddingResponse"
    assert type(response.provider_metadata).__name__ == "ProviderMetadata"
    assert type(response.model_metadata).__name__ == "ModelMetadata"
