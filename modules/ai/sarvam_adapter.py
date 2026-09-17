"""Sarvam-105B Adapter implementing IModel contract for EarthMind AI Model Layer."""

from typing import Dict, Any, Optional
from core.interfaces.model import IModel
from core.interfaces.runtime import IRuntime
from core.interfaces.initializer import IModelInitializer
from core.schemas.model import (
    ModelGenerationRequest,
    ModelGenerationResponse,
    DeploymentConfig,
    DeploymentMode
)
from core.config.settings import ModelConfig
from core.errors.exceptions import ModelNotLoadedError, ModelExecutionError
from modules.ai.model_registry import ModelRegistry
from modules.ai.model_initializer import ModelInitializer
from modules.ai.model_runtime import ModelRuntime, MockInferenceBackend
from modules.ai.inference_executor import InferenceExecutor
from modules.ai.deployment_strategy import (
    DeploymentStrategy,
    RemoteDeploymentStrategy,
    LocalDeploymentStrategy,
    HybridDeploymentStrategy,
    load_deployment_config
)


class Sarvam105BAdapter(IModel):
    """Adapter for Sarvam-105B main model implementing IModel contract.

    Resolves configuration via ModelRegistry and routes execution through
    InferenceExecutor -> ModelRuntime -> InferenceBackend while preserving
    generic model interface without loading heavy weights (~424 GB).
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        model_identifier: str = "sarvam-105b",
        version: Optional[str] = None,
        config: Optional[ModelConfig] = None,
        runtime: Optional[IRuntime] = None,
        initializer: Optional[IModelInitializer] = None,
        backend: Optional[MockInferenceBackend] = None,
        deployment_config: Optional[DeploymentConfig] = None,
        deployment_strategy: Optional[DeploymentStrategy] = None
    ):
        self._registry = registry or ModelRegistry()
        if config:
            self._config = config
        elif version:
            version_rec = self._registry.select_version(model_identifier, version)
            self._config = ModelConfig(
                identifier=version_rec.identifier,
                version=version_rec.version,
                family=version_rec.family,
                provider=version_rec.provider,
                repo_id=version_rec.repo_id,
                revision=version_rec.revision,
                model_type=version_rec.model_type,
                license=version_rec.license,
                provenance=version_rec.provenance,
                is_main_model=version_rec.is_main_model,
                lifecycle_state=version_rec.state.value,
                metadata=version_rec.metadata
            )
        else:
            self._config = self._registry.get_model(model_identifier)

        self._initializer = initializer or ModelInitializer(self._config)
        self._runtime = runtime or ModelRuntime(backend=backend)

        # Setup Deployment Strategy
        self._deployment_config = deployment_config or load_deployment_config({
            "model_identifier": self._config.identifier,
            "repo_id": self._config.repo_id,
            "revision": self._config.revision
        })

        if deployment_strategy:
            self._deployment_strategy = deployment_strategy
        else:
            if self._deployment_config.deployment_mode == DeploymentMode.LOCAL:
                self._deployment_strategy = LocalDeploymentStrategy(self._deployment_config)
            elif self._deployment_config.deployment_mode == DeploymentMode.HYBRID:
                self._deployment_strategy = HybridDeploymentStrategy(self._deployment_config)
            else:
                self._deployment_strategy = RemoteDeploymentStrategy(self._deployment_config)

        self._executor = InferenceExecutor(
            initializer=self._initializer,
            runtime=self._runtime,
            config=self._config
        )
        self._is_loaded: bool = False

    @property
    def config(self) -> ModelConfig:
        return self._config

    @property
    def runtime(self) -> IRuntime:
        return self._runtime

    @property
    def initializer(self) -> IModelInitializer:
        return self._initializer

    @property
    def executor(self) -> InferenceExecutor:
        return self._executor

    def load(self) -> None:
        """Initialize adapter runtime state and initializer without downloading heavy weights (~424 GB)."""
        self._initializer.initialize(self._config)
        self._runtime.initialize()
        self._is_loaded = True

    def unload(self) -> None:
        """Reset adapter runtime state and stop runtime."""
        self._runtime.shutdown()
        self._is_loaded = False

    def cancel(self, request_id: str) -> bool:
        """Cancel an in-flight inference request by ID."""
        return self._runtime.cancel(request_id)

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResponse:
        """Generate model response using generic ModelGenerationRequest schema through controlled inference pathway."""
        if not self._is_loaded:
            raise ModelNotLoadedError(self._config.identifier)

        if not isinstance(request, ModelGenerationRequest):
            raise ModelExecutionError(self._config.identifier, "Invalid request payload type")

        try:
            return self._executor.execute_inference(request)
        except Exception as e:
            if isinstance(e, (ModelNotLoadedError, ModelExecutionError)):
                raise e
            raise ModelExecutionError(self._config.identifier, str(e)) from e

    @property
    def deployment_config(self) -> DeploymentConfig:
        return self._deployment_config

    @property
    def deployment_strategy(self) -> DeploymentStrategy:
        return self._deployment_strategy

    def status(self) -> Dict[str, Any]:
        """Return operational status and configuration metadata."""
        readiness = self._deployment_strategy.check_readiness()
        return {
            "identifier": self._config.identifier,
            "version": getattr(self._config, "version", "1.0.0"),
            "provider": self._config.provider,
            "repo_id": self._config.repo_id,
            "revision": self._config.revision,
            "lifecycle_state": getattr(self._config, "lifecycle_state", "ACTIVE"),
            "deployment_mode": self._deployment_config.deployment_mode.value,
            "environment_profile": self._deployment_config.environment_profile.value,
            "deployment_readiness": readiness.state.value,
            "is_main_model": self._config.is_main_model,
            "loaded": self._is_loaded,
            "health": "healthy" if self._is_loaded else "unloaded",
            "initializer_status": self._initializer.status(),
            "runtime_status": self._runtime.status()
        }
