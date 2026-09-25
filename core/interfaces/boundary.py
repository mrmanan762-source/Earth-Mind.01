from typing import Protocol, List, Any, runtime_checkable
from typing import Optional
from modules.context.boundary.models import (
    RAGContextContract,
    MemoryContextContract,
    ContextSourceRecord,
    PromotionCandidate,
    GovernanceDecision,
    PromotionRecord,
)


@runtime_checkable
class IRAGContextProvider(Protocol):
    """Interface for RAG context providers returning structured RAGContextContracts."""
    provider_name: str

    def get_rag_context(self, request: Any) -> List[RAGContextContract]:
        """Retrieve RAG context items conforming to RAGContextContract."""
        ...


@runtime_checkable
class IMemoryContextProvider(Protocol):
    """Interface for Memory context providers returning structured MemoryContextContracts."""
    provider_name: str

    def get_memory_context(self, request: Any) -> List[MemoryContextContract]:
        """Retrieve Memory context items conforming to MemoryContextContract."""
        ...


@runtime_checkable
class IBoundaryValidator(Protocol):
    """Interface for validating boundary compliance and preventing cross-domain violations."""

    def validate_record(self, record: ContextSourceRecord) -> None:
        """Validate a ContextSourceRecord against C.3 boundary and classification rules."""
        ...

    def validate_rag_contract(self, rag_contract: RAGContextContract) -> None:
        """Validate a RAGContextContract."""
        ...

    def validate_memory_contract(self, memory_contract: MemoryContextContract) -> None:
        """Validate a MemoryContextContract."""
        ...


@runtime_checkable
class IPromotionGovernanceEngine(Protocol):
    """Interface for cross-domain context promotion governance engine (C.3.3)."""

    def evaluate_candidate(self, candidate: PromotionCandidate) -> GovernanceDecision:
        """Evaluate a cross-domain promotion candidate against C.3 governance policies."""
        ...

    def execute_governance(
        self, candidate: PromotionCandidate
    ) -> PromotionRecord:
        """Evaluate and create a formal promotion record for a cross-domain candidate."""
        ...

    def approve_review(
        self,
        candidate: PromotionCandidate,
        reviewer_id: str,
        reason: str = "Approved by authorized review",
    ) -> PromotionRecord:
        """Approve a promotion candidate that previously required review."""
        ...

    def reject_review(
        self,
        candidate: PromotionCandidate,
        reviewer_id: str,
        reason: str = "Rejected during review",
    ) -> PromotionRecord:
        """Reject a promotion candidate that required review."""
        ...
