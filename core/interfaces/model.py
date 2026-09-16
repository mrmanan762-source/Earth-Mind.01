"""Generic IModel Interface for EarthMind AI Model Layer."""

from typing import Protocol, Dict, Any, runtime_checkable
from core.schemas.model import ModelGenerationRequest, ModelGenerationResponse

@runtime_checkable
class IModel(Protocol):
    """Generic, model-agnostic contract for AI models in EarthMind."""

    def load(self) -> None:
        """Load model resources."""
        ...

    def unload(self) -> None:
        """Unload model resources and free memory/device context."""
        ...

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResponse:
        """Generate response given a structured model request."""
        ...

    def status(self) -> Dict[str, Any]:
        """Return model operational status and health capability."""
        ...
