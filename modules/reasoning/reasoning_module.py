import uuid
from typing import Any, Dict, Optional, Tuple

from core.interfaces.module import ModuleInterface
from core.interfaces.services import InspectorInterface
from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest, ApplicationResponse
from modules.reasoning.capability import ModelLayerReasoningCapability
from modules.reasoning.engine import ReasoningEngine
from modules.reasoning.enums import ReasoningState
from modules.reasoning.errors import InvalidReasoningInputError, ReasoningError
from modules.reasoning.interfaces import IReasoningCapability
from modules.reasoning.schemas import (
    ReasoningInput,
    ReasoningPolicyConfig,
    ReasoningResult,
    ReasoningValidationHandoff,
)

logger = get_logger("modules.reasoning")


class ReasoningModule(ModuleInterface):
    """B3 Reasoning Engine Module.

    Reasons over available evidence, context, conflicts, and uncertainties.
    Outputs structured reasoning findings and hands off results to Inspector for validation.
    Does NOT own final agricultural decision or action logic (owned by B4).
    """

    module_name = "reasoning"

    def __init__(
        self,
        capability: Optional[IReasoningCapability] = None,
        inspector: Optional[InspectorInterface] = None
    ):
        self._capability = capability or ModelLayerReasoningCapability()
        self._engine = ReasoningEngine(capability=self._capability, inspector=inspector)
        self._is_initialized: bool = False

    @property
    def engine(self) -> ReasoningEngine:
        return self._engine

    def initialize(self) -> None:
        """Initialize Reasoning Engine module resources."""
        self._is_initialized = True
        logger.info("B3 Reasoning Engine module initialized successfully.")

    def shutdown(self) -> None:
        """Shut down Reasoning Engine module resources."""
        self._is_initialized = False
        logger.info("B3 Reasoning Engine module shut down.")

    def set_capability(self, capability: IReasoningCapability) -> None:
        """Attach or replace the reasoning capability implementation."""
        self._capability = capability
        self._engine.set_capability(capability)

    def set_inspector(self, inspector: InspectorInterface) -> None:
        """Attach or update the Inspector service for validation handoffs."""
        self._engine.set_inspector(inspector)

    def reason(
        self,
        input_data: ReasoningInput,
        cancel_requested: bool = False
    ) -> Tuple[ReasoningResult, ReasoningValidationHandoff]:
        """Core B3 reasoning entry point executing complete 12-state pipeline."""
        if not input_data or not input_data.request_id:
            raise InvalidReasoningInputError("ReasoningInput with valid request_id is required.")

        return self._engine.execute(input_data, cancel_requested=cancel_requested)

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        """Handles incoming application workflow requests for the reasoning module."""
        op = request.operation
        payload = request.payload or {}

        if op in ("reason", "analyze", "execute_reasoning"):
            task = payload.get("task", "Analyze reasoning context")
            policy_dict = payload.get("policy", {})
            policy = ReasoningPolicyConfig(**policy_dict) if policy_dict else ReasoningPolicyConfig()

            reasoning_input = ReasoningInput(
                request_id=request.request_id,
                task=task,
                policy=policy,
                trace_id=request.request_id,
                metadata=request.metadata
            )

            try:
                result, handoff = self.reason(reasoning_input)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS" if result.status == ReasoningState.COMPLETED else "PARTIAL",
                    response={
                        "result": result.model_dump(),
                        "handoff": handoff.model_dump(),
                    }
                )
            except ReasoningError as re:
                logger.error(f"Reasoning error in handle(): {str(re)}")
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="ERROR",
                    warnings=[str(re)]
                )
            except Exception as e:
                logger.error(f"Unexpected error in ReasoningModule.handle(): {str(e)}")
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="ERROR",
                    warnings=[f"Internal error: {str(e)}"]
                )

        return ApplicationResponse(
            request_id=request.request_id,
            status="SUCCESS",
            response=f"Reasoning module operational; received operation '{op}'"
        )
