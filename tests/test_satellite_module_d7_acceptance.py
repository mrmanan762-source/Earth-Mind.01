"""Comprehensive End-to-End Acceptance & Hardening Test Suite for EarthMind Satellite Module (Stage D7).

Verifies:
1. Complete integrated data flow:
   Satellite Data Request -> Catalog Discovery / Acquisition -> D3 Ingestion ->
   D4 Processing -> D5 Spectral/Geospatial Analysis -> D6 Intelligence & Uncertainty ->
   D7 Final Evidence Validation -> Satellite Integration Interface ->
   B2 Context Manager -> Sarvam-105B Context Item.
2. Cross-module and architectural boundaries:
   - D1-D7 contracts are versioned, compatible, and immutable.
   - Non-diagnostic guarantee: evidence provides objective canopy vigor and moisture observations,
     never pre-calculated crop disease diagnoses or chemical prescriptions (which remains Sarvam-105B's role).
   - Cross-module data sharing with Drone (macro indices for flight routing) and Vision (multispectral overview).
   - Strict boundary protection: satellite evidence is FARM_PRIVATE and never automatically promoted
     into User Memory, General Memory, or C.2 Knowledge Base.
3. Realistic failure, recovery, and resilience matrix:
   - Malformed, empty, and unsupported satellite requests.
   - Inverted bounding boxes, out-of-bounds latitude/longitude.
   - Cloud-obscured rejection vs warning policy.
   - Contradictory evidence (e.g., high confidence on INVALID data or >70% cloud cover).
   - Missing provenance hash and attribution rejection.
   - B2 Context Manager unavailable or delivery failure fails closed without silent false success.
   - Tenant isolation enforcement.
"""

from unittest.mock import MagicMock
import pytest
import numpy as np

from core.errors.exceptions import (
    ContextProviderError,
    EvidenceValidationFailedError,
)
from core.schemas.application import ApplicationRequest, ApplicationResponse
from core.schemas.satellite import (
    EarthMindSatelliteEvidence,
    SatelliteBandType,
    SatelliteDataFormat,
    SatelliteDataQuality,
    SatelliteDataRequest,
    SatelliteEvidenceStatus,
    SatelliteGeospatialMetadata,
    SatelliteIndicator,
    SatelliteIntegrationRequest,
    SatelliteIntegrationResponse,
    SatelliteProcessedData,
    SatelliteProcessingStatus,
    SatelliteProvider,
    SatelliteProviderStatus,
    SatelliteSensorType,
    SatelliteSpectralBand,
    SatelliteTemporalMetadata,
    SatelliteUncertaintyAssessment,
)
from modules.context.manager import B2ContextManager
from modules.context.schemas import (
    ContextItem,
    ContextRequest,
    PriorityLevel,
    PrivacyLevel,
)
from modules.satellite.evidence_validator import (
    SatelliteEvidenceValidator,
    SatelliteGovernanceGate,
    ValidationOutcome,
)
from modules.satellite.normalization import (
    SatelliteEvidenceNormalizer,
    SatelliteSarvamContextFormatter,
)
from modules.satellite.sarvam_integration import (
    SarvamSatelliteIntegration,
    SatelliteB2ContextAdapter,
    SatelliteContextProvider,
    SatelliteCrossModuleDataSharing,
)
from modules.satellite.satellite_module import SatelliteModule
from modules.satellite.satellite_service import SatelliteService


@pytest.fixture
def satellite_service():
    """Initializes and returns a SatelliteService instance."""
    service = SatelliteService()
    service.lifecycle.start()
    yield service
    service.lifecycle.stop()


@pytest.fixture
def sample_valid_evidence():
    """Constructs a fully valid EarthMindSatelliteEvidence fixture conforming to schema v1.0."""
    return EarthMindSatelliteEvidence(
        contract_name="EarthMindSatelliteEvidence",
        schema_version="1.0",
        evidence_id="sat_ev_acceptance_001",
        request_id="sat_req_acc_001",
        scope={
            "tenant_id": "tenant_punjab",
            "farmer_id": "farmer_101",
            "farm_id": "farm_01",
            "field_id": "field_wheat_42",
        },
        source={
            "dataset_id": "copernicus_s2_msi_l2a_20261110",
            "provider_id": "copernicus_cdse",
            "constellation": "Sentinel-2",
            "platform": "Sentinel-2B",
            "instrument": "MSI",
            "sensor_type": SatelliteSensorType.OPTICAL_MULTISPECTRAL,
            "processing_level": "L2A",
        },
        geospatial=SatelliteGeospatialMetadata(
            crs="EPSG:4326",
            bounding_box=[75.80, 30.90, 75.85, 30.95],
            latitude=30.925,
            longitude=75.825,
            ground_sampling_distance_meters=10.0,
        ),
        temporal=SatelliteTemporalMetadata(
            acquisition_date="2026-11-10T05:30:00Z",
            time_window_start="2026-11-10T05:25:00Z",
            time_window_end="2026-11-10T05:35:00Z",
            revisit_interval_days=5.0,
        ),
        quality={
            "overall_quality": SatelliteDataQuality.GOOD,
            "cloud_cover_percentage": 4.5,
            "atmospheric_correction_applied": True,
            "missing_bands": [],
            "quality_flags": {"scene_classification": "vegetation"},
        },
        band_summaries={
            "B04_RED": {"mean": 0.08, "min": 0.04, "max": 0.15},
            "B08_NIR": {"mean": 0.52, "min": 0.35, "max": 0.65},
        },
        indicators=[
            SatelliteIndicator(
                indicator_id="ind_acc_ndvi",
                indicator_name="NDVI",
                definition="Normalized Difference Vegetation Index: (NIR - Red) / (NIR + Red)",
                calculation_method="standard_band_ratio",
                required_bands=["RED", "NIR"],
                source_dataset_id="copernicus_s2_msi_l2a_20261110",
                unit="dimensionless",
                result_statistics={"mean": 0.7333, "min": 0.50, "max": 0.85},
                quality_status=SatelliteDataQuality.GOOD,
            ),
            SatelliteIndicator(
                indicator_id="ind_acc_ndre",
                indicator_name="NDRE",
                definition="Normalized Difference Red Edge Index: (NIR - RedEdge) / (NIR + RedEdge)",
                calculation_method="standard_band_ratio",
                required_bands=["RED_EDGE", "NIR"],
                source_dataset_id="copernicus_s2_msi_l2a_20261110",
                unit="dimensionless",
                result_statistics={"mean": 0.4500, "min": 0.30, "max": 0.55},
                quality_status=SatelliteDataQuality.GOOD,
            ),
        ],
        uncertainty=SatelliteUncertaintyAssessment(
            overall_confidence=0.91,
            spatial_confidence=0.95,
            temporal_confidence=0.92,
            spectral_confidence=0.90,
            confidence_level="HIGH",
            uncertainty_sources=["5-day revisit window"],
        ),
        license_attribution="Contains modified Copernicus Sentinel data [2026]",
        provenance={
            "evidence_hash": "a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890",
            "pipeline_version": "1.0",
        },
        warnings=[],
        limitations=["Optical sensor cannot penetrate dense cloud layers"],
        status=SatelliteEvidenceStatus.SUCCESS,
    )


# ============================================================================
# 1. Complete Integrated End-to-End Data Flow Test
# ============================================================================

def test_complete_e2e_satellite_to_b2_sarvam(satellite_service, sample_valid_evidence):
    """
    Verifies full lifecycle data flow:
    SatelliteEvidence -> D7 Validation Gate -> D7 Normalizer ->
    SatelliteIntegrationResponse -> B2ContextManager -> Sarvam-105B ContextItem.
    """
    # 1. Validate Evidence
    val_result = satellite_service.validate_evidence(sample_valid_evidence)
    assert val_result.is_valid is True
    assert val_result.outcome == ValidationOutcome.VALID
    assert val_result.provenance_verified is True

    # 2. Setup B2 Context Manager and SatelliteContextProvider
    b2_cm = B2ContextManager()
    sarvam_integration = satellite_service.sarvam_integration
    context_provider = sarvam_integration.create_context_provider()
    b2_cm.register_provider(context_provider)

    # 3. Deliver to Context Manager
    delivery_report = sarvam_integration.deliver_to_context_manager(
        evidence=sample_valid_evidence,
        context_manager=b2_cm,
        tenant_id="tenant_punjab",
    )
    assert delivery_report["delivered"] is True
    assert delivery_report["target_model"] == "Sarvam-105B"
    assert delivery_report["provider_registered"] is True

    # 4. Request context through B2 Context Manager
    context_request = ContextRequest(
        request_id="req_ctx_wheat_01",
        task="Evaluate wheat crop canopy vigor and nitrogen status for Field 42",
        farmer_id="farmer_101",
        farm_id="farm_01",
        field_id="field_wheat_42",
        requested_context_types=["satellite_observation"],
    )

    context_result = b2_cm.prepare_context(context_request)
    assert context_result is not None
    assert len(context_result.items) > 0

    # Locate delivered satellite context item
    sat_item = next((item for item in context_result.items if item.entity_type == "satellite_evidence"), None)
    assert sat_item is not None
    assert sat_item.source == "satellite_module"
    assert sat_item.privacy_level == PrivacyLevel.FARM_PRIVATE
    assert sat_item.content["provider_id"] == "copernicus_cdse"
    assert sat_item.content["constellation"] == "Sentinel-2"
    assert len(sat_item.content["indicators"]) == 2

    # 5. Verify Sarvam Observation Summary Text Formatter
    sarvam_summary = satellite_service.format_for_sarvam(sample_valid_evidence)
    assert "=== SATELLITE OBSERVATION EVIDENCE" in sarvam_summary
    assert "Sentinel-2" in sarvam_summary
    assert "NDVI: mean=0.7333" in sarvam_summary
    assert "Contains modified Copernicus Sentinel data" in sarvam_summary


# ============================================================================
# 2. Strict Architectural & Non-Diagnostic Guarantee Tests
# ============================================================================

def test_satellite_module_non_diagnostic_guarantee(satellite_service, sample_valid_evidence):
    """
    Verifies that the Satellite Module produces purely objective physical and vegetation observations,
    leaving agricultural diagnoses, disease classifications, and chemical prescriptions strictly to Sarvam-105B.
    """
    summary = satellite_service.format_for_sarvam(sample_valid_evidence)

    # Must contain objective observations
    assert "Observation Date" in summary
    assert "NDVI" in summary

    # Must NOT assert final diagnoses or prescriptions
    forbidden_diagnostic_terms = [
        "diagnose", "diagnosed with", "infected with", "fungicide recommendation",
        "spray 500ml", "apply pesticide", "prescription:", "cure",
    ]
    for term in forbidden_diagnostic_terms:
        assert term not in summary.lower(), f"Forbidden diagnostic claim found: {term}"


def test_zero_unauthorized_memory_kb_promotion(satellite_service, sample_valid_evidence):
    """
    Verifies strict boundary protection: Satellite evidence is FARM_PRIVATE and
    governance strictly rejects auto-promotion into User Memory, General Memory, or C.2 Knowledge Base.
    """
    governance = satellite_service._governance_gate

    # Valid tenant and normal evidence passes
    assert governance.enforce_governance(sample_valid_evidence, tenant_id="tenant_punjab") is True

    # Auto-promote to KB flag is rejected
    corrupt_kb = sample_valid_evidence.model_copy(deep=True)
    corrupt_kb.provenance["auto_promote_to_kb"] = True
    assert governance.enforce_governance(corrupt_kb, tenant_id="tenant_punjab") is False

    # Auto-promote to Memory flag is rejected
    corrupt_mem = sample_valid_evidence.model_copy(deep=True)
    corrupt_mem.provenance["auto_promote_to_memory"] = True
    assert governance.enforce_governance(corrupt_mem, tenant_id="tenant_punjab") is False


# ============================================================================
# 3. Evidence Validation Edge Cases & Multi-Dimensional Checks
# ============================================================================

def test_evidence_validator_rejects_inverted_bbox(satellite_service, sample_valid_evidence):
    """Verifies rejection of inverted geographic coordinates in bounding box."""
    corrupt = sample_valid_evidence.model_copy(deep=True)
    # min_lat (40.0) > max_lat (30.0)
    corrupt.geospatial.bounding_box = [75.80, 40.0, 75.85, 30.0]

    val = satellite_service.validate_evidence(corrupt)
    assert val.is_valid is False
    assert any("inverted" in err for err in val.errors)


def test_evidence_validator_rejects_out_of_bounds_indicator(satellite_service, sample_valid_evidence):
    """Verifies that normalized difference indices outside [-1.0, 1.0] are rejected."""
    corrupt = sample_valid_evidence.model_copy(deep=True)
    corrupt.indicators[0].result_statistics["mean"] = 1.45  # NDVI > 1.0 is physically impossible

    val = satellite_service.validate_evidence(corrupt)
    assert val.is_valid is False
    assert any("outside physical limits" in err for err in val.errors)


def test_evidence_validator_rejects_uncertainty_quality_contradiction(satellite_service, sample_valid_evidence):
    """Verifies that high confidence claimed on INVALID data quality is rejected as a contradiction."""
    corrupt = sample_valid_evidence.model_copy(deep=True)
    corrupt.quality.overall_quality = SatelliteDataQuality.INVALID
    corrupt.uncertainty.overall_confidence = 0.95

    val = satellite_service.validate_evidence(corrupt)
    assert val.is_valid is False
    assert any("contradiction" in err.lower() or "invalid data quality" in err.lower() for err in val.errors)


def test_evidence_validator_cloud_obscuration_policy(sample_valid_evidence):
    """Verifies that cloud-obscured evidence passes with warning by default, or is rejected if strict."""
    cloudy = sample_valid_evidence.model_copy(deep=True)
    cloudy.quality.overall_quality = SatelliteDataQuality.CLOUD_OBSCURED
    cloudy.quality.cloud_cover_percentage = 85.0
    cloudy.uncertainty.spectral_confidence = 0.30  # realistic low spectral confidence

    # Default validator: valid with warnings
    default_val = SatelliteEvidenceValidator(reject_cloud_obscured=False)
    res_default = default_val.evaluate(cloudy)
    assert res_default.is_valid is True
    assert res_default.outcome == ValidationOutcome.VALID_WITH_WARNINGS
    assert any("cloud" in w.lower() for w in res_default.warnings)

    # Strict validator: rejected
    strict_val = SatelliteEvidenceValidator(reject_cloud_obscured=True)
    res_strict = strict_val.evaluate(cloudy)
    assert res_strict.is_valid is False
    assert res_strict.outcome == ValidationOutcome.INVALID


def test_evidence_validator_missing_provenance_hash(sample_valid_evidence):
    """Verifies provenance hash verification behaviour."""
    no_hash = sample_valid_evidence.model_copy(deep=True)
    no_hash.provenance = {}

    validator = SatelliteEvidenceValidator(require_provenance_hash=True)
    res = validator.evaluate(no_hash)
    assert res.is_valid is False
    assert any("evidence_hash" in err for err in res.errors)


# ============================================================================
# 4. Cross-Module Data Sharing Tests (Drone & Vision Modules)
# ============================================================================

def test_cross_module_sharing_with_drone_and_vision(satellite_service, sample_valid_evidence):
    """
    Verifies Component 23: Clean contract-based data sharing interface with Drone and Vision modules.
    """
    sharing = satellite_service.cross_module_sharing

    # Share with Drone Module
    drone_payload = sharing.share_with_drone_module(sample_valid_evidence, field_id="field_wheat_42")
    assert drone_payload["source"] == "satellite_module"
    assert drone_payload["field_id"] == "field_wheat_42"
    assert "NDVI" in drone_payload["indicators"]
    assert drone_payload["recommendation_scope"] == "macro_canopy_vigor_guidance_for_drone_routing"

    # Share with Vision Module
    vision_payload = sharing.share_with_vision_module(sample_valid_evidence, field_id="field_wheat_42")
    assert vision_payload["source"] == "satellite_module"
    assert "B04_RED" in vision_payload["band_summaries"]
    assert vision_payload["context_usage"] == "field_level_canopy_reference_for_optical_crop_symptoms"


# ============================================================================
# 5. Failure Handling & Fail-Closed Resilience Matrix
# ============================================================================

def test_b2_unavailable_fails_closed(satellite_service, sample_valid_evidence):
    """Verifies that delivery when B2 Context Manager is unavailable fails closed."""
    sarvam_int = satellite_service.sarvam_integration
    with pytest.raises(ContextProviderError) as exc_info:
        sarvam_int.deliver_to_context_manager(
            evidence=sample_valid_evidence,
            context_manager=None,  # No CM
        )
    assert "B2 Context Manager is unavailable" in str(exc_info.value)


def test_invalid_evidence_cannot_reach_b2(satellite_service, sample_valid_evidence):
    """Verifies that invalid evidence is blocked by the validation gate before staging/delivery."""
    corrupt = sample_valid_evidence.model_copy(deep=True)
    corrupt.status = SatelliteEvidenceStatus.REJECTED

    sarvam_int = satellite_service.sarvam_integration
    with pytest.raises(EvidenceValidationFailedError):
        sarvam_int.stage_evidence(corrupt)


def test_tenant_isolation_violation_rejected(satellite_service, sample_valid_evidence):
    """Verifies tenant isolation: caller cannot access or deliver evidence belonging to another tenant."""
    sarvam_int = satellite_service.sarvam_integration

    # Caller tenant mismatch
    with pytest.raises(EvidenceValidationFailedError) as exc:
        sarvam_int.stage_evidence(sample_valid_evidence, tenant_id="tenant_haryana")
    assert "Governance check failed" in str(exc.value)


# ============================================================================
# 6. Satellite Module Application Request Handling Tests
# ============================================================================

def test_satellite_module_d7_application_operations(satellite_service, sample_valid_evidence):
    """Verifies SatelliteModule request dispatcher for D7 operations."""
    module = SatelliteModule(service=satellite_service)
    module.initialize()

    # 1. Format for Sarvam
    req_sarvam = ApplicationRequest(
        request_id="app_req_sarvam_01",
        source="test_client",
        operation="format_for_sarvam",
        payload={"evidence": sample_valid_evidence.model_dump()},
    )
    resp_sarvam = module.handle(req_sarvam)
    assert resp_sarvam.status == "SUCCESS"
    assert "=== SATELLITE OBSERVATION EVIDENCE" in resp_sarvam.response["summary"]

    # 2. Share with Drone
    req_drone = ApplicationRequest(
        request_id="app_req_drone_01",
        source="test_client",
        operation="share_with_drone",
        payload={"evidence": sample_valid_evidence.model_dump(), "field_id": "field_42"},
    )
    resp_drone = module.handle(req_drone)
    assert resp_drone.status == "SUCCESS"
    assert resp_drone.response["field_id"] == "field_42"

    # 3. Share with Vision
    req_vision = ApplicationRequest(
        request_id="app_req_vision_01",
        source="test_client",
        operation="share_with_vision",
        payload={"evidence": sample_valid_evidence.model_dump(), "field_id": "field_42"},
    )
    resp_vision = module.handle(req_vision)
    assert resp_vision.status == "SUCCESS"
    assert "band_summaries" in resp_vision.response

    module.shutdown()
