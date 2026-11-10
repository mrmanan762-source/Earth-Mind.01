"""SatelliteService for EarthMind Satellite Module (Stage D2: Core Foundation).

Central coordinator binding:
- Configuration (`SatelliteConfig`)
- Lifecycle Management (`SatelliteLifecycleManager`)
- Provider Registry (`SatelliteProviderRegistry`)
- Provider Capability Management (`ProviderCapabilityManager`)
- Provider Adapter Registry (`SatelliteAdapterRegistry`)
- Request Validation (`SatelliteRequestValidator`)
- Foundational Diagnostics (`SatelliteDiagnostics`)
"""

from typing import Any, Dict, List, Optional

from core.config.settings import SatelliteConfig, settings
from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteAcquisitionResult,
    SatelliteAcquisitionStatus,
    SatelliteDataRequest,
    SatelliteDatasetMetadata,
    SatelliteProvider,
    SatelliteProviderStatus,
)
from modules.satellite.adapters import (
    BaseSatelliteProviderAdapter,
    CopernicusCdseAdapter,
    IsroBhuvanAdapter,
    MockSatelliteProviderAdapter,
    NasaEarthdataAdapter,
    SatelliteAdapterRegistry,
)
from modules.satellite.capabilities import ProviderCapabilityManager
from modules.satellite.diagnostics import SatelliteDiagnostics
from modules.satellite.errors import (
    SatelliteError,
    SatelliteInvalidArgumentError,
    SatelliteProviderError,
    SatelliteProviderUnavailableError,
)
from modules.satellite.lifecycle import (
    SatelliteLifecycleManager,
    SatelliteLifecycleState,
    SatelliteLifecycleTracker,
)
from modules.satellite.registry import SatelliteProviderRegistry
from modules.satellite.request_validator import SatelliteRequestValidator

logger = get_logger("modules.satellite.service")


class SatelliteService:
    """Satellite service orchestrating provider access, validation, and lifecycle."""

    def __init__(
        self,
        config: Optional[SatelliteConfig] = None,
        lifecycle_manager: Optional[SatelliteLifecycleManager] = None,
        provider_registry: Optional[SatelliteProviderRegistry] = None,
        capability_manager: Optional[ProviderCapabilityManager] = None,
        adapter_registry: Optional[SatelliteAdapterRegistry] = None,
        request_validator: Optional[SatelliteRequestValidator] = None,
        diagnostics: Optional[SatelliteDiagnostics] = None,
    ):
        self._config = config or getattr(settings, "satellite", SatelliteConfig())
        self._lifecycle_tracker = SatelliteLifecycleTracker()
        self._lifecycle = lifecycle_manager or SatelliteLifecycleManager(tracker=self._lifecycle_tracker)
        self._capability_manager = capability_manager or ProviderCapabilityManager()
        self._provider_registry = provider_registry or SatelliteProviderRegistry(
            capability_manager=self._capability_manager
        )
        self._adapter_registry = adapter_registry or SatelliteAdapterRegistry()
        self._validator = request_validator or SatelliteRequestValidator(
            strict=self._config.strict_validation
        )
        self._diagnostics = diagnostics or SatelliteDiagnostics()

        # Connect lifecycle hooks to sync diagnostics state
        self._lifecycle.add_startup_hook(self._on_startup)
        self._lifecycle.add_shutdown_hook(self._on_shutdown)

        # Register default adapters based on config
        self._register_configured_adapters()

    @property
    def config(self) -> SatelliteConfig:
        return self._config

    @property
    def lifecycle(self) -> SatelliteLifecycleManager:
        return self._lifecycle

    @property
    def provider_registry(self) -> SatelliteProviderRegistry:
        return self._provider_registry

    @property
    def capability_manager(self) -> ProviderCapabilityManager:
        return self._capability_manager

    @property
    def adapter_registry(self) -> SatelliteAdapterRegistry:
        return self._adapter_registry

    @property
    def validator(self) -> SatelliteRequestValidator:
        return self._validator

    @property
    def diagnostics(self) -> SatelliteDiagnostics:
        return self._diagnostics

    def _on_startup(self) -> None:
        """Invoked when module starts."""
        self._diagnostics.set_lifecycle_state("RUNNING")
        for prov in self._provider_registry.list_providers():
            self._diagnostics.update_provider_status(
                prov.provider_id,
                prov.status.value,
            )

    def _on_shutdown(self) -> None:
        """Invoked when module stops."""
        self._diagnostics.set_lifecycle_state("STOPPED")

    def _register_configured_adapters(self) -> None:
        """Register adapters according to SatelliteConfig settings."""
        nasa = NasaEarthdataAdapter(
            api_key=self._config.nasa_api_key,
            timeout=self._config.default_timeout,
            max_retries=self._config.max_retries,
            enabled=self._config.nasa_enabled,
        )
        self._adapter_registry.register_adapter(nasa)
        self._provider_registry.register_provider(nasa.get_provider_manifest(), allow_overwrite=True)
        self._diagnostics.update_provider_status(nasa.provider_id, "INITIALIZED")

        isro = IsroBhuvanAdapter(
            api_key=self._config.isro_api_key,
            timeout=self._config.default_timeout,
            max_retries=self._config.max_retries,
            enabled=self._config.isro_enabled,
        )
        self._adapter_registry.register_adapter(isro)
        self._provider_registry.register_provider(isro.get_provider_manifest(), allow_overwrite=True)
        self._diagnostics.update_provider_status(isro.provider_id, "INITIALIZED")

        copernicus = CopernicusCdseAdapter(
            client_id=self._config.copernicus_client_id,
            client_secret=self._config.copernicus_client_secret,
            timeout=self._config.default_timeout,
            max_retries=self._config.max_retries,
            enabled=self._config.copernicus_enabled,
        )
        self._adapter_registry.register_adapter(copernicus)
        self._provider_registry.register_provider(copernicus.get_provider_manifest(), allow_overwrite=True)
        self._diagnostics.update_provider_status(copernicus.provider_id, "INITIALIZED")

        if self._config.mock_provider_enabled:
            mock = MockSatelliteProviderAdapter(enabled=True)
            self._adapter_registry.register_adapter(mock)
            self._provider_registry.register_provider(mock.get_provider_manifest(), allow_overwrite=True)
            self._diagnostics.update_provider_status(mock.provider_id, "INITIALIZED")

    def search_catalog(self, request: SatelliteDataRequest, provider_id: Optional[str] = None) -> List[SatelliteDatasetMetadata]:
        """Validate request and search provider catalog (D2 foundation)."""
        self._diagnostics.record_metric("requests_total", 1)
        self._diagnostics.record_metric("catalog_searches_total", 1)

        try:
            self._validator.validate_request(request)
        except SatelliteInvalidArgumentError as exc:
            self._diagnostics.record_metric("requests_rejected", 1)
            self._diagnostics.record_error("search_catalog", "INVALID_ARGUMENT", str(exc), provider_id=provider_id)
            raise

        target_provider_id = provider_id or (request.target_constellations and self._resolve_provider_for_constellations(request.target_constellations))
        if not target_provider_id:
            available = [p.provider_id for p in self._provider_registry.list_providers() if self._provider_registry.is_provider_available(p.provider_id)]
            target_provider_id = available[0] if available else "copernicus_cdse"

        adapter = self._adapter_registry.get_adapter(target_provider_id)
        if not adapter:
            err = SatelliteProviderUnavailableError(
                provider_id=target_provider_id,
                details=f"No adapter registered for provider '{target_provider_id}'.",
            )
            self._diagnostics.record_metric("catalog_searches_failed", 1)
            self._diagnostics.record_error("search_catalog", "PROVIDER_UNAVAILABLE", str(err), provider_id=target_provider_id)
            raise err

        try:
            results = adapter.search_catalog(request)
            self._diagnostics.record_metric("requests_success", 1)
            return results
        except Exception as exc:
            self._diagnostics.record_metric("catalog_searches_failed", 1)
            self._diagnostics.record_error("search_catalog", "SEARCH_FAILED", str(exc), provider_id=target_provider_id)
            raise

    def acquire_dataset(self, dataset_id: str, request: SatelliteDataRequest, provider_id: str) -> SatelliteAcquisitionResult:
        """Validate request and execute dataset acquisition via adapter (D2 foundation)."""
        self._diagnostics.record_metric("requests_total", 1)
        self._diagnostics.record_metric("acquisitions_total", 1)

        try:
            self._validator.validate_request(request)
        except SatelliteInvalidArgumentError as exc:
            self._diagnostics.record_metric("requests_rejected", 1)
            self._diagnostics.record_error("acquire_dataset", "INVALID_ARGUMENT", str(exc), provider_id=provider_id)
            raise

        adapter = self._adapter_registry.get_adapter(provider_id)
        if not adapter:
            err = SatelliteProviderUnavailableError(
                provider_id=provider_id,
                details=f"No adapter registered for provider '{provider_id}'.",
            )
            self._diagnostics.record_metric("acquisitions_failed", 1)
            self._diagnostics.record_error("acquire_dataset", "PROVIDER_UNAVAILABLE", str(err), provider_id=provider_id)
            raise err

        try:
            result = adapter.acquire_dataset(dataset_id, request)
            if result.status == SatelliteAcquisitionStatus.FAILED:
                self._diagnostics.record_metric("acquisitions_failed", 1)
            else:
                self._diagnostics.record_metric("requests_success", 1)
            return result
        except Exception as exc:
            self._diagnostics.record_metric("acquisitions_failed", 1)
            self._diagnostics.record_error("acquire_dataset", "ACQUISITION_FAILED", str(exc), provider_id=provider_id)
            raise

    def _resolve_provider_for_constellations(self, constellations: List[str]) -> Optional[str]:
        for c in constellations:
            capable = self._capability_manager.list_capable_providers(constellation=c)
            for pid in capable:
                if self._provider_registry.is_provider_available(pid):
                    return pid
        return None

    def check_health(self) -> Dict[str, Any]:
        return self._diagnostics.get_health_status()
