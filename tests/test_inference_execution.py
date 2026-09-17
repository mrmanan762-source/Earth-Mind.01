import time
import pytest
import logging
from core.schemas.model import (
    ModelGenerationRequest,
    ModelGenerationResponse,
    InferenceExecutionState
)
from core.interfaces.initializer import InitializationState
from core.interfaces.runtime import RuntimeState
from core.interfaces.model import IModel
from core.config.settings import ModelConfig
from modules.ai.sarvam_adapter import Sarvam105BAdapter
from modules.ai.model_runtime import ModelRuntime, MockInferenceBackend
from modules.ai.model_initializer import ModelInitializer
from modules.ai.inference_executor import InferenceExecutor, sanitize_text


def test_valid_inference_request_and_response_normalization():
    adapter = Sarvam105BAdapter()
    adapter.load()

    req = ModelGenerationRequest(
        request_id="test-req-001",
        task="Assess soil nitrogen level",
        instructions="Provide high-level recommendations",
        context={"field_id": "field_42", "ph": 6.8},
        conversation=[{"role": "user", "content": "Hello"}],
        tools_available=[{"name": "soil_tester"}],
        constraints={"max_tokens": 100},
        metadata={"user_tier": "premium"}
    )

    resp = adapter.generate(req)

    assert isinstance(resp, ModelGenerationResponse)
    assert resp.request_id == "test-req-001"
    assert resp.status == "success"
    assert "Assess soil nitrogen level" in resp.response
    assert resp.confidence_level == 0.95
    assert resp.uncertainty == 0.05
    assert resp.warnings == []
    assert resp.model_version == "mrmanan762/EarthMind@fb187764"
    assert resp.metadata["execution_state"] == InferenceExecutionState.COMPLETED.value
    assert resp.metadata["model_identifier"] == "sarvam-105b"
    assert resp.metadata["user_tier"] == "premium"
    assert resp.metadata["context_preserved"] is True
    assert resp.metadata["conversation_length"] == 1

    adapter.unload()


def test_invalid_request_validation():
    adapter = Sarvam105BAdapter()
    adapter.load()

    # Empty task
    req_empty_task = ModelGenerationRequest(
        request_id="test-invalid-1",
        task="   "
    )
    resp = adapter.generate(req_empty_task)
    assert resp.status == InferenceExecutionState.FAILED.value
    assert resp.metadata["execution_state"] == InferenceExecutionState.FAILED.value
    assert resp.metadata["error_code"] == "INFERENCE_VALIDATION_ERROR"
    assert "Field 'task' is required" in resp.warnings[0]

    adapter.unload()


def test_model_not_ready_unavailability():
    config = ModelConfig(
        identifier="sarvam-105b",
        provider="huggingface",
        repo_id="mrmanan762/EarthMind",
        revision="fb187764dbad56ed8b26742a802909e858e9bb72"
    )
    initializer = ModelInitializer(config)
    # Intentionally do NOT initialize initializer -> state remains UNINITIALIZED
    backend = MockInferenceBackend()
    runtime = ModelRuntime(backend=backend)
    runtime.initialize()

    executor = InferenceExecutor(initializer=initializer, runtime=runtime, config=config)

    req = ModelGenerationRequest(request_id="req-not-ready", task="Pest prediction")
    resp = executor.execute_inference(req)

    assert resp.status == InferenceExecutionState.UNAVAILABLE.value
    assert resp.metadata["execution_state"] == InferenceExecutionState.UNAVAILABLE.value
    assert resp.metadata["error_code"] == "MODEL_NOT_READY"


def test_runtime_unavailable():
    config = ModelConfig(
        identifier="sarvam-105b",
        provider="huggingface",
        repo_id="mrmanan762/EarthMind",
        revision="fb187764dbad56ed8b26742a802909e858e9bb72"
    )
    initializer = ModelInitializer(config)
    initializer.initialize(config)

    # Runtime is NOT initialized -> state UNINITIALIZED
    runtime = ModelRuntime()
    executor = InferenceExecutor(initializer=initializer, runtime=runtime, config=config)

    req = ModelGenerationRequest(request_id="req-rt-unavail", task="Crop recommendation")
    resp = executor.execute_inference(req)

    assert resp.status == InferenceExecutionState.UNAVAILABLE.value
    assert resp.metadata["execution_state"] == InferenceExecutionState.UNAVAILABLE.value
    assert resp.metadata["error_code"] == "RUNTIME_UNAVAILABLE"


def test_mock_backend_controlled_failure():
    backend = MockInferenceBackend(should_fail=True, fail_message="Simulated GPU OOM error")
    adapter = Sarvam105BAdapter(backend=backend)
    adapter.load()

    req = ModelGenerationRequest(request_id="req-fail-01", task="Simulate failure")
    resp = adapter.generate(req)

    assert resp.status == InferenceExecutionState.FAILED.value
    assert resp.metadata["execution_state"] == InferenceExecutionState.FAILED.value
    assert "Simulated GPU OOM error" in resp.warnings[0]

    adapter.unload()


def test_execution_timeout_simulation():
    backend = MockInferenceBackend(simulate_delay=1.0)
    adapter = Sarvam105BAdapter(backend=backend)
    adapter.load()

    req = ModelGenerationRequest(request_id="req-timeout-01", task="Long running query")
    # Timeout set to 0.1s while delay is 1.0s
    resp = adapter.executor.execute_inference(req, timeout=0.1)

    assert resp.status == InferenceExecutionState.TIMEOUT.value
    assert resp.metadata["execution_state"] == InferenceExecutionState.TIMEOUT.value
    assert "timed out" in resp.warnings[0]

    adapter.unload()


def test_execution_cancellation_simulation():
    backend = MockInferenceBackend(simulate_delay=0.5)
    adapter = Sarvam105BAdapter(backend=backend)
    adapter.load()

    req = ModelGenerationRequest(request_id="req-cancel-01", task="Cancellable request")

    # Request cancellation before/during execution
    adapter.cancel("req-cancel-01")
    resp = adapter.generate(req)

    assert resp.status == InferenceExecutionState.CANCELLED.value
    assert resp.metadata["execution_state"] == InferenceExecutionState.CANCELLED.value
    assert "cancelled" in resp.warnings[0]

    adapter.unload()


def test_concurrency_limit_enforcement():
    backend = MockInferenceBackend(simulate_delay=0.15)
    runtime = ModelRuntime(backend=backend, max_concurrency=1)
    runtime.initialize()

    config = ModelConfig(
        identifier="sarvam-105b",
        provider="huggingface",
        repo_id="mrmanan762/EarthMind",
        revision="fb187764dbad56ed8b26742a802909e858e9bb72"
    )
    initializer = ModelInitializer(config)
    initializer.initialize(config)

    executor = InferenceExecutor(initializer=initializer, runtime=runtime, config=config)

    import threading
    results = {}

    def _worker(req_id, req_timeout):
        req = ModelGenerationRequest(request_id=req_id, task="Concurrent task")
        res = executor.execute_inference(req, timeout=req_timeout)
        results[req_id] = res

    t1 = threading.Thread(target=_worker, args=("req-conc-1", 0.5))
    t2 = threading.Thread(target=_worker, args=("req-conc-2", 0.05))

    t1.start()
    time.sleep(0.01)
    t2.start()

    t1.join()
    t2.join()

    assert results["req-conc-1"].status == "success"
    assert results["req-conc-2"].status == InferenceExecutionState.TIMEOUT.value


def test_duplicate_request_id_prevention():
    adapter = Sarvam105BAdapter()
    adapter.load()

    req1 = ModelGenerationRequest(request_id="req-dup-100", task="First execution")
    resp1 = adapter.generate(req1)
    assert resp1.status == "success"

    req2 = ModelGenerationRequest(request_id="req-dup-100", task="Second execution attempt")
    resp2 = adapter.generate(req2)
    assert resp2.status == InferenceExecutionState.FAILED.value
    assert "Duplicate inference request" in resp2.warnings[0]

    adapter.unload()


def test_multimodal_reference_boundary():
    adapter = Sarvam105BAdapter()
    adapter.load()

    req = ModelGenerationRequest(
        request_id="req-multi-1",
        task="Identify crop disease from attached reference",
        multimodal_data={"image_ref": "s3://earthmind-bucket/drone_img_123.jpg"}
    )

    resp = adapter.generate(req)
    assert resp.status == "success"
    assert resp.metadata["multimodal_reference_passed"] is True
    assert "image_ref" in resp.metadata["multimodal_keys"]

    adapter.unload()


def test_logging_does_not_expose_secrets(caplog):
    caplog.set_level(logging.INFO)

    secret_str = "HF_TOKEN='hf_1234567890abcdef' api_key='secret_999'"
    sanitized = sanitize_text(secret_str)

    assert "hf_1234567890abcdef" not in sanitized
    assert "secret_999" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized


def test_complete_imodel_adapter_runtime_backend_pathway():
    adapter = Sarvam105BAdapter()
    assert isinstance(adapter, IModel)

    # State before load
    assert adapter.status()["loaded"] is False

    adapter.load()
    status = adapter.status()
    assert status["loaded"] is True
    assert status["initializer_status"]["is_ready"] is True
    assert status["runtime_status"]["state"] == RuntimeState.READY.value

    req = ModelGenerationRequest(
        request_id="req-pipeline-check",
        task="Evaluate soil moisture index",
        instructions="Provide score"
    )

    resp = adapter.generate(req)
    assert resp.request_id == "req-pipeline-check"
    assert resp.status == "success"
    assert resp.model_version == "mrmanan762/EarthMind@fb187764"

    adapter.unload()
    assert adapter.status()["loaded"] is False
