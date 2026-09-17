"""IRuntime interface for EarthMind AI Model Layer."""

from enum import Enum
from typing import Protocol, Dict, Any, runtime_checkable
from core.schemas.model import ModelGenerationRequest, ModelGenerationResponse


class RuntimeState(str, Enum):
    UNINITIALIZED = "UNINITIALIZED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    EXECUTING = "EXECUTING"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@runtime_checkable
class IRuntime(Protocol):
    """Generic runtime interface for AI execution models in EarthMind."""

    @property
    def state(self) -> RuntimeState:
        ...

    def initialize(self) -> None:
        ...

    def execute(self, request: ModelGenerationRequest) -> ModelGenerationResponse:
        ...

    def cancel(self, request_id: str) -> bool:
        ...

    def shutdown(self) -> None:
        ...

    def status(self) -> Dict[str, Any]:
        ...
