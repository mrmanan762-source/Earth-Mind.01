"""Generic Model Loading and Initialization Interfaces for EarthMind."""

from enum import Enum
from typing import Protocol, Dict, Any, Optional, runtime_checkable

class InitializationState(str, Enum):
    """Explicit model initialization states."""
    NOT_INITIALIZED = "NOT_INITIALIZED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    NOT_READY = "NOT_READY"
    REINITIALIZING = "REINITIALIZING"

class LoadingStrategy(str, Enum):
    """Supported model loading strategies."""
    REMOTE = "REMOTE"
    LOCAL = "LOCAL"
    HYBRID = "HYBRID"

@runtime_checkable
class IArtifactResolver(Protocol):
    """Protocol for resolving model artifacts from ModelRegistry/ModelConfig."""
    def resolve_artifact(self, model_identifier: str) -> Dict[str, Any]:
        ...

@runtime_checkable
class IEnvironmentDetector(Protocol):
    """Protocol for detecting system compute/memory resources."""
    def detect_environment(self) -> Dict[str, Any]:
        ...
    def check_resource_sufficiency(self, required_resources: Dict[str, Any]) -> bool:
        ...

@runtime_checkable
class ICompatibilityChecker(Protocol):
    """Protocol for validating model artifact compatibility with current environment."""
    def validate_compatibility(self, artifact: Dict[str, Any], env_info: Dict[str, Any]) -> bool:
        ...

@runtime_checkable
class ILoadingStrategy(Protocol):
    """Protocol for model loading strategies (Remote, Local, Hybrid)."""
    def prepare_artifact(self, artifact: Dict[str, Any], env_info: Dict[str, Any]) -> Dict[str, Any]:
        ...

@runtime_checkable
class IModelInitializer(Protocol):
    """Protocol for model initialization lifecycle and readiness management."""
    def initialize(self, model_identifier: str = "sarvam-105b") -> Dict[str, Any]:
        ...
    def reinitialize(self, model_identifier: str = "sarvam-105b") -> Dict[str, Any]:
        ...
    def check_readiness(self) -> bool:
        ...
    def status(self) -> Dict[str, Any]:
        ...
