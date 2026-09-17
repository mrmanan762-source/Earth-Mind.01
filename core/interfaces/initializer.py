"""IModelInitializer interface for EarthMind AI Model Layer."""

from enum import Enum
from typing import Protocol, Dict, Any, runtime_checkable
from core.config.settings import ModelConfig


class InitializationState(str, Enum):
    UNINITIALIZED = "UNINITIALIZED"
    RESOLVING = "RESOLVING"
    LOADING = "LOADING"
    READY = "READY"
    FAILED = "FAILED"


@runtime_checkable
class IModelInitializer(Protocol):
    """Generic initializer interface for EarthMind AI models."""

    @property
    def state(self) -> InitializationState:
        ...

    def initialize(self, config: ModelConfig) -> bool:
        ...

    def check_compatibility(self, config: ModelConfig) -> bool:
        ...

    def status(self) -> Dict[str, Any]:
        ...
