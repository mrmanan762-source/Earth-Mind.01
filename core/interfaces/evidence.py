"""Protocol interface for EarthMind Stage R11 Evidence Builder."""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.schemas.evidence import EvidenceBuildRequest, EvidenceBuildResponse, EvidencePackage


@runtime_checkable
class IEvidenceBuilderEngine(Protocol):
    """
    Protocol interface for R11 Evidence Builder Engine.
    Constructs a traceable, normalized Evidence Package from upstream retrieval outputs (R8/R10).
    """

    def build_evidence(self, request: "EvidenceBuildRequest") -> "EvidenceBuildResponse":
        """
        Build an EvidencePackage from R8 reranking response and/or R10 web search response.

        Args:
            request: EvidenceBuildRequest containing query, R8 response, and/or R10 response.

        Returns:
            EvidenceBuildResponse containing the constructed EvidencePackage.
        """
        ...
