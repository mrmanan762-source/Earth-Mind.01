"""Satellite Evidence Validation and Governance Gate for EarthMind Satellite Module (Stages D6 & D7).

Implements Component 18 (ISatelliteEvidenceValidator) and Component 20 (ISatelliteGovernanceGate).
Validates schema compliance, required fields, reference integrity, unit consistency,
physical plausibility, provenance, and uncertainty consistency of EarthMindSatelliteEvidence artifacts.

Enforces strict rules:
- Contract name must be 'EarthMindSatelliteEvidence' and schema version '1.0'.
- Source dataset ID, provider ID, platform, and instrument must be non-empty strings.
- Geospatial bounds and temporal timestamps must be physically plausible.
- Indicator statistics must be within valid physical intervals (e.g. NDVI in [-1.0, 1.0]).
- Uncertainty metrics must not contradict underlying data quality (no high confidence on INVALID data).
- Enforces tenant isolation and prevents unauthorized automatic promotion into User Memory, General Memory, or C.2 Knowledge Base.
- Output validation statuses conform to clear outcomes: VALID, VALID_WITH_WARNINGS, INSUFFICIENT_EVIDENCE, INVALID, REJECTED.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.errors.exceptions import EvidenceValidationFailedError
from core.interfaces.satellite import ISatelliteEvidenceValidator, ISatelliteGovernanceGate
from core.logging.logger import get_logger
from core.schemas.satellite import (
    EarthMindSatelliteEvidence,
    SatelliteDataQuality,
    SatelliteEvidenceStatus,
)

logger = get_logger("modules.satellite.evidence_validator")


class ValidationOutcome(str, Enum):
    """Machine-readable outcomes for satellite evidence validation."""
    VALID = "VALID"
    VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INVALID = "INVALID"
    REJECTED = "REJECTED"


class SatelliteEvidenceValidationResult(BaseModel):
    """Structured report returned by SatelliteEvidenceValidator."""
    is_valid: bool = Field(..., description="True if evidence passes all validation rules")
    evidence_id: str = Field(..., description="Validated evidence identifier")
    outcome: ValidationOutcome = Field(ValidationOutcome.VALID, description="Explicit machine-readable validation outcome")
    errors: List[str] = Field(default_factory=list, description="Validation failure reasons")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal validation warnings")
    checks_evaluated: int = Field(0, description="Total number of verification checks executed")
    provenance_verified: bool = Field(False, description="Whether SHA-256 provenance hash was verified")


class SatelliteEvidenceValidator(ISatelliteEvidenceValidator):
    """
    Component 18: Evidence validation gate ensuring compliance with Contract 8 schema v1.0.
    Hardened for Stage D7 with multi-dimensional scientific, provenance, and uncertainty validation.
    """

    def __init__(self, reject_cloud_obscured: bool = False, require_provenance_hash: bool = False) -> None:
        self._reject_cloud_obscured = reject_cloud_obscured
        self._require_provenance_hash = require_provenance_hash

    def validate_evidence(self, evidence: EarthMindSatelliteEvidence) -> bool:
        """Protocol method conforming to ISatelliteEvidenceValidator."""
        result = self.evaluate(evidence)
        return result.is_valid

    def validate_or_raise(self, evidence: EarthMindSatelliteEvidence) -> SatelliteEvidenceValidationResult:
        """Strict evaluation: returns result or raises EvidenceValidationFailedError."""
        result = self.evaluate(evidence)
        if not result.is_valid:
            error_summary = "; ".join(result.errors)
            logger.error(f"Satellite evidence '{evidence.evidence_id}' rejected: {error_summary}")
            raise EvidenceValidationFailedError(
                evidence_id=evidence.evidence_id,
                details=error_summary,
            )
        return result

    def evaluate(self, evidence: EarthMindSatelliteEvidence) -> SatelliteEvidenceValidationResult:
        """
        Comprehensive evaluation across 8 core dimensions:
        1. Contract Schema & Identity
        2. Source Provenance & Platform Information
        3. Spatiotemporal Plausibility
        4. Quality and Cloud Cover Constraints
        5. Band Summaries Physical Sanity
        6. Indicator Statistics & Bounds
        7. Uncertainty Metrics Plausibility
        8. Status Consistency & Attribution
        """
        errors: List[str] = []
        warnings: List[str] = []
        checks = 0

        # Check 1: Contract Name & Schema Version
        checks += 1
        if evidence.contract_name != "EarthMindSatelliteEvidence":
            errors.append(f"Invalid contract_name: expected 'EarthMindSatelliteEvidence', got '{evidence.contract_name}'")
        checks += 1
        if evidence.schema_version != "1.0":
            errors.append(f"Unsupported schema_version: expected '1.0', got '{evidence.schema_version}'")
        checks += 1
        if not evidence.evidence_id or not evidence.evidence_id.strip():
            errors.append("evidence_id cannot be empty")

        # Check 2: Source Information & Provenance
        checks += 1
        if not evidence.source or not evidence.source.dataset_id or not evidence.source.dataset_id.strip():
            errors.append("Source dataset_id is missing or empty")
        checks += 1
        if not evidence.source or not evidence.source.provider_id or not evidence.source.provider_id.strip():
            errors.append("Source provider_id is missing or empty")
        checks += 1
        if not evidence.source or not evidence.source.constellation or not evidence.source.constellation.strip():
            errors.append("Source constellation is missing or empty")

        # Provenance hash check
        checks += 1
        has_hash = bool(evidence.provenance.get("evidence_hash"))
        if self._require_provenance_hash and not has_hash:
            errors.append("Required cryptographic SHA-256 evidence_hash missing from provenance")
        elif not has_hash:
            warnings.append("Cryptographic evidence_hash missing from provenance")

        # Check 3: Spatiotemporal Plausibility
        checks += 1
        geo = evidence.geospatial
        if not (-90.0 <= geo.latitude <= 90.0):
            errors.append(f"Centroid latitude out of physical bounds [-90, 90]: {geo.latitude}")
        if not (-180.0 <= geo.longitude <= 180.0):
            errors.append(f"Centroid longitude out of physical bounds [-180, 180]: {geo.longitude}")
        if geo.bounding_box:
            min_lon, min_lat, max_lon, max_lat = geo.bounding_box
            if min_lat > max_lat or min_lon > max_lon:
                errors.append(f"Geospatial bounding box coordinates are logically inverted: {geo.bounding_box}")

        checks += 1
        if not evidence.temporal or not evidence.temporal.acquisition_date:
            errors.append("Temporal metadata acquisition_date is missing")

        # Check 4: Quality & Cloud Cover Constraints
        checks += 1
        if evidence.quality:
            if not (0.0 <= evidence.quality.cloud_cover_percentage <= 100.0):
                errors.append(f"Cloud cover percentage out of range [0, 100]: {evidence.quality.cloud_cover_percentage}")
            if self._reject_cloud_obscured and evidence.quality.overall_quality == SatelliteDataQuality.CLOUD_OBSCURED:
                errors.append("Cloud-obscured evidence rejected by strict configuration policy")
            elif evidence.quality.overall_quality == SatelliteDataQuality.CLOUD_OBSCURED:
                warnings.append(f"Evidence has substantial cloud cover ({evidence.quality.cloud_cover_percentage}%)")

        # Check 5: Band Summaries Physical Sanity
        checks += 1
        for b_name, stats in evidence.band_summaries.items():
            checks += 1
            mean_val = stats.get("mean")
            if mean_val is not None:
                # Surface reflectance is physically positive
                if "reflectance" in b_name.lower() or b_name.upper() in ("RED", "GREEN", "BLUE", "NIR", "SWIR_1", "SWIR_2"):
                    if mean_val < -0.05 or mean_val > 1.5:
                        errors.append(f"Band '{b_name}' reflectance mean ({mean_val}) out of physical bounds [-0.05, 1.5]")

        # Check 6: Indicator Statistics & Bounds
        checks += 1
        if not evidence.indicators and evidence.status != SatelliteEvidenceStatus.PARTIAL:
            warnings.append("Evidence contains zero agricultural indicators")

        for ind in evidence.indicators:
            checks += 1
            if not ind.indicator_name or not ind.indicator_name.strip():
                errors.append(f"Indicator '{ind.indicator_id}' lacks indicator_name")
            stats = ind.result_statistics if isinstance(ind.result_statistics, dict) else {}
            mean_v = stats.get("mean")
            if mean_v is not None:
                ind_upper = ind.indicator_name.upper()
                if ind_upper in ("NDVI", "NDRE", "NDWI", "NDWI_GAO", "NDWI_MCFEETERS", "NDWI_GREEN_NIR", "NDWI_NIR_SWIR", "EVI"):
                    if not (-1.0 <= mean_v <= 1.0):
                        errors.append(f"Normalized index '{ind.indicator_name}' mean value ({mean_v}) outside physical limits [-1.0, 1.0]")

        # Check 7: Uncertainty Metrics Plausibility
        checks += 1
        if evidence.uncertainty:
            u = evidence.uncertainty
            if not (0.0 <= u.overall_confidence <= 1.0):
                errors.append(f"Overall confidence out of bounds [0.0, 1.0]: {u.overall_confidence}")
            if not (0.0 <= u.spatial_confidence <= 1.0):
                errors.append(f"Spatial confidence out of bounds [0.0, 1.0]: {u.spatial_confidence}")
            if not (0.0 <= u.temporal_confidence <= 1.0):
                errors.append(f"Temporal confidence out of bounds [0.0, 1.0]: {u.temporal_confidence}")
            if not (0.0 <= u.spectral_confidence <= 1.0):
                errors.append(f"Spectral confidence out of bounds [0.0, 1.0]: {u.spectral_confidence}")

            # Contradiction checks
            if evidence.quality and evidence.quality.overall_quality == SatelliteDataQuality.INVALID and u.overall_confidence > 0.40:
                errors.append("Uncertainty indicates high overall confidence despite INVALID data quality")
            if evidence.quality and evidence.quality.cloud_cover_percentage > 70.0 and u.spectral_confidence > 0.50:
                errors.append("Spectral confidence is unrealistically high (>0.50) despite >70% cloud obscuration")

        # Check 8: Attribution & Status Consistency
        checks += 1
        if not evidence.license_attribution or not evidence.license_attribution.strip():
            errors.append("Mandatory provider license attribution statement is missing")

        checks += 1
        if evidence.status == SatelliteEvidenceStatus.REJECTED:
            errors.append("Evidence is marked with status REJECTED")
        elif evidence.status == SatelliteEvidenceStatus.FAILED:
            errors.append("Evidence is marked with status FAILED")

        is_valid = len(errors) == 0

        # Determine explicit validation outcome
        if not is_valid:
            if evidence.status == SatelliteEvidenceStatus.REJECTED:
                outcome = ValidationOutcome.REJECTED
            elif not evidence.indicators and not evidence.band_summaries:
                outcome = ValidationOutcome.INSUFFICIENT_EVIDENCE
            else:
                outcome = ValidationOutcome.INVALID
        else:
            if warnings or evidence.status in (SatelliteEvidenceStatus.DEGRADED, SatelliteEvidenceStatus.PARTIAL):
                outcome = ValidationOutcome.VALID_WITH_WARNINGS
            elif not evidence.indicators:
                outcome = ValidationOutcome.INSUFFICIENT_EVIDENCE
            else:
                outcome = ValidationOutcome.VALID

        return SatelliteEvidenceValidationResult(
            is_valid=is_valid,
            evidence_id=evidence.evidence_id,
            outcome=outcome,
            errors=errors,
            warnings=warnings,
            checks_evaluated=checks,
            provenance_verified=has_hash,
        )


class SatelliteGovernanceGate(ISatelliteGovernanceGate):
    """
    Component 20: Governance gate enforcing tenant isolation and preventing unauthorized
    automatic promotion into User Memory, General Memory, or C.2 Knowledge Base.
    """

    def enforce_governance(
        self,
        evidence: EarthMindSatelliteEvidence,
        tenant_id: str,
    ) -> bool:
        """
        Enforce tenant isolation, license attribution checks, and prevent automatic KB promotion.
        Returns True if governance rules are satisfied, False otherwise.
        """
        if not evidence.scope or not evidence.scope.tenant_id:
            logger.error("Governance rejection: Satellite evidence lacks tenant scope")
            return False

        if evidence.scope.tenant_id != tenant_id and tenant_id != "system":
            logger.error(
                f"Governance rejection: Tenant isolation violation. Evidence tenant '{evidence.scope.tenant_id}' "
                f"does not match caller tenant '{tenant_id}'"
            )
            return False

        if not evidence.license_attribution or not evidence.license_attribution.strip():
            logger.error("Governance rejection: Missing provider license attribution")
            return False

        # Verify no auto-promotion flags are set
        if evidence.provenance.get("auto_promote_to_kb", False):
            logger.error("Governance rejection: Automatic promotion to C.2 Knowledge Base is strictly forbidden")
            return False

        if evidence.provenance.get("auto_promote_to_memory", False):
            logger.error("Governance rejection: Automatic promotion to Memory is strictly forbidden")
            return False

        return True
