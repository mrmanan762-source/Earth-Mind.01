from typing import Any, List, Optional
from core.errors.exceptions import BoundaryValidationError, ContextProviderError
from core.logging.logger import get_logger
from core.interfaces.boundary import IRAGContextProvider, IMemoryContextProvider
from modules.context.boundary.enums import ContextScope, KnowledgeClassification
from modules.context.boundary.models import (
    MemoryContextContract,
    MemoryContextRequest,
    RAGContextContract,
    RAGContextRequest,
)
from modules.context.boundary.validator import BoundaryValidator
from modules.context.schemas import ContextItem, ContextRequest

logger = get_logger("modules.context.boundary.adapters")


class RAGContextProviderAdapter:
    """
    Adapter integrating IRAGContextProvider with B2 Context Manager ContextProvider protocol.
    Translates B2 ContextRequest -> RAGContextRequest, executes RAG retrieval,
    validates returned RAGContextContracts via BoundaryValidator, and returns B2 ContextItems.
    """

    def __init__(
        self,
        rag_provider: IRAGContextProvider,
        provider_name: Optional[str] = None,
        validator: Optional[BoundaryValidator] = None,
    ):
        self._rag_provider = rag_provider
        self.provider_name = provider_name or getattr(rag_provider, "provider_name", "rag_provider")
        self._validator = validator or BoundaryValidator()

    def get_rag_context(self, request: RAGContextRequest) -> List[RAGContextContract]:
        """Delegate directly to underlying IRAGContextProvider if called via C.3 interface."""
        return self._rag_provider.get_rag_context(request)

    def get_context(self, request: ContextRequest) -> List[ContextItem]:
        """B2 ContextProvider protocol method."""
        logger.debug(f"RAGContextProviderAdapter '{self.provider_name}' processing request {request.request_id}")

        # Map ContextRequest to RAGContextRequest
        rag_request = RAGContextRequest(
            request_id=request.request_id,
            request_origin="B2_CONTEXT_MANAGER",
            session_id=request.session_id,
            query_text=request.task,
            classification=KnowledgeClassification.GENERAL_KNOWLEDGE,
            scope=ContextScope.GLOBAL,
            content_types=request.requested_context_types,
            time_range=request.time_range,
            relevance_threshold=request.relevance_threshold,
            maximum_result_count=10,
            trace_id=request.trace_id,
            metadata=request.metadata,
        )

        try:
            contracts = self._rag_provider.get_rag_context(rag_request)
        except Exception as e:
            logger.error(f"RAG provider '{self.provider_name}' execution failed: {str(e)}")
            raise ContextProviderError(self.provider_name, f"RAG provider failed: {str(e)}")

        context_items: List[ContextItem] = []
        for contract in contracts:
            try:
                # Validate boundary compliance
                self._validator.validate_rag_contract(contract)
                # Convert to B2 ContextItem preserving source identity & provenance
                item = ContextItem.from_rag_contract(contract)
                context_items.append(item)
            except BoundaryValidationError as bve:
                logger.warning(f"RAG contract boundary validation failed in '{self.provider_name}': {str(bve)}")
                raise

        return context_items


class MemoryContextProviderAdapter:
    """
    Adapter integrating IMemoryContextProvider with B2 Context Manager ContextProvider protocol.
    Translates B2 ContextRequest -> MemoryContextRequest, executes Memory retrieval,
    validates returned MemoryContextContracts via BoundaryValidator, and returns B2 ContextItems.
    """

    def __init__(
        self,
        memory_provider: IMemoryContextProvider,
        provider_name: Optional[str] = None,
        validator: Optional[BoundaryValidator] = None,
    ):
        self._memory_provider = memory_provider
        self.provider_name = provider_name or getattr(memory_provider, "provider_name", "memory_provider")
        self._validator = validator or BoundaryValidator()

    def get_memory_context(self, request: MemoryContextRequest) -> List[MemoryContextContract]:
        """Delegate directly to underlying IMemoryContextProvider if called via C.3 interface."""
        return self._memory_provider.get_memory_context(request)

    def get_context(self, request: ContextRequest) -> List[ContextItem]:
        """B2 ContextProvider protocol method."""
        logger.debug(f"MemoryContextProviderAdapter '{self.provider_name}' processing request {request.request_id}")

        # Determine target scope from request entity IDs
        scope = ContextScope.FARMER
        if request.field_id:
            scope = ContextScope.FIELD
        elif request.farm_id:
            scope = ContextScope.FARM
        elif request.crop_cycle_id:
            scope = ContextScope.CROP_CYCLE

        allow_pii = request.policy.allow_pii if request.policy else False

        memory_request = MemoryContextRequest(
            request_id=request.request_id,
            request_origin="B2_CONTEXT_MANAGER",
            farmer_id=request.farmer_id,
            farm_id=request.farm_id,
            field_id=request.field_id,
            crop_cycle_id=request.crop_cycle_id,
            session_id=request.session_id,
            query_text=request.task,
            classification=KnowledgeClassification.FARMER_KNOWLEDGE,
            scope=scope,
            requested_memory_types=request.requested_context_types,
            time_range=request.time_range,
            relevance_threshold=request.relevance_threshold,
            maximum_result_count=10,
            allow_pii=allow_pii,
            trace_id=request.trace_id,
            metadata=request.metadata,
        )

        try:
            contracts = self._memory_provider.get_memory_context(memory_request)
        except Exception as e:
            logger.error(f"Memory provider '{self.provider_name}' execution failed: {str(e)}")
            raise ContextProviderError(self.provider_name, f"Memory provider failed: {str(e)}")

        context_items: List[ContextItem] = []
        for contract in contracts:
            try:
                # Validate boundary compliance
                self._validator.validate_memory_contract(contract)
                # Convert to B2 ContextItem preserving source identity & provenance
                item = ContextItem.from_memory_contract(contract)
                context_items.append(item)
            except BoundaryValidationError as bve:
                logger.warning(f"Memory contract boundary validation failed in '{self.provider_name}': {str(bve)}")
                raise

        return context_items
