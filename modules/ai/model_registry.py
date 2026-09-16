"""EarthMind AI Module: ModelRegistry component."""

from typing import Dict, List, Optional
from core.config.settings import ModelConfig, settings
from core.errors.exceptions import EarthMindException

class ModelNotFoundError(EarthMindException):
    def __init__(self, identifier: str):
        super().__init__(
            message=f"Model identifier '{identifier}' is not registered in ModelRegistry.",
            error_code="MODEL_NOT_FOUND",
            module="ai",
            operation="registry_resolve"
        )

class InvalidModelConfigError(EarthMindException):
    def __init__(self, identifier: str, details: str):
        super().__init__(
            message=f"Invalid configuration for model '{identifier}': {details}",
            error_code="INVALID_MODEL_CONFIG",
            module="ai",
            operation="registry_validate"
        )

class ModelRegistry:
    """Central registry for managing EarthMind model configurations."""

    def __init__(self, register_defaults: bool = True):
        self._models: Dict[str, ModelConfig] = {}
        if register_defaults:
            self.register_model(settings.main_model)

    def register_model(self, config: ModelConfig) -> None:
        """Register or update a ModelConfig in the registry after validation."""
        try:
            config.validate_config()
        except ValueError as e:
            raise InvalidModelConfigError(config.identifier, str(e)) from e

        self._models[config.identifier] = config

    def get_model(self, identifier: str) -> ModelConfig:
        """Resolve and return a registered ModelConfig by its identifier."""
        if identifier not in self._models:
            raise ModelNotFoundError(identifier)
        return self._models[identifier]

    def get_main_model(self) -> ModelConfig:
        """Resolve the primary/main EarthMind model configuration."""
        for config in self._models.values():
            if config.is_main_model:
                return config
        # Fallback to default main model setting if not explicitly marked in dict
        return settings.main_model

    def list_models(self) -> List[str]:
        """Return a list of registered model identifiers."""
        return list(self._models.keys())

    def is_registered(self, identifier: str) -> bool:
        """Check if a model identifier is registered."""
        return identifier in self._models
