from typing import Protocol, List, Any, runtime_checkable
from modules.context.boundary.models import (
    RAGContextContract,
    MemoryContextContract,
    ContextSourceRecord,
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
