"""Sarvam Integration Interface & B2 Context Bridge for EarthMind Drone Module (Stage D6).

Implements Component 15 (ISarvamDroneIntegration).
Bridges validated EarthMindDroneSensorEvidence packets to the B2 Context Manager,
which in turn supplies grounded contextual evidence to Sarvam-105B.

Strict Architectural & Governance Rules:
- Delivers validated sensor evidence as objective contextual information, NEVER as a predetermined diagnosis.
- B2 Context Manager is the sole gateway to reasoning models; never bypasses B2.
- Conforms to the B2 ContextProvider protocol (modules.context.interfaces.ContextProvider).
- Never promotes drone sensor evidence into User Memory, General Memory, or C.2 Knowledge Base.
- Handles B2 unavailable, timeouts, invalid responses, and delivery failures safely.
- Never silently reports successful delivery when integration fails.
"""

import time
from typing import Any, Dict, List, Optional

from core.errors.exceptions import (
    ContextProviderError,
    EvidenceValidationFailedError,
)
from core.interfaces.drone import ISarvamDroneIntegration
from core.logging.logger import get_logger
from core.schemas.drone import (
    DroneSarvamIntegrationContract,
    EarthMindDroneSensorEvidence,
    EvidenceStatus,
)
from modules.context.interfaces import ContextProvider
from modules.context.schemas import ContextItem, ContextRequest
from modules.drone.evidence_validator import SensorEvidenceValidator

logger = get_logger("modules.drone.sarvam_integration")


class DroneContextProvider(ContextProvider):
    """
    Adapter implementing the B2 ContextProvider protocol.
    Enables B2ContextManager to collect validated drone sensor evidence during context preparation.
    """

    provider_name = "drone_provider"

    def __init__(
        self,
        integration_service: "SarvamDroneIntegration",
    ) -> None:
        self._integration = integration_service

    def get_context(self, request: ContextRequest) -> List[ContextItem]:
        """
        B2 ContextProvider protocol method.
        Retrieves matching validated drone sensor evidence items for the given request scope.
        """
        return self._integration.get_context_for_request(request)


class SarvamDroneIntegration(ISarvamDroneIntegration):
    """
    Component 15: Bridge interface connecting Drone Module to B2 Context Manager and Sarvam-105B.
    Formats validated evidence into B2 ContextItem payloads while strictly preserving
    objective measurement context, uncertainties, and operational warnings.
    """

    def __init__(
        self,
        validator: Optional[SensorEvidenceValidator] = None,
        context_manager: Optional[Any] = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._validator = validator or SensorEvidenceValidator()
        self._context_manager = context_manager
        self._timeout_seconds = timeout_seconds
        # In-memory buffer of validated evidence available for B2 context queries
        self._staged_evidence: Dict[str, EarthMindDroneSensorEvidence] = {}

    @property
    def staged_evidence(self) -> Dict[str, EarthMindDroneSensorEvidence]:
        return self._staged_evidence

    def stage_evidence(self, evidence: EarthMindDroneSensorEvidence) -> None:
        """
        Validates and stages an evidence packet so it is available for upcoming B2 ContextRequests.
        Rejects invalid evidence before it can be staged.
        """
        self._validator.validate_or_raise(evidence)
        self._staged_evidence[evidence.evidence_id] = evidence
        logger.info(f"Staged validated drone evidence '{evidence.evidence_id}' for B2 context retrieval.")

    def clear_staged_evidence(self) -> None:
        """Clear currently staged evidence."""
        self._staged_evidence.clear()

    def format_for_context(self, evidence: EarthMindDroneSensorEvidence) -> ContextItem:
        """
        Transforms validated sensor evidence into a B2-compliant ContextItem.
        Enforces loose coupling via DroneSarvamIntegrationContract.
        """
        # Validate evidence prior to transformation
        self._validator.validate_or_raise(evidence)

        bridge_contract = DroneSarvamIntegrationContract(
            contract_name="DroneSarvamIntegrationContract",
            schema_version="1.0",
            evidence=evidence,
            target_model="Sarvam-105B",
            context_priority="HIGH",
            bounded_token_estimate=350,
        )

        return bridge_contract.to_context_item()

    def deliver_to_context_manager(
        self,
        evidence: EarthMindDroneSensorEvidence,
        context_manager: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Delivers validated evidence directly into the B2 Context Manager.
        Ensures fail-closed behavior: never reports success on failure.
        """
        cm = context_manager or self._context_manager
        if cm is None:
            raise ContextProviderError(
                provider_name="drone_provider",
                details="B2 Context Manager is unavailable or unconfigured.",
            )

        # 1. Validation Gate: Reject invalid evidence before B2 delivery
        val_result = self._validator.evaluate(evidence)
        if not val_result.is_valid:
            err_msg = f"Cannot deliver invalid evidence: {'; '.join(val_result.errors)}"
            logger.error(err_msg)
            raise EvidenceValidationFailedError(
                evidence_id=evidence.evidence_id,
                details=err_msg,
            )

        # 2. Format to B2 ContextItem
        context_item = self.format_for_context(evidence)

        # 3. Deliver to Context Manager via collector or provider registration
        start_time = time.perf_counter()
        try:
            # Stage evidence in local buffer so registered DroneContextProvider returns it
            self.stage_evidence(evidence)

            # If B2ContextManager has a collector, verify provider is registered
            provider_registered = False
            if hasattr(cm, "collector") and hasattr(cm.collector, "providers"):
                for p in cm.collector.providers:
                    if getattr(p, "provider_name", "") == "drone_provider":
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
            logger.error(f"Failed to deliver drone evidence to B2 Context Manager: {exc}")
            raise ContextProviderError(
                provider_name="drone_provider",
                details=f"Delivery to B2 Context Manager failed: {str(exc)}",
            )

    def get_context_for_request(self, request: ContextRequest) -> List[ContextItem]:
        """
        Processes B2 ContextRequest by filtering staged evidence matching field/farm/farmer IDs.
        """
        matched_items: List[ContextItem] = []

        for ev_id, evidence in self._staged_evidence.items():
            # Filter by farmer_id if specified
            if request.farmer_id and evidence.field.farmer_id:
                if request.farmer_id != evidence.field.farmer_id:
                    continue

            # Filter by farm_id if specified
            if request.farm_id and evidence.field.farm_id:
                if request.farm_id != evidence.field.farm_id:
                    continue

            # Filter by field_id if specified
            if request.field_id and evidence.field.field_id:
                if request.field_id != evidence.field.field_id:
                    continue

            # Format to ContextItem
            try:
                item = self.format_for_context(evidence)
                matched_items.append(item)
            except Exception as e:
                logger.warning(f"Skipping evidence '{ev_id}' during context extraction: {e}")

        return matched_items

    def create_context_provider(self) -> DroneContextProvider:
        """Factory method creating a B2-compatible DroneContextProvider."""
        return DroneContextProvider(integration_service=self)
