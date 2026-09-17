"""Model Initializer for EarthMind AI Model Layer."""

from typing import Dict, Any, Optional
from core.interfaces.initializer import IModelInitializer, InitializationState
from core.config.settings import ModelConfig
from core.logging.logger import get_logger

logger = get_logger("modules.ai.initializer")


class ModelInitializer(IModelInitializer):
    """Model initializer enforcing compatibility checks and readiness tracking without loading heavy weights."""

    def __init__(self, config: Optional[ModelConfig] = None):
        self._config = config
        self._state = InitializationState.UNINITIALIZED

    @property
    def state(self) -> InitializationState:
        return self._state

    def check_compatibility(self, config: ModelConfig) -> bool:
        """Verify model configuration compatibility."""
        try:
            return config.validate_config()
        except Exception as e:
            logger.warning(f"Compatibility check failed for model '{config.identifier}': {e}")
            return False

    def initialize(self, config: Optional[ModelConfig] = None) -> bool:
        """Initialize model configuration and transition to READY state."""
        target_config = config or self._config
        if not target_config:
            self._state = InitializationState.FAILED
            logger.error("Model initialization failed: No ModelConfig provided.")
            return False

        self._config = target_config
        self._state = InitializationState.RESOLVING
        logger.info(f"Resolving model artifacts for '{self._config.identifier}' ({self._config.repo_id}@{self._config.revision[:8]})...")

        if not self.check_compatibility(self._config):
            self._state = InitializationState.FAILED
            logger.error(f"Model initialization failed: Incompatible config for '{self._config.identifier}'.")
            return False

        self._state = InitializationState.LOADING
        logger.info(f"Preparing initialization state for '{self._config.identifier}' (stub mode, zero weight download)...")

        self._state = InitializationState.READY
        logger.info(f"Model '{self._config.identifier}' initialized and READY.")
        return True

    def status(self) -> Dict[str, Any]:
        return {
            "state": self._state.value,
            "identifier": self._config.identifier if self._config else None,
            "repo_id": self._config.repo_id if self._config else None,
            "revision": self._config.revision if self._config else None,
            "is_ready": self._state == InitializationState.READY
        }
