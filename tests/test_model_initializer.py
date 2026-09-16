import pytest
from core.interfaces.initializer import IModelInitializer, InitializationState, LoadingStrategy
from core.config.settings import ModelLoadingConfig, settings
from core.errors.exceptions import (
    ArtifactNotFoundError,
    EnvironmentIncompatibleError,
    InitializationError,
    ReadinessError,
    ResourceUnavailableError
)
from modules.ai.model_registry import ModelRegistry
from modules.ai.artifact_initializer import (
    ModelArtifactResolver,
    EnvironmentDetector,
    CompatibilityChecker,
    RemoteLoadingStrategy,
    LocalLoadingStrategy,
    ModelInitializer
)
from modules.ai.sarvam_adapter import Sarvam105BAdapter

def test_initializer_interface_contract():
    initializer = ModelInitializer()
    assert isinstance(initializer, IModelInitializer)

def test_artifact_resolution_exact_repo_and_pinned_revision():
    resolver = ModelArtifactResolver()
    artifact = resolver.resolve_artifact("sarvam-105b")

    assert artifact["identifier"] == "sarvam-105b"
    assert artifact["repo_id"] == "mrmanan762/EarthMind"
    assert artifact["revision"] == "fb187764dbad56ed8b26742a802909e858e9bb72"
    assert artifact["provider"] == "huggingface"
    assert artifact["is_main_model"] is True

def test_artifact_resolution_unregistered_model_raises_error():
    resolver = ModelArtifactResolver()
    with pytest.raises(ArtifactNotFoundError) as exc_info:
        resolver.resolve_artifact("unknown-model-id")
    assert "unknown-model-id" in str(exc_info.value)

def test_environment_detection():
    detector = EnvironmentDetector()
    env_info = detector.detect_environment()

    assert "cpu_count" in env_info
    assert "environment" in env_info
    assert "estimated_ram_gb" in env_info
    assert env_info["has_gpu"] is False

def test_compatibility_validation():
    checker = CompatibilityChecker()
    valid_artifact = {
        "identifier": "sarvam-105b",
        "repo_id": "mrmanan762/EarthMind",
        "revision": "fb187764dbad56ed8b26742a802909e858e9bb72"
    }
    assert checker.validate_compatibility(valid_artifact, {}) is True

    invalid_artifact = {
        "identifier": "invalid",
        "repo_id": "invalid_no_slash",
        "revision": "fb187764dbad56ed8b26742a802909e858e9bb72"
    }
    with pytest.raises(EnvironmentIncompatibleError):
        checker.validate_compatibility(invalid_artifact, {})

def test_successful_remote_initialization_lifecycle():
    initializer = ModelInitializer()
    assert initializer.state == InitializationState.NOT_INITIALIZED
    assert initializer.check_readiness() is False

    status = initializer.initialize("sarvam-105b")
    assert initializer.state == InitializationState.READY
    assert initializer.check_readiness() is True
    assert status["readiness"] is True
    assert status["active_artifact"]["repo_id"] == "mrmanan762/EarthMind"
    assert status["active_artifact"]["revision"] == "fb187764dbad56ed8b26742a802909e858e9bb72"
    assert status["prepared_info"]["strategy"] == LoadingStrategy.REMOTE.value

def test_local_loading_insufficient_resources_safeguard():
    config = ModelLoadingConfig(loading_strategy="local")
    initializer = ModelInitializer(config=config)

    with pytest.raises(ResourceUnavailableError) as exc_info:
        initializer.initialize("sarvam-105b")
    assert initializer.state == InitializationState.NOT_READY
    assert "424 GB Sarvam-105B model requires >=500 GB RAM" in str(exc_info.value)

def test_reinitialization_lifecycle():
    initializer = ModelInitializer()
    initializer.initialize("sarvam-105b")
    assert initializer.state == InitializationState.READY

    status_reinit = initializer.reinitialize("sarvam-105b")
    assert initializer.state == InitializationState.READY
    assert status_reinit["readiness"] is True

def test_sarvam_adapter_model_initializer_integration():
    initializer = ModelInitializer()
    adapter = Sarvam105BAdapter(initializer=initializer)

    assert adapter.status()["loaded"] is False

    adapter.load()
    assert adapter.status()["loaded"] is True
    assert adapter.status()["health"] == "healthy"
    assert initializer.check_readiness() is True

    status_dict = adapter.status()
    assert "initializer" in status_dict
    assert status_dict["initializer"]["active_artifact"]["repo_id"] == "mrmanan762/EarthMind"

def test_secret_safety_no_tokens_exposed():
    initializer = ModelInitializer()
    initializer.initialize("sarvam-105b")
    status = initializer.status()
    status_str = str(status)

    assert "HF_TOKEN" not in status_str
    assert "secret" not in status_str.lower()
    assert "token" not in status_str.lower()
