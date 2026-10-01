from modules.context.boundary.enums import (
    KnowledgeClassification,
    ContextSourceType,
    ContextOwnership,
    ContextScope,
    PersistenceIntent,
    TransitionType,
    GovernanceOutcome,
    GovernanceState,
    GovernanceFailureReason,
)
from modules.context.boundary.models import (
    ContextSourceRecord,
    RAGContextContract,
    MemoryContextContract,
    RAGContextRequest,
    MemoryContextRequest,
    PromotionCandidate,
    GovernanceDecision,
    PromotionRecord,
)
from modules.context.boundary.validator import BoundaryValidator
from core.errors.exceptions import (
    BoundaryError,
    BoundaryValidationError,
    PromotionNotAllowedError,
    ScopeViolationBoundaryError,
    PrivacyBoundaryError,
)

def __getattr__(name: str):
    if name in {"IRAGContextProvider", "IMemoryContextProvider", "IBoundaryValidator", "IPromotionGovernanceEngine"}:
        import core.interfaces.boundary as _cib
        return getattr(_cib, name)
    elif name in {"RAGContextProviderAdapter", "MemoryContextProviderAdapter"}:
        import modules.context.boundary.adapters as _adapters
        return getattr(_adapters, name)
    elif name == "RAGContextProvider":
        import modules.knowledge_base.integration as _mki
        return getattr(_mki, name)
    elif name == "ContextGovernanceEngine":
        import modules.context.boundary.governance as _gov
        return getattr(_gov, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    "KnowledgeClassification",
    "ContextSourceType",
    "ContextOwnership",
    "ContextScope",
    "PersistenceIntent",
    "TransitionType",
    "GovernanceOutcome",
    "GovernanceState",
    "GovernanceFailureReason",
    "ContextSourceRecord",
    "RAGContextContract",
    "MemoryContextContract",
    "RAGContextRequest",
    "MemoryContextRequest",
    "PromotionCandidate",
    "GovernanceDecision",
    "PromotionRecord",
    "ContextGovernanceEngine",
    "RAGContextProviderAdapter",
    "MemoryContextProviderAdapter",
    "IRAGContextProvider",
    "IMemoryContextProvider",
    "IBoundaryValidator",
    "IPromotionGovernanceEngine",
    "BoundaryValidator",
    "BoundaryError",
    "BoundaryValidationError",
    "PromotionNotAllowedError",
    "ScopeViolationBoundaryError",
    "PrivacyBoundaryError",
]
