"""Memory Context Provider for EarthMind Memory Module Level 5 (EarthMind Integration).

Implements IMemoryContextProvider protocol, querying the secure MemoryService
under strict AuthorizationContext and boundary governance, converting authorized
MemoryRecord instances to MemoryContextContract objects for B2 Context Manager.
"""

from typing import Any, Dict, List, Optional
from core.interfaces.boundary import IMemoryContextProvider
from core.logging.logger import get_logger
from core.schemas.memory import (
    AuthorizationContext,
    MemoryDomain,
    MemoryOperation,
    MemoryRecord,
    MemoryRecordStatus,
    MemoryScope,
    MemorySearchCriteria,
)
from modules.context.boundary.enums import (
    ContextScope,
    KnowledgeClassification,
)
from modules.context.boundary.models import (
    MemoryContextContract,
    MemoryContextRequest,
)
from modules.memory.errors import (
    MemoryError,
    MemoryForbiddenError,
    MemoryUnauthorizedError,
)
from modules.memory.memory_service import MemoryService

logger = get_logger("modules.memory.context_provider")


class MemoryContextProvider(IMemoryContextProvider):
    """
    Supplies authorized memory records to B2 Context Manager via IMemoryContextProvider.
    Translates MemoryContextRequest into authorized MemorySearchCriteria, queries
    MemoryService, validates scope/domain boundaries, and converts eligible records
    to MemoryContextContract instances.
    """

    provider_name: str = "memory_provider"

    def __init__(
        self,
        memory_service: MemoryService,
        provider_name: Optional[str] = None,
        fail_silent_on_unauthorized: bool = True,
    ):
        self.memory_service = memory_service
        if provider_name:
            self.provider_name = provider_name
        self.fail_silent_on_unauthorized = fail_silent_on_unauthorized

    def get_memory_context(self, request: MemoryContextRequest) -> List[MemoryContextContract]:
        """
        Retrieve Memory context items conforming to MemoryContextContract for B2.

        Enforces:
        - Scope translation (FARMER, SESSION, FARM, FIELD, CROP_CYCLE, GLOBAL).
        - Domain determination (USER vs GENERAL).
        - Trusted AuthorizationContext construction without owner spoofing.
        - Exclusion of DELETED or EXPIRED records.
        - Bounded result limits.
        - Safe failure handling and graceful fallback.
        """
        if not isinstance(request, MemoryContextRequest):
            logger.warning("Invalid request passed to MemoryContextProvider; returning empty context.")
            return []

        logger.debug(
            f"MemoryContextProvider handling request {request.request_id} for farmer '{request.farmer_id}' "
            f"scope={request.scope.value}"
        )

        # 1. Resolve Scope & Target Domain
        c3_to_memory_scope = {
            ContextScope.FARMER: MemoryScope.USER,
            ContextScope.SESSION: MemoryScope.CONVERSATION,
            ContextScope.FARM: MemoryScope.FARM,
            ContextScope.FIELD: MemoryScope.FIELD,
            ContextScope.CROP_CYCLE: MemoryScope.CROP_CYCLE,
            ContextScope.GLOBAL: MemoryScope.GENERAL,
        }
        memory_scope = c3_to_memory_scope.get(request.scope, MemoryScope.USER)

        # Domain separation: GLOBAL scope maps to GENERAL memory domain; farmer scopes map to USER domain
        target_domain = MemoryDomain.GENERAL if request.scope == ContextScope.GLOBAL else MemoryDomain.USER

        # 2. Determine Scope ID & Owner ID
        scope_id = None
        if memory_scope == MemoryScope.USER:
            scope_id = request.farmer_id
        elif memory_scope == MemoryScope.CONVERSATION:
            scope_id = request.session_id or request.farmer_id
        elif memory_scope == MemoryScope.FARM:
            scope_id = request.farm_id or request.farmer_id
        elif memory_scope == MemoryScope.FIELD:
            scope_id = request.field_id or request.farmer_id
        elif memory_scope == MemoryScope.CROP_CYCLE:
            scope_id = request.crop_cycle_id or request.farmer_id
        elif memory_scope == MemoryScope.GENERAL:
            scope_id = request.metadata.get("scope_id", "general")

        # 3. Construct AuthorizationContext
        # For USER domain: mandatory authenticated owner (farmer_id). If missing, fail closed.
        if target_domain == MemoryDomain.USER:
            if not request.farmer_id or not str(request.farmer_id).strip():
                logger.warning(
                    f"MemoryContextRequest {request.request_id} for USER domain has no farmer_id. Access denied."
                )
                if self.fail_silent_on_unauthorized:
                    return []
                raise MemoryUnauthorizedError("Missing farmer_id for user memory retrieval.")

            farmer_id = request.farmer_id.strip()
            accessible = {MemoryScope.USER.value: [farmer_id]}
            if scope_id and memory_scope.value != MemoryScope.USER.value:
                accessible[memory_scope.value] = [scope_id]

            auth_context = AuthorizationContext(
                principal_id=farmer_id,
                owner_id=farmer_id,
                roles=["farmer"],
                accessible_scopes=accessible,
                requested_operation=MemoryOperation.SEARCH,
                policy_context={"correlation_id": request.trace_id or request.request_id},
            )
            owner_id = farmer_id
        else:
            # GENERAL domain read access: can be requested by user or system
            principal_id = request.farmer_id or "system_context_collector"
            auth_context = AuthorizationContext(
                principal_id=principal_id,
                roles=["reader"],
                accessible_scopes={MemoryScope.GENERAL.value: [scope_id or "general"]},
                requested_operation=MemoryOperation.SEARCH,
                policy_context={"correlation_id": request.trace_id or request.request_id},
            )
            owner_id = None

        # 4. Construct MemorySearchCriteria (do NOT filter on request.trace_id as correlation_id unless requested)
        limit = min(max(request.maximum_result_count, 1), 50)
        criteria = MemorySearchCriteria(
            domain=target_domain,
            owner_id=owner_id,
            scope_type=memory_scope,
            scope_id=scope_id,
            status=MemoryRecordStatus.ACTIVE,
            limit=limit,
        )

        # 5. Execute Memory Retrieval under Authorization
        try:
            search_fn = getattr(self.memory_service, "search_records", None) or getattr(self.memory_service, "search")
            records = search_fn(context=auth_context, criteria=criteria)
        except (MemoryForbiddenError, MemoryUnauthorizedError) as auth_err:
            logger.warning(f"Memory retrieval authorization rejected for request {request.request_id}: {str(auth_err)}")
            if self.fail_silent_on_unauthorized:
                return []
            raise
        except MemoryError as mem_err:
            logger.error(f"Memory service operational error during context retrieval: {str(mem_err)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in MemoryContextProvider: {str(e)}")
            raise

        # 6. Transform Records to MemoryContextContract
        contracts: List[MemoryContextContract] = []
        for record in records:
            # Invariant: Never include DELETED or EXPIRED records in B2 context
            if record.status in (MemoryRecordStatus.DELETED, MemoryRecordStatus.EXPIRED):
                continue

            try:
                contract = record.to_context_contract()
                # Attach request correlation/trace if present
                if request.trace_id and not contract.trace_id:
                    contract = contract.model_copy(update={"trace_id": request.trace_id})
                contracts.append(contract)
            except Exception as conv_err:
                logger.warning(f"Failed to convert record {record.record_id} to MemoryContextContract: {conv_err}")
                continue

        logger.debug(f"MemoryContextProvider returning {len(contracts)} contracts for request {request.request_id}")
        return contracts
