import uuid
from typing import Optional
from core.interfaces.module import ModuleInterface
from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest, ApplicationResponse
from modules.context.manager import B2ContextManager
from modules.context.schemas import ContextRequest, PolicyConfig

logger = get_logger("modules.context.context_module")


class ContextModule(ModuleInterface):
    """
    Module implementation wrapping B2 Context Manager for application lifecycle integration.
    """

    module_name = "context"

    def __init__(self, manager: Optional[B2ContextManager] = None):
        self.manager = manager or B2ContextManager()
        self._is_initialized = False

    def initialize(self) -> None:
        logger.info("Initializing Context Module...")
        self._is_initialized = True
        logger.info("Context Module initialized successfully.")

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        logger.info(f"ContextModule handling request {request.request_id} operation: {request.operation}")

        payload = request.payload or {}
        policy_dict = payload.get("policy", {})
        policy = PolicyConfig(**policy_dict) if isinstance(policy_dict, dict) else PolicyConfig()

        context_req = ContextRequest(
            request_id=request.request_id,
            farmer_id=payload.get("farmer_id") or request.metadata.get("farmer_id"),
            farm_id=payload.get("farm_id") or request.metadata.get("farm_id"),
            field_id=payload.get("field_id") or request.metadata.get("field_id"),
            crop_cycle_id=payload.get("crop_cycle_id") or request.metadata.get("crop_cycle_id"),
            session_id=payload.get("session_id") or request.metadata.get("session_id"),
            task=payload.get("task") or payload.get("prompt"),
            requested_context_types=payload.get("requested_context_types", []),
            time_range=payload.get("time_range"),
            token_limit=payload.get("token_limit", 4096),
            relevance_threshold=payload.get("relevance_threshold", 0.5),
            policy=policy,
            trace_id=request.metadata.get("trace_id") or request.request_id,
        )

        try:
            result = self.manager.prepare_context(context_req)
            return ApplicationResponse(
                request_id=request.request_id,
                status=result.state.value,
                response=result.structured_context,
                warnings=result.warnings,
                metadata={"total_tokens": result.total_tokens, "item_count": len(result.items)},
            )
        except Exception as e:
            logger.error(f"ContextModule processing error: {str(e)}")
            return ApplicationResponse(
                request_id=request.request_id,
                status="ERROR",
                response=None,
                warnings=[str(e)],
            )

    def shutdown(self) -> None:
        logger.info("Shutting down Context Module...")
        self._is_initialized = False
        logger.info("Context Module shut down cleanly.")
