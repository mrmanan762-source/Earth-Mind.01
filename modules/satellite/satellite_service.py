"""SatelliteService for EarthMind Satellite Module (Stage D3: Discovery, Acquisition & Ingestion).

Central coordinator binding:
- Configuration (`SatelliteConfig`)
- Lifecycle Management (`SatelliteLifecycleManager`)
- Provider Registry (`SatelliteProviderRegistry`)
- Provider Capability Management (`ProviderCapabilityManager`)
- Provider Adapter Registry (`SatelliteAdapterRegistry`)
- Request Validation (`SatelliteRequestValidator`)
- Foundational Diagnostics (`SatelliteDiagnostics`)
- Data Catalog (`SatelliteDataCatalog`)
- Preliminary Quality Validation (`SatellitePreValidator`)
- Storage Adapter (`ISatelliteCacheStorageAdapter`)
- Format Detection (`SatelliteFormatDetector`)
- Metadata Extraction (`SatelliteMetadataExtractor`)
- Raw Data Ingestion (`SatelliteIngestionEngine`)
- Hybrid Caching (`SatelliteHybridCache`)
- Catalog Discovery (`SatelliteDiscoveryEngine`)
- Request Lifecycle Management (`SatelliteRequestManager`)
- Data Acquisition (`SatelliteDataAcquisitionEngine`)
"""

from typing import Any, Dict, List, Optional

from core.config.settings import SatelliteConfig, settings
from core.interfaces.satellite import ISatelliteCacheStorageAdapter
from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteAcquisitionResult,
    SatelliteAcquisitionStatus,
    SatelliteDataFormat,
    SatelliteDataQuality,
    SatelliteDataRequest,
    SatelliteDatasetMetadata,
    SatelliteProvider,
    SatelliteProviderStatus,
    SatelliteRawDataReference,
)
from modules.satellite.acquisition import SatelliteDataAcquisitionEngine
from modules.satellite.adapters import (
    BaseSatelliteProviderAdapter,
    CopernicusCdseAdapter,
    IsroBhuvanAdapter,
    MockSatelliteProviderAdapter,
    NasaEarthdataAdapter,
    SatelliteAdapterRegistry,
)
from modules.satellite.cache import SatelliteHybridCache
from modules.satellite.capabilities import ProviderCapabilityManager
from modules.satellite.catalog import SatelliteDataCatalog
from modules.satellite.diagnostics import SatelliteDiagnostics
from modules.satellite.discovery import SatelliteDiscoveryEngine
from modules.satellite.errors import (
    SatelliteError,
    SatelliteInvalidArgumentError,
    SatelliteProviderError,
    SatelliteProviderUnavailableError,
)
from modules.satellite.formats import SatelliteFormatDetector
from modules.satellite.ingestion import SatelliteIngestionEngine
from modules.satellite.lifecycle import (
    SatelliteLifecycleManager,
    SatelliteLifecycleState,
    SatelliteLifecycleTracker,
)
from modules.satellite.metadata_extractor import SatelliteMetadataExtractor
from modules.satellite.pre_validator import SatellitePreValidator
from modules.satellite.registry import SatelliteProviderRegistry
from modules.satellite.request_manager import SatelliteRequestManager
from modules.satellite.request_validator import SatelliteRequestValidator
from modules.satellite.storage import resolve_satellite_storage_adapter

logger = get_logger("modules.satellite.service")


class SatelliteService:
    """Satellite service orchestrating discovery, acquisition, ingestion, and hybrid caching."""

    def __init__(
        self,
        config: Optional[SatelliteConfig] = None,
        lifecycle_manager: Optional[SatelliteLifecycleManager] = None,
        provider_registry: Optional[SatelliteProviderRegistry] = None,
        capability_manager: Optional[ProviderCapabilityManager] = None,
        adapter_registry: Optional[SatelliteAdapterRegistry] = None,
        request_validator: Optional[SatelliteRequestValidator] = None,
        diagnostics: Optional[SatelliteDiagnostics] = None,
        storage_adapter: Optional[ISatelliteCacheStorageAdapter] = None,
        catalog: Optional[SatelliteDataCatalog] = None,
        hybrid_cache: Optional[SatelliteHybridCache] = None,
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

        # D3 Core Ingestion, Catalog & Storage Components
        is_prod = (getattr(settings, "environment", "development").lower() in ("production", "prod"))
        self._storage = storage_adapter or resolve_satellite_storage_adapter(
            adapter_type=self._config.storage_adapter,
            base_dir=getattr(self._config, "storage_base_dir", "/tmp/earthmind_satellite_storage"),
            is_production=is_prod,
        )
        self._catalog = catalog or SatelliteDataCatalog()
        self._pre_validator = SatellitePreValidator()
        self._format_detector = SatelliteFormatDetector()
        self._metadata_extractor = SatelliteMetadataExtractor()
        self._ingestion_engine = SatelliteIngestionEngine(
            storage_adapter=self._storage,
            format_detector=self._format_detector,
            metadata_extractor=self._metadata_extractor,
            max_file_size_bytes=getattr(self._config, "max_download_size_bytes", 1024 * 1024 * 1024),
        )
        self._cache = hybrid_cache or SatelliteHybridCache(
            catalog=self._catalog,
            default_ttl_seconds=self._config.cache_ttl_seconds,
            max_entries=getattr(self._config, "cache_max_entries", 1000),
        )

        # D3 Discovery, Request Management & Acquisition
        self._request_manager = SatelliteRequestManager(
            max_concurrent_requests=self._config.max_concurrent_requests
        )
        self._discovery_engine = SatelliteDiscoveryEngine(
            provider_registry=self._provider_registry,
            adapter_registry=self._adapter_registry,
            capability_manager=self._capability_manager,
            catalog=self._catalog,
        )
        self._acquisition_engine = SatelliteDataAcquisitionEngine(
            discovery_engine=self._discovery_engine,
            adapter_registry=self._adapter_registry,
            ingestion_engine=self._ingestion_engine,
            cache=self._cache,
            request_manager=self._request_manager,
        )

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

    @property
    def catalog(self) -> SatelliteDataCatalog:
        return self._catalog

    @property
    def pre_validator(self) -> SatellitePreValidator:
        return self._pre_validator

    @property
    def storage(self) -> ISatelliteCacheStorageAdapter:
        return self._storage

    @property
    def format_detector(self) -> SatelliteFormatDetector:
        return self._format_detector

    @property
    def metadata_extractor(self) -> SatelliteMetadataExtractor:
        return self._metadata_extractor

    @property
    def ingestion_engine(self) -> SatelliteIngestionEngine:
        return self._ingestion_engine

    @property
    def cache(self) -> SatelliteHybridCache:
        return self._cache

    @property
    def discovery_engine(self) -> SatelliteDiscoveryEngine:
        return self._discovery_engine

    @property
    def request_manager(self) -> SatelliteRequestManager:
        return self._request_manager

    @property
    def acquisition_engine(self) -> SatelliteDataAcquisitionEngine:
        return self._acquisition_engine

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

    def search_catalog(
        self,
        request: SatelliteDataRequest,
        provider_id: Optional[str] = None,
    ) -> List[SatelliteDatasetMetadata]:
        """Validate request and search provider catalog across discovery engine."""
        self._diagnostics.record_metric("requests_total", 1)
        self._diagnostics.record_metric("catalog_searches_total", 1)

        try:
            self._validator.validate_request(request)
        except SatelliteInvalidArgumentError as exc:
            self._diagnostics.record_metric("requests_rejected", 1)
            self._diagnostics.record_error("search_catalog", "INVALID_ARGUMENT", str(exc), provider_id=provider_id)
            raise

        try:
            if provider_id:
                adapter = self._adapter_registry.get_adapter(provider_id)
                if not adapter:
                    raise SatelliteProviderUnavailableError(
                        provider_id=provider_id,
                        details=f"No adapter registered for provider '{provider_id}'.",
                    )
                results = adapter.search_catalog(request)
            else:
                results = self._discovery_engine.discover_datasets(request)

            self._diagnostics.record_metric("requests_success", 1)
            return results
        except Exception as exc:
            self._diagnostics.record_metric("catalog_searches_failed", 1)
            self._diagnostics.record_error("search_catalog", "SEARCH_FAILED", str(exc), provider_id=provider_id)
            raise

    def acquire_dataset(
        self,
        dataset_id: str,
        request: SatelliteDataRequest,
        provider_id: str,
    ) -> SatelliteAcquisitionResult:
        """Validate request and execute dataset acquisition via adapter or engine."""
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
                # Cache acquired result
                if result.dataset_metadata:
                    self._cache.put(result.dataset_metadata)
            return result
        except Exception as exc:
            self._diagnostics.record_metric("acquisitions_failed", 1)
            self._diagnostics.record_error("acquire_dataset", "ACQUISITION_FAILED", str(exc), provider_id=provider_id)
            raise

    def acquire(self, request: SatelliteDataRequest) -> SatelliteAcquisitionResult:
        """Execute full acquisition workflow via SatelliteDataAcquisitionEngine."""
        self._diagnostics.record_metric("requests_total", 1)
        self._diagnostics.record_metric("acquisitions_total", 1)

        try:
            self._validator.validate_request(request)
        except SatelliteInvalidArgumentError as exc:
            self._diagnostics.record_metric("requests_rejected", 1)
            self._diagnostics.record_error("acquire", "INVALID_ARGUMENT", str(exc))
            raise

        try:
            result = self._acquisition_engine.acquire(request)
            if result.status == SatelliteAcquisitionStatus.ACQUIRED:
                self._diagnostics.record_metric("requests_success", 1)
            else:
                self._diagnostics.record_metric("acquisitions_failed", 1)
            return result
        except Exception as exc:
            self._diagnostics.record_metric("acquisitions_failed", 1)
            self._diagnostics.record_error("acquire", "ACQUISITION_FAILED", str(exc))
            raise

    def ingest_raw_data(
        self,
        dataset_id: str,
        provider_id: str,
        data_bytes: bytes,
        data_format: SatelliteDataFormat,
        file_name: Optional[str] = None,
        expected_sha256: Optional[str] = None,
        manifest_payload: Optional[Dict[str, Any]] = None,
    ) -> SatelliteRawDataReference:
        """Ingest raw data bytes, verify integrity, and store reference."""
        return self._ingestion_engine.ingest_raw_data(
            dataset_id=dataset_id,
            provider_id=provider_id,
            data_bytes=data_bytes,
            data_format=data_format,
            file_name=file_name,
            expected_sha256=expected_sha256,
            manifest_payload=manifest_payload,
        )

    def check_health(self) -> Dict[str, Any]:
        """Aggregate health status from diagnostics, catalog, and storage."""
        health = self._diagnostics.get_health_status()
        health.update({
            "catalog_entries": self._catalog.count(),
            "cache_entries": self._cache.size(),
            "storage_adapter": self._config.storage_adapter,
        })
        return health
