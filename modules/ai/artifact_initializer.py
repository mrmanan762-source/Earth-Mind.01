"""Model Artifact Resolution, Environment Detection, Compatibility Checking, and Model Initialization infrastructure."""

import os
import sys
from typing import Dict, Any, Optional
from core.interfaces.initializer import (
    IModelInitializer,
    IArtifactResolver,
    IEnvironmentDetector,
    ICompatibilityChecker,
    ILoadingStrategy,
    InitializationState,
    LoadingStrategy
)
from core.config.settings import ModelLoadingConfig, settings
from core.logging.logger import get_logger
from core.errors.exceptions import (
    ArtifactNotFoundError,
    EnvironmentIncompatibleError,
    InitializationError,
    ReadinessError,
    ResourceUnavailableError
)
from modules.ai.model_registry import ModelRegistry, ModelNotFoundError

logger = get_logger("ai_initializer")

class ModelArtifactResolver(IArtifactResolver):
    """Resolves model artifacts from ModelRegistry without creating secondary configuration."""

    def __init__(self, registry: Optional[ModelRegistry] = None):
        self._registry = registry or ModelRegistry()

    def resolve_artifact(self, model_identifier: str) -> Dict[str, Any]:
        try:
            config = self._registry.get_model(model_identifier)
            return {
                "identifier": config.identifier,
                "repo_id": config.repo_id,
                "revision": config.revision,
                "provider": config.provider,
                "model_type": config.model_type,
                "license": config.license,
                "provenance": config.provenance,
                "is_main_model": config.is_main_model
            }
        except ModelNotFoundError as e:
            logger.error(f"Artifact resolution failed: {e}")
            raise ArtifactNotFoundError(model_identifier, str(e)) from e
        except Exception as e:
            logger.error(f"Unexpected error resolving artifact '{model_identifier}': {e}")
            raise ArtifactNotFoundError(model_identifier, str(e)) from e

class EnvironmentDetector(IEnvironmentDetector):
    """Detects host system resources and environment compatibility."""

    def detect_environment(self) -> Dict[str, Any]:
        return {
            "environment": settings.environment,
            "cpu_count": os.cpu_count() or 1,
            "python_version": sys.version.split()[0],
            "has_gpu": False,
            "gpu_count": 0,
            "estimated_ram_gb": 16.0,  # Safe dev default estimate
            "estimated_vram_gb": 0.0
        }

    def check_resource_sufficiency(self, required_resources: Dict[str, Any]) -> bool:
        env_info = self.detect_environment()
        req_ram = required_resources.get("required_ram_gb", 0.0)
        req_vram = required_resources.get("required_vram_gb", 0.0)

        if req_ram > env_info["estimated_ram_gb"]:
            return False
        if req_vram > env_info["estimated_vram_gb"]:
            return False
        return True

class CompatibilityChecker(ICompatibilityChecker):
    """Validates compatibility between model artifact requirements and environment capabilities."""

    def validate_compatibility(self, artifact: Dict[str, Any], env_info: Dict[str, Any]) -> bool:
        if not artifact.get("repo_id") or "/" not in artifact["repo_id"]:
            raise EnvironmentIncompatibleError(f"Invalid repository ID format in artifact '{artifact.get('identifier')}'.")

        if not artifact.get("revision") or len(artifact["revision"]) < 8:
            raise EnvironmentIncompatibleError(f"Invalid pinned revision in artifact '{artifact.get('identifier')}'.")

        return True

class RemoteLoadingStrategy(ILoadingStrategy):
    """Primary remote loading strategy for Sarvam-105B hosted on Hugging Face (mrmanan762/EarthMind)."""

    def prepare_artifact(self, artifact: Dict[str, Any], env_info: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"Preparing remote artifact endpoint for '{artifact['identifier']}' ({artifact['repo_id']}@{artifact['revision'][:8]}).")
        return {
            "status": "prepared",
            "strategy": LoadingStrategy.REMOTE.value,
            "repo_id": artifact["repo_id"],
            "revision": artifact["revision"],
            "remote_endpoint": f"https://huggingface.co/{artifact['repo_id']}/tree/{artifact['revision']}"
        }

class LocalLoadingStrategy(ILoadingStrategy):
    """Local loading strategy with resource safeguards against downloading ~424 GB model weights."""

    def prepare_artifact(self, artifact: Dict[str, Any], env_info: Dict[str, Any]) -> Dict[str, Any]:
        # Local loading safeguard check
        if artifact.get("identifier") == "sarvam-105b" and env_info.get("estimated_ram_gb", 0) < 500:
            raise ResourceUnavailableError(
                "SystemMemory",
                f"Local loading of ~424 GB Sarvam-105B model requires >=500 GB RAM/VRAM. Found {env_info.get('estimated_ram_gb')} GB."
            )

        return {
            "status": "prepared",
            "strategy": LoadingStrategy.LOCAL.value,
            "local_path": settings.loading.local_cache_dir
        }

class ModelInitializer(IModelInitializer):
    """Manages model loading and initialization lifecycle, readiness checks, and reinitialization."""

    def __init__(
        self,
        config: Optional[ModelLoadingConfig] = None,
        resolver: Optional[IArtifactResolver] = None,
        detector: Optional[IEnvironmentDetector] = None,
        checker: Optional[ICompatibilityChecker] = None,
        registry: Optional[ModelRegistry] = None
    ):
        self.config = config or settings.loading
        self.resolver = resolver or ModelArtifactResolver(registry=registry)
        self.detector = detector or EnvironmentDetector()
        self.checker = checker or CompatibilityChecker()

        self._state: InitializationState = InitializationState.NOT_INITIALIZED
        self._active_artifact: Optional[Dict[str, Any]] = None
        self._prepared_info: Optional[Dict[str, Any]] = None

    @property
    def state(self) -> InitializationState:
        return self._state

    def initialize(self, model_identifier: str = "sarvam-105b") -> Dict[str, Any]:
        """Execute structured model initialization lifecycle."""
        if self._state == InitializationState.INITIALIZING:
            raise InitializationError(model_identifier, "Initialization is already in progress.")

        logger.info(f"Starting model initialization for '{model_identifier}'...")
        self._state = InitializationState.INITIALIZING

        try:
            # 1. Resolve artifact
            artifact = self.resolver.resolve_artifact(model_identifier)
            logger.info(f"Resolved artifact '{artifact['identifier']}' -> {artifact['repo_id']}@{artifact['revision'][:8]}")

            # 2. Detect environment
            env_info = self.detector.detect_environment()

            # 3. Compatibility check
            self.checker.validate_compatibility(artifact, env_info)

            # 4. Select strategy
            strategy_name = self.config.loading_strategy.upper()
            if strategy_name == LoadingStrategy.LOCAL.value:
                strategy: ILoadingStrategy = LocalLoadingStrategy()
            else:
                strategy = RemoteLoadingStrategy()

            # 5. Prepare loading strategy (with resource safeguards)
            prepared = strategy.prepare_artifact(artifact, env_info)

            # 6. Finalize readiness
            self._active_artifact = artifact
            self._prepared_info = prepared
            self._state = InitializationState.READY

            logger.info(f"Model initialization for '{model_identifier}' completed successfully. State set to READY.")
            return self.status()

        except Exception as e:
            self._state = InitializationState.NOT_READY
            logger.error(f"Initialization failed for model '{model_identifier}': {e}")
            if isinstance(e, (ArtifactNotFoundError, EnvironmentIncompatibleError, ResourceUnavailableError)):
                raise e
            raise InitializationError(model_identifier, str(e)) from e

    def reinitialize(self, model_identifier: str = "sarvam-105b") -> Dict[str, Any]:
        """Safely reset previous state and re-execute initialization lifecycle."""
        logger.info(f"Reinitializing model '{model_identifier}'...")
        self._state = InitializationState.REINITIALIZING
        self._active_artifact = None
        self._prepared_info = None
        return self.initialize(model_identifier=model_identifier)

    def check_readiness(self) -> bool:
        """Confirm if the model artifact is loaded, initialized, and ready for execution."""
        if self._state != InitializationState.READY:
            return False
        if not self._active_artifact or not self._prepared_info:
            return False
        return True

    def status(self) -> Dict[str, Any]:
        """Return structured status without revealing sensitive credentials or tokens."""
        return {
            "state": self._state.value,
            "readiness": self.check_readiness(),
            "loading_strategy": self.config.loading_strategy,
            "active_artifact": {
                "identifier": self._active_artifact["identifier"],
                "repo_id": self._active_artifact["repo_id"],
                "revision": self._active_artifact["revision"]
            } if self._active_artifact else None,
            "prepared_info": self._prepared_info
        }
