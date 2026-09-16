import pytest
from core.interfaces.runtime import IRuntime, RuntimeState
from core.schemas.model import ModelGenerationRequest, ModelGenerationResponse
from core.config.settings import ModelRuntimeConfig
from core.errors.exceptions import (
    InvalidRuntimeStateError,
    RuntimeUnavailableError,
    ResourceUnavailableError,
    ModelTimeoutError,
    ModelCancelledError,
    ModelExecutionError,
    ModelNotLoadedError
)
from modules.ai.runtime import BaseModelRuntime, MockModelRuntime
from modules.ai.sarvam_adapter import Sarvam105BAdapter

def test_runtime_interface_contract():
    runtime = MockModelRuntime()
    assert isinstance(runtime, IRuntime)

def test_runtime_initial_state():
    runtime = MockModelRuntime()
    assert runtime.state == RuntimeState.NOT_INITIALIZED

def test_runtime_lifecycle_and_state_transitions():
    runtime = MockModelRuntime()

    # Initialize: NOT_INITIALIZED -> READY
    runtime.initialize()
    assert runtime.state == RuntimeState.READY

    # Start: READY -> RUNNING
    runtime.start()
    assert runtime.state == RuntimeState.RUNNING

    # Stop: RUNNING -> STOPPED
    runtime.stop()
    assert runtime.state == RuntimeState.STOPPED

    # Shutdown: STOPPED -> NOT_INITIALIZED
    runtime.shutdown()
    assert runtime.state == RuntimeState.NOT_INITIALIZED

def test_invalid_state_transitions():
    runtime = MockModelRuntime()

    # Cannot start before initializing
    with pytest.raises(InvalidRuntimeStateError):
        runtime.start()

    # Cannot stop before starting
    with pytest.raises(InvalidRuntimeStateError):
        runtime.stop()

def test_successful_request_execution():
    runtime = MockModelRuntime()
    runtime.initialize()
    runtime.start()

    req = ModelGenerationRequest(request_id="req-1", task="Soil moisture prediction")
    resp = runtime.execute(req)

    assert isinstance(resp, ModelGenerationResponse)
    assert resp.request_id == "req-1"
    assert resp.status == "success"
    assert "Soil moisture prediction" in resp.response

def test_resource_unavailable_handling():
    runtime = MockModelRuntime(simulate_resource_failure=True)
    with pytest.raises(ResourceUnavailableError) as exc_info:
        runtime.initialize()
    assert runtime.state == RuntimeState.FAILED
    assert "Simulated GPU allocation failure" in str(exc_info.value)

def test_execution_failure_handling():
    runtime = MockModelRuntime(simulate_execution_failure=True)
    runtime.initialize()
    runtime.start()

    req = ModelGenerationRequest(request_id="req-fail", task="Failing task")
    with pytest.raises(ModelExecutionError) as exc_info:
        runtime.execute(req)
    assert "Simulated runtime model failure" in str(exc_info.value)

def test_timeout_handling():
    runtime = MockModelRuntime(simulate_timeout=True)
    runtime.initialize()
    runtime.start()

    req = ModelGenerationRequest(request_id="req-timeout", task="Slow computation")
    with pytest.raises(ModelTimeoutError) as exc_info:
        runtime.execute(req, timeout=1.0)
    assert "req-timeout" in str(exc_info.value)
    assert exc_info.value.error_contract.error_code == "MODEL_TIMEOUT"

def test_cancellation_handling():
    runtime = MockModelRuntime()
    runtime.initialize()
    runtime.start()

    req = ModelGenerationRequest(request_id="req-cancel", task="Cancellable task")
    runtime.cancel("req-cancel")

    with pytest.raises(ModelCancelledError) as exc_info:
        runtime.execute(req)
    assert "req-cancel" in str(exc_info.value)

def test_concurrency_limit_behavior():
    config = ModelRuntimeConfig(concurrency_limit=1)
    runtime = MockModelRuntime(config=config)
    runtime.initialize()
    runtime.start()

    # Artificially set active execution count to 1
    runtime._active_count = 1

    req = ModelGenerationRequest(request_id="req-rejected", task="Over-limit task")
    with pytest.raises(RuntimeUnavailableError) as exc_info:
        runtime.execute(req)
    assert "Concurrency limit reached" in str(exc_info.value)

def test_runtime_status_and_health():
    runtime = MockModelRuntime()
    st_unloaded = runtime.status()
    assert st_unloaded["state"] == "NOT_INITIALIZED"
    assert st_unloaded["health"] == "unhealthy"

    runtime.initialize()
    st_ready = runtime.status()
    assert st_ready["state"] == "READY"
    assert st_ready["health"] == "healthy"

def test_sarvam_adapter_runtime_integration():
    mock_rt = MockModelRuntime()
    adapter = Sarvam105BAdapter(runtime=mock_rt)

    assert adapter.status()["loaded"] is False

    # Load adapter -> initializes and starts runtime
    adapter.load()
    assert adapter.status()["loaded"] is True
    assert adapter.status()["health"] == "healthy"
    assert mock_rt.state == RuntimeState.RUNNING

    # Generate request via adapter
    req = ModelGenerationRequest(request_id="sarvam-req-1", task="Crop disease identification")
    resp = adapter.generate(req)

    assert resp.request_id == "sarvam-req-1"
    assert resp.status == "success"
    assert "Crop disease identification" in resp.response

    # Unload adapter -> stops and shuts down runtime
    adapter.unload()
    assert adapter.status()["loaded"] is False
    assert mock_rt.state == RuntimeState.NOT_INITIALIZED

    # Generation after unload fails with ModelNotLoadedError
    with pytest.raises(ModelNotLoadedError):
        adapter.generate(req)
