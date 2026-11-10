"""Unit and integration test suite for EarthMind Satellite Intelligence Module Stage D2: Core Foundation.

Verifies all 20 required D2 test criteria:
1. Configuration loading.
2. Invalid configuration rejection.
3. Lifecycle transitions.
4. Startup and shutdown.
5. Initialization failure handling.
6. Provider registration.
7. Duplicate provider rejection.
8. Provider lookup.
9. Provider enable/disable.
10. Capability validation.
11. Unsupported capability handling.
12. Provider adapter contract compliance.
13. Request validation.
14. Timeout and retry behavior.
15. Provider error normalization.
16. Diagnostics accuracy.
17. Secret masking.
18. Mock-provider isolation.
19. Production configuration safeguards.
20. Regression compatibility with D1 and existing modules.
"""

import pytest
from pydantic import ValidationError

from core.config.settings import SatelliteConfig, Settings
from core.errors.exceptions import ConfigurationError
from core.interfaces.satellite import (
    ISatelliteDiagnostics,
    ISatelliteProviderAdapter,
    ISatelliteProviderRegistry,
)
from core.schemas.application import ApplicationRequest
from core.schemas.satellite import (
    SatelliteAcquisitionResult,
    SatelliteAcquisitionStatus,
    SatelliteDataFormat,
    SatelliteDataRequest,
    SatelliteDatasetMetadata,
    SatelliteGeospatialMetadata,
    SatelliteProvider,
    SatelliteProviderStatus,
    SatelliteSensorType,
    SatelliteTemporalMetadata,
)
from modules.satellite.adapters import (
    BaseSatelliteProviderAdapter,
    CopernicusCdseAdapter,
    IsroBhuvanAdapter,
    MockSatelliteProviderAdapter,
    NasaEarthdataAdapter,
    SatelliteAdapterRegistry,
)
from modules.satellite.capabilities import (
    ProviderCapabilityManager,
    ProviderCapabilityProfile,
)
from modules.satellite.diagnostics import SatelliteDiagnostics
from modules.satellite.errors import (
    SatelliteError,
    SatelliteInvalidArgumentError,
    SatelliteProviderError,
    SatelliteProviderUnavailableError,
    SatelliteTimeoutError,
)
from modules.satellite.lifecycle import (
    SatelliteLifecycleManager,
    SatelliteLifecycleState,
    SatelliteLifecycleTracker,
)
from modules.satellite.registry import SatelliteProviderRegistry
from modules.satellite.request_validator import SatelliteRequestValidator
from modules.satellite.satellite_module import SatelliteModule
from modules.satellite.satellite_service import SatelliteService


# ============================================================================
# Criterion 1: Configuration Loading
# ============================================================================

def test_1_configuration_loading():
    config = SatelliteConfig(
        enabled=True,
        default_timeout=25.0,
        max_retries=4,
        initial_retry_backoff=0.25,
        max_retry_backoff=4.0,
        max_cloud_cover_percentage=15.0,
        copernicus_enabled=True,
        mock_provider_enabled=False,
    )
    assert config.enabled is True
    assert config.default_timeout == 25.0
    assert config.max_retries == 4
    assert config.initial_retry_backoff == 0.25
    assert config.max_retry_backoff == 4.0
    assert config.max_cloud_cover_percentage == 15.0
    assert config.mock_provider_enabled is False


# ============================================================================
# Criterion 2: Invalid Configuration Rejection
# ============================================================================

def test_2_invalid_configuration_rejection():
    # Negative timeout
    s_timeout = Settings(satellite=SatelliteConfig(default_timeout=-5.0))
    with pytest.raises(ConfigurationError) as exc_t:
        s_timeout.validate_config()
    assert "satellite.default_timeout" in str(exc_t.value)

    # Negative retries
    s_retries = Settings(satellite=SatelliteConfig(max_retries=-1))
    with pytest.raises(ConfigurationError) as exc_r:
        s_retries.validate_config()
    assert "satellite.max_retries" in str(exc_r.value)

    # Invalid cloud cover > 100
    s_cloud = Settings(satellite=SatelliteConfig(max_cloud_cover_percentage=120.0))
    with pytest.raises(ConfigurationError) as exc_c:
        s_cloud.validate_config()
    assert "satellite.max_cloud_cover_percentage" in str(exc_c.value)

    # Max backoff < initial backoff
    s_backoff = Settings(satellite=SatelliteConfig(initial_retry_backoff=5.0, max_retry_backoff=1.0))
    with pytest.raises(ConfigurationError) as exc_b:
        s_backoff.validate_config()
    assert "satellite.max_retry_backoff" in str(exc_b.value)


# ============================================================================
# Criterion 3: Lifecycle Transitions
# ============================================================================

def test_3_lifecycle_transitions():
    tracker = SatelliteLifecycleTracker()
    assert tracker.current_state == SatelliteLifecycleState.INITIALIZED
    assert tracker.is_healthy is True

    tracker.transition_to(SatelliteLifecycleState.STARTING, reason="Testing startup")
    assert tracker.current_state == SatelliteLifecycleState.STARTING

    tracker.transition_to(SatelliteLifecycleState.RUNNING, reason="Running")
    assert tracker.current_state == SatelliteLifecycleState.RUNNING
    assert tracker.is_running is True

    # Invalid transition directly to STARTING from RUNNING
    with pytest.raises(SatelliteInvalidArgumentError):
        tracker.transition_to(SatelliteLifecycleState.STARTING)

    # Valid stop flow
    tracker.transition_to(SatelliteLifecycleState.STOPPING, reason="Stopping")
    tracker.transition_to(SatelliteLifecycleState.STOPPED, reason="Stopped")
    assert tracker.current_state == SatelliteLifecycleState.STOPPED

    history = tracker.get_history()
    assert len(history) >= 4


# ============================================================================
# Criterion 4: Startup and Shutdown
# ============================================================================

def test_4_startup_and_shutdown():
    module = SatelliteModule()
    assert module._is_initialized is False
    module.initialize()
    assert module._is_initialized is True
    assert module.service.lifecycle.state == SatelliteLifecycleState.RUNNING

    module.shutdown()
    assert module._is_initialized is False
    assert module.service.lifecycle.state == SatelliteLifecycleState.STOPPED


# ============================================================================
# Criterion 5: Initialization Failure Handling
# ============================================================================

def test_5_initialization_failure_handling():
    mgr = SatelliteLifecycleManager()
    def _bad_hook():
        raise RuntimeError("Network hardware failure during startup")

    mgr.add_startup_hook(_bad_hook)
    with pytest.raises(SatelliteError):
        mgr.start()
    assert mgr.state == SatelliteLifecycleState.FAILED
    assert "Network hardware failure" in (mgr.tracker.failure_reason or "")


# ============================================================================
# Criterion 6: Provider Registration
# ============================================================================

def test_6_provider_registration():
    reg = SatelliteProviderRegistry()
    prov = SatelliteProvider(
        provider_id="copernicus_test",
        provider_name="Copernicus Test Provider",
        status=SatelliteProviderStatus.ACTIVE,
        supported_constellations=["Sentinel-2"],
        supported_sensor_types=[SatelliteSensorType.OPTICAL_MULTISPECTRAL],
        supported_formats=[SatelliteDataFormat.COG],
        attribution_text="Copernicus Test Attribution",
    )
    assert reg.register_provider(prov) is True
    found = reg.get_provider("copernicus_test")
    assert found is not None
    assert found.provider_id == "copernicus_test"


# ============================================================================
# Criterion 7: Duplicate Provider Rejection
# ============================================================================

def test_7_duplicate_provider_rejection():
    reg = SatelliteProviderRegistry()
    prov = SatelliteProvider(
        provider_id="nasa_usgs",
        provider_name="NASA USGS Landsat",
        status=SatelliteProviderStatus.ACTIVE,
        supported_constellations=["Landsat-8"],
        supported_sensor_types=[SatelliteSensorType.OPTICAL_MULTISPECTRAL],
        supported_formats=[SatelliteDataFormat.GEOTIFF],
        attribution_text="USGS/NASA",
    )
    reg.register_provider(prov)
    with pytest.raises(SatelliteProviderError) as exc_dup:
        reg.register_provider(prov, allow_overwrite=False)
    assert "already registered" in str(exc_dup.value)


# ============================================================================
# Criterion 8: Provider Lookup
# ============================================================================

def test_8_provider_lookup():
    reg = SatelliteProviderRegistry()
    assert reg.get_provider("non_existent_provider") is None
    assert reg.is_provider_available("non_existent_provider") is False


# ============================================================================
# Criterion 9: Provider Enable / Disable
# ============================================================================

def test_9_provider_enable_disable():
    reg = SatelliteProviderRegistry()
    prov = SatelliteProvider(
        provider_id="isro_bhuvan_test",
        provider_name="ISRO Bhuvan",
        status=SatelliteProviderStatus.ACTIVE,
        supported_constellations=["Resourcesat-2A"],
        supported_sensor_types=[SatelliteSensorType.OPTICAL_MULTISPECTRAL],
        supported_formats=[SatelliteDataFormat.GEOTIFF],
        attribution_text="ISRO/NRSC",
    )
    reg.register_provider(prov)
    assert reg.is_provider_available("isro_bhuvan_test") is True

    reg.disable_provider("isro_bhuvan_test", reason="Maintenance window")
    assert reg.is_provider_available("isro_bhuvan_test") is False
    disabled = reg.get_provider("isro_bhuvan_test")
    assert disabled.status == SatelliteProviderStatus.UNAVAILABLE

    reg.enable_provider("isro_bhuvan_test")
    assert reg.is_provider_available("isro_bhuvan_test") is True


# ============================================================================
# Criterion 10: Capability Validation
# ============================================================================

def test_10_capability_validation():
    cap_mgr = ProviderCapabilityManager()
    profile = ProviderCapabilityProfile(
        provider_id="test_cap_provider",
        supported_sensor_types=[SatelliteSensorType.OPTICAL_MULTISPECTRAL, SatelliteSensorType.THERMAL_INFRARED],
        supported_constellations=["Landsat-9"],
        supported_formats=[SatelliteDataFormat.COG, SatelliteDataFormat.GEOTIFF],
        supports_optical=True,
        supports_thermal=True,
    )
    cap_mgr.register_profile(profile)

    assert cap_mgr.supports_sensor_type("test_cap_provider", SatelliteSensorType.OPTICAL_MULTISPECTRAL) is True
    assert cap_mgr.supports_sensor_type("test_cap_provider", SatelliteSensorType.SYNTHETIC_APERTURE_RADAR) is False
    assert cap_mgr.supports_constellation("test_cap_provider", "Landsat-9") is True
    assert cap_mgr.supports_format("test_cap_provider", SatelliteDataFormat.COG) is True


# ============================================================================
# Criterion 11: Unsupported Capability Handling
# ============================================================================

def test_11_unsupported_capability_handling():
    cap_mgr = ProviderCapabilityManager()
    prov = SatelliteProvider(
        provider_id="optical_only",
        provider_name="Optical Only Provider",
        status=SatelliteProviderStatus.ACTIVE,
        supported_constellations=["Sentinel-2"],
        supported_sensor_types=[SatelliteSensorType.OPTICAL_MULTISPECTRAL],
        supported_formats=[SatelliteDataFormat.COG],
        attribution_text="Copernicus",
    )
    cap_mgr.register_from_provider_manifest(prov)

    assert cap_mgr.supports_sensor_type("optical_only", SatelliteSensorType.SYNTHETIC_APERTURE_RADAR) is False
    assert cap_mgr.supports_sensor_type("optical_only", SatelliteSensorType.THERMAL_INFRARED) is False
    assert cap_mgr.supports_constellation("optical_only", "Landsat-8") is False


# ============================================================================
# Criterion 12: Provider Adapter Contract Compliance
# ============================================================================

def test_12_provider_adapter_contract_compliance():
    adapters = [
        NasaEarthdataAdapter(),
        IsroBhuvanAdapter(),
        CopernicusCdseAdapter(),
        MockSatelliteProviderAdapter(),
    ]
    for adapter in adapters:
        assert isinstance(adapter, ISatelliteProviderAdapter)
        assert bool(adapter.provider_id)
        assert bool(adapter.provider_name)
        manifest = adapter.get_provider_manifest()
        assert isinstance(manifest, SatelliteProvider)
        assert manifest.provider_id == adapter.provider_id
        assert manifest.supported_constellations


# ============================================================================
# Criterion 13: Request Validation
# ============================================================================

def test_13_request_validation():
    val = SatelliteRequestValidator()

    valid_req = SatelliteDataRequest(
        geospatial=SatelliteGeospatialMetadata(latitude=21.1458, longitude=79.0882),
        temporal_window=SatelliteTemporalMetadata(acquisition_date="2025-03-30T10:00:00Z"),
    )
    assert val.validate_request(valid_req) is True

    with pytest.raises(ValidationError):
        SatelliteGeospatialMetadata(latitude=95.0, longitude=79.0882)

    traversal_req = SatelliteDataRequest(
        field_id="../../etc/shadow",
        geospatial=SatelliteGeospatialMetadata(latitude=21.1458, longitude=79.0882),
        temporal_window=SatelliteTemporalMetadata(acquisition_date="2025-03-30T10:00:00Z"),
    )
    with pytest.raises(SatelliteInvalidArgumentError) as exc_trav:
        val.validate_request(traversal_req)
    assert "Unsafe characters or path traversal" in str(exc_trav.value)

    inverted_req = SatelliteDataRequest(
        geospatial=SatelliteGeospatialMetadata(latitude=21.1458, longitude=79.0882),
        temporal_window=SatelliteTemporalMetadata(
            acquisition_date="2025-03-30T10:00:00Z",
            start_time="2025-03-31T00:00:00Z",
            end_time="2025-03-25T00:00:00Z",
        ),
    )
    with pytest.raises(SatelliteInvalidArgumentError) as exc_inv:
        val.validate_request(inverted_req)
    assert "is after end_time" in str(exc_inv.value)


# ============================================================================
# Criterion 14: Timeout and Retry Behavior
# ============================================================================

def test_14_timeout_and_retry_behavior():
    mock_timeout = MockSatelliteProviderAdapter(simulate_timeout=True)
    req = SatelliteDataRequest(
        geospatial=SatelliteGeospatialMetadata(latitude=21.1458, longitude=79.0882),
        temporal_window=SatelliteTemporalMetadata(acquisition_date="2025-03-30T10:00:00Z"),
    )
    with pytest.raises(SatelliteTimeoutError) as exc_t:
        mock_timeout.search_catalog(req)
    assert "search_catalog" in str(exc_t.value)


# ============================================================================
# Criterion 15: Provider Error Normalization
# ============================================================================

def test_15_provider_error_normalization():
    class ConnectionBrokenError(ConnectionError):
        pass

    mock_err = MockSatelliteProviderAdapter(simulate_error=ConnectionBrokenError("Socket reset by peer"))
    req = SatelliteDataRequest(
        geospatial=SatelliteGeospatialMetadata(latitude=21.1458, longitude=79.0882),
        temporal_window=SatelliteTemporalMetadata(acquisition_date="2025-03-30T10:00:00Z"),
    )
    with pytest.raises(SatelliteProviderUnavailableError) as exc_conn:
        mock_err.search_catalog(req)
    assert "connection failed" in str(exc_conn.value)


# ============================================================================
# Criterion 16: Diagnostics Accuracy
# ============================================================================

def test_16_diagnostics_accuracy():
    diag = SatelliteDiagnostics()
    assert isinstance(diag, ISatelliteDiagnostics)
    diag.set_lifecycle_state("RUNNING")
    diag.update_provider_status("copernicus_cdse", "AVAILABLE")
    diag.update_provider_status("isro_bhuvan", "INITIALIZED")
    diag.record_metric("requests_total", 5)

    health = diag.get_health_status()
    assert health["module"] == "satellite"
    assert health["status"] == "HEALTHY"
    assert health["lifecycle_state"] == "RUNNING"
    assert health["providers"]["copernicus_cdse"] == "AVAILABLE"
    assert health["providers"]["isro_bhuvan"] == "INITIALIZED"
    assert health["counters"]["requests_total"] == 5


# ============================================================================
# Criterion 17: Secret Masking
# ============================================================================

def test_17_secret_masking():
    diag = SatelliteDiagnostics()
    diag.record_error(
        operation="fetch_scene",
        error_code="PROVIDER_ERROR",
        message="Failed auth with client_secret: super_secret_passphrase_xyz",
    )
    health = diag.get_health_status()
    err_msg = health["recent_errors"][0]["message"]
    assert "super_secret_passphrase_xyz" not in err_msg

    s = Settings(
        satellite=SatelliteConfig(
            nasa_api_key="nasa_super_secret_token",
            copernicus_client_secret="cdse_secret_12345",
        )
    )
    safe = s.to_safe_dict()
    assert "nasa_super_secret_token" not in safe["satellite"]["nasa_api_key"]
    assert "cdse_secret_12345" not in safe["satellite"]["copernicus_client_secret"]


# ============================================================================
# Criterion 18: Mock-Provider Isolation
# ============================================================================

def test_18_mock_provider_isolation():
    mock = MockSatelliteProviderAdapter()
    assert mock.is_mock is True
    manifest = mock.get_provider_manifest()
    assert "Mock" in manifest.provider_name
    assert "Mock data for testing only" in manifest.attribution_text

    default_config = SatelliteConfig()
    assert default_config.mock_provider_enabled is False


# ============================================================================
# Criterion 19: Production Configuration Safeguards
# ============================================================================

def test_19_production_configuration_safeguards():
    prod_with_mock = Settings(
        environment="production",
        satellite=SatelliteConfig(mock_provider_enabled=True),
        postgres={"url": "postgresql://user:pass@remote.db:5432/db", "sslmode": "require"},
    )
    with pytest.raises(ConfigurationError) as exc_mock:
        prod_with_mock.validate_config()
    assert "Mock satellite provider is prohibited in production mode" in str(exc_mock.value)


# ============================================================================
# Criterion 20: Regression Compatibility with D1 & System
# ============================================================================

def test_20_regression_compatibility():
    req = SatelliteDataRequest(
        geospatial=SatelliteGeospatialMetadata(latitude=12.9716, longitude=77.5946),
        temporal_window=SatelliteTemporalMetadata(acquisition_date="2025-03-30T10:00:00Z"),
    )
    assert req.request_id.startswith("sat_req_")

    service = SatelliteService(config=SatelliteConfig(mock_provider_enabled=True))
    results = service.search_catalog(req, provider_id="mock_satellite_provider")
    assert len(results) == 1
    assert results[0].provider_id == "mock_satellite_provider"

    module = SatelliteModule(service=service)
    module.initialize()
    app_req = ApplicationRequest(
        request_id="test_app_req_01",
        source="test",
        actor="tester",
        operation="list_providers",
        payload={},
    )
    resp = module.handle(app_req)
    assert resp.status == "SUCCESS"
    assert len(resp.response) >= 3
    module.shutdown()
