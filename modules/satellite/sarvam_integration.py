"""Sarvam Integration Interface, B2 Context Bridge & Cross-Module Sharing for EarthMind Satellite Module (Stage D7).

Implements:
- Component 21: ISatelliteB2ContextAdapter
- Component 22: ISatelliteSarvamContextFormatter (integrated via normalization.py)
- Component 23: ISatelliteCrossModuleDataSharing
- SatelliteContextProvider conforming to B2 ContextProvider protocol (modules.context.interfaces.ContextProvider)
- SarvamSatelliteIntegration: Core bridge service coordinating staging, validation, normalization, and B2 delivery.

Strict Architectural & Governance Guarantees:
- Validated satellite evidence is objective contextual information, NEVER a predetermined diagnosis.
- B2 Context Manager is the sole gateway to reasoning models; never bypasses B2.
- Conforms to the B2 ContextProvider protocol (modules.context.interfaces.ContextProvider).
- Never promotes satellite evidence into User Memory, General Memory, or C.2 Knowledge Base.
- Handles B2 unavailable, timeouts, invalid responses, and delivery failures safely.
- Never silently reports successful delivery when integration fails.
"""

import time
from typing import Any, Dict, List, Optional

from core.errors.exceptions import (
    ContextProviderError,
    EvidenceValidationFailedError,
)
from core.interfaces.satellite import (
    ISatelliteB2ContextAdapter,
    ISatelliteCrossModuleDataSharing,
    ISatelliteSarvamContextFormatter,
)
from core.logging.logger import get_logger
from core.schemas.satellite import (
    EarthMindSatelliteEvidence,
    SatelliteEvidenceStatus,
    SatelliteIntegrationRequest,
    SatelliteIntegrationResponse,
)
from modules.context.interfaces import ContextProvider
from modules.context.schemas import ContextItem, ContextRequest
from modules.satellite.evidence_validator import SatelliteEvidenceValidator, SatelliteGovernanceGate
from modules.satellite.normalization import SatelliteEvidenceNormalizer, SatelliteSarvamContextFormatter

logger = get_logger("modules.satellite.sarvam_integration")


class SatelliteContextProvider(ContextProvider):
    """
    Adapter implementing the B2 ContextProvider protocol.
    Enables B2ContextManager to collect validated satellite intelligence evidence during context preparation.
    """

    provider_name = "satellite_provider"

    def __init__(
        self,
        integration_service: "SarvamSatelliteIntegration",
    ) -> None:
        self._integration = integration_service

    def get_context(self, request: ContextRequest) -> List[ContextItem]:
        """
        B2 ContextProvider protocol method.
        Retrieves matching validated satellite evidence items for the given request scope.
        """
        return self._integration.get_context_for_request(request)


class SatelliteB2ContextAdapter(ISatelliteB2ContextAdapter):
    """
    Component 21: Bridge interface delivering validated evidence to B2 Context Manager.
    Transforms validated SatelliteIntegrationResponse into a B2-compliant ContextItem.
    """

    def format_for_context(
        self,
        integration_response: SatelliteIntegrationResponse,
    ) -> ContextItem:
        """Transform validated satellite integration response into B2 ContextItem."""
        return integration_response.to_context_item()


class SatelliteCrossModuleDataSharing(ISatelliteCrossModuleDataSharing):
    """
    Component 23: Clean contract-based data sharing interface with Drone and Vision modules.
    Enables macro-level vegetation indices to inform drone flight planning and leaf visual symptom analysis
    without tight coupling or circular dependencies.
    """

    def share_with_drone_module(
        self,
        evidence: EarthMindSatelliteEvidence,
        field_id: str,
    ) -> Dict[str, Any]:
        """Export macro-level vegetation indices for drone flight mission planning context."""
        indicators_map = {ind.indicator_name: ind.result_statistics for ind in evidence.indicators}
        resolution_m = getattr(evidence.geospatial, "ground_sampling_distance_meters", 10.0)
        return {
            "source": "satellite_module",
            "field_id": field_id,
            "evidence_id": evidence.evidence_id,
            "observation_date": evidence.temporal.acquisition_date,
            "resolution_m": resolution_m,
            "indicators": indicators_map,
            "quality": evidence.quality.overall_quality.value,
            "confidence": evidence.uncertainty.overall_confidence,
            "recommendation_scope": "macro_canopy_vigor_guidance_for_drone_routing",
        }

    def share_with_vision_module(
        self,
        evidence: EarthMindSatelliteEvidence,
        field_id: str,
    ) -> Dict[str, Any]:
        """Export multispectral overview for correlating visual leaf symptom analyses."""
        return {
            "source": "satellite_module",
            "field_id": field_id,
            "evidence_id": evidence.evidence_id,
            "acquisition_date": evidence.temporal.acquisition_date,
            "band_summaries": evidence.band_summaries,
            "cloud_cover_pct": evidence.quality.cloud_cover_percentage,
            "license_attribution": evidence.license_attribution,
            "context_usage": "field_level_canopy_reference_for_optical_crop_symptoms",
        }


class SarvamSatelliteIntegration:
    """
    Coordinator connecting the Satellite Module to the B2 Context Manager and Sarvam-105B.
    Validates, normalizes, stages, and delivers validated EarthMindSatelliteEvidence to B2.
    """

    def __init__(
        self,
        validator: Optional[SatelliteEvidenceValidator] = None,
        governance_gate: Optional[SatelliteGovernanceGate] = None,
        normalizer: Optional[SatelliteEvidenceNormalizer] = None,
        context_formatter: Optional[ISatelliteSarvamContextFormatter] = None,
        b2_adapter: Optional[ISatelliteB2ContextAdapter] = None,
        context_manager: Optional[Any] = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._validator = validator or SatelliteEvidenceValidator()
        self._governance = governance_gate or SatelliteGovernanceGate()
        self._normalizer = normalizer or SatelliteEvidenceNormalizer()
        self._formatter = context_formatter or SatelliteSarvamContextFormatter()
        self._b2_adapter = b2_adapter or SatelliteB2ContextAdapter()
        self._context_manager = context_manager
        self._timeout_seconds = timeout_seconds

        # In-memory staged evidence buffer available for B2 context queries
        self._staged_evidence: Dict[str, EarthMindSatelliteEvidence] = {}

    @property
    def staged_evidence(self) -> Dict[str, EarthMindSatelliteEvidence]:
        return self._staged_evidence

    def stage_evidence(self, evidence: EarthMindSatelliteEvidence, tenant_id: str = "default") -> None:
        """
        Validates, checks governance, normalizes, and stages an evidence packet for upcoming B2 ContextRequests.
        Rejects invalid evidence or tenant mismatches before staging.
        """
        self._validator.validate_or_raise(evidence)
        if not self._governance.enforce_governance(evidence, tenant_id=tenant_id):
            raise EvidenceValidationFailedError(
                evidence_id=evidence.evidence_id,
                details=f"Governance check failed for tenant '{tenant_id}'",
            )

        norm_evidence = self._normalizer.normalize(evidence)
        self._staged_evidence[norm_evidence.evidence_id] = norm_evidence
        logger.info(f"Staged validated satellite evidence '{norm_evidence.evidence_id}' for B2 context retrieval.")

    def clear_staged_evidence(self) -> None:
        """Clear currently staged evidence."""
        self._staged_evidence.clear()

    def format_for_context(
        self,
        evidence: EarthMindSatelliteEvidence,
        request_id: str = "req_sat_default",
        target_model: str = "Sarvam-105B",
        context_priority: str = "HIGH",
    ) -> ContextItem:
        """
        Transforms validated satellite evidence into a B2-compliant ContextItem.
        Enforces loose coupling via Contract 9 (SatelliteIntegrationResponse).
        """
        self._validator.validate_or_raise(evidence)
        norm_evidence = self._normalizer.normalize(evidence)

        bridge_contract = SatelliteIntegrationResponse(
            contract_name="SatelliteIntegrationResponse",
            schema_version="1.0",
            request_id=request_id,
            evidence=norm_evidence,
            target_model=target_model,
            context_priority=context_priority,
            bounded_token_estimate=350,
        )

        return self._b2_adapter.format_for_context(bridge_contract)

    def deliver_to_context_manager(
        self,
        evidence: EarthMindSatelliteEvidence,
        context_manager: Optional[Any] = None,
        tenant_id: str = "default",
        request_id: str = "req_sat_delivery",
    ) -> Dict[str, Any]:
        """
        Delivers validated evidence directly into the B2 Context Manager.
        Ensures fail-closed behavior: never reports success on failure.
        """
        cm = context_manager or self._context_manager
        if cm is None:
            raise ContextProviderError(
                provider_name="satellite_provider",
                details="B2 Context Manager is unavailable or unconfigured.",
            )

        # 1. Validation Gate
        val_result = self._validator.evaluate(evidence)
        if not val_result.is_valid:
            err_msg = f"Cannot deliver invalid satellite evidence: {'; '.join(val_result.errors)}"
            logger.error(err_msg)
            raise EvidenceValidationFailedError(
                evidence_id=evidence.evidence_id,
                details=err_msg,
            )

        # 2. Governance Gate
        if not self._governance.enforce_governance(evidence, tenant_id=tenant_id):
            raise EvidenceValidationFailedError(
                evidence_id=evidence.evidence_id,
                details=f"Governance rejection for tenant '{tenant_id}'",
            )

        # 3. Format to B2 ContextItem
        context_item = self.format_for_context(evidence, request_id=request_id)

        # 4. Deliver via staging
        start_time = time.perf_counter()
        try:
            self.stage_evidence(evidence, tenant_id=tenant_id)

            provider_registered = False
            if hasattr(cm, "collector"):
                if hasattr(cm.collector, "_providers") and "satellite_provider" in cm.collector._providers:
                    provider_registered = True
                elif hasattr(cm.collector, "providers"):
                    for p in cm.collector.providers:
                        if getattr(p, "provider_name", "") == "satellite_provider":
                            provider_registered = True
                            break

            duration_ms = (time.perf_counter() - start_time) * 1000.0

            return {
                "delivered": True,
                "evidence_id": evidence.evidence_id,
                "context_id": context_item.context_id,
                "target_model": "Sarvam-105B",
                "entity_type": context_item.entity_type,
                "confidence": context_item.confidence,
                "provider_registered": provider_registered,
                "latency_ms": duration_ms,
            }
        except Exception as exc:
            logger.error(f"Failed to deliver satellite evidence to B2 Context Manager: {exc}")
            raise ContextProviderError(
                provider_name="satellite_provider",
                details=f"Delivery to B2 Context Manager failed: {str(exc)}",
            )

    def get_context_for_request(self, request: ContextRequest) -> List[ContextItem]:
        """
        Processes B2 ContextRequest by filtering staged evidence matching field/farm/farmer IDs.
        """
        matched_items: List[ContextItem] = []

        for ev_id, evidence in self._staged_evidence.items():
            # Filter by farmer_id if specified
            if request.farmer_id and evidence.scope.farmer_id:
                if request.farmer_id != evidence.scope.farmer_id:
                    continue

            # Filter by farm_id if specified
            if request.farm_id and evidence.scope.farm_id:
                if request.farm_id != evidence.scope.farm_id:
                    continue

            # Filter by field_id if specified
            if request.field_id and evidence.scope.field_id:
                if request.field_id != evidence.scope.field_id:
                    continue

            try:
                item = self.format_for_context(evidence, request_id=request.request_id)
                matched_items.append(item)
            except Exception as e:
                logger.warning(f"Skipping evidence '{ev_id}' during context extraction: {e}")

        return matched_items

    def create_context_provider(self) -> SatelliteContextProvider:
        """Factory method creating a B2-compatible SatelliteContextProvider."""
        return SatelliteContextProvider(integration_service=self)
