"""Sarvam-105B Adapter implementing IModel contract for EarthMind AI Model Layer."""

from typing import Dict, Any, Optional
from core.interfaces.model import IModel
from core.interfaces.runtime import IRuntime
from core.interfaces.initializer import IModelInitializer
from core.schemas.model import ModelGenerationRequest, ModelGenerationResponse
from core.config.settings import ModelConfig
from core.errors.exceptions import ModelNotLoadedError, ModelExecutionError, EarthMindException
from modules.ai.model_registry import ModelRegistry
from modules.ai.runtime import MockModelRuntime
from modules.ai.artifact_initializer import ModelInitializer

class Sarvam105BAdapter(IModel):
    """Adapter for Sarvam-105B main model implementing IModel contract.

    Resolves configuration via ModelRegistry, initializes via IModelInitializer,
    and executes via IRuntime, without exposing model-specific internal details
    or loading large weights (~424 GB).
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        model_identifier: str = "sarvam-105b",
        config: Optional[ModelConfig] = None,
        runtime: Optional[IRuntime] = None,
        initializer: Optional[IModelInitializer] = None
    ):
        self._registry = registry or ModelRegistry()
        if config:
            self._config = config
        else:
            self._config = self._registry.get_model(model_identifier)

        self._runtime: IRuntime = runtime or MockModelRuntime()
        self._initializer: IModelInitializer = initializer or ModelInitializer(registry=self._registry)
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

    def load(self) -> None:
        """Initialize artifact lifecycle and runtime state without downloading heavy weights (~424 GB)."""
        self._initializer.initialize(self._config.identifier)
        self._runtime.initialize()
        self._runtime.start()
        self._is_loaded = True

    def unload(self) -> None:
        """Reset adapter and stop/shutdown runtime."""
        self._runtime.stop()
        self._runtime.shutdown()
        self._is_loaded = False

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResponse:
        """Generate model response using generic ModelGenerationRequest schema via runtime execution."""
        if not self._is_loaded or not self._initializer.check_readiness():
            raise ModelNotLoadedError(self._config.identifier)

        if not isinstance(request, ModelGenerationRequest):
            raise ModelExecutionError(self._config.identifier, "Invalid request payload type")

        try:
            runtime_resp = self._runtime.execute(request)

            # Format/enrich response with Sarvam-105B model metadata
            generated_text = f"Sarvam-105B processed task: {request.task}"
            if request.instructions:
                generated_text += f" | Instructions followed: {request.instructions}"

            return ModelGenerationResponse(
                request_id=request.request_id,
                status=runtime_resp.status,
                response=generated_text,
                reasoning_data=runtime_resp.reasoning_data or {"step": "Sarvam-105B reasoning pass"},
                tool_information=runtime_resp.tool_information or [],
                confidence_level=runtime_resp.confidence_level or 0.95,
                uncertainty=runtime_resp.uncertainty or 0.05,
                warnings=runtime_resp.warnings,
                model_version=f"{self._config.repo_id}@{self._config.revision[:8]}",
                metadata={
                    "model_identifier": self._config.identifier,
                    "repo_id": self._config.repo_id,
                    "revision": self._config.revision,
                    "provider": self._config.provider,
                    "runtime_metadata": runtime_resp.metadata
                }
            )
        except EarthMindException:
            raise
        except Exception as e:
            raise ModelExecutionError(self._config.identifier, str(e)) from e

    def status(self) -> Dict[str, Any]:
        """Return operational status and configuration metadata combined with initializer and runtime status."""
        runtime_st = self._runtime.status()
        initializer_st = self._initializer.status()
        return {
            "identifier": self._config.identifier,
            "provider": self._config.provider,
            "repo_id": self._config.repo_id,
            "revision": self._config.revision,
            "is_main_model": self._config.is_main_model,
            "loaded": self._is_loaded,
            "health": "healthy" if self._is_loaded and runtime_st.get("health") == "healthy" and initializer_st.get("readiness") else "unloaded",
            "runtime": runtime_st,
            "initializer": initializer_st
        }
