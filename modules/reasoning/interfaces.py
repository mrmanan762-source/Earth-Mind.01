from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from modules.reasoning.schemas import (
    EvidenceConflict,
    EvidenceItem,
    EvidenceRelationship,
    ReasoningInput,
    ReasoningResult,
    ReasoningValidationHandoff,
)


@runtime_checkable
class IReasoningCapability(Protocol):
    """Model-agnostic contract for reasoning capability providers in B3.

    B3 depends on this interface rather than direct AI model adapters or Sarvam internals.
    """
    capability_name: str

    def reason(self, input_data: ReasoningInput) -> ReasoningResult:
        """Perform reasoning over provided input and return structured ReasoningResult."""
        ...

    def status(self) -> Dict[str, Any]:
        """Return operational status and capabilities metadata."""
        ...


@runtime_checkable
class IEvidenceManager(Protocol):
    """Contract for evidence processing, relationship analysis, and conflict detection."""

    def prepare_evidence(self, input_data: ReasoningInput) -> List[EvidenceItem]:
        """Extract, parse, and enrich evidence items from input and context."""
        ...

    def identify_relationships(self, evidence_items: List[EvidenceItem]) -> List[EvidenceRelationship]:
        """Detect relationships across provided evidence items."""
        ...

    def detect_conflicts(self, evidence_items: List[EvidenceItem]) -> List[EvidenceConflict]:
        """Detect conflicting evidence items without auto-resolving or discarding them."""
        ...


@runtime_checkable
class IReasoningStrategy(Protocol):
    """Contract for controlled reasoning execution strategy flow."""

    def execute_strategy(self, input_data: ReasoningInput) -> ReasoningResult:
        """Execute 13-step controlled reasoning strategy."""
        ...


@runtime_checkable
class IInspectorHandoff(Protocol):
    """Contract for Inspector validation handoff."""

    def handoff_validation(self, result: ReasoningResult) -> ReasoningValidationHandoff:
        """Submit reasoning result for Inspector validation."""
        ...
