"""Comprehensive Test Suite for EarthMind Satellite Module Stage D3.

Verifies:
Catalog:
1. Dataset registration.
2. Dataset retrieval.
3. Metadata validation.
4. Dataset version handling.
5. Duplicate dataset handling.
6. Provenance preservation.

Discovery:
7. Geographic filtering.
8. Temporal filtering.
9. Provider capability filtering.
10. Unsupported provider handling.
11. Provider unavailable handling.
12. Provider response normalization.

Acquisition:
13. Successful acquisition.
14. Acquisition failure.
15. Timeout handling.
16. Retry limits.
17. Duplicate request handling.
18. Cancellation behavior where supported.
19. Partial acquisition handling.

Ingestion:
20. Supported format detection.
21. Unsupported format rejection.
22. Corrupted input rejection.
23. Metadata extraction.
24. Integrity verification.
25. Raw data preservation.

Caching:
26. Cache hit.
27. Cache miss.
28. Expired cache handling.
29. Geographic mismatch.
30. Temporal mismatch.
31. Dataset version mismatch.
32. Cache invalidation.
33. Duplicate acquisition prevention.

Security and Regression:
34. Secret masking.
35. Tenant isolation.
36. Safe archive handling.
37. Resource limits.
38. Production storage configuration.
39. D1 contract compatibility.
40. D2 registry and adapter compatibility.
"""

import os
import shutil
import time
import pytest

from core.config.settings import SatelliteConfig, Settings
from core.errors.exceptions import ConfigurationError
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
    SatelliteRawDataReference,
    SatelliteSensorType,
    SatelliteSpectralBand,
    SatelliteTemporalMetadata,
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
from modules.satellite.discovery import SatelliteDiscoveryEngine
from modules.satellite.errors import (
    SatelliteIngestionError,
    SatelliteInvalidArgumentError,
    SatelliteProcessingError,
    SatelliteProviderUnavailableError,
    SatelliteTimeoutError,
    SatelliteUnsupportedFormatError,
)
from modules.satellite.formats import SatelliteFormatDetector
from modules.satellite.ingestion import SatelliteIngestionEngine
from modules.satellite.metadata_extractor import SatelliteMetadataExtractor
from modules.satellite.pre_validator import SatellitePreValidator
from modules.satellite.registry import SatelliteProviderRegistry
from modules.satellite.request_manager import (
    SatelliteRequestManager,
    SatelliteRequestState,
)
from modules.satellite.satellite_module import SatelliteModule
from modules.satellite.satellite_service import SatelliteService
from modules.satellite.storage import (
    FilesystemSatelliteStorageAdapter,
    InMemorySatelliteStorageAdapter,
    resolve_satellite_storage_adapter,
)


@pytest.fixture
def sample_geo():
    return SatelliteGeospatialMetadata(
        latitude=20.5937,
        longitude=78.9629,
        bounding_box=[78.0, 20.0, 79.0, 21.0],
        crs="EPSG:4326",
        spatial_resolution_meters=10.0,
    )


@pytest.fixture
def sample_temporal():
    return SatelliteTemporalMetadata(
        acquisition_date="2025-03-30T05:16:51Z",
        revisit_interval_days=5.0,
    )


@pytest.fixture
def sample_request(sample_geo, sample_temporal):
    return SatelliteDataRequest(
        request_id="sat_req_test001",
        tenant_id="tenant_123",
        geospatial=sample_geo,
        temporal_window=sample_temporal,
        target_constellations=["Sentinel-2", "Mock-Sentinel"],
        max_cloud_cover_percentage=20.0,
    )


@pytest.fixture
def sample_metadata(sample_geo, sample_temporal):
    return SatelliteDatasetMetadata(
        dataset_id="S2A_MSIL2A_20250330_TEST",
        provider_id="copernicus_cdse",
        constellation="Sentinel-2",
        platform="Sentinel-2A",
        instrument="MSI",
        sensor_type=SatelliteSensorType.OPTICAL_MULTISPECTRAL,
        processing_level="LEVEL-2A",
        geospatial=sample_geo,
        temporal=sample_temporal,
        cloud_cover_percentage=5.0,
        quality_status=SatelliteDataQuality.EXCELLENT,
        license_attribution="Contains modified Copernicus Sentinel data [2025] processed by EarthMind",
    )


# ============================================================================
# Catalog Tests (1 - 6)
# ============================================================================

def test_1_dataset_registration(sample_metadata):
    catalog = SatelliteDataCatalog()
    success = catalog.register_dataset(sample_metadata)
    assert success is True
    assert catalog.count() == 1


def test_2_dataset_retrieval(sample_metadata):
    catalog = SatelliteDataCatalog()
    catalog.register_dataset(sample_metadata)
    retrieved = catalog.get_dataset(sample_metadata.dataset_id)
    assert retrieved is not None
    assert retrieved.dataset_id == sample_metadata.dataset_id
    assert retrieved.constellation == "Sentinel-2"


def test_3_metadata_validation():
    catalog = SatelliteDataCatalog()
    with pytest.raises(SatelliteInvalidArgumentError):
        catalog.register_dataset(None)


def test_4_dataset_version_handling(sample_metadata):
    catalog = SatelliteDataCatalog()
    catalog.register_dataset(sample_metadata)
    assert catalog.get_dataset_version(sample_metadata.dataset_id) == 1

    # Update with allow_update=True
    updated_meta = sample_metadata.model_copy(update={"cloud_cover_percentage": 2.5})
    catalog.register_dataset(updated_meta, allow_update=True)
    assert catalog.get_dataset_version(sample_metadata.dataset_id) == 2
    assert catalog.get_dataset(sample_metadata.dataset_id).cloud_cover_percentage == 2.5


def test_5_duplicate_dataset_handling(sample_metadata):
    catalog = SatelliteDataCatalog()
    assert catalog.register_dataset(sample_metadata) is True
    # Default allow_update is False -> duplicate rejected
    assert catalog.register_dataset(sample_metadata, allow_update=False) is False
    assert catalog.count() == 1


def test_6_provenance_preservation(sample_metadata):
    catalog = SatelliteDataCatalog()
    catalog.register_dataset(sample_metadata)
    res = catalog.get_dataset(sample_metadata.dataset_id)
    assert res.license_attribution == sample_metadata.license_attribution
    assert res.provider_id == "copernicus_cdse"


# ============================================================================
# Discovery Tests (7 - 12)
# ============================================================================

def test_7_geographic_filtering(sample_metadata, sample_temporal):
    catalog = SatelliteDataCatalog()
    catalog.register_dataset(sample_metadata)

    # Within bounding box [78.0, 20.0, 79.0, 21.0]
    hits = catalog.search_spatial_temporal(latitude=20.5, longitude=78.5)
    assert len(hits) == 1

    # Outside bounding box
    misses = catalog.search_spatial_temporal(latitude=12.0, longitude=77.0)
    assert len(misses) == 0


def test_8_temporal_filtering(sample_metadata):
    catalog = SatelliteDataCatalog()
    catalog.register_dataset(sample_metadata)

    # Within 30 days
    hits = catalog.search_spatial_temporal(
        latitude=20.5,
        longitude=78.5,
        target_date="2025-04-05",
        lookback_days=30,
    )
    assert len(hits) == 1

    # Outside lookback window (e.g. 100 days away with 10 day window)
    misses = catalog.search_spatial_temporal(
        latitude=20.5,
        longitude=78.5,
        target_date="2025-08-01",
        lookback_days=10,
    )
    assert len(misses) == 0


def test_9_provider_capability_filtering(sample_request):
    prov_reg = SatelliteProviderRegistry()
    cap_mgr = ProviderCapabilityManager()
    adapter_reg = SatelliteAdapterRegistry()
    mock_adapter = MockSatelliteProviderAdapter(enabled=True)
    adapter_reg.register_adapter(mock_adapter)
    prov_reg.register_provider(mock_adapter.get_provider_manifest())

    discovery = SatelliteDiscoveryEngine(
        provider_registry=prov_reg,
        adapter_registry=adapter_reg,
        capability_manager=cap_mgr,
    )

    results = discovery.discover_datasets(sample_request)
    assert len(results) >= 1
    assert results[0].provider_id == "mock_satellite_provider"


def test_10_unsupported_provider_handling(sample_request):
    prov_reg = SatelliteProviderRegistry()
    cap_mgr = ProviderCapabilityManager()
    adapter_reg = SatelliteAdapterRegistry()
    discovery = SatelliteDiscoveryEngine(
        provider_registry=prov_reg,
        adapter_registry=adapter_reg,
        capability_manager=cap_mgr,
    )
    # No providers registered
    results = discovery.discover_datasets(sample_request)
    assert results == []


def test_11_provider_unavailable_handling(sample_request):
    prov_reg = SatelliteProviderRegistry()
    cap_mgr = ProviderCapabilityManager()
    adapter_reg = SatelliteAdapterRegistry()
    mock_adapter = MockSatelliteProviderAdapter(enabled=False)
    adapter_reg.register_adapter(mock_adapter)
    manifest = mock_adapter.get_provider_manifest()
    manifest.status = SatelliteProviderStatus.UNAVAILABLE
    prov_reg.register_provider(manifest)

    discovery = SatelliteDiscoveryEngine(
        provider_registry=prov_reg,
        adapter_registry=adapter_reg,
        capability_manager=cap_mgr,
    )
    results = discovery.discover_datasets(sample_request)
    assert results == []


def test_12_provider_response_normalization(sample_request):
    prov_reg = SatelliteProviderRegistry()
    cap_mgr = ProviderCapabilityManager()
    adapter_reg = SatelliteAdapterRegistry()
    mock_adapter = MockSatelliteProviderAdapter(enabled=True)
    adapter_reg.register_adapter(mock_adapter)
    prov_reg.register_provider(mock_adapter.get_provider_manifest())

    discovery = SatelliteDiscoveryEngine(
        provider_registry=prov_reg,
        adapter_registry=adapter_reg,
        capability_manager=cap_mgr,
    )
    results = discovery.discover_datasets(sample_request)
    optimal = discovery.select_optimal_dataset(results, sample_request)
    assert optimal is not None
    assert isinstance(optimal, SatelliteDatasetMetadata)
    assert optimal.cloud_cover_percentage <= sample_request.max_cloud_cover_percentage


# ============================================================================
# Acquisition Tests (13 - 19)
# ============================================================================

def test_13_successful_acquisition(sample_request):
    service = SatelliteService(
        config=SatelliteConfig(mock_provider_enabled=True, storage_adapter="in_memory")
    )
    result = service.acquire(sample_request)
    assert result.status == SatelliteAcquisitionStatus.ACQUIRED
    assert result.dataset_metadata is not None
    assert result.cached is False


def test_14_acquisition_failure(sample_request):
    failing_adapter = MockSatelliteProviderAdapter()
    def _fail_acquire(dataset_id, request):
        raise ConnectionError("Connection refused by provider API gateway")
    failing_adapter.acquire_dataset = _fail_acquire

    service = SatelliteService(config=SatelliteConfig(mock_provider_enabled=False))
    service.adapter_registry.register_adapter(failing_adapter)
    service.provider_registry.register_provider(failing_adapter.get_provider_manifest(), allow_overwrite=True)

    result = service.acquire(sample_request)
    assert result.status == SatelliteAcquisitionStatus.FAILED
    assert "Connection refused" in result.error_message


def test_15_timeout_handling(sample_request):
    timeout_adapter = MockSatelliteProviderAdapter(simulate_timeout=True)
    with pytest.raises(SatelliteTimeoutError):
        timeout_adapter.search_catalog(sample_request)


def test_16_retry_limits():
    calls = 0
    def _fail_op():
        nonlocal calls
        calls += 1
        raise ConnectionError("Simulated socket drop")

    adapter = MockSatelliteProviderAdapter()
    adapter._max_retries = 2
    adapter._timeout = 10.0
    with pytest.raises(SatelliteProviderUnavailableError):
        adapter.execute_with_retry("test_retry", _fail_op)
    assert calls == 3  # Initial + 2 retries


def test_17_duplicate_request_handling():
    mgr = SatelliteRequestManager()
    r1 = mgr.create_request("req_unique_1")
    r2 = mgr.create_request("req_unique_1")
    assert r1 is r2


def test_18_cancellation_behavior():
    mgr = SatelliteRequestManager()
    mgr.create_request("req_cancel_test")
    mgr.transition_state("req_cancel_test", SatelliteRequestState.DISCOVERING)
    assert mgr.cancel_request("req_cancel_test") is True
    assert mgr.get_request("req_cancel_test").state == SatelliteRequestState.CANCELLED
    # Cannot cancel already cancelled
    assert mgr.cancel_request("req_cancel_test") is False


def test_19_partial_acquisition_handling(sample_request):
    partial_adapter = MockSatelliteProviderAdapter()
    def _partial_acquire(dataset_id, request):
        return SatelliteAcquisitionResult(
            request_id=request.request_id,
            status=SatelliteAcquisitionStatus.NOT_FOUND,
            provider_id="mock_satellite_provider",
            error_message="Scene partially corrupted on remote provider server",
        )
    partial_adapter.acquire_dataset = _partial_acquire
    service = SatelliteService(config=SatelliteConfig(mock_provider_enabled=False))
    service.adapter_registry.register_adapter(partial_adapter)
    service.provider_registry.register_provider(partial_adapter.get_provider_manifest(), allow_overwrite=True)

    result = service.acquire(sample_request)
    assert result.status == SatelliteAcquisitionStatus.NOT_FOUND
    assert "partially corrupted" in result.error_message


# ============================================================================
# Ingestion Tests (20 - 25)
# ============================================================================

def test_20_supported_format_detection():
    detector = SatelliteFormatDetector()
    assert detector.detect_format(b"II*\x00\x08") == SatelliteDataFormat.GEOTIFF
    assert detector.detect_format(b"MM\x00*\x00") == SatelliteDataFormat.GEOTIFF
    assert detector.detect_format(b"II*\x00", file_name="scene.cog.tif") == SatelliteDataFormat.COG
    assert detector.detect_format(b"CDF\x01\x00") == SatelliteDataFormat.NETCDF
    assert detector.detect_format(b"\x89HDF\r\n\x1a\n") == SatelliteDataFormat.HDF5
    assert detector.detect_format(b"PK\x03\x04", file_name="S2A_MSIL2A.SAFE.zip") == SatelliteDataFormat.SAFE
    assert detector.detect_format(b'{"type": "FeatureCollection"}') == SatelliteDataFormat.GEOJSON
    assert detector.detect_format(b'{"name": "stac_item"}') == SatelliteDataFormat.JSON
    assert detector.detect_format(b"time,band,reflectance\n1,B04,0.12\n") == SatelliteDataFormat.CSV


def test_21_unsupported_format_rejection():
    detector = SatelliteFormatDetector()
    with pytest.raises(SatelliteUnsupportedFormatError):
        detector.detect_format(b"", file_name=None)


def test_22_corrupted_input_rejection():
    engine = SatelliteIngestionEngine()
    with pytest.raises(SatelliteIngestionError):
        engine.ingest_raw_data("ds_1", "prov_1", b"", SatelliteDataFormat.RAW_BINARY)


def test_23_metadata_extraction(sample_geo, sample_temporal):
    extractor = SatelliteMetadataExtractor()
    ref = SatelliteRawDataReference(
        dataset_id="S2B_TEST_EXTRACT",
        provider_id="copernicus_cdse",
        storage_uri="earthmind://satellite/raw/test.tif",
        data_format=SatelliteDataFormat.GEOTIFF,
        size_bytes=1024,
    )
    manifest = {
        "geospatial": sample_geo,
        "temporal": sample_temporal,
        "cloud_cover": 3.2,
        "available_bands": [{"band_id": "B04", "band_name": "RED", "spatial_resolution_meters": 10.0}],
    }
    meta = extractor.extract_metadata(ref, manifest_payload=manifest)
    assert meta.dataset_id == "S2B_TEST_EXTRACT"
    assert meta.constellation == "Sentinel-2"
    assert meta.cloud_cover_percentage == 3.2
    assert len(meta.available_bands) == 1


def test_24_integrity_verification():
    engine = SatelliteIngestionEngine()
    import hashlib
    data = b"II*\x00_valid_payload"
    correct_hash = hashlib.sha256(data).hexdigest()

    # Passes with correct hash
    ref = engine.ingest_raw_data("ds_hash", "mock_prov", data, SatelliteDataFormat.GEOTIFF, expected_sha256=correct_hash)
    assert ref.sha256_hash == correct_hash

    # Fails with wrong hash
    with pytest.raises(SatelliteIngestionError) as exc:
        engine.ingest_raw_data("ds_hash", "mock_prov", data, SatelliteDataFormat.GEOTIFF, expected_sha256="wrong_hash")
    assert "Integrity check failed" in str(exc.value)


def test_25_raw_data_preservation():
    storage = InMemorySatelliteStorageAdapter()
    engine = SatelliteIngestionEngine(storage_adapter=storage)
    payload = b"II*\x00_test_preserve_bytes"
    ref = engine.ingest_raw_data("ds_preserve", "mock_prov", payload, SatelliteDataFormat.GEOTIFF)

    persisted_bytes = storage.get_raw_payload(ref.reference_id)
    assert persisted_bytes == payload


# ============================================================================
# Caching Tests (26 - 33)
# ============================================================================

def test_26_cache_hit(sample_request, sample_metadata):
    cache = SatelliteHybridCache()
    cache.put(sample_metadata)
    hit = cache.match_request(sample_request)
    assert hit is not None
    assert hit.cached is True
    assert hit.dataset_metadata.dataset_id == sample_metadata.dataset_id


def test_27_cache_miss(sample_request):
    cache = SatelliteHybridCache()
    assert cache.match_request(sample_request) is None


def test_28_expired_cache_handling(sample_request, sample_metadata):
    cache = SatelliteHybridCache(default_ttl_seconds=1)
    cache.put(sample_metadata, ttl_seconds=1)
    assert cache.get_by_id(sample_metadata.dataset_id) is not None

    time.sleep(1.1)
    assert cache.get_by_id(sample_metadata.dataset_id) is None
    assert cache.match_request(sample_request) is None


def test_29_geographic_mismatch(sample_metadata, sample_temporal):
    cache = SatelliteHybridCache()
    cache.put(sample_metadata)

    far_geo = SatelliteGeospatialMetadata(
        latitude=-45.0,
        longitude=120.0,
        bounding_box=[119.0, -46.0, 121.0, -44.0],
    )
    far_req = SatelliteDataRequest(
        geospatial=far_geo,
        temporal_window=sample_temporal,
    )
    assert cache.match_request(far_req) is None


def test_30_temporal_mismatch(sample_metadata, sample_geo):
    cache = SatelliteHybridCache()
    cache.put(sample_metadata)

    old_temporal = SatelliteTemporalMetadata(acquisition_date="2020-01-01T00:00:00Z")
    old_req = SatelliteDataRequest(
        geospatial=sample_geo,
        temporal_window=old_temporal,
    )
    assert cache.match_request(old_req) is None


def test_31_dataset_version_mismatch(sample_metadata):
    catalog = SatelliteDataCatalog()
    catalog.register_dataset(sample_metadata)
    assert catalog.get_dataset_version(sample_metadata.dataset_id) == 1

    updated = sample_metadata.model_copy(update={"cloud_cover_percentage": 1.0})
    catalog.register_dataset(updated, allow_update=True)
    assert catalog.get_dataset_version(sample_metadata.dataset_id) == 2


def test_32_cache_invalidation(sample_metadata):
    cache = SatelliteHybridCache()
    cache.put(sample_metadata)
    assert cache.get_by_id(sample_metadata.dataset_id) is not None

    assert cache.invalidate(sample_metadata.dataset_id) is True
    assert cache.get_by_id(sample_metadata.dataset_id) is None


def test_33_duplicate_acquisition_prevention(sample_request):
    service = SatelliteService(config=SatelliteConfig(mock_provider_enabled=True))
    # First acquisition fetches via provider
    r1 = service.acquire(sample_request)
    assert r1.cached is False

    # Second acquisition with same target parameters should be served from cache
    req_2 = sample_request.model_copy(update={"request_id": "sat_req_test002"})
    r2 = service.acquire(req_2)
    assert r2.cached is True
    assert r2.dataset_metadata.dataset_id == r1.dataset_metadata.dataset_id


# ============================================================================
# Security & Regression Tests (34 - 40)
# ============================================================================

def test_34_secret_masking():
    settings = Settings(
        satellite=SatelliteConfig(
            nasa_api_key="super_secret_nasa_key",
            copernicus_client_secret="secret_copernicus_12345",
        )
    )
    safe_dict = settings.to_safe_dict()
    assert "super_secret_nasa_key" not in safe_dict["satellite"]["nasa_api_key"]
    assert "secret_copernicus_12345" not in safe_dict["satellite"]["copernicus_client_secret"]


def test_35_tenant_isolation(sample_request):
    mgr = SatelliteRequestManager()
    mgr.create_request("req_t1", tenant_id="tenant_alpha")
    mgr.create_request("req_t2", tenant_id="tenant_beta")
    assert mgr.get_request("req_t1").tenant_id == "tenant_alpha"
    assert mgr.get_request("req_t2").tenant_id == "tenant_beta"


def test_36_safe_archive_handling():
    detector = SatelliteFormatDetector()
    # Safe detection from header bytes without unzipping archive to disk
    zip_bytes = b"PK\x03\x04\x14\x00\x00\x00"
    fmt = detector.detect_format(zip_bytes, file_name="safe_container.SAFE.zip")
    assert fmt == SatelliteDataFormat.SAFE


def test_37_resource_limits():
    detector = SatelliteFormatDetector(max_sample_bytes=100)
    with pytest.raises(SatelliteUnsupportedFormatError) as exc:
        detector.detect_format(b"X" * 1000)
    assert "exceeds maximum allowable limit" in str(exc.value)


def test_38_production_storage_configuration():
    # Production forbids in-memory storage adapter
    with pytest.raises(ConfigurationError) as exc:
        resolve_satellite_storage_adapter(adapter_type="in_memory", is_production=True)
    assert "In-memory satellite storage adapter is prohibited in production mode" in str(exc.value)

    # Filesystem is allowed in production
    fs_adapter = resolve_satellite_storage_adapter(adapter_type="filesystem", is_production=True)
    assert isinstance(fs_adapter, FilesystemSatelliteStorageAdapter)


def test_39_d1_contract_compatibility(sample_metadata):
    # Verify D1 SatelliteDatasetMetadata and SatelliteAcquisitionResult integrity
    acq_res = SatelliteAcquisitionResult(
        request_id="sat_req_d1_check",
        status=SatelliteAcquisitionStatus.ACQUIRED,
        provider_id="copernicus_cdse",
        dataset_metadata=sample_metadata,
        cached=False,
    )
    assert acq_res.status == SatelliteAcquisitionStatus.ACQUIRED
    assert acq_res.dataset_metadata.constellation == "Sentinel-2"


def test_40_d2_registry_and_adapter_compatibility():
    service = SatelliteService(config=SatelliteConfig(mock_provider_enabled=True))
    providers = service.provider_registry.list_providers()
    assert len(providers) >= 3  # NASA, ISRO, Copernicus + Mock
    assert service.provider_registry.is_provider_available("copernicus_cdse") is True
    assert service.adapter_registry.get_adapter("copernicus_cdse") is not None
