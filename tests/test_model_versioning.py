"""Unit tests for Step 6 — Model Versioning & Replacement for EarthMind AI Model Layer."""

import pytest
from core.schemas.model import (
    ModelVersionRecord,
    ModelLifecycleState,
    ModelGenerationRequest
)
from core.config.settings import settings, ModelConfig
from core.errors.exceptions import (
    UnknownModelVersionError,
    InvalidLifecycleTransitionError,
    ModelCompatibilityError,
    ValidationGateError,
    ModelActivationError,
    ModelRollbackError,
    RetiredModelSelectedError,
    InvalidRevisionError
)
from modules.ai.model_registry import (
    ModelRegistry,
    ModelNotFoundError,
    InvalidModelConfigError
)
from modules.ai.compatibility import ModelCompatibilityChecker, ValidationGate
from modules.ai.sarvam_adapter import Sarvam105BAdapter


def test_default_sarvam_version_registered_and_pinned():
    """Verify default Sarvam-105B version is registered, active, and pinned to configured SHA."""
    registry = ModelRegistry()
    active_rec = registry.get_active_version("sarvam-105b")

    assert active_rec.identifier == "sarvam-105b"
    assert active_rec.version == "1.0.0"
    assert active_rec.repo_id == "mrmanan762/EarthMind"
    assert active_rec.revision == "fb187764dbad56ed8b26742a802909e858e9bb72"
    assert active_rec.state == ModelLifecycleState.ACTIVE
    assert active_rec.is_main_model is True


def test_version_registration_and_retrieval():
    """Test registering and retrieving explicit model version records."""
    registry = ModelRegistry(register_defaults=False)
    assert registry.list_versions() == []

    v1 = ModelVersionRecord(
        identifier="crop-analyzer",
        version="1.0.0",
        family="earthmind-crop",
        provider="huggingface",
        repo_id="mrmanan762/crop-analyzer",
        revision="a1b2c3d4e5f67890",
        model_type="causal_lm",
        state=ModelLifecycleState.REGISTERED,
        registration_timestamp="2025-01-01T00:00:00Z"
    )

    registry.register_version(v1)
    assert registry.version_exists("crop-analyzer", "1.0.0") is True

    retrieved = registry.get_version("crop-analyzer", "1.0.0")
    assert retrieved.identifier == "crop-analyzer"
    assert retrieved.version == "1.0.0"
    assert retrieved.revision == "a1b2c3d4e5f67890"
    assert retrieved.state == ModelLifecycleState.REGISTERED


def test_invalid_revision_and_repo_id():
    """Test validation errors for invalid revision and repo_id."""
    registry = ModelRegistry(register_defaults=False)

    # Short revision
    short_rev = ModelVersionRecord(
        identifier="invalid-model",
        version="1.0.0",
        repo_id="mrmanan762/EarthMind",
        revision="123",  # too short
        registration_timestamp="2025-01-01T00:00:00Z"
    )
    with pytest.raises(InvalidRevisionError):
        registry.register_version(short_rev)

    # Invalid repo_id missing slash
    bad_repo = ModelVersionRecord(
        identifier="invalid-repo",
        version="1.0.0",
        repo_id="invalid_repo_name",
        revision="a1b2c3d4e5f67890",
        registration_timestamp="2025-01-01T00:00:00Z"
    )
    with pytest.raises(InvalidModelConfigError):
        registry.register_version(bad_repo)


def test_multiple_model_versions_coexist():
    """Test registering multiple versions for the same model identifier."""
    registry = ModelRegistry(register_defaults=False)

    v1 = ModelVersionRecord(
        identifier="sarvam-105b",
        version="1.0.0",
        repo_id="mrmanan762/EarthMind",
        revision="11111111222222223333333344444444",
        registration_timestamp="2025-01-01T00:00:00Z"
    )
    v2 = ModelVersionRecord(
        identifier="sarvam-105b",
        version="2.0.0",
        repo_id="mrmanan762/EarthMind",
        revision="55555555666666667777777788888888",
        registration_timestamp="2025-01-02T00:00:00Z"
    )

    registry.register_version(v1)
    registry.register_version(v2)

    versions = registry.list_versions("sarvam-105b")
    assert len(versions) == 2
    version_tags = [v.version for v in versions]
    assert "1.0.0" in version_tags
    assert "2.0.0" in version_tags


def test_compatibility_checker():
    """Test compatibility validator checking provider, revision, architecture, and execution strategy."""
    checker = ModelCompatibilityChecker()

    valid_record = ModelVersionRecord(
        identifier="test-model",
        version="1.0.0",
        provider="huggingface",
        repo_id="mrmanan762/test-model",
        revision="a1b2c3d4e5f67890",
        model_type="causal_lm",
        execution_strategy="causal_lm_adapter",
        registration_timestamp="2025-01-01T00:00:00Z"
    )

    res = checker.check_compatibility(valid_record)
    assert res["is_compatible"] is True

    # Invalid provider
    bad_provider = valid_record.model_copy(update={"provider": "unsupported_provider"})
    with pytest.raises(ModelCompatibilityError):
        checker.check_compatibility(bad_provider)

    # Invalid model_type
    bad_type = valid_record.model_copy(update={"model_type": "unsupported_type"})
    with pytest.raises(ModelCompatibilityError):
        checker.check_compatibility(bad_type)


def test_validation_gate_and_staging():
    """Test candidate version passing validation gate and reaching STAGED state."""
    registry = ModelRegistry(register_defaults=False)

    candidate = ModelVersionRecord(
        identifier="sarvam-105b",
        version="2.0.0",
        repo_id="mrmanan762/EarthMind",
        revision="1234567890abcdef1234567890abcdef",
        state=ModelLifecycleState.REGISTERED,
        registration_timestamp="2025-01-01T00:00:00Z"
    )
    registry.register_version(candidate)

    val_res = registry.validate_version("sarvam-105b", "2.0.0")
    assert val_res.is_valid is True

    staged_rec = registry.stage_version("sarvam-105b", "2.0.0", val_res)
    assert staged_rec.state == ModelLifecycleState.STAGED


def test_staging_protection_active_model_remains_unchanged():
    """Verify staging a candidate version does NOT automatically alter active production model."""
    registry = ModelRegistry()  # includes default v1.0.0 active
    active_before = registry.get_active_version("sarvam-105b")
    assert active_before.version == "1.0.0"

    v2 = ModelVersionRecord(
        identifier="sarvam-105b",
        version="2.0.0",
        repo_id="mrmanan762/EarthMind",
        revision="22222222222222222222222222222222",
        state=ModelLifecycleState.REGISTERED,
        registration_timestamp="2025-01-02T00:00:00Z"
    )
    registry.register_version(v2)
    registry.stage_version("sarvam-105b", "2.0.0")

    active_after = registry.get_active_version("sarvam-105b")
    assert active_after.version == "1.0.0"  # still v1.0.0!


def test_controlled_replacement_flow():
    """Test full replacement flow: Register -> Validate -> Stage -> Activate -> Previous -> Rollback."""
    registry = ModelRegistry()  # v1.0.0 active

    v1 = registry.get_active_version("sarvam-105b")
    assert v1.version == "1.0.0"

    # 1. Register candidate v2.0.0
    v2 = ModelVersionRecord(
        identifier="sarvam-105b",
        version="2.0.0",
        repo_id="mrmanan762/EarthMind",
        revision="99999999888888887777777766666666",
        state=ModelLifecycleState.REGISTERED,
        registration_timestamp="2025-01-02T00:00:00Z"
    )
    registry.register_version(v2)

    # 2. Stage
    registry.stage_version("sarvam-105b", "2.0.0")

    # 3. Activate v2.0.0
    active_v2 = registry.activate_version("sarvam-105b", "2.0.0")
    assert active_v2.version == "2.0.0"
    assert active_v2.state == ModelLifecycleState.ACTIVE

    # Previous v1.0.0 should now be DEPRECATED
    v1_after = registry.get_version("sarvam-105b", "1.0.0")
    assert v1_after.state == ModelLifecycleState.DEPRECATED

    # 4. Roll back to previous active (v1.0.0)
    restored_v1 = registry.rollback_version("sarvam-105b")
    assert restored_v1.version == "1.0.0"
    assert restored_v1.state == ModelLifecycleState.ACTIVE

    # v2.0.0 should now be demoted to DEPRECATED
    v2_after = registry.get_version("sarvam-105b", "2.0.0")
    assert v2_after.state == ModelLifecycleState.DEPRECATED


def test_invalid_lifecycle_transition_and_retired_protection():
    """Verify invalid lifecycle transitions and retired model selection prevention."""
    registry = ModelRegistry(register_defaults=False)

    rec = ModelVersionRecord(
        identifier="sarvam-105b",
        version="1.0.0",
        repo_id="mrmanan762/EarthMind",
        revision="a1b2c3d4e5f67890",
        state=ModelLifecycleState.REGISTERED,
        registration_timestamp="2025-01-01T00:00:00Z"
    )
    registry.register_version(rec)

    # Retire model
    registry.retire_version("sarvam-105b", "1.0.0")
    retired_rec = registry.get_version("sarvam-105b", "1.0.0")
    assert retired_rec.state == ModelLifecycleState.RETIRED

    # Cannot transition RETIRED directly to ACTIVE
    with pytest.raises(InvalidLifecycleTransitionError):
        registry.update_lifecycle_state("sarvam-105b", "1.0.0", ModelLifecycleState.ACTIVE)

    # Cannot select RETIRED model as active
    with pytest.raises(RetiredModelSelectedError):
        registry.select_version("sarvam-105b", "1.0.0")

    with pytest.raises(RetiredModelSelectedError):
        registry.activate_version("sarvam-105b", "1.0.0")


def test_deprecation():
    """Test deprecating a model version."""
    registry = ModelRegistry()
    registry.deprecate_version("sarvam-105b", "1.0.0")
    dep_rec = registry.get_version("sarvam-105b", "1.0.0")
    assert dep_rec.state == ModelLifecycleState.DEPRECATED


def test_traceability_audit_log():
    """Test audit log records model registration, staging, activation, deprecation, and rollback events."""
    registry = ModelRegistry()  # logs default registration

    v2 = ModelVersionRecord(
        identifier="sarvam-105b",
        version="2.0.0",
        repo_id="mrmanan762/EarthMind",
        revision="a1b2c3d4e5f67890",
        state=ModelLifecycleState.REGISTERED,
        registration_timestamp="2025-01-02T00:00:00Z"
    )
    registry.register_version(v2)
    registry.stage_version("sarvam-105b", "2.0.0")
    registry.activate_version("sarvam-105b", "2.0.0")

    audit_log = registry.get_audit_log("sarvam-105b")
    operations = [e["operation"] for e in audit_log]

    assert "default_registered" in operations
    assert "version_registered" in operations
    assert "staged" in operations
    assert "activated" in operations

    for entry in audit_log:
        assert "timestamp" in entry
        assert "identifier" in entry
        assert "version" in entry
        assert "repo_id" in entry
        assert "revision" in entry


def test_sarvam_adapter_with_version_selection():
    """Test Sarvam105BAdapter initializing with explicit version and performing inference execution."""
    registry = ModelRegistry()

    # Create and register v2.0.0
    v2 = ModelVersionRecord(
        identifier="sarvam-105b",
        version="2.0.0",
        repo_id="mrmanan762/EarthMind",
        revision="11223344556677889900aabbccddeeff",
        state=ModelLifecycleState.ACTIVE,
        registration_timestamp="2025-01-02T00:00:00Z"
    )
    registry.register_version(v2)

    adapter = Sarvam105BAdapter(registry=registry, model_identifier="sarvam-105b", version="2.0.0")
    adapter.load()

    status = adapter.status()
    assert status["version"] == "2.0.0"
    assert status["revision"] == "11223344556677889900aabbccddeeff"

    req = ModelGenerationRequest(
        request_id="test-req-v2",
        task="Test task with Sarvam v2.0.0"
    )
    resp = adapter.generate(req)
    assert resp.status == "success"
    assert resp.metadata["version"] == "2.0.0"
    assert resp.metadata["revision"] == "11223344556677889900aabbccddeeff"

    adapter.unload()
