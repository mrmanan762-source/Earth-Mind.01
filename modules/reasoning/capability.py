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
        capability_name: str = "model_layer_reasoning_capability"
    ):
        self._model = model
        self.capability_name = capability_name

    def set_model(self, model: IModel) -> None:
        """Set or update the underlying IModel provider."""
        self._model = model

    def reason(self, input_data: ReasoningInput) -> ReasoningResult:
        """Execute reasoning request by formulating ModelGenerationRequest to generic IModel."""
        if self._model is None:
            raise ReasoningCapabilityUnavailableError(
                self.capability_name, "No underlying IModel adapter attached."
            )

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

        # Format model response into structured findings with grounding and source attribution
        raw_response = str(gen_response.response or "No reasoning content generated")
        evidence_ids = [e.evidence_id for e in input_data.evidence_items]

        # Extract unique source IDs from evidence
        sources = sorted(list({e.source_id for e in input_data.evidence_items if e.source_id}))
        source_citation = f" [Sources: {', '.join(sources)}]" if sources else ""

        # Evaluate dynamic relevance between task query tokens and retrieved evidence content
        stop_words = {"what", "is", "the", "and", "who", "for", "of", "in", "to", "how", "a", "can", "before", "or", "under", "with", "on", "at", "by"}
        task_tokens = [w.strip("?,.!").lower() for w in input_data.task.split() if w.strip("?,.!").lower() not in stop_words and len(w) > 2]

        corpus_text_combined = ""
        if input_data.evidence_items:
            for e in input_data.evidence_items:
                if isinstance(e.content, dict):
                    txt = e.content.get("text") or e.content.get("content") or str(e.content)
                else:
                    txt = str(e.content)
                corpus_text_combined += " " + txt.lower()

        matching_tokens = [t for t in task_tokens if t in corpus_text_combined] if corpus_text_combined else []
        is_relevant = len(matching_tokens) > 0 if task_tokens else True

        if not raw_response.startswith("Processed task:"):
            # Model generated custom non-generic content directly
            response_text = f"{raw_response}{source_citation}"
            confidence = gen_response.confidence_level if gen_response.confidence_level is not None else 0.8
        elif not is_relevant and input_data.evidence_items:
            response_text = (
                f"No relevant agricultural evidence found in the frozen corpus for the query: '{input_data.task}'. "
                f"The EarthMind Knowledge Base contains verified agricultural evidence and does not fabricate answers for out-of-scope non-agricultural topics."
            )
            confidence = 0.0
            evidence_ids = []
        elif input_data.evidence_items:
            # Construct grounded synthesis from top retrieved evidence items
            evidence_snippets = []
            for e in input_data.evidence_items[:3]:
                txt = ""
                if isinstance(e.content, dict):
                    txt = e.content.get("text") or e.content.get("content") or str(e.content)
                else:
                    txt = str(e.content)
                clean_snippet = " ".join(txt.split())
                if clean_snippet:
                    evidence_snippets.append(f"• ({e.source_id}): {clean_snippet[:220]}...")

            snippets_text = "\n".join(evidence_snippets)
            response_text = (
                f"Based on retrieved corpus evidence for '{input_data.task}':\n"
                f"{snippets_text}\n"
                f"Supporting Sources: {', '.join(sources)}"
            )
            confidence = gen_response.confidence_level if gen_response.confidence_level is not None else 0.85
        else:
            response_text = f"{raw_response}{source_citation}"
            confidence = gen_response.confidence_level if gen_response.confidence_level is not None else 0.8

        finding = ReasoningFinding(
            finding_id=f"finding_{input_data.request_id}_1",
            statement=response_text,
            confidence_score=confidence,
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
        model_status = self._model.status() if (self._model and hasattr(self._model, "status")) else {"status": "unattached"}
        return {
            "capability_name": self.capability_name,
            "attached_model": model_status.get("identifier", "none") if isinstance(model_status, dict) else "attached",
            "model_status": model_status,
            "ready": self._model is not None,
        }
