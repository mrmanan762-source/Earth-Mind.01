"""Sarvam-105B Adapter implementing IModel contract for EarthMind AI Model Layer."""

from typing import Dict, Any, Optional
from core.interfaces.model import IModel
from core.interfaces.runtime import IRuntime
from core.interfaces.initializer import IModelInitializer
from core.schemas.model import ModelGenerationRequest, ModelGenerationResponse
from core.config.settings import ModelConfig
from core.errors.exceptions import ModelNotLoadedError, ModelExecutionError
from modules.ai.model_registry import ModelRegistry
from modules.ai.model_initializer import ModelInitializer
from modules.ai.model_runtime import ModelRuntime, MockInferenceBackend
from modules.ai.inference_executor import InferenceExecutor


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
        config: Optional[ModelConfig] = None,
        runtime: Optional[IRuntime] = None,
        initializer: Optional[IModelInitializer] = None,
        backend: Optional[MockInferenceBackend] = None
    ):
        self._registry = registry or ModelRegistry()
        if config:
            self._config = config
        else:
            self._config = self._registry.get_model(model_identifier)

        self._initializer = initializer or ModelInitializer(self._config)
        self._runtime = runtime or ModelRuntime(backend=backend)
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

    def status(self) -> Dict[str, Any]:
        """Return operational status and configuration metadata."""
        return {
            "identifier": self._config.identifier,
            "provider": self._config.provider,
            "repo_id": self._config.repo_id,
            "revision": self._config.revision,
            "is_main_model": self._config.is_main_model,
            "loaded": self._is_loaded,
            "health": "healthy" if self._is_loaded else "unloaded",
            "initializer_status": self._initializer.status(),
            "runtime_status": self._runtime.status()
        }
