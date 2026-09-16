"""Model Runtime infrastructure and Mock Runtime implementation for EarthMind."""

import time
from typing import Dict, Any, Optional, Set
from core.interfaces.runtime import IRuntime, RuntimeState
from core.schemas.model import ModelGenerationRequest, ModelGenerationResponse
from core.config.settings import ModelRuntimeConfig, settings
from core.logging.logger import get_logger
from core.errors.exceptions import (
    InvalidRuntimeStateError,
    RuntimeUnavailableError,
    ResourceUnavailableError,
    ModelTimeoutError,
    ModelCancelledError,
    ModelExecutionError
)

logger = get_logger("ai_runtime")

class BaseModelRuntime(IRuntime):
    """Base abstract runtime handling state machine, concurrency, resources, timeouts, and cancellations."""

    def __init__(self, config: Optional[ModelRuntimeConfig] = None):
        self.config = config or settings.runtime
        self._state: RuntimeState = RuntimeState.NOT_INITIALIZED
        self._active_count: int = 0
        self._cancelled_requests: Set[str] = set()
        self._resources_allocated: bool = False

    @property
    def state(self) -> RuntimeState:
        return self._state

    def initialize(self) -> None:
        """Transition from NOT_INITIALIZED / STOPPED to READY."""
        if self._state not in (RuntimeState.NOT_INITIALIZED, RuntimeState.STOPPED):
            raise InvalidRuntimeStateError(self._state.value, "initialize")

        logger.info(f"Runtime initializing (mode={self.config.runtime_mode})...")
        self._state = RuntimeState.INITIALIZING

        try:
            self._check_resources()
            self._allocate_resources()
            self._state = RuntimeState.READY
            logger.info("Runtime initialization complete. State set to READY.")
        except Exception as e:
            self._state = RuntimeState.FAILED
            logger.error(f"Runtime initialization failed: {e}")
            raise e

    def start(self) -> None:
        """Transition from READY to RUNNING."""
        if self._state not in (RuntimeState.READY, RuntimeState.RUNNING):
            raise InvalidRuntimeStateError(self._state.value, "start")

        self._state = RuntimeState.RUNNING
        logger.info("Runtime started. State set to RUNNING.")

    def stop(self) -> None:
        """Transition from RUNNING / READY to STOPPED."""
        if self._state not in (RuntimeState.RUNNING, RuntimeState.READY, RuntimeState.FAILED):
            raise InvalidRuntimeStateError(self._state.value, "stop")

        logger.info("Runtime stopping...")
        self._state = RuntimeState.STOPPING
        self._release_resources()
        self._state = RuntimeState.STOPPED
        logger.info("Runtime stopped. State set to STOPPED.")

    def shutdown(self) -> None:
        """Cleanup all resources and reset to NOT_INITIALIZED."""
        logger.info("Runtime shutting down...")
        if self._state not in (RuntimeState.STOPPED, RuntimeState.FAILED, RuntimeState.NOT_INITIALIZED):
            self._release_resources()
        self._cancelled_requests.clear()
        self._active_count = 0
        self._state = RuntimeState.NOT_INITIALIZED
        logger.info("Runtime shutdown complete. State set to NOT_INITIALIZED.")

    def _check_resources(self) -> None:
        """Hook for resource availability checks."""
        pass

    def _allocate_resources(self) -> None:
        """Hook for resource allocation."""
        self._resources_allocated = True

    def _release_resources(self) -> None:
        """Hook for releasing resources."""
        self._resources_allocated = False

    def status(self) -> Dict[str, Any]:
        """Return structured status of runtime health and state."""
        return {
            "state": self._state.value,
            "runtime_mode": self.config.runtime_mode,
            "concurrency_limit": self.config.concurrency_limit,
            "active_executions": self._active_count,
            "resources_allocated": self._resources_allocated,
            "health": "healthy" if self._state in (RuntimeState.READY, RuntimeState.RUNNING) else "unhealthy"
        }

    def cancel(self, request_id: str) -> bool:
        """Register cancellation request for request_id."""
        logger.info(f"Cancellation requested for request '{request_id}'.")
        self._cancelled_requests.add(request_id)
        return True

    def execute(self, request: ModelGenerationRequest, timeout: Optional[float] = None) -> ModelGenerationResponse:
        """Base execution wrapper controlling concurrency, cancellation, timeout, and state checks."""
        if self._state not in (RuntimeState.READY, RuntimeState.RUNNING):
            raise RuntimeUnavailableError(f"Runtime in state '{self._state.value}' is not operational.")

        if self._active_count >= self.config.concurrency_limit:
            logger.warning(f"Concurrency limit ({self.config.concurrency_limit}) reached for request '{request.request_id}'.")
            raise RuntimeUnavailableError("Concurrency limit reached.")

        if request.request_id in self._cancelled_requests:
            self._cancelled_requests.remove(request.request_id)
            raise ModelCancelledError(request.request_id)

        effective_timeout = timeout if timeout is not None else self.config.execution_timeout

        self._active_count += 1
        logger.info(f"Request '{request.request_id}' execution started (active: {self._active_count}).")

        try:
            response = self._do_execute(request, effective_timeout)
            logger.info(f"Request '{request.request_id}' execution completed successfully.")
            return response
        except Exception as e:
            logger.error(f"Request '{request.request_id}' execution failed: {e}")
            raise e
        finally:
            self._active_count = max(0, self._active_count - 1)

    def _do_execute(self, request: ModelGenerationRequest, timeout: float) -> ModelGenerationResponse:
        raise NotImplementedError("Subclasses must implement _do_execute")

class MockModelRuntime(BaseModelRuntime):
    """Lightweight mock runtime for deterministic testing without heavy weight loading (~424 GB)."""

    def __init__(
        self,
        config: Optional[ModelRuntimeConfig] = None,
        simulate_resource_failure: bool = False,
        simulate_execution_failure: bool = False,
        simulate_timeout: bool = False,
        simulated_delay: float = 0.0
    ):
        super().__init__(config=config)
        self.simulate_resource_failure = simulate_resource_failure
        self.simulate_execution_failure = simulate_execution_failure
        self.simulate_timeout = simulate_timeout
        self.simulated_delay = simulated_delay

    def _check_resources(self) -> None:
        if self.simulate_resource_failure:
            raise ResourceUnavailableError("MockGPU", "Simulated GPU allocation failure.")

    def _do_execute(self, request: ModelGenerationRequest, timeout: float) -> ModelGenerationResponse:
        if request.request_id in self._cancelled_requests:
            self._cancelled_requests.remove(request.request_id)
            raise ModelCancelledError(request.request_id)

        if self.simulate_timeout:
            time.sleep(min(0.01, timeout))
            raise ModelTimeoutError(request.request_id, timeout)

        if self.simulated_delay > 0:
            time.sleep(min(self.simulated_delay, timeout))

        if self.simulate_execution_failure:
            raise ModelExecutionError("mock-runtime", "Simulated runtime model failure.")

        return ModelGenerationResponse(
            request_id=request.request_id,
            status="success",
            response=f"MockRuntime result for task: {request.task}",
            reasoning_data={"step": "mock reasoning"},
            tool_information=request.tools_available or [],
            confidence_level=0.99,
            uncertainty=0.01,
            warnings=[],
            model_version="mock-runtime-v1",
            metadata={"runtime_mode": self.config.runtime_mode}
        )
