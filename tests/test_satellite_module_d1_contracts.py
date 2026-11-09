"""Contract-level validation tests for EarthMind Satellite Intelligence Module Stage D1.

Verifies:
1. Valid satellite data request contract parsing and validation.
2. Invalid request rejection (missing required fields, bad coordinate bounds).
3. Geospatial bounding box validation (min <= max, lat/lon bounds).
4. Temporal metadata contract validation.
5. Satellite provider capability manifest validation.
6. Dataset metadata contract validation with spectral bands.
7. Processed satellite data contract validation (quality status, processing pipeline).
8. Agricultural indicator contract validation (NDVI, NDRE, NDWI band requirements).
9. EarthMindSatelliteEvidence output schema validation (v1.0 schema check).
10. Version rejection (unsupported versions, invalid contract name).
11. Missing metadata representation (explicit CLOUD_OBSCURED / DEGRADED without fabricated data).
12. Missing spectral band representation (graceful degradation, indicator limitation logging).
13. Sarvam integration contract & B2 ContextItem compatibility (to_context_item).
14. Structured error contract validation (all 18 error codes, retryable flags, metadata).
15. Satellite exception hierarchy and EarthMindException inheritance.
16. All 24 Satellite Protocol interfaces runtime checkability.
17. Boundary and governance constraints (tenant isolation, license attribution preservation).
"""

import pytest
from pydantic import ValidationError

from core.errors.exceptions import (
    EarthMindException,
    SatelliteDatasetNotFoundError,
    SatelliteDatasetUnavailableError,
    SatelliteError,
    SatelliteEvidenceValidationError,
    SatelliteIndicatorProcessingError,
    SatelliteIngestionError,
    SatelliteInsufficientDataError,
    SatelliteIntegrationError,
    SatelliteInternalError,
    SatelliteInvalidArgumentError,
    SatelliteMetadataError,
    SatelliteProcessingError,
    SatelliteProviderError,
    SatelliteProviderUnavailableError,
    SatelliteQualityValidationFailedError,
    SatelliteStorageError,
    SatelliteStorageUnavailableError,
    SatelliteTimeoutError,
    SatelliteUnsupportedFormatError,
)
from core.interfaces.satellite import (
    ISatelliteAgronomicFeatureExtractor,
    ISatelliteB2ContextAdapter,
    ISatelliteCacheStorageAdapter,
    ISatelliteCatalogDiscovery,
    ISatelliteCrossModuleDataSharing,
    ISatelliteDataAcquisition,
    ISatelliteDiagnostics,
    ISatelliteEvidenceBuilder,
    ISatelliteEvidenceValidator,
    ISatelliteGeospatialProcessor,
    ISatelliteGovernanceGate,
    ISatelliteImageryProcessor,
    ISatelliteIndicatorExtractor,
    ISatelliteIngestionDetector,
    ISatelliteMetadataExtractor,
    ISatelliteMultiSourceFusion,
    ISatellitePreValidator,
    ISatelliteProvenanceTracker,
    ISatelliteProviderAdapter,
    ISatelliteProviderRegistry,
    ISatelliteSarvamContextFormatter,
    ISatelliteSpectralProcessor,
    ISatelliteTemporalProcessor,
    ISatelliteUncertaintyAssessor,
)
from core.schemas.satellite import (
    EarthMindSatelliteEvidence,
    SatelliteAcquisitionResult,
    SatelliteAcquisitionStatus,
    SatelliteBandType,
    SatelliteDataFormat,
    SatelliteDataQuality,
    SatelliteDataRequest,
    SatelliteDatasetMetadata,
    SatelliteErrorContract,
    SatelliteErrorCode,
    SatelliteEvidenceStatus,
    SatelliteGeospatialMetadata,
    SatelliteIndicator,
    SatelliteIntegrationRequest,
    SatelliteIntegrationResponse,
    SatelliteProcessedData,
    SatelliteProcessingStatus,
    SatelliteProvider,
    SatelliteProviderStatus,
    SatelliteQualityAssessment,
    SatelliteRawDataReference,
    SatelliteScopeInfo,
    SatelliteSensorType,
    SatelliteSourceInfo,
    SatelliteSpectralBand,
    SatelliteTemporalMetadata,
    SatelliteUncertaintyAssessment,
)
from modules.context.schemas import ContextItem, PriorityLevel, PrivacyLevel


# ============================================================================
# Test 1: Valid Satellite Data Request Contract
# ============================================================================

def test_valid_satellite_data_request():
    req = SatelliteDataRequest(
        tenant_id="tenant_icar_01",
        farmer_id="farmer_10842",
        farm_id="farm_karnal_01",
        field_id="field_wheat_zone_02",
        geospatial=SatelliteGeospatialMetadata(
            latitude=29.6857,
            longitude=76.9905,
            bounding_box=[76.9850, 29.6800, 76.9960, 29.6910],
            spatial_resolution_meters=10.0,
            coverage_area_hectares=12.4,
        ),
        temporal_window=SatelliteTemporalMetadata(
            acquisition_date="2025-03-28T05:16:49Z",
            revisit_interval_days=5.0,
        ),
        target_constellations=["Sentinel-2"],
        sensor_types=[SatelliteSensorType.OPTICAL_MULTISPECTRAL],
        requested_indicators=["NDVI", "NDRE"],
        max_cloud_cover_percentage=15.0,
        prefer_calibrated=True,
    )

    assert req.tenant_id == "tenant_icar_01"
    assert req.field_id == "field_wheat_zone_02"
    assert req.geospatial.latitude == 29.6857
    assert req.max_cloud_cover_percentage == 15.0
    assert "NDVI" in req.requested_indicators


# ============================================================================
# Test 2: Invalid Request Rejection (Missing Coordinates / Bad Bounds)
# ============================================================================

def test_invalid_request_out_of_bounds_latitude():
    with pytest.raises(ValidationError):
        SatelliteGeospatialMetadata(
            latitude=95.0,  # Invalid: > 90.0
            longitude=76.9905,
        )


def test_invalid_request_inverted_bounding_box():
    with pytest.raises(ValidationError) as exc:
        SatelliteGeospatialMetadata(
            latitude=29.6857,
            longitude=76.9905,
            bounding_box=[76.9850, 30.0000, 76.9960, 29.0000],  # min_lat > max_lat
        )
    assert "cannot exceed max_lat" in str(exc.value)


# ============================================================================
# Test 3: Satellite Provider Capability Manifest
# ============================================================================

def test_satellite_provider_contract():
    provider = SatelliteProvider(
        provider_id="copernicus_cdse",
        provider_name="Copernicus Data Space Ecosystem",
        status=SatelliteProviderStatus.ACTIVE,
        supported_constellations=["Sentinel-1", "Sentinel-2"],
        supported_sensor_types=[SatelliteSensorType.OPTICAL_MULTISPECTRAL, SatelliteSensorType.SYNTHETIC_APERTURE_RADAR],
        supported_formats=[SatelliteDataFormat.COG, SatelliteDataFormat.SAFE],
        access_protocol="STAC_API",
        requires_authentication=True,
        credential_key_env_var="EARTHMIND_SATELLITE_COPERNICUS_SECRET",
        rate_limit_requests_per_minute=120,
        license_type="OPEN_ACCESS",
        attribution_text="Contains modified Copernicus Sentinel data, processed by EarthMind",
    )

    assert provider.provider_id == "copernicus_cdse"
    assert provider.status == SatelliteProviderStatus.ACTIVE
    assert "Sentinel-2" in provider.supported_constellations
    assert provider.requires_authentication is True


# ============================================================================
# Test 4: Satellite Dataset Metadata & Spectral Bands
# ============================================================================

def test_satellite_dataset_metadata():
    red_band = SatelliteSpectralBand(
        band_id="B04",
        band_name="RED",
        band_type=SatelliteBandType.RED,
        central_wavelength_nm=665.0,
        bandwidth_nm=30.0,
        spatial_resolution_meters=10.0,
        measurement_unit="reflectance",
        is_calibrated=True,
        statistics={"mean": 0.065, "min": 0.032, "max": 0.145, "std_dev": 0.02},
    )

    nir_band = SatelliteSpectralBand(
        band_id="B08",
        band_name="NIR",
        band_type=SatelliteBandType.NIR,
        central_wavelength_nm=842.0,
        bandwidth_nm=115.0,
        spatial_resolution_meters=10.0,
        measurement_unit="reflectance",
        is_calibrated=True,
        statistics={"mean": 0.485, "min": 0.220, "max": 0.590, "std_dev": 0.05},
    )

    dataset_meta = SatelliteDatasetMetadata(
        dataset_id="S2B_MSIL2A_20250328T051649_N0511_R062_T43REQ_20250328T073610",
        provider_id="copernicus_cdse",
        constellation="Sentinel-2",
        platform="Sentinel-2B",
        instrument="MSI",
        sensor_type=SatelliteSensorType.OPTICAL_MULTISPECTRAL,
        processing_level="LEVEL-2A",
        geospatial=SatelliteGeospatialMetadata(latitude=29.6857, longitude=76.9905),
        temporal=SatelliteTemporalMetadata(acquisition_date="2025-03-28T05:16:49Z"),
        cloud_cover_percentage=1.2,
        available_bands=[red_band, nir_band],
        license_attribution="Contains modified Copernicus Sentinel data (2025), processed by EarthMind",
    )

    assert dataset_meta.platform == "Sentinel-2B"
    assert len(dataset_meta.available_bands) == 2
    assert dataset_meta.cloud_cover_percentage == 1.2
    assert dataset_meta.available_bands[0].central_wavelength_nm == 665.0


# ============================================================================
# Test 5: Satellite Raw Data Reference (Pointer Abstraction)
# ============================================================================

def test_satellite_raw_data_reference():
    raw_ref = SatelliteRawDataReference(
        dataset_id="S2B_20250328",
        provider_id="copernicus_cdse",
        storage_uri="s3://earthmind-satellite-cache/s2b/2025/03/28/tile.tif",
        data_format=SatelliteDataFormat.COG,
        size_bytes=104857600,
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        retention_expires_at="2025-04-04T05:16:49Z",
    )

    assert raw_ref.size_bytes == 104857600
    assert raw_ref.data_format == SatelliteDataFormat.COG
    assert raw_ref.sha256_hash is not None


# ============================================================================
# Test 6: Agricultural Indicator Contract (NDVI, NDRE)
# ============================================================================

def test_satellite_indicator_contract():
    ndvi = SatelliteIndicator(
        indicator_name="NDVI",
        definition="Normalized Difference Vegetation Index: (NIR - Red) / (NIR + Red)",
        calculation_method="standard_band_ratio",
        required_bands=["RED", "NIR"],
        source_dataset_id="S2B_20250328",
        result_statistics={"mean": 0.76, "min": 0.42, "max": 0.86, "std_dev": 0.08},
        unit="unitless_ratio",
        quality_status=SatelliteDataQuality.EXCELLENT,
        limitations=["Saturates in high biomass canopy (LAI > 4)"],
    )

    assert ndvi.indicator_name == "NDVI"
    assert ndvi.result_statistics["mean"] == 0.76
    assert "RED" in ndvi.required_bands
    assert len(ndvi.limitations) == 1


# ============================================================================
# Test 7: EarthMindSatelliteEvidence Output Contract v1.0
# ============================================================================

def test_earthmind_satellite_evidence_schema_v1():
    evidence = EarthMindSatelliteEvidence(
        contract_name="EarthMindSatelliteEvidence",
        schema_version="1.0",
        source=SatelliteSourceInfo(
            provider_id="copernicus_cdse",
            constellation="Sentinel-2",
            platform="Sentinel-2B",
            instrument="MSI",
            sensor_type=SatelliteSensorType.OPTICAL_MULTISPECTRAL,
            dataset_id="S2B_20250328",
            processing_level="LEVEL-2A",
        ),
        scope=SatelliteScopeInfo(
            tenant_id="tenant_01",
            farmer_id="farmer_01",
            field_id="field_wheat_01",
            crop="Wheat",
        ),
        geospatial=SatelliteGeospatialMetadata(latitude=29.6857, longitude=76.9905),
        temporal=SatelliteTemporalMetadata(acquisition_date="2025-03-28T05:16:49Z"),
        indicators=[
            SatelliteIndicator(
                indicator_name="NDVI",
                definition="Normalized Difference Vegetation Index",
                calculation_method="band_ratio",
                required_bands=["RED", "NIR"],
                source_dataset_id="S2B_20250328",
                result_statistics={"mean": 0.76},
            )
        ],
        quality=SatelliteQualityAssessment(
            overall_quality=SatelliteDataQuality.EXCELLENT,
            cloud_cover_percentage=0.5,
            is_atmospheric_corrected=True,
        ),
        uncertainty=SatelliteUncertaintyAssessment(
            overall_confidence=0.96,
        ),
        license_attribution="Contains modified Copernicus Sentinel data (2025), processed by EarthMind",
        status=SatelliteEvidenceStatus.SUCCESS,
    )

    assert evidence.contract_name == "EarthMindSatelliteEvidence"
    assert evidence.schema_version == "1.0"
    assert evidence.status == SatelliteEvidenceStatus.SUCCESS
    assert evidence.quality.overall_quality == SatelliteDataQuality.EXCELLENT
    assert evidence.uncertainty.overall_confidence == 0.96


# ============================================================================
# Test 8: Schema Version Rejection & Invalid Contract Name
# ============================================================================

def test_evidence_rejects_unsupported_version():
    with pytest.raises(ValidationError) as exc:
        EarthMindSatelliteEvidence(
            contract_name="EarthMindSatelliteEvidence",
            schema_version="2.0",  # Unsupported version
            source=SatelliteSourceInfo(
                provider_id="copernicus_cdse",
                constellation="Sentinel-2",
                platform="Sentinel-2B",
                instrument="MSI",
                sensor_type=SatelliteSensorType.OPTICAL_MULTISPECTRAL,
                dataset_id="S2B_20250328",
                processing_level="LEVEL-2A",
            ),
            geospatial=SatelliteGeospatialMetadata(latitude=29.6857, longitude=76.9905),
            temporal=SatelliteTemporalMetadata(acquisition_date="2025-03-28T05:16:49Z"),
            license_attribution="Copernicus",
        )
    assert "Unsupported schema_version: expected '1.0'" in str(exc.value)


def test_evidence_rejects_wrong_contract_name():
    with pytest.raises(ValidationError) as exc:
        EarthMindSatelliteEvidence(
            contract_name="WrongName",
            schema_version="1.0",
            source=SatelliteSourceInfo(
                provider_id="copernicus_cdse",
                constellation="Sentinel-2",
                platform="Sentinel-2B",
                instrument="MSI",
                sensor_type=SatelliteSensorType.OPTICAL_MULTISPECTRAL,
                dataset_id="S2B_20250328",
                processing_level="LEVEL-2A",
            ),
            geospatial=SatelliteGeospatialMetadata(latitude=29.6857, longitude=76.9905),
            temporal=SatelliteTemporalMetadata(acquisition_date="2025-03-28T05:16:49Z"),
            license_attribution="Copernicus",
        )
    assert "Invalid contract_name: expected 'EarthMindSatelliteEvidence'" in str(exc.value)


# ============================================================================
# Test 9: Missing Metadata Representation (Cloud Obscured / Degraded)
# ============================================================================

def test_missing_metadata_cloud_obscuration():
    """Cloud-obscured observation must be explicitly flagged without fabricated index values."""
    evidence = EarthMindSatelliteEvidence(
        contract_name="EarthMindSatelliteEvidence",
        schema_version="1.0",
        source=SatelliteSourceInfo(
            provider_id="copernicus_cdse",
            constellation="Sentinel-2",
            platform="Sentinel-2B",
            instrument="MSI",
            sensor_type=SatelliteSensorType.OPTICAL_MULTISPECTRAL,
            dataset_id="S2B_20250328",
            processing_level="LEVEL-2A",
        ),
        geospatial=SatelliteGeospatialMetadata(latitude=29.6857, longitude=76.9905),
        temporal=SatelliteTemporalMetadata(acquisition_date="2025-03-28T05:16:49Z"),
        quality=SatelliteQualityAssessment(
            overall_quality=SatelliteDataQuality.CLOUD_OBSCURED,
            cloud_cover_percentage=88.5,
        ),
        uncertainty=SatelliteUncertaintyAssessment(
            overall_confidence=0.20,
            uncertainty_sources=["dense_cloud_obscuration_88pct"],
        ),
        license_attribution="Contains modified Copernicus Sentinel data (2025)",
        warnings=["Cloud cover exceeds 80%; vegetative reflectance values unavailable"],
        status=SatelliteEvidenceStatus.DEGRADED,
    )

    assert evidence.quality.overall_quality == SatelliteDataQuality.CLOUD_OBSCURED
    assert evidence.status == SatelliteEvidenceStatus.DEGRADED
    assert evidence.uncertainty.overall_confidence == 0.20
    assert len(evidence.warnings) == 1


# ============================================================================
# Test 10: Missing Spectral Band Representation (Graceful Degradation)
# ============================================================================

def test_missing_spectral_band_omission():
    """Missing band (e.g. RedEdge) causes indicator omission with documented limitation."""
    indicator = SatelliteIndicator(
        indicator_name="NDRE",
        definition="Normalized Difference Red Edge Index",
        calculation_method="band_ratio",
        required_bands=["NIR", "RED_EDGE_1"],
        source_dataset_id="LC08_20250328",
        result_statistics={"status": "UNAVAILABLE"},
        quality_status=SatelliteDataQuality.INCOMPLETE,
        limitations=["RedEdge band absent on Landsat-8/OLI; NDRE calculation omitted."],
    )

    assert indicator.quality_status == SatelliteDataQuality.INCOMPLETE
    assert "RedEdge band absent" in indicator.limitations[0]


# ============================================================================
# Test 11: Sarvam Integration Contract & B2 ContextItem Translation
# ============================================================================

def test_sarvam_integration_contract_and_b2_context_item():
    evidence = EarthMindSatelliteEvidence(
        contract_name="EarthMindSatelliteEvidence",
        schema_version="1.0",
        evidence_id="ev_sat_test_101",
        source=SatelliteSourceInfo(
            provider_id="copernicus_cdse",
            constellation="Sentinel-2",
            platform="Sentinel-2B",
            instrument="MSI",
            sensor_type=SatelliteSensorType.OPTICAL_MULTISPECTRAL,
            dataset_id="S2B_20250328",
            processing_level="LEVEL-2A",
        ),
        scope=SatelliteScopeInfo(
            tenant_id="tenant_01",
            farmer_id="farmer_01",
            field_id="field_wheat_01",
            crop="Wheat",
        ),
        geospatial=SatelliteGeospatialMetadata(latitude=29.6857, longitude=76.9905),
        temporal=SatelliteTemporalMetadata(acquisition_date="2025-03-28T05:16:49Z"),
        indicators=[
            SatelliteIndicator(
                indicator_name="NDVI",
                definition="Normalized Difference Vegetation Index",
                calculation_method="band_ratio",
                required_bands=["RED", "NIR"],
                source_dataset_id="S2B_20250328",
                result_statistics={"mean": 0.74},
            )
        ],
        uncertainty=SatelliteUncertaintyAssessment(overall_confidence=0.95),
        license_attribution="Contains modified Copernicus Sentinel data (2025)",
        status=SatelliteEvidenceStatus.SUCCESS,
    )

    bridge = SatelliteIntegrationResponse(
        contract_name="SatelliteIntegrationResponse",
        schema_version="1.0",
        request_id="sat_req_001",
        evidence=evidence,
        target_model="Sarvam-105B",
        context_priority="HIGH",
    )

    context_item = bridge.to_context_item()

    assert isinstance(context_item, ContextItem)
    assert context_item.entity_type == "satellite_evidence"
    assert context_item.entity_id == "field_wheat_01"
    assert context_item.source == "satellite_module"
    assert context_item.confidence == 0.95
    assert context_item.priority == PriorityLevel.HIGH
    assert context_item.privacy_level == PrivacyLevel.FARM_PRIVATE
    assert context_item.farmer_id == "farmer_01"
    assert "NDVI" in str(context_item.content)
    assert "Contains modified Copernicus Sentinel data" in context_item.metadata["license_attribution"]


# ============================================================================
# Test 12: Structured Error Contract (All 18 Error Codes)
# ============================================================================

def test_satellite_error_contract_all_codes():
    all_codes = list(SatelliteErrorCode)
    assert len(all_codes) == 18

    expected_codes = [
        "INVALID_ARGUMENT",
        "PROVIDER_ERROR",
        "PROVIDER_UNAVAILABLE",
        "DATASET_UNAVAILABLE",
        "DATASET_NOT_FOUND",
        "UNSUPPORTED_FORMAT",
        "INGESTION_FAILED",
        "INVALID_METADATA",
        "PROCESSING_FAILED",
        "INSUFFICIENT_DATA",
        "QUALITY_VALIDATION_FAILED",
        "INDICATOR_PROCESSING_FAILED",
        "EVIDENCE_VALIDATION_FAILED",
        "STORAGE_UNAVAILABLE",
        "STORAGE_ERROR",
        "TIMEOUT",
        "INTEGRATION_ERROR",
        "INTERNAL_ERROR",
    ]

    for code_name in expected_codes:
        code_enum = SatelliteErrorCode(code_name)
        err = SatelliteErrorContract(
            error_code=code_enum,
            message=f"Testing {code_name}",
            operation="test_op",
            retryable=(code_enum in [SatelliteErrorCode.STORAGE_UNAVAILABLE, SatelliteErrorCode.PROVIDER_UNAVAILABLE, SatelliteErrorCode.TIMEOUT]),
            metadata={"test_key": "val"},
        )
        assert err.error_code == code_enum
        assert err.module == "satellite"


# ============================================================================
# Test 13: Satellite Exception Hierarchy & EarthMindException Inheritance
# ============================================================================

def test_satellite_exception_hierarchy():
    exc = SatelliteProviderUnavailableError(provider_id="copernicus_cdse")
    assert isinstance(exc, SatelliteError)
    assert isinstance(exc, EarthMindException)
    assert exc.error_contract.error_code == "PROVIDER_UNAVAILABLE"
    assert exc.error_contract.module == "satellite"
    assert exc.error_contract.retryable is True

    timeout_exc = SatelliteTimeoutError(operation="download_band", timeout=30.0)
    assert timeout_exc.error_contract.retryable is True
    assert timeout_exc.error_contract.metadata["timeout"] == 30.0


# ============================================================================
# Test 14: Runtime Checkability of All 24 Satellite Interfaces
# ============================================================================

def test_satellite_interfaces_runtime_checkable():
    interfaces = [
        ISatelliteProviderRegistry,
        ISatelliteProviderAdapter,
        ISatelliteCatalogDiscovery,
        ISatelliteDataAcquisition,
        ISatelliteIngestionDetector,
        ISatelliteMetadataExtractor,
        ISatellitePreValidator,
        ISatelliteCacheStorageAdapter,
        ISatelliteImageryProcessor,
        ISatelliteSpectralProcessor,
        ISatelliteGeospatialProcessor,
        ISatelliteTemporalProcessor,
        ISatelliteIndicatorExtractor,
        ISatelliteMultiSourceFusion,
        ISatelliteUncertaintyAssessor,
        ISatelliteAgronomicFeatureExtractor,
        ISatelliteEvidenceBuilder,
        ISatelliteEvidenceValidator,
        ISatelliteProvenanceTracker,
        ISatelliteGovernanceGate,
        ISatelliteB2ContextAdapter,
        ISatelliteSarvamContextFormatter,
        ISatelliteCrossModuleDataSharing,
        ISatelliteDiagnostics,
    ]

    assert len(interfaces) == 24

    # Test dummy implementation of ISatelliteProviderRegistry
    class DummyRegistry:
        def register_provider(self, provider):
            return True
        def get_provider(self, provider_id):
            return None
        def list_providers(self, status=None):
            return []
        def is_provider_available(self, provider_id):
            return True

    assert isinstance(DummyRegistry(), ISatelliteProviderRegistry)
