"""Generic Model Runtime Interface and Runtime State definitions for EarthMind."""

from enum import Enum
from typing import Protocol, Dict, Any, Optional, runtime_checkable
from core.schemas.model import ModelGenerationRequest, ModelGenerationResponse

class RuntimeState(str, Enum):
    """Explicit runtime operational states."""
    NOT_INITIALIZED = "NOT_INITIALIZED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"

@runtime_checkable
class IRuntime(Protocol):
    """Generic, model-agnostic contract for model execution runtimes."""

    def initialize(self) -> None:
        """Initialize runtime environment and check resource availability."""
        ...

    def start(self) -> None:
        """Start the runtime and transition state to READY/RUNNING."""
        ...

    def stop(self) -> None:
        """Stop runtime execution and transition to STOPPED state."""
        ...

    def shutdown(self) -> None:
        """Cleanup all runtime resources and reset state to NOT_INITIALIZED."""
        ...

    def status(self) -> Dict[str, Any]:
        """Return structured runtime health, state, and resource status."""
        ...

    def execute(self, request: ModelGenerationRequest, timeout: Optional[float] = None) -> ModelGenerationResponse:
        """Execute model generation request within controlled runtime context."""
        ...

    def cancel(self, request_id: str) -> bool:
        """Cancel an ongoing or queued model generation request."""
        ...
