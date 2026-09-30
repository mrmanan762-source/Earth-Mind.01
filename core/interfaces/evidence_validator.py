"""Protocol interface for EarthMind Stage R12 Evidence Validator."""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.schemas.evidence_validator import EvidenceValidationRequest, EvidenceValidationResponse


@runtime_checkable
class IEvidenceValidatorEngine(Protocol):
    """
    Protocol interface for R12 Evidence Validator Engine.
    Validates an Evidence Package produced by Stage R11 Evidence Builder before B2 Context Manager handoff.
    """

    def validate_evidence_package(self, request: "EvidenceValidationRequest") -> "EvidenceValidationResponse":
        """
        Validate an EvidencePackage for structure, identity, provenance, completeness,
        consistency, ranks/scores, web evidence, and duplicate/conflict detection.

        Args:
            request: EvidenceValidationRequest containing EvidencePackage and runtime policy settings.

        Returns:
            EvidenceValidationResponse containing detailed validation findings and result.
        """
        ...
