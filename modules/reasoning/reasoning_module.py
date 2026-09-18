import uuid
from typing import Any, Dict, Optional, Tuple

from core.interfaces.module import ModuleInterface
from core.interfaces.services import InspectorInterface
from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest, ApplicationResponse
from modules.reasoning.capability import ModelLayerReasoningCapability
from modules.reasoning.enums import ReasoningState, ValidationStatus
from modules.reasoning.errors import InvalidReasoningInputError, ReasoningError
from modules.reasoning.evidence import EvidenceManager
from modules.reasoning.interfaces import IReasoningCapability
from modules.reasoning.schemas import (
    ReasoningInput,
    ReasoningPolicyConfig,
    ReasoningResult,
    ReasoningValidationHandoff,
)
from modules.reasoning.strategy import ReasoningStrategyController
from modules.reasoning.traceability import ReasoningTraceManager
from modules.reasoning.validation import InspectorHandoffManager

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
        self._evidence_manager = EvidenceManager()
        self._strategy_controller = ReasoningStrategyController(
            capability=self._capability,
            evidence_manager=self._evidence_manager
        )
        self._trace_manager = ReasoningTraceManager()
        self._handoff_manager = InspectorHandoffManager(inspector=inspector)
        self._is_initialized: bool = False

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
        self._strategy_controller = ReasoningStrategyController(
            capability=self._capability,
            evidence_manager=self._evidence_manager
        )

    def set_inspector(self, inspector: InspectorInterface) -> None:
        """Attach or update the Inspector service for validation handoffs."""
        self._handoff_manager.set_inspector(inspector)

    def reason(self, input_data: ReasoningInput) -> Tuple[ReasoningResult, ReasoningValidationHandoff]:
        """Core B3 reasoning entry point.

        Processes ReasoningInput, executes controlled reasoning strategy, records structured traces,
        and submits findings for Inspector validation handoff.
        """
        if not input_data or not input_data.request_id:
            raise InvalidReasoningInputError("ReasoningInput with valid request_id is required.")

        req_id = input_data.request_id
        trace_id = input_data.trace_id or f"trace_{req_id}"

        # Record start in audit trace
        self._trace_manager.record_operation(
            request_id=req_id,
            operation="start_reasoning",
            timestamp="",
            metadata={"task": input_data.task}
        )

        # Execute 13-step strategy
        result: ReasoningResult = self._strategy_controller.execute_strategy(input_data)

        # Record strategy completion in trace
        self._trace_manager.record_operation(
            request_id=req_id,
            operation="strategy_executed",
            evidence_ids=result.evidence_references,
            finding_ids=[f.finding_id for f in result.findings],
            iteration_index=result.iteration_metadata.get("total_iterations", 1)
        )

        # Submit for Inspector validation handoff (Core Rule 7)
        handoff: ReasoningValidationHandoff = self._handoff_manager.handoff_validation(result)

        # Record handoff in trace
        self._trace_manager.record_operation(
            request_id=req_id,
            operation="inspector_handoff",
            finding_ids=[f.finding_id for f in result.findings],
            metadata={"handoff_status": handoff.validation_status.value}
        )

        return result, handoff

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
                        "trace_summary": self._trace_manager.build_trace_summary(result, handoff)
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
