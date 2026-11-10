"""Satellite Provider Adapter Framework for EarthMind Satellite Module (Stage D2).

Implements:
- Abstract base provider adapter conforming to ISatelliteProviderAdapter
- Standardized timeout, bounded retry with exponential backoff, and error normalization
- Extension points for:
  1. NASA Earthdata Adapter (`NasaEarthdataAdapter`)
  2. ISRO / NRSC Bhuvan Adapter (`IsroBhuvanAdapter`)
  3. Copernicus CDSE Adapter (`CopernicusCdseAdapter`)
- Deterministic mock adapter for development/testing (`MockSatelliteProviderAdapter`)
- Central adapter registry (`SatelliteAdapterRegistry`)

IMPORTANT (D2 Boundary):
These are adapter architectural foundations and extension points.
No live provider API calls or downloads occur in Stage D2.
"""

from abc import ABC, abstractmethod
import math
import random
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from core.interfaces.satellite import ISatelliteProviderAdapter
from core.logging.logger import get_logger
from core.schemas.satellite import (
    SatelliteAcquisitionResult,
    SatelliteAcquisitionStatus,
    SatelliteDataFormat,
    SatelliteDataQuality,
    SatelliteDataRequest,
    SatelliteDatasetMetadata,
    SatelliteGeospatialMetadata,
    SatelliteProvider,
    SatelliteProviderStatus,
    SatelliteSensorType,
    SatelliteTemporalMetadata,
)
from modules.satellite.errors import (
    SatelliteDatasetNotFoundError,
    SatelliteDatasetUnavailableError,
    SatelliteError,
    SatelliteInternalError,
    SatelliteInvalidArgumentError,
    SatelliteProviderError,
    SatelliteProviderUnavailableError,
    SatelliteTimeoutError,
)

logger = get_logger("modules.satellite.adapters")


class BaseSatelliteProviderAdapter(ISatelliteProviderAdapter, ABC):
    """Abstract base adapter establishing contract compliance, retries, and error normalization."""

    def __init__(
        self,
        provider_id: str,
        provider_name: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        initial_backoff: float = 0.5,
        max_backoff: float = 5.0,
        enabled: bool = True,
    ):
        self._provider_id = provider_id
        self._provider_name = provider_name
        self._timeout = timeout
        self._max_retries = max_retries
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._enabled = enabled
        self._is_available = True

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def timeout(self) -> float:
        return self._timeout

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def is_available(self) -> bool:
        return self._enabled and self._is_available

    def set_availability(self, available: bool) -> None:
        self._is_available = available

    @abstractmethod
    def get_provider_manifest(self) -> SatelliteProvider:
        """Return standardized SatelliteProvider manifest for registry registration."""
        ...

    def execute_with_retry(
        self,
        operation_name: str,
        func: Callable[[], Any],
        retry_exceptions: Optional[List[type]] = None,
    ) -> Any:
        """Execute operation with bounded retry, exponential backoff, and error normalization."""
        if not self.is_available:
            raise SatelliteProviderUnavailableError(
                provider_id=self._provider_id,
                details=f"Provider adapter '{self._provider_id}' is currently unavailable or disabled.",
            )

        retryable_types = tuple(retry_exceptions or [TimeoutError, ConnectionError, OSError])
        attempts = 0
        last_error = None

        while attempts <= self._max_retries:
            try:
                start_t = time.time()
                result = func()
                elapsed = time.time() - start_t
                if elapsed > self._timeout:
                    raise TimeoutError(f"Operation exceeded configured adapter timeout of {self._timeout}s")
                return result
            except TimeoutError as exc:
                last_error = exc
                attempts += 1
                if attempts > self._max_retries:
                    raise SatelliteTimeoutError(
                        operation=f"{self._provider_id}:{operation_name}",
                        timeout=self._timeout,
                    ) from exc
            except retryable_types as exc:
                last_error = exc
                attempts += 1
                if attempts > self._max_retries:
                    raise SatelliteProviderUnavailableError(
                        provider_id=self._provider_id,
                        details=f"Provider '{self._provider_id}' connection failed after {attempts} attempts: {exc}",
                    ) from exc
            except SatelliteError:
                # Direct satellite errors pass through unchanged
                raise
            except Exception as exc:
                # Unhandled runtime exception normalized to SatelliteProviderError
                logger.error(f"Provider '{self._provider_id}' encountered unexpected error in '{operation_name}': {exc}")
                raise SatelliteProviderError(
                    provider_id=self._provider_id,
                    details=f"Unexpected error in provider '{self._provider_id}': {exc}",
                    operation=operation_name,
                ) from exc

            # Calculate backoff delay with small jitter
            backoff = min(self._initial_backoff * (2 ** (attempts - 1)), self._max_backoff)
            jitter = random.uniform(0.0, 0.1 * backoff)
            time.sleep(backoff + jitter)

        raise SatelliteProviderError(
            provider_id=self._provider_id,
            details=f"Provider '{self._provider_id}' operation failed: {last_error}",
            operation=operation_name,
        )


class NasaEarthdataAdapter(BaseSatelliteProviderAdapter):
    """Provider adapter extension point for NASA Earthdata / CMR / USGS Landsat."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        enabled: bool = True,
    ):
        super().__init__(
            provider_id="nasa_earthdata",
            provider_name="NASA Earthdata / USGS",
            timeout=timeout,
            max_retries=max_retries,
            enabled=enabled,
        )
        self._api_key = api_key

    def get_provider_manifest(self) -> SatelliteProvider:
        return SatelliteProvider(
            provider_id=self._provider_id,
            provider_name=self._provider_name,
            status=SatelliteProviderStatus.ACTIVE if self.is_available else SatelliteProviderStatus.UNAVAILABLE,
            supported_constellations=["Landsat-8", "Landsat-9", "MODIS-Terra", "MODIS-Aqua"],
            supported_sensor_types=[
                SatelliteSensorType.OPTICAL_MULTISPECTRAL,
                SatelliteSensorType.THERMAL_INFRARED,
            ],
            supported_formats=[
                SatelliteDataFormat.GEOTIFF,
                SatelliteDataFormat.COG,
                SatelliteDataFormat.HDF5,
            ],
            access_protocol="REST_API",
            requires_authentication=True,
            credential_key_env_var="EARTHMIND_SATELLITE_NASA_API_KEY",
            rate_limit_requests_per_minute=60,
            license_type="OPEN_ACCESS",
            attribution_text="NASA EOSDIS / USGS Earth Resources Observation and Science (EROS) Center",
        )

    def search_catalog(self, request: SatelliteDataRequest) -> List[SatelliteDatasetMetadata]:
        def _op():
            logger.info(f"[{self._provider_id}] Catalog search stub invoked for request '{request.request_id}'.")
            return []
        return self.execute_with_retry("search_catalog", _op)

    def acquire_dataset(self, dataset_id: str, request: SatelliteDataRequest) -> SatelliteAcquisitionResult:
        def _op():
            return SatelliteAcquisitionResult(
                request_id=request.request_id,
                status=SatelliteAcquisitionStatus.PENDING,
                provider_id=self._provider_id,
                error_message="Live NASA acquisition is scheduled for Stage D3.",
            )
        return self.execute_with_retry("acquire_dataset", _op)


class IsroBhuvanAdapter(BaseSatelliteProviderAdapter):
    """Provider adapter extension point for ISRO / NRSC Bhuvan & Bhoonidhi (Resourcesat, Cartosat, RISAT)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        enabled: bool = True,
    ):
        super().__init__(
            provider_id="isro_bhuvan",
            provider_name="ISRO NRSC Bhuvan / Bhoonidhi",
            timeout=timeout,
            max_retries=max_retries,
            enabled=enabled,
        )
        self._api_key = api_key

    def get_provider_manifest(self) -> SatelliteProvider:
        return SatelliteProvider(
            provider_id=self._provider_id,
            provider_name=self._provider_name,
            status=SatelliteProviderStatus.ACTIVE if self.is_available else SatelliteProviderStatus.UNAVAILABLE,
            supported_constellations=["Resourcesat-2A", "Cartosat-2", "RISAT-1A (EOS-04)"],
            supported_sensor_types=[
                SatelliteSensorType.OPTICAL_MULTISPECTRAL,
                SatelliteSensorType.SYNTHETIC_APERTURE_RADAR,
            ],
            supported_formats=[
                SatelliteDataFormat.GEOTIFF,
                SatelliteDataFormat.RAW_BINARY,
            ],
            access_protocol="REST_API",
            requires_authentication=True,
            credential_key_env_var="EARTHMIND_SATELLITE_ISRO_API_KEY",
            rate_limit_requests_per_minute=30,
            license_type="OPEN_ACCESS",
            attribution_text="Indian Space Research Organisation (ISRO) / National Remote Sensing Centre (NRSC)",
        )

    def search_catalog(self, request: SatelliteDataRequest) -> List[SatelliteDatasetMetadata]:
        def _op():
            logger.info(f"[{self._provider_id}] Catalog search stub invoked for request '{request.request_id}'.")
            return []
        return self.execute_with_retry("search_catalog", _op)

    def acquire_dataset(self, dataset_id: str, request: SatelliteDataRequest) -> SatelliteAcquisitionResult:
        def _op():
            return SatelliteAcquisitionResult(
                request_id=request.request_id,
                status=SatelliteAcquisitionStatus.PENDING,
                provider_id=self._provider_id,
                error_message="Live ISRO acquisition is scheduled for Stage D3.",
            )
        return self.execute_with_retry("acquire_dataset", _op)


class CopernicusCdseAdapter(BaseSatelliteProviderAdapter):
    """Provider adapter extension point for Copernicus Data Space Ecosystem (Sentinel-1, Sentinel-2, Sentinel-3)."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        enabled: bool = True,
    ):
        super().__init__(
            provider_id="copernicus_cdse",
            provider_name="Copernicus Data Space Ecosystem (CDSE)",
            timeout=timeout,
            max_retries=max_retries,
            enabled=enabled,
        )
        self._client_id = client_id
        self._client_secret = client_secret

    def get_provider_manifest(self) -> SatelliteProvider:
        return SatelliteProvider(
            provider_id=self._provider_id,
            provider_name=self._provider_name,
            status=SatelliteProviderStatus.ACTIVE if self.is_available else SatelliteProviderStatus.UNAVAILABLE,
            supported_constellations=["Sentinel-1", "Sentinel-2", "Sentinel-3"],
            supported_sensor_types=[
                SatelliteSensorType.OPTICAL_MULTISPECTRAL,
                SatelliteSensorType.SYNTHETIC_APERTURE_RADAR,
                SatelliteSensorType.THERMAL_INFRARED,
            ],
            supported_formats=[
                SatelliteDataFormat.SAFE,
                SatelliteDataFormat.COG,
                SatelliteDataFormat.GEOTIFF,
            ],
            access_protocol="STAC_API",
            requires_authentication=True,
            credential_key_env_var="EARTHMIND_SATELLITE_COPERNICUS_CLIENT_ID",
            rate_limit_requests_per_minute=120,
            license_type="OPEN_ACCESS",
            attribution_text="Contains modified Copernicus Sentinel data [2025] processed by EarthMind",
        )

    def search_catalog(self, request: SatelliteDataRequest) -> List[SatelliteDatasetMetadata]:
        def _op():
            logger.info(f"[{self._provider_id}] Catalog search stub invoked for request '{request.request_id}'.")
            return []
        return self.execute_with_retry("search_catalog", _op)

    def acquire_dataset(self, dataset_id: str, request: SatelliteDataRequest) -> SatelliteAcquisitionResult:
        def _op():
            return SatelliteAcquisitionResult(
                request_id=request.request_id,
                status=SatelliteAcquisitionStatus.PENDING,
                provider_id=self._provider_id,
                error_message="Live Copernicus acquisition is scheduled for Stage D3.",
            )
        return self.execute_with_retry("acquire_dataset", _op)


class MockSatelliteProviderAdapter(BaseSatelliteProviderAdapter):
    """Deterministic mock provider adapter for unit testing and local development."""

    def __init__(
        self,
        provider_id: str = "mock_satellite_provider",
        provider_name: str = "Deterministic Mock Satellite Provider",
        simulate_error: Optional[Exception] = None,
        simulate_timeout: bool = False,
        supported_sensor_types: Optional[List[SatelliteSensorType]] = None,
        enabled: bool = True,
    ):
        super().__init__(
            provider_id=provider_id,
            provider_name=provider_name,
            timeout=5.0,
            max_retries=1,
            initial_backoff=0.01,
            max_backoff=0.05,
            enabled=enabled,
        )
        self.simulate_error = simulate_error
        self.simulate_timeout = simulate_timeout
        self.supported_sensor_types = supported_sensor_types or [
            SatelliteSensorType.OPTICAL_MULTISPECTRAL,
            SatelliteSensorType.THERMAL_INFRARED,
        ]
        self.is_mock = True

    def get_provider_manifest(self) -> SatelliteProvider:
        return SatelliteProvider(
            provider_id=self._provider_id,
            provider_name=self._provider_name,
            status=SatelliteProviderStatus.ACTIVE if self.is_available else SatelliteProviderStatus.UNAVAILABLE,
            supported_constellations=["Mock-Sat-1", "Mock-Sentinel"],
            supported_sensor_types=self.supported_sensor_types,
            supported_formats=[SatelliteDataFormat.COG, SatelliteDataFormat.GEOTIFF, SatelliteDataFormat.JSON],
            access_protocol="MOCK_IN_MEMORY",
            requires_authentication=False,
            attribution_text="Mock data for testing only - Not real satellite observations",
        )

    def search_catalog(self, request: SatelliteDataRequest) -> List[SatelliteDatasetMetadata]:
        def _op():
            if self.simulate_timeout:
                raise TimeoutError("Simulated provider timeout during catalog search")
            if self.simulate_error:
                raise self.simulate_error

            meta = SatelliteDatasetMetadata(
                dataset_id=f"MOCK_SCENE_{request.request_id[-6:]}",
                provider_id=self._provider_id,
                constellation="Mock-Sentinel",
                platform="Mock-Sat-1",
                instrument="Mock-MSI",
                sensor_type=SatelliteSensorType.OPTICAL_MULTISPECTRAL,
                processing_level="LEVEL-2A",
                geospatial=request.geospatial,
                temporal=request.temporal_window,
                cloud_cover_percentage=min(request.max_cloud_cover_percentage, 5.0),
                quality_status=SatelliteDataQuality.EXCELLENT,
                license_attribution="Mock test data",
            )
            return [meta]
        return self.execute_with_retry("search_catalog", _op)

    def acquire_dataset(self, dataset_id: str, request: SatelliteDataRequest) -> SatelliteAcquisitionResult:
        def _op():
            if self.simulate_timeout:
                raise TimeoutError("Simulated provider timeout during dataset acquisition")
            if self.simulate_error:
                raise self.simulate_error

            meta = SatelliteDatasetMetadata(
                dataset_id=dataset_id,
                provider_id=self._provider_id,
                constellation="Mock-Sentinel",
                platform="Mock-Sat-1",
                instrument="Mock-MSI",
                sensor_type=SatelliteSensorType.OPTICAL_MULTISPECTRAL,
                processing_level="LEVEL-2A",
                geospatial=request.geospatial,
                temporal=request.temporal_window,
                cloud_cover_percentage=5.0,
                quality_status=SatelliteDataQuality.EXCELLENT,
                license_attribution="Mock test data",
            )
            return SatelliteAcquisitionResult(
                request_id=request.request_id,
                status=SatelliteAcquisitionStatus.ACQUIRED,
                provider_id=self._provider_id,
                dataset_metadata=meta,
                download_size_bytes=1024 * 1024,
                cached=False,
                warnings=["Served by deterministic mock adapter"],
            )
        return self.execute_with_retry("acquire_dataset", _op)


class SatelliteAdapterRegistry:
    """Manages active Satellite provider adapter instances and dispatch."""

    def __init__(self):
        self._lock = threading.RLock()
        self._adapters: Dict[str, BaseSatelliteProviderAdapter] = {}

    def register_adapter(self, adapter: BaseSatelliteProviderAdapter) -> None:
        """Register an adapter instance."""
        with self._lock:
            pid = adapter.provider_id
            self._adapters[pid] = adapter
            logger.info(f"Registered satellite provider adapter '{pid}' ({adapter.provider_name}).")

    def get_adapter(self, provider_id: str) -> Optional[BaseSatelliteProviderAdapter]:
        """Retrieve adapter by provider ID."""
        with self._lock:
            return self._adapters.get(provider_id)

    def list_adapters(self) -> List[BaseSatelliteProviderAdapter]:
        """List all registered adapters."""
        with self._lock:
            return list(self._adapters.values())

    def unregister_adapter(self, provider_id: str) -> bool:
        """Unregister adapter."""
        with self._lock:
            if provider_id in self._adapters:
                del self._adapters[provider_id]
                return True
            return False

    def clear(self) -> None:
        """Clear registered adapters."""
        with self._lock:
            self._adapters.clear()
