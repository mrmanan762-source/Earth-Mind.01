"""Unit tests for Step 7 — Configuration & Deployment Strategy for EarthMind AI Layer."""

import os
import pytest
from core.schemas.model import (
    DeploymentConfig,
    DeploymentMode,
    EnvironmentProfile,
    DeploymentReadinessState,
    ResourcePolicy,
    ModelGenerationRequest
)
from core.errors.exceptions import (
    DeploymentConfigError,
    UnsupportedDeploymentModeError,
    ResourceUnavailableError,
    RemoteEndpointUnavailableError,
    DeploymentReadinessError
)
from modules.ai.deployment_strategy import (
    parse_deployment_mode,
    resolve_environment_profile,
    load_deployment_config,
    validate_deployment_config,
    ResourcePolicyEvaluator,
    DeploymentReadinessEvaluator,
    RemoteDeploymentStrategy,
    LocalDeploymentStrategy,
    HybridDeploymentStrategy
)
from modules.ai.sarvam_adapter import Sarvam105BAdapter
from modules.ai.model_registry import ModelRegistry


def test_parse_deployment_mode():
    """Test deployment mode parsing and validation."""
    assert parse_deployment_mode("REMOTE") == DeploymentMode.REMOTE
    assert parse_deployment_mode("local") == DeploymentMode.LOCAL
    assert parse_deployment_mode("Hybrid") == DeploymentMode.HYBRID

    with pytest.raises(UnsupportedDeploymentModeError):
        parse_deployment_mode("INVALID_MODE")


def test_resolve_environment_profile():
    """Test environment profile resolution."""
    assert resolve_environment_profile("DEV") == EnvironmentProfile.DEVELOPMENT
    assert resolve_environment_profile("TEST") == EnvironmentProfile.TEST
    assert resolve_environment_profile("PRODUCTION") == EnvironmentProfile.PRODUCTION


def test_configuration_precedence():
    """Test configuration precedence: Runtime overrides > Env vars > Profile defaults."""
    # Default profile DEVELOPMENT
    cfg_dev = load_deployment_config(profile=EnvironmentProfile.DEVELOPMENT)
    assert cfg_dev.environment_profile == EnvironmentProfile.DEVELOPMENT
    assert cfg_dev.resource_policy.timeout_seconds == 30.0

    # Env var override
    os.environ["EARTHMIND_DEPLOYMENT_MODE"] = "HYBRID"
    try:
        cfg_env = load_deployment_config()
        assert cfg_env.deployment_mode == DeploymentMode.HYBRID
    finally:
        del os.environ["EARTHMIND_DEPLOYMENT_MODE"]

    # Explicit runtime override beats env var
    os.environ["EARTHMIND_DEPLOYMENT_MODE"] = "LOCAL"
    try:
        cfg_override = load_deployment_config({"deployment_mode": "REMOTE"})
        assert cfg_override.deployment_mode == DeploymentMode.REMOTE
    finally:
        del os.environ["EARTHMIND_DEPLOYMENT_MODE"]


def test_deployment_config_validation():
    """Test configuration validation rules and error handling."""
    # Valid config
    valid_cfg = DeploymentConfig(
        model_identifier="sarvam-105b",
        repo_id="mrmanan762/EarthMind",
        revision="fb187764dbad56ed8b26742a802909e858e9bb72",
        deployment_mode=DeploymentMode.REMOTE,
        remote_endpoint="https://api.earthmind.ai/v1"
    )
    assert validate_deployment_config(valid_cfg) is True

    # Missing remote endpoint in REMOTE mode
    invalid_remote = valid_cfg.model_copy(update={"remote_endpoint": None})
    with pytest.raises(DeploymentConfigError):
        validate_deployment_config(invalid_remote)

    # Missing local artifact path in LOCAL mode
    invalid_local = DeploymentConfig(
        model_identifier="sarvam-105b",
        repo_id="mrmanan762/EarthMind",
        revision="fb187764dbad56ed8b26742a802909e858e9bb72",
        deployment_mode=DeploymentMode.LOCAL,
        local_artifact_path=None
    )
    with pytest.raises(DeploymentConfigError):
        validate_deployment_config(invalid_local)


def test_resource_policy_evaluator():
    """Test resource policy evaluation for local/system constraints."""
    evaluator = ResourcePolicyEvaluator()

    # Safe memory request
    safe_policy = ResourcePolicy(min_memory_gb=16.0, gpu_required=False)
    res_safe = evaluator.evaluate(safe_policy)
    assert res_safe["is_met"] is True

    # Excessive memory request (preventing 400+ GB model local load attempts in dev)
    excessive_policy = ResourcePolicy(min_memory_gb=500.0)
    res_excessive = evaluator.evaluate(excessive_policy)
    assert res_excessive["is_met"] is False


def test_deployment_readiness_evaluator():
    """Test readiness state classification (READY, ENDPOINT_UNAVAILABLE, RESOURCE_UNAVAILABLE, MISCONFIGURED)."""
    evaluator = DeploymentReadinessEvaluator()

    valid_remote_cfg = DeploymentConfig(
        model_identifier="sarvam-105b",
        repo_id="mrmanan762/EarthMind",
        revision="fb187764dbad56ed8b26742a802909e858e9bb72",
        deployment_mode=DeploymentMode.REMOTE,
        remote_endpoint="https://api.earthmind.ai/v1"
    )

    res_ready = evaluator.evaluate(valid_remote_cfg, mock_endpoint_available=True)
    assert res_ready.state == DeploymentReadinessState.READY
    assert res_ready.is_ready is True

    res_unavail = evaluator.evaluate(valid_remote_cfg, mock_endpoint_available=False)
    assert res_unavail.state == DeploymentReadinessState.ENDPOINT_UNAVAILABLE
    assert res_unavail.is_ready is False


def test_remote_deployment_strategy():
    """Test RemoteDeploymentStrategy routing."""
    cfg = DeploymentConfig(
        model_identifier="sarvam-105b",
        repo_id="mrmanan762/EarthMind",
        revision="fb187764dbad56ed8b26742a802909e858e9bb72",
        deployment_mode=DeploymentMode.REMOTE,
        remote_endpoint="https://api.earthmind.ai/v1"
    )
    strategy = RemoteDeploymentStrategy(cfg)
    req = ModelGenerationRequest(request_id="req-1", task="Remote execution task")

    route = strategy.route_request(req)
    assert route["strategy"] == "REMOTE"
    assert route["endpoint"] == "https://api.earthmind.ai/v1"


def test_local_deployment_strategy():
    """Test LocalDeploymentStrategy routing."""
    cfg = DeploymentConfig(
        model_identifier="sarvam-105b",
        repo_id="mrmanan762/EarthMind",
        revision="fb187764dbad56ed8b26742a802909e858e9bb72",
        deployment_mode=DeploymentMode.LOCAL,
        local_artifact_path="./models/cache"
    )
    strategy = LocalDeploymentStrategy(cfg)
    req = ModelGenerationRequest(request_id="req-2", task="Local execution task")

    route = strategy.route_request(req)
    assert route["strategy"] == "LOCAL"
    assert route["artifact_path"] == "./models/cache"


def test_hybrid_deployment_strategy():
    """Test HybridDeploymentStrategy routing based on task/model complexity."""
    cfg = DeploymentConfig(
        model_identifier="sarvam-105b",
        repo_id="mrmanan762/EarthMind",
        revision="fb187764dbad56ed8b26742a802909e858e9bb72",
        deployment_mode=DeploymentMode.HYBRID,
        remote_endpoint="https://api.earthmind.ai/v1",
        local_artifact_path="./models/cache"
    )
    strategy = HybridDeploymentStrategy(cfg)

    # Main Sarvam-105B heavy task -> REMOTE
    req_heavy = ModelGenerationRequest(request_id="req-heavy", task="Heavy main crop reasoning task")
    route_heavy = strategy.route_request(req_heavy)
    assert route_heavy["strategy"] == "HYBRID"
    assert route_heavy["target_execution"] == "REMOTE"

    # Lightweight task -> LOCAL
    cfg_light = cfg.model_copy(update={"model_identifier": "crop-filter-v1"})
    strategy_light = HybridDeploymentStrategy(cfg_light)
    req_light = ModelGenerationRequest(request_id="req-light", task="Simple filter task")
    route_light = strategy_light.route_request(req_light)
    assert route_light["target_execution"] == "LOCAL"


def test_secret_handling():
    """Verify secrets are referenced via config keys and not leaked/hardcoded."""
    cfg = DeploymentConfig(
        model_identifier="sarvam-105b",
        repo_id="mrmanan762/EarthMind",
        revision="fb187764dbad56ed8b26742a802909e858e9bb72",
        deployment_mode=DeploymentMode.REMOTE,
        remote_endpoint="https://api.earthmind.ai/v1",
        secret_keys=["HF_TOKEN", "EARTHMIND_API_KEY"]
    )
    cfg_str = str(cfg)
    assert "HF_TOKEN" in cfg.secret_keys
    # Secret values must not be hardcoded in config attributes
    assert "hf_" not in cfg_str


def test_sarvam_adapter_deployment_integration():
    """Test Sarvam105BAdapter status and initialization with deployment configuration."""
    registry = ModelRegistry()
    adapter = Sarvam105BAdapter(registry=registry)

    status = adapter.status()
    assert status["deployment_mode"] in ("REMOTE", "LOCAL", "HYBRID")
    assert status["environment_profile"] in ("DEVELOPMENT", "TEST", "PRODUCTION")
    assert status["deployment_readiness"] == "READY"
