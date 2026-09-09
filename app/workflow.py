from typing import Dict, Any, Optional
from core.schemas.application import ApplicationRequest, ApplicationResponse
from core.logging.logger import get_logger
from core.errors.exceptions import ModuleNotFoundError, ModuleExecutionError
from app.lifecycle import LifecycleManager

logger = get_logger("app.workflow")

class WorkflowEngine:
    """Orchestrates system workflow requests between registered modules."""

    def __init__(self, lifecycle: LifecycleManager):
        self.lifecycle = lifecycle

    def dispatch(self, request: ApplicationRequest) -> ApplicationResponse:
        """
        Dispatches a request to the appropriate target module based on source/metadata/operation.
        """
        logger.info(f"Processing request {request.request_id} for operation: {request.operation}")

        # Route to target module
        target_module_name = request.metadata.get("target_module", "ai")
        try:
            module = self.lifecycle.get_module(target_module_name)
        except ModuleNotFoundError as e:
            logger.error(f"Target module '{target_module_name}' not found.")
            return ApplicationResponse(
                request_id=request.request_id,
                status="ERROR",
                warnings=[str(e)]
            )

        try:
            # Optional pre-execution inspector validation if inspector is available
            try:
                inspector = self.lifecycle.get_module("inspector")
                if inspector and hasattr(inspector, "inspect_request"):
                    inspector.inspect_request(request)
            except ModuleNotFoundError:
                pass

            response = module.handle(request)
            return response
        except Exception as e:
            logger.error(f"Error executing request on {target_module_name}: {str(e)}")
            raise ModuleExecutionError(target_module_name, str(e))
