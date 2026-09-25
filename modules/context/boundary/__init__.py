from modules.context.boundary.enums import (
    KnowledgeClassification,
    ContextSourceType,
    ContextOwnership,
    ContextScope,
    PersistenceIntent,
)
from modules.context.boundary.models import (
    ContextSourceRecord,
    RAGContextContract,
    MemoryContextContract,
    RAGContextRequest,
    MemoryContextRequest,
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
    if name in {"IRAGContextProvider", "IMemoryContextProvider", "IBoundaryValidator"}:
        import core.interfaces.boundary as _cib
        return getattr(_cib, name)
    elif name in {"RAGContextProviderAdapter", "MemoryContextProviderAdapter"}:
        import modules.context.boundary.adapters as _adapters
        return getattr(_adapters, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    "KnowledgeClassification",
    "ContextSourceType",
    "ContextOwnership",
    "ContextScope",
    "PersistenceIntent",
    "ContextSourceRecord",
    "RAGContextContract",
    "MemoryContextContract",
    "RAGContextRequest",
    "MemoryContextRequest",
    "RAGContextProviderAdapter",
    "MemoryContextProviderAdapter",
    "IRAGContextProvider",
    "IMemoryContextProvider",
    "IBoundaryValidator",
    "BoundaryValidator",
    "BoundaryError",
    "BoundaryValidationError",
    "PromotionNotAllowedError",
    "ScopeViolationBoundaryError",
    "PrivacyBoundaryError",
]
