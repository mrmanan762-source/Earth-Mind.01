"""Comprehensive Unit and Integration Test Suite for EarthMind Satellite Module Stage D6.

Covers all 19 mandatory testing requirements:
1. Intelligence generation.
2. Indicator organization.
3. Provenance preservation.
4. Spatial and temporal compatibility.
5. Multi-source fusion.
6. Incompatible dataset rejection.
7. Conflicting observation detection.
8. Missing evidence handling.
9. Measurement uncertainty.
10. Qualitative uncertainty reporting.
11. Invalid confidence rejection.
12. Insufficient evidence handling.
13. Output schema validation.
14. Unit validation.
15. Processing version preservation.
16. Storage references.
17. Tenant isolation.
18. Error handling.
19. D1–D5 regression compatibility.
"""

import copy
import pytest
import numpy as np

from core.errors.exceptions import EvidenceValidationFailedError
from core.schemas.application import ApplicationRequest
from core.schemas.satellite import (
    EarthMindSatelliteEvidence,
    SatelliteBandType,
    SatelliteDataFormat,
    SatelliteDataQuality,
    SatelliteDataRequest,
    SatelliteEvidenceStatus,
    SatelliteGeospatialMetadata,
    SatelliteIndicator,
    SatelliteProcessedData,
    SatelliteProcessingStatus,
    SatelliteSensorType,
    SatelliteSpectralBand,
    SatelliteTemporalMetadata,
    SatelliteUncertaintyAssessment,
)
from modules.satellite.evidence_builder import SatelliteEvidenceBuilder
from modules.satellite.evidence_validator import (
    SatelliteEvidenceValidator,
    SatelliteGovernanceGate,
)
from modules.satellite.fusion import SatelliteMultiSourceFusionEngine
from modules.satellite.intelligence import SatelliteAgriculturalIntelligenceEngine
from modules.satellite.satellite_module import SatelliteModule
from modules.satellite.satellite_service import SatelliteService
from modules.satellite.uncertainty import (
    SatelliteConfidenceLevel,
    SatelliteUncertaintyAssessor,
)


@pytest.fixture
def sample_geospatial():
    return SatelliteGeospatialMetadata(
        latitude=29.6857,
        longitude=76.9905,
        bounding_box=[76.9850, 29.6800, 76.9960, 29.6910],
        crs="EPSG:4326",
        spatial_resolution_meters=10.0,
        coverage_area_hectares=12.4,
        field_id="field_karnal_01",
        farm_id="farm_karnal_main",
    )


@pytest.fixture
def sample_temporal():
    return SatelliteTemporalMetadata(
        acquisition_date="2025-03-28T05:16:49Z",
        revisit_interval_days=5.0,
        temporal_coverage_type="SCENE_INSTANTANEOUS",
    )


@pytest.fixture
def sample_bands():
    return {
        "RED": SatelliteSpectralBand(
            band_id="B04",
            band_name="RED",
            band_type=SatelliteBandType.RED,
            spatial_resolution_meters=10.0,
            measurement_unit="reflectance",
            is_calibrated=True,
            data_format=SatelliteDataFormat.COG,
            band_raster_ref="sat_storage://raw/S2B_B04.tif",
            statistics={"mean": 0.065, "min": 0.030, "max": 0.140, "std_dev": 0.02},
        ),
        "NIR": SatelliteSpectralBand(
            band_id="B08",
            band_name="NIR",
            band_type=SatelliteBandType.NIR,
            spatial_resolution_meters=10.0,
            measurement_unit="reflectance",
            is_calibrated=True,
            data_format=SatelliteDataFormat.COG,
            band_raster_ref="sat_storage://raw/S2B_B08.tif",
            statistics={"mean": 0.485, "min": 0.220, "max": 0.590, "std_dev": 0.06},
        ),
    }


@pytest.fixture
def sample_indicators():
    return [
        SatelliteIndicator(
            indicator_id="sat_ind_ndvi_001",
            indicator_name="NDVI",
            definition="Normalized Difference Vegetation Index: (NIR - Red) / (NIR + Red)",
            calculation_method="standard_band_ratio",
            required_bands=["RED", "NIR"],
            source_dataset_id="S2B_MSIL2A_20250328",
            result_statistics={"mean": 0.76, "min": 0.42, "max": 0.86, "std_dev": 0.08, "cv": 0.105},
            unit="unitless_ratio",
            quality_status=SatelliteDataQuality.EXCELLENT,
            limitations=["Saturates at high biomass (LAI > 4)"],
        ),
        SatelliteIndicator(
            indicator_id="sat_ind_ndwi_001",
            indicator_name="NDWI_GAO",
            definition="Canopy Water Index: (NIR - SWIR) / (NIR + SWIR)",
            calculation_method="canopy_water_ratio",
            required_bands=["NIR", "SWIR_1"],
            source_dataset_id="S2B_MSIL2A_20250328",
            result_statistics={"mean": 0.35, "min": 0.15, "max": 0.52, "std_dev": 0.05},
            unit="unitless_ratio",
            quality_status=SatelliteDataQuality.EXCELLENT,
            limitations=["Proxy for canopy water content, not soil moisture"],
        ),
    ]


@pytest.fixture
def sample_processed_data(sample_geospatial, sample_temporal, sample_bands):
    return SatelliteProcessedData(
        processed_id="proc_sat_test_001",
        dataset_id="S2B_MSIL2A_20250328",
        field_id="field_karnal_01",
        processing_status=SatelliteProcessingStatus.PROCESSED,
        processing_pipeline="standard_satellite_pipeline_v1",
        engine_version="1.0.0",
        processed_bands=sample_bands,
        geospatial=sample_geospatial,
        temporal=sample_temporal,
        quality_status=SatelliteDataQuality.EXCELLENT,
        atmospheric_correction_applied=True,
        cloud_mask_applied=True,
        cloud_coverage_over_target=1.5,
        provenance={"step": "boa_reflectance_conversion"},
    )


@pytest.fixture
def sample_request(sample_geospatial, sample_temporal):
    return SatelliteDataRequest(
        request_id="sat_req_test_001",
        tenant_id="tenant_icar_01",
        farmer_id="farmer_10842",
        farm_id="farm_karnal_main",
        field_id="field_karnal_01",
        geospatial=sample_geospatial,
        temporal_window=sample_temporal,
        target_constellations=["Sentinel-2"],
        requested_indicators=["NDVI", "NDWI"],
    )


# ============================================================================
# 1. Intelligence Generation & 2. Indicator Organization
# ============================================================================

def test_intelligence_generation_and_indicator_organization(
    sample_indicators, sample_geospatial, sample_temporal
):
    engine = SatelliteAgriculturalIntelligenceEngine()
    intel = engine.generate_agricultural_intelligence(
        indicators=sample_indicators,
        geospatial=sample_geospatial,
        temporal=sample_temporal,
        spatial_summary={"spatial_heterogeneity": "MODERATE", "zonal_statistics": {"zone_1": 0.74}},
        change_summary={"mean_delta": 0.05, "category": "VEGETATION_STABLE"},
    )

    assert intel["intelligence_type"] == "AGRICULTURAL_SATELLITE_OBSERVATION"
    assert "NDVI" in intel["canopy_vigor"]
    assert intel["canopy_vigor"]["NDVI"]["mean"] == 0.76
    assert "NDWI_GAO" in intel["canopy_moisture"]
    assert intel["canopy_moisture"]["NDWI_GAO"]["mean"] == 0.35
    assert intel["spatial_context"]["coverage_area_hectares"] == 12.4
    assert intel["temporal_context"]["pixel_change_summary"]["category"] == "VEGETATION_STABLE"
    assert "non_diagnostic_statement" in intel
    assert "Sarvam-105B" in intel["non_diagnostic_statement"]


# ============================================================================
# 3. Provenance Preservation & 15. Processing Version Preservation
# ============================================================================

def test_provenance_and_processing_version_preservation(
    sample_request, sample_processed_data, sample_indicators
):
    builder = SatelliteEvidenceBuilder()
    evidence = builder.build_evidence(
        request=sample_request,
        processed_data=sample_processed_data,
        indicators=sample_indicators,
    )

    assert evidence.contract_name == "EarthMindSatelliteEvidence"
    assert evidence.schema_version == "1.0"
    assert "evidence_hash" in evidence.provenance
    assert len(evidence.provenance["evidence_hash"]) == 64  # SHA-256
    assert evidence.provenance["pipeline"] == "standard_satellite_pipeline_v1"
    assert evidence.provenance["engine_version"] == "1.0.0"


# ============================================================================
# 4. Spatial & Temporal Compatibility & 5. Multi-Source Fusion
# ============================================================================

def test_spatial_temporal_compatibility_and_fusion(
    sample_processed_data, sample_indicators
):
    fusion_engine = SatelliteMultiSourceFusionEngine(max_temporal_delta_days=5.0, max_spatial_delta_deg=0.2)

    # Observation 2: Compatible (S2A 2 days earlier, same field)
    obs2 = copy.deepcopy(sample_processed_data)
    obs2.dataset_id = "S2A_MSIL2A_20250326"
    obs2.temporal.acquisition_date = "2025-03-26T05:16:49Z"

    s_ok, dist = fusion_engine.evaluate_spatial_compatibility(sample_processed_data, obs2)
    assert s_ok is True
    assert dist == 0.0

    t_ok, delta = fusion_engine.evaluate_temporal_compatibility(sample_processed_data, obs2)
    assert t_ok is True
    assert delta == 2.0

    fused = fusion_engine.fuse_multi_source_intelligence(
        observations=[sample_processed_data, obs2],
        indicators=sample_indicators,
    )
    assert fused["fusion_status"] == "FUSED"
    assert len(fused["constellations_included"]) == 2
    assert fused["indicators_fused_count"] == 2


# ============================================================================
# 6. Incompatible Dataset Rejection
# ============================================================================

def test_incompatible_dataset_rejection(sample_processed_data):
    fusion_engine = SatelliteMultiSourceFusionEngine(max_temporal_delta_days=3.0, max_spatial_delta_deg=0.1)

    # Far away observation (e.g. 5 degrees away)
    obs_far = copy.deepcopy(sample_processed_data)
    obs_far.dataset_id = "S2B_FAR_AWAY"
    obs_far.geospatial.latitude = 35.0
    obs_far.temporal.acquisition_date = "2025-03-10T05:16:49Z"  # 18 days delta

    fused = fusion_engine.fuse_constellations([sample_processed_data, obs_far])
    warnings = fused["warnings"]
    assert any("spatial centroid differs" in w for w in warnings)
    assert any("temporal delta" in w for w in warnings)


# ============================================================================
# 7. Conflicting Observation Detection
# ============================================================================

def test_conflicting_observation_detection(sample_indicators):
    fusion_engine = SatelliteMultiSourceFusionEngine()

    # Conflicting NDVI: duplicate indicator with divergent mean (0.76 vs 0.25 -> diff=0.51)
    ind_conflict = copy.deepcopy(sample_indicators[0])
    ind_conflict.source_dataset_id = "S2A_MSIL2A_20250326"
    ind_conflict.result_statistics = {"mean": 0.25, "min": 0.10, "max": 0.40}

    conflicts = fusion_engine.detect_indicator_conflicts(
        indicators=[sample_indicators[0], ind_conflict],
        divergence_threshold=0.30,
    )
    assert len(conflicts) == 1
    assert "Significant divergence in 'NDVI'" in conflicts[0]


# ============================================================================
# 8. Missing Evidence Handling
# ============================================================================

def test_missing_evidence_handling(sample_processed_data):
    fusion_engine = SatelliteMultiSourceFusionEngine()
    # Optical only, missing SAR and Thermal
    fused = fusion_engine.fuse_multi_source_intelligence(
        observations=[sample_processed_data],
        indicators=[],
    )
    missing = fused["missing_information"]
    assert any("SAR/Radar" in m for m in missing)
    assert any("Thermal infrared" in m for m in missing)


# ============================================================================
# 9. Measurement Uncertainty & 10. Qualitative Uncertainty Reporting
# ============================================================================

def test_measurement_uncertainty_and_qualitative_reporting(
    sample_geospatial, sample_temporal
):
    assessor = SatelliteUncertaintyAssessor()

    # High quality evaluation
    u_high = assessor.assess_comprehensive_uncertainty(
        quality_status=SatelliteDataQuality.EXCELLENT,
        geospatial=sample_geospatial,
        temporal=sample_temporal,
        cloud_cover_target=2.0,
        is_atmospheric_corrected=True,
        revisit_age_days=3.0,
        bands_count=4,
        indicators_count=2,
    )
    assert u_high.overall_confidence >= 0.85
    assert assessor.determine_confidence_level(u_high.overall_confidence) == SatelliteConfidenceLevel.HIGH

    # Cloud obscured and uncalibrated evaluation
    u_degraded = assessor.assess_comprehensive_uncertainty(
        quality_status=SatelliteDataQuality.CLOUD_OBSCURED,
        geospatial=sample_geospatial,
        temporal=sample_temporal,
        cloud_cover_target=65.0,
        is_atmospheric_corrected=False,
        revisit_age_days=25.0,
        bands_count=4,
        indicators_count=2,
    )
    assert u_degraded.overall_confidence < 0.60
    assert any("obscured by cloud" in s for s in u_degraded.uncertainty_sources)
    assert any("Atmospheric correction unapplied" in s for s in u_degraded.uncertainty_sources)


# ============================================================================
# 11. Invalid Confidence Rejection
# ============================================================================

def test_invalid_confidence_rejection(
    sample_request, sample_processed_data, sample_indicators
):
    builder = SatelliteEvidenceBuilder()
    validator = SatelliteEvidenceValidator()

    evidence = builder.build_evidence(
        request=sample_request,
        processed_data=sample_processed_data,
        indicators=sample_indicators,
    )

    # Artificially inject contradictory confidence: INVALID quality but high confidence (0.95)
    evidence.quality.overall_quality = SatelliteDataQuality.INVALID
    evidence.uncertainty.overall_confidence = 0.95

    val_res = validator.evaluate(evidence)
    assert val_res.is_valid is False
    assert any("high overall confidence despite INVALID" in err for err in val_res.errors)


# ============================================================================
# 12. Insufficient Evidence Handling
# ============================================================================

def test_insufficient_evidence_handling():
    assessor = SatelliteUncertaintyAssessor()
    res = assessor.assess_uncertainty(
        quality_status=SatelliteDataQuality.INVALID,
        cloud_cover_target=95.0,
        is_calibrated=False,
        revisit_age_days=60.0,
    )
    assert res["overall_confidence"] < 0.30
    assert res["confidence_level"] == SatelliteConfidenceLevel.INSUFFICIENT_EVIDENCE.value


# ============================================================================
# 13. Output Schema Validation & 14. Unit Validation
# ============================================================================

def test_output_schema_and_unit_validation(
    sample_request, sample_processed_data, sample_indicators
):
    builder = SatelliteEvidenceBuilder()
    validator = SatelliteEvidenceValidator()

    evidence = builder.build_evidence(
        request=sample_request,
        processed_data=sample_processed_data,
        indicators=sample_indicators,
    )

    # Valid schema evaluation
    val_res = validator.evaluate(evidence)
    assert val_res.is_valid is True
    assert val_res.provenance_verified is True

    # Check units
    for ind in evidence.indicators:
        assert ind.unit == "unitless_ratio"

    # Invert contract name
    invalid_evidence = copy.deepcopy(evidence)
    invalid_evidence.contract_name = "WrongContract"
    val_res2 = validator.evaluate(invalid_evidence)
    assert val_res2.is_valid is False
    assert any("Invalid contract_name" in err for err in val_res2.errors)


# ============================================================================
# 16. Storage References
# ============================================================================

def test_storage_references(sample_processed_data):
    for b_name, b_obj in sample_processed_data.processed_bands.items():
        assert b_obj.band_raster_ref is not None
        assert b_obj.band_raster_ref.startswith("sat_storage://")


# ============================================================================
# 17. Tenant Isolation & Governance Gate
# ============================================================================

def test_tenant_isolation_and_governance(
    sample_request, sample_processed_data, sample_indicators
):
    builder = SatelliteEvidenceBuilder()
    gate = SatelliteGovernanceGate()

    evidence = builder.build_evidence(
        request=sample_request,
        processed_data=sample_processed_data,
        indicators=sample_indicators,
    )

    # Authorized tenant
    assert gate.enforce_governance(evidence, tenant_id="tenant_icar_01") is True

    # Unauthorized tenant
    assert gate.enforce_governance(evidence, tenant_id="tenant_rogue_02") is False

    # Check anti-promotion: verify auto-promotion to memory/KB is blocked
    evidence_leak = copy.deepcopy(evidence)
    evidence_leak.provenance["auto_promote_to_kb"] = True
    assert gate.enforce_governance(evidence_leak, tenant_id="tenant_icar_01") is False


# ============================================================================
# 18. Error Handling & Validation Or Raise
# ============================================================================

def test_evidence_validator_validate_or_raise(
    sample_request, sample_processed_data, sample_indicators
):
    builder = SatelliteEvidenceBuilder()
    validator = SatelliteEvidenceValidator()

    evidence = builder.build_evidence(
        request=sample_request,
        processed_data=sample_processed_data,
        indicators=sample_indicators,
    )

    # Should succeed without error
    res = validator.validate_or_raise(evidence)
    assert res.is_valid is True

    # Corrupt evidence (missing dataset_id)
    corrupt = copy.deepcopy(evidence)
    corrupt.source.dataset_id = ""

    with pytest.raises(EvidenceValidationFailedError):
        validator.validate_or_raise(corrupt)


# ============================================================================
# 19. SatelliteService & SatelliteModule Dispatch (D1-D5 Regression Compatibility)
# ============================================================================

def test_service_and_module_d6_workflow_dispatch(
    sample_request, sample_processed_data, sample_indicators
):
    service = SatelliteService()
    module = SatelliteModule(service=service)
    module.initialize()

    # 1. Uncertainty assessment via module
    req_unc = ApplicationRequest(
        request_id="app_req_unc_01",
        source="test_client",
        operation="assess_uncertainty",
        payload={
            "quality_status": "GOOD",
            "cloud_cover_target": 5.0,
            "is_calibrated": True,
            "revisit_age_days": 4.0,
        },
    )
    resp_unc = module.handle(req_unc)
    assert resp_unc.status == "SUCCESS"
    assert resp_unc.response["confidence_level"] == "HIGH"

    # 2. Extract agronomic features via module
    req_intel = ApplicationRequest(
        request_id="app_req_intel_01",
        source="test_client",
        operation="extract_agronomic_features",
        payload={"indicators": [ind.model_dump() for ind in sample_indicators]},
    )
    resp_intel = module.handle(req_intel)
    assert resp_intel.status == "SUCCESS"
    assert "canopy_vigor_observations" in resp_intel.response

    # 3. Build evidence via module
    req_build = ApplicationRequest(
        request_id="app_req_build_01",
        source="test_client",
        operation="build_evidence",
        payload={
            "request": sample_request.model_dump(),
            "processed_data": sample_processed_data.model_dump(),
            "indicators": [ind.model_dump() for ind in sample_indicators],
        },
    )
    resp_build = module.handle(req_build)
    assert resp_build.status == "SUCCESS"
    assert resp_build.response["contract_name"] == "EarthMindSatelliteEvidence"

    # 4. Validate evidence via module
    req_val = ApplicationRequest(
        request_id="app_req_val_01",
        source="test_client",
        operation="validate_evidence",
        payload={"evidence": resp_build.response},
    )
    resp_val = module.handle(req_val)
    assert resp_val.status == "SUCCESS"
    assert resp_val.response["is_valid"] is True

    module.shutdown()
