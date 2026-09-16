import pytest
from pydantic import ValidationError

from core.interfaces.model import IModel
from core.schemas.model import ModelGenerationRequest, ModelGenerationResponse
from core.config.settings import ModelConfig, settings
from core.errors.exceptions import ModelNotLoadedError, ModelExecutionError
from modules.ai.model_registry import ModelRegistry, ModelNotFoundError
from modules.ai.sarvam_adapter import Sarvam105BAdapter

def test_imodel_interface_contract():
    adapter = Sarvam105BAdapter()
    assert isinstance(adapter, IModel)

def test_valid_model_generation_request_and_response():
    req = ModelGenerationRequest(
        request_id="req-123",
        task="Analyze crop soil health",
        instructions="Provide nitrogen and pH recommendations",
        context={"field_id": "field_42"},
        conversation=[{"role": "user", "content": "How is field 42?"}],
        multimodal_data={"soil_sample_img": "s3://soil/img1.png"},
        tools_available=[{"name": "soil_analyzer"}],
        constraints={"max_tokens": 500},
        metadata={"priority": "high"}
    )
    assert req.request_id == "req-123"
    assert req.task == "Analyze crop soil health"

    resp = ModelGenerationResponse(
        request_id=req.request_id,
        status="success",
        response="Soil pH is 6.5, nitrogen levels optimal.",
        reasoning_data={"step": "analysis complete"},
        tool_information=[],
        confidence_level=0.98,
        uncertainty=0.02,
        warnings=[],
        model_version="mrmanan762/EarthMind@fb187764",
        metadata={"latency_ms": 120}
    )
    assert resp.request_id == "req-123"
    assert resp.status == "success"
    assert resp.confidence_level == 0.98

def test_invalid_model_generation_request():
    with pytest.raises(ValidationError):
        # Missing required request_id and task
        ModelGenerationRequest()

def test_sarvam_adapter_construction_and_registry_resolution():
    registry = ModelRegistry()
    adapter = Sarvam105BAdapter(registry=registry)

    assert adapter.config.identifier == "sarvam-105b"
    assert adapter.config.repo_id == "mrmanan762/EarthMind"
    assert adapter.config.revision == "fb187764dbad56ed8b26742a802909e858e9bb72"
    assert adapter.config.is_main_model is True

def test_sarvam_adapter_lifecycle_and_status():
    adapter = Sarvam105BAdapter()
    status_unloaded = adapter.status()
    assert status_unloaded["loaded"] is False
    assert status_unloaded["health"] == "unloaded"
    assert status_unloaded["repo_id"] == "mrmanan762/EarthMind"
    assert status_unloaded["revision"] == "fb187764dbad56ed8b26742a802909e858e9bb72"

    adapter.load()
    status_loaded = adapter.status()
    assert status_loaded["loaded"] is True
    assert status_loaded["health"] == "healthy"

    adapter.unload()
    status_after = adapter.status()
    assert status_after["loaded"] is False

def test_generate_when_not_loaded_raises_error():
    adapter = Sarvam105BAdapter()
    req = ModelGenerationRequest(request_id="req-1", task="Test task")

    with pytest.raises(ModelNotLoadedError) as exc_info:
        adapter.generate(req)
    assert "sarvam-105b" in str(exc_info.value)

def test_successful_generation_mocked_path():
    adapter = Sarvam105BAdapter()
    adapter.load()

    req = ModelGenerationRequest(
        request_id="req-200",
        task="Pest risk assessment",
        instructions="Focus on aphid infestation"
    )

    resp = adapter.generate(req)
    assert isinstance(resp, ModelGenerationResponse)
    assert resp.request_id == "req-200"
    assert resp.status == "success"
    assert "Pest risk assessment" in resp.response
    assert "aphid infestation" in resp.response
    assert resp.metadata["repo_id"] == "mrmanan762/EarthMind"
    assert resp.metadata["revision"] == "fb187764dbad56ed8b26742a802909e858e9bb72"

def test_adapter_replaceability_and_custom_config():
    custom_config = ModelConfig(
        identifier="custom-model",
        provider="huggingface",
        repo_id="mrmanan762/EarthMind",
        revision="fb187764dbad56ed8b26742a802909e858e9bb72",
        is_main_model=False
    )
    registry = ModelRegistry(register_defaults=False)
    registry.register_model(custom_config)

    adapter = Sarvam105BAdapter(registry=registry, model_identifier="custom-model")
    assert adapter.config.identifier == "custom-model"
    assert isinstance(adapter, IModel)
