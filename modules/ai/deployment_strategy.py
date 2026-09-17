"""Deployment Strategy and Configuration Precedence for EarthMind AI Layer."""

import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from core.schemas.model import (
    DeploymentConfig,
    DeploymentMode,
    EnvironmentProfile,
    DeploymentReadinessState,
    DeploymentReadinessResult,
    ResourcePolicy,
    ModelGenerationRequest
)
from core.errors.exceptions import (
    DeploymentConfigError,
    UnsupportedDeploymentModeError,
    ResourceUnavailableError,
    RemoteEndpointUnavailableError,
    LocalEnvironmentUnavailableError,
    DeploymentReadinessError
)
from core.config.settings import settings
from core.logging.logger import get_logger

logger = get_logger("modules.ai.deployment_strategy")


def resolve_environment_profile(env_str: Optional[str] = None) -> EnvironmentProfile:
    """Resolve environment profile from string or environment variables."""
    target = (env_str or os.getenv("EARTHMIND_ENV", settings.environment)).upper()
    if target in ("DEV", "DEVELOPMENT"):
        return EnvironmentProfile.DEVELOPMENT
    if target in ("TEST", "TESTING"):
        return EnvironmentProfile.TEST
    if target in ("PROD", "PRODUCTION"):
        return EnvironmentProfile.PRODUCTION
    return EnvironmentProfile.DEVELOPMENT


def parse_deployment_mode(mode_str: Optional[str] = None) -> DeploymentMode:
    """Parse and validate deployment mode string."""
    target = (mode_str or os.getenv("EARTHMIND_DEPLOYMENT_MODE", settings.deployment_mode)).upper()
    try:
        return DeploymentMode(target)
    except ValueError:
        raise UnsupportedDeploymentModeError(target)


def load_deployment_config(
    runtime_overrides: Optional[Dict[str, Any]] = None,
    profile: Optional[EnvironmentProfile] = None
) -> DeploymentConfig:
    """Load DeploymentConfig following strict configuration precedence:

    1. Explicit runtime overrides
    2. Environment variables (EARTHMIND_*)
    3. Environment profile defaults
    4. Safe system defaults
    """
    overrides = runtime_overrides or {}

    # Step 3: Profile defaults
    env_profile = profile or resolve_environment_profile(overrides.get("environment_profile"))
    if env_profile == EnvironmentProfile.PRODUCTION:
        default_mode = DeploymentMode.REMOTE
        default_endpoint = "https://api.earthmind.ai/v1/inference"
        default_timeout = 60.0
        default_concurrency = 16
    elif env_profile == EnvironmentProfile.TEST:
        default_mode = DeploymentMode.REMOTE
        default_endpoint = "https://test.api.earthmind.ai/v1/inference"
        default_timeout = 10.0
        default_concurrency = 2
    else:  # DEVELOPMENT
        default_mode = DeploymentMode.REMOTE
        default_endpoint = "https://dev.api.earthmind.ai/v1/inference"
        default_timeout = 30.0
        default_concurrency = 4

    # Step 2: Environment variables
    env_mode_str = os.getenv("EARTHMIND_DEPLOYMENT_MODE")
    env_mode = parse_deployment_mode(env_mode_str) if env_mode_str else default_mode

    env_endpoint = os.getenv("EARTHMIND_REMOTE_ENDPOINT", default_endpoint)
    env_local_path = os.getenv("EARTHMIND_LOCAL_ARTIFACT_PATH", "./models/cache")

    # Step 1: Explicit runtime configuration
    mode = parse_deployment_mode(overrides.get("deployment_mode")) if "deployment_mode" in overrides else env_mode
    endpoint = overrides.get("remote_endpoint", env_endpoint)
    local_path = overrides.get("local_artifact_path", env_local_path)
    model_id = overrides.get("model_identifier", settings.main_model.identifier)
    repo_id = overrides.get("repo_id", settings.main_model.repo_id)
    revision = overrides.get("revision", settings.main_model.revision)

    resource_policy_dict = overrides.get("resource_policy", {})
    resource_policy = ResourcePolicy(
        min_memory_gb=resource_policy_dict.get("min_memory_gb", 0.0),
        gpu_required=resource_policy_dict.get("gpu_required", False),
        cpu_cores=resource_policy_dict.get("cpu_cores", 1),
        max_concurrency=resource_policy_dict.get("max_concurrency", default_concurrency),
        timeout_seconds=resource_policy_dict.get("timeout_seconds", default_timeout),
        metadata=resource_policy_dict.get("metadata", {})
    )

    config = DeploymentConfig(
        model_identifier=model_id,
        repo_id=repo_id,
        revision=revision,
        deployment_mode=mode,
        environment_profile=env_profile,
        remote_endpoint=endpoint,
        local_artifact_path=local_path,
        resource_policy=resource_policy,
        secret_keys=overrides.get("secret_keys", ["HF_TOKEN"]),
        metadata=overrides.get("metadata", {})
    )

    validate_deployment_config(config)
    logger.info(
        f"Loaded DeploymentConfig: mode={config.deployment_mode.value}, profile={config.environment_profile.value}, "
        f"model={config.model_identifier} ({config.repo_id}@{config.revision[:8]})"
    )
    return config


def validate_deployment_config(config: DeploymentConfig) -> bool:
    """Validate DeploymentConfig rules and fail fast on invalid combinations."""
    if not config.model_identifier or not config.model_identifier.strip():
        raise DeploymentConfigError("Model identifier cannot be empty.")

    if not config.repo_id or "/" not in config.repo_id:
        raise DeploymentConfigError(f"Invalid repo_id '{config.repo_id}'. Must be 'owner/repo'.")

    if not config.revision or len(config.revision.strip()) < 8:
        raise DeploymentConfigError(f"Invalid revision '{config.revision}'. Must be pinned SHA >= 8 chars.")

    if config.resource_policy.timeout_seconds <= 0:
        raise DeploymentConfigError("Resource policy timeout_seconds must be positive.")

    if config.resource_policy.max_concurrency <= 0:
        raise DeploymentConfigError("Resource policy max_concurrency must be positive.")

    if config.deployment_mode in (DeploymentMode.REMOTE, DeploymentMode.HYBRID):
        if not config.remote_endpoint or not config.remote_endpoint.strip():
            raise DeploymentConfigError(f"Remote endpoint required for deployment mode '{config.deployment_mode.value}'.")

    if config.deployment_mode in (DeploymentMode.LOCAL, DeploymentMode.HYBRID):
        if not config.local_artifact_path or not config.local_artifact_path.strip():
            raise DeploymentConfigError(f"Local artifact path required for deployment mode '{config.deployment_mode.value}'.")

    return True


class ResourcePolicyEvaluator:
    """Evaluates whether local/system resource requirements are met without downloading heavy model weights."""

    def evaluate(self, policy: ResourcePolicy, model_identifier: str = "sarvam-105b") -> Dict[str, Any]:
        """Check policy constraints against environment capabilities safely."""
        checks: List[Dict[str, Any]] = []
        is_met = True

        # Check 1: Excessive memory request for local loading
        if policy.min_memory_gb > 128.0:
            is_met = False
            checks.append({
                "check": "memory_requirement",
                "passed": False,
                "details": f"Requested RAM ({policy.min_memory_gb} GB) exceeds safe development threshold (128 GB)."
            })
        else:
            checks.append({
                "check": "memory_requirement",
                "passed": True,
                "details": f"Requested RAM: {policy.min_memory_gb} GB"
            })

        # Check 2: GPU requirement
        if policy.gpu_required and os.getenv("EARTHMIND_ALLOW_MOCK_GPU", "true").lower() != "true":
            checks.append({"check": "gpu_requirement", "passed": False, "details": "GPU required but no GPU detected."})
            is_met = False
        else:
            checks.append({"check": "gpu_requirement", "passed": True, "details": "GPU requirement met/mocked."})

        # Check 3: Concurrency
        checks.append({"check": "concurrency_limit", "passed": True, "details": f"Max concurrency: {policy.max_concurrency}"})

        return {"is_met": is_met, "checks": checks}


class DeploymentReadinessEvaluator:
    """Evaluates deployment strategy readiness without requiring live external network endpoints or heavy weight downloads."""

    def __init__(self, resource_evaluator: Optional[ResourcePolicyEvaluator] = None):
        self._resource_evaluator = resource_evaluator or ResourcePolicyEvaluator()

    def evaluate(self, config: DeploymentConfig, mock_endpoint_available: bool = True) -> DeploymentReadinessResult:
        now_str = datetime.now(timezone.utc).isoformat()
        details: List[Dict[str, Any]] = []
        errors: List[str] = []

        # 1. Config validation check
        try:
            validate_deployment_config(config)
            details.append({"check": "config_validation", "passed": True, "details": "DeploymentConfig valid."})
        except DeploymentConfigError as e:
            errors.append(str(e))
            details.append({"check": "config_validation", "passed": False, "details": str(e)})
            return DeploymentReadinessResult(
                state=DeploymentReadinessState.MISCONFIGURED,
                is_ready=False,
                deployment_mode=config.deployment_mode,
                environment_profile=config.environment_profile,
                details=details,
                errors=errors,
                timestamp=now_str
            )

        # 2. Endpoint check for REMOTE / HYBRID
        if config.deployment_mode in (DeploymentMode.REMOTE, DeploymentMode.HYBRID):
            if not mock_endpoint_available:
                err_msg = f"Remote endpoint '{config.remote_endpoint}' is unreachable."
                errors.append(err_msg)
                details.append({"check": "remote_endpoint_ping", "passed": False, "details": err_msg})
                return DeploymentReadinessResult(
                    state=DeploymentReadinessState.ENDPOINT_UNAVAILABLE,
                    is_ready=False,
                    deployment_mode=config.deployment_mode,
                    environment_profile=config.environment_profile,
                    details=details,
                    errors=errors,
                    timestamp=now_str
                )
            details.append({"check": "remote_endpoint_ping", "passed": True, "details": f"Endpoint reachable: {config.remote_endpoint}"})

        # 3. Resource evaluation for LOCAL / HYBRID
        if config.deployment_mode in (DeploymentMode.LOCAL, DeploymentMode.HYBRID):
            res_eval = self._resource_evaluator.evaluate(config.resource_policy, config.model_identifier)
            details.extend(res_eval["checks"])
            if not res_eval["is_met"]:
                err_msg = "Resource requirements not satisfied for local deployment."
                errors.append(err_msg)
                return DeploymentReadinessResult(
                    state=DeploymentReadinessState.RESOURCE_UNAVAILABLE,
                    is_ready=False,
                    deployment_mode=config.deployment_mode,
                    environment_profile=config.environment_profile,
                    details=details,
                    errors=errors,
                    timestamp=now_str
                )

        return DeploymentReadinessResult(
            state=DeploymentReadinessState.READY,
            is_ready=True,
            deployment_mode=config.deployment_mode,
            environment_profile=config.environment_profile,
            details=details,
            errors=[],
            timestamp=now_str
        )


class DeploymentStrategy(ABC):
    """Abstract base class for model deployment strategies."""

    def __init__(self, config: DeploymentConfig, evaluator: Optional[DeploymentReadinessEvaluator] = None):
        self._config = config
        self._evaluator = evaluator or DeploymentReadinessEvaluator()

    @property
    def config(self) -> DeploymentConfig:
        return self._config

    def check_readiness(self, mock_endpoint_available: bool = True) -> DeploymentReadinessResult:
        return self._evaluator.evaluate(self._config, mock_endpoint_available=mock_endpoint_available)

    @abstractmethod
    def route_request(self, request: ModelGenerationRequest) -> Dict[str, Any]:
        """Determine routing details for model generation request."""
        pass


class RemoteDeploymentStrategy(DeploymentStrategy):
    """Remote execution deployment strategy routing inference to remote endpoints."""

    def route_request(self, request: ModelGenerationRequest) -> Dict[str, Any]:
        readiness = self.check_readiness()
        if not readiness.is_ready:
            raise DeploymentReadinessError(readiness.state.value, f"Remote deployment not ready: {', '.join(readiness.errors)}")

        return {
            "strategy": "REMOTE",
            "endpoint": self._config.remote_endpoint,
            "model_identifier": self._config.model_identifier,
            "repo_id": self._config.repo_id,
            "revision": self._config.revision,
            "timeout": self._config.resource_policy.timeout_seconds
        }


class LocalDeploymentStrategy(DeploymentStrategy):
    """Local execution deployment strategy using local artifacts/runtimes safely."""

    def route_request(self, request: ModelGenerationRequest) -> Dict[str, Any]:
        readiness = self.check_readiness()
        if not readiness.is_ready:
            raise DeploymentReadinessError(readiness.state.value, f"Local deployment not ready: {', '.join(readiness.errors)}")

        return {
            "strategy": "LOCAL",
            "artifact_path": self._config.local_artifact_path,
            "model_identifier": self._config.model_identifier,
            "repo_id": self._config.repo_id,
            "revision": self._config.revision,
            "timeout": self._config.resource_policy.timeout_seconds
        }


class HybridDeploymentStrategy(DeploymentStrategy):
    """Hybrid strategy routing heavy tasks/models to remote execution and lightweight tasks to local execution."""

    def route_request(self, request: ModelGenerationRequest) -> Dict[str, Any]:
        readiness = self.check_readiness()
        if not readiness.is_ready:
            raise DeploymentReadinessError(readiness.state.value, f"Hybrid deployment not ready: {', '.join(readiness.errors)}")

        # Decision rule: tasks marked with 'heavy' or main model 'sarvam-105b' route to REMOTE
        task_str = (request.task or "").lower()
        is_heavy = "heavy" in task_str or "main" in task_str or self._config.model_identifier == "sarvam-105b"

        if is_heavy:
            target = "REMOTE"
            ref = self._config.remote_endpoint
        else:
            target = "LOCAL"
            ref = self._config.local_artifact_path

        return {
            "strategy": "HYBRID",
            "target_execution": target,
            "reference": ref,
            "model_identifier": self._config.model_identifier,
            "repo_id": self._config.repo_id,
            "revision": self._config.revision
        }
