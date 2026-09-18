from typing import Any, Dict, Optional
from core.interfaces.model import IModel
from core.schemas.model import ModelGenerationRequest
from core.logging.logger import get_logger
from modules.reasoning.enums import ReasoningState
from modules.reasoning.errors import ReasoningCapabilityUnavailableError
from modules.reasoning.interfaces import IReasoningCapability
from modules.reasoning.schemas import (
    ReasoningFinding,
    ReasoningInput,
    ReasoningResult,
)

logger = get_logger("modules.reasoning.capability")


class ModelLayerReasoningCapability(IReasoningCapability):
    """Adapter bridging B3 Reasoning Engine to EarthMind's AI Model Layer.

    Implements `IReasoningCapability` contract using generic `IModel` interface,
    preserving model capability independence (e.g. routing to Sarvam-105B via adapter).
    """

    def __init__(
        self,
        model: Optional[IModel] = None,
        capability_name: str = "model_layer_reasoning_capability",
        auto_attach: bool = True
    ):
        self._model = model
        self.capability_name = capability_name
        self._auto_attach = auto_attach and (model is None)

    def set_model(self, model: Optional[IModel]) -> None:
        """Set or update the underlying IModel provider."""
        self._model = model
        self._auto_attach = False

    def _ensure_model_attached(self) -> None:
        if self._model is None:
            if self._auto_attach:
                try:
                    from modules.ai.sarvam_adapter import Sarvam105BAdapter
                    adapter = Sarvam105BAdapter()
                    adapter.load()
                    self._model = adapter
                except Exception as e:
                    logger.error(f"Failed to auto-attach Sarvam105BAdapter: {str(e)}")
                    raise ReasoningCapabilityUnavailableError(
                        self.capability_name, f"No underlying IModel adapter attached: {str(e)}"
                    ) from e
            else:
                raise ReasoningCapabilityUnavailableError(
                    self.capability_name, "No underlying IModel adapter attached."
                )

    def reason(self, input_data: ReasoningInput) -> ReasoningResult:
        """Execute reasoning request by formulating ModelGenerationRequest to generic IModel."""
        self._ensure_model_attached()

        # Build generic model generation request
        model_req = ModelGenerationRequest(
            request_id=input_data.request_id,
            task=f"Reasoning task: {input_data.task}",
            instructions="Analyze context and evidence items, identify relationships, conflicts, and uncertainties.",
            context={
                "task": input_data.task,
                "evidence_count": len(input_data.evidence_items),
                "constraints": input_data.constraints,
                "metadata": input_data.metadata,
            },
            metadata={"trace_id": input_data.trace_id, "capability": self.capability_name}
        )

        try:
            gen_response = self._model.generate(model_req)
        except Exception as e:
            logger.error(f"Reasoning model invocation failed: {str(e)}")
            raise ReasoningCapabilityUnavailableError(self.capability_name, str(e)) from e

        # Format model response into structured findings
        response_text = str(gen_response.response or "No reasoning content generated")
        evidence_ids = [e.evidence_id for e in input_data.evidence_items]

        finding = ReasoningFinding(
            finding_id=f"finding_{input_data.request_id}_1",
            statement=response_text,
            confidence_score=gen_response.confidence_level if gen_response.confidence_level is not None else 0.8,
            evidence_ids=evidence_ids,
            trace_id=input_data.trace_id,
            metadata={"model_version": gen_response.model_version}
        )

        return ReasoningResult(
            request_id=input_data.request_id,
            status=ReasoningState.COMPLETED,
            findings=[finding],
            evidence_references=evidence_ids,
            reasoning_operation_trace=[
                {
                    "operation": "invoke_model_capability",
                    "capability": self.capability_name,
                    "model_version": gen_response.model_version,
                    "status": gen_response.status,
                }
            ],
            model_capability_metadata={
                "capability_name": self.capability_name,
                "model_version": gen_response.model_version,
                "warnings": gen_response.warnings,
            },
            trace_id=input_data.trace_id,
            metadata={"capability_name": self.capability_name}
        )

    def status(self) -> Dict[str, Any]:
        """Return capability health and underlying model status."""
        model_status = {}
        if self._model and hasattr(self._model, "status"):
            try:
                raw_st = self._model.status()
                model_status = raw_st if isinstance(raw_st, dict) else {"status": str(raw_st)}
            except Exception as e:
                model_status = {"status_error": str(e)}
        else:
            model_status = {"status": "unattached"}

        return {
            "capability_name": self.capability_name,
            "attached_model": model_status.get("identifier", "none") if isinstance(model_status, dict) else "attached",
            "model_status": model_status,
            "ready": self._model is not None,
        }
