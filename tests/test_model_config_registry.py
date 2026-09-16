import pytest
from core.config.settings import ModelConfig, settings
from modules.ai.model_registry import (
    ModelRegistry,
    ModelNotFoundError,
    InvalidModelConfigError
)

def test_sarvam_105b_config_defaults():
    main_model = settings.main_model
    assert main_model.identifier == "sarvam-105b"
    assert main_model.provider == "huggingface"
    assert main_model.repo_id == "mrmanan762/EarthMind"
    assert main_model.revision == "fb187764dbad56ed8b26742a802909e858e9bb72"
    assert main_model.model_type == "causal_lm"
    assert main_model.license == "Apache-2.0"
    assert "sarvamai/sarvam-105b" in main_model.provenance
    assert main_model.is_main_model is True
    assert main_model.validate_config() is True

def test_model_registry_defaults():
    registry = ModelRegistry()
    assert registry.is_registered("sarvam-105b") is True
    assert "sarvam-105b" in registry.list_models()

    resolved = registry.get_model("sarvam-105b")
    assert resolved.repo_id == "mrmanan762/EarthMind"
    assert resolved.revision == "fb187764dbad56ed8b26742a802909e858e9bb72"

    main_model = registry.get_main_model()
    assert main_model.identifier == "sarvam-105b"

def test_custom_model_registration_and_resolution():
    registry = ModelRegistry(register_defaults=False)
    assert registry.list_models() == []

    custom_config = ModelConfig(
        identifier="custom-sarvam",
        provider="huggingface",
        repo_id="mrmanan762/EarthMind",
        revision="fb187764dbad56ed8b26742a802909e858e9bb72",
        model_type="causal_lm",
        is_main_model=False
    )
    registry.register_model(custom_config)
    assert registry.is_registered("custom-sarvam") is True
    assert registry.get_model("custom-sarvam") == custom_config

def test_unregistered_model_resolution_raises_error():
    registry = ModelRegistry()
    with pytest.raises(ModelNotFoundError) as exc_info:
        registry.get_model("nonexistent-model")
    assert "nonexistent-model" in str(exc_info.value)

def test_invalid_repo_id_raises_error():
    registry = ModelRegistry(register_defaults=False)
    invalid_config = ModelConfig(
        identifier="invalid-repo-model",
        provider="huggingface",
        repo_id="invalid_repo_name_without_slash",
        revision="fb187764dbad56ed8b26742a802909e858e9bb72"
    )
    with pytest.raises(InvalidModelConfigError) as exc_info:
        registry.register_model(invalid_config)
    assert "Invalid repo_id" in str(exc_info.value)

def test_invalid_revision_raises_error():
    registry = ModelRegistry(register_defaults=False)
    invalid_config = ModelConfig(
        identifier="invalid-rev-model",
        provider="huggingface",
        repo_id="mrmanan762/EarthMind",
        revision="123"  # too short
    )
    with pytest.raises(InvalidModelConfigError) as exc_info:
        registry.register_model(invalid_config)
    assert "Invalid revision" in str(exc_info.value)
