"""Sarvam-105B Adapter implementing IModel contract for EarthMind AI Model Layer."""

from typing import Dict, Any, Optional
from core.interfaces.model import IModel
from core.schemas.model import ModelGenerationRequest, ModelGenerationResponse
from core.config.settings import ModelConfig
from core.errors.exceptions import ModelNotLoadedError, ModelExecutionError
from modules.ai.model_registry import ModelRegistry

class Sarvam105BAdapter(IModel):
    """Adapter for Sarvam-105B main model implementing IModel contract.

    Resolves configuration via ModelRegistry and exposes generic model interface
    without exposing model-specific internal details or loading large weights.
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        model_identifier: str = "sarvam-105b",
        config: Optional[ModelConfig] = None
    ):
        self._registry = registry or ModelRegistry()
        if config:
            self._config = config
        else:
            self._config = self._registry.get_model(model_identifier)

        self._is_loaded: bool = False

    @property
    def config(self) -> ModelConfig:
        return self._config

    def load(self) -> None:
        """Initialize adapter runtime state without downloading heavy weights (~424 GB)."""
        self._is_loaded = True

    def unload(self) -> None:
        """Reset adapter runtime state."""
        self._is_loaded = False

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResponse:
        """Generate model response using generic ModelGenerationRequest schema."""
        if not self._is_loaded:
            raise ModelNotLoadedError(self._config.identifier)

        if not isinstance(request, ModelGenerationRequest):
            raise ModelExecutionError(self._config.identifier, "Invalid request payload type")

        try:
            # Controlled stub response for Sarvam-105B adapter
            generated_text = f"Sarvam-105B processed task: {request.task}"
            if request.instructions:
                generated_text += f" | Instructions followed: {request.instructions}"

            return ModelGenerationResponse(
                request_id=request.request_id,
                status="success",
                response=generated_text,
                reasoning_data={"step": "Sarvam-105B reasoning pass"},
                tool_information=request.tools_available or [],
                confidence_level=0.95,
                uncertainty=0.05,
                warnings=[],
                model_version=f"{self._config.repo_id}@{self._config.revision[:8]}",
                metadata={
                    "model_identifier": self._config.identifier,
                    "repo_id": self._config.repo_id,
                    "revision": self._config.revision,
                    "provider": self._config.provider
                }
            )
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
            "health": "healthy" if self._is_loaded else "unloaded"
        }
