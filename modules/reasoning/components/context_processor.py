from typing import List, Tuple
from modules.context.schemas import ContextResult
from modules.reasoning.enums import EvidenceScope
from modules.reasoning.errors import InvalidReasoningInputError
from modules.reasoning.evidence import EvidenceManager
from modules.reasoning.schemas import (
    AssumptionItem,
    EvidenceItem,
    MissingInformationItem,
    ReasoningInput,
)


class InputValidator:
    """Validates ReasoningInput payload schema, task description, and configuration bounds."""

    def validate(self, input_data: ReasoningInput) -> None:
        if not input_data:
            raise InvalidReasoningInputError("ReasoningInput cannot be None.")

        if not input_data.request_id or not isinstance(input_data.request_id, str):
            raise InvalidReasoningInputError("ReasoningInput must specify a non-empty request_id.")

        if not input_data.task or not isinstance(input_data.task, str) or not input_data.task.strip():
            raise InvalidReasoningInputError("ReasoningInput must specify a non-empty task description.")

        if input_data.policy and input_data.policy.max_iterations < 1:
            raise InvalidReasoningInputError("policy.max_iterations must be at least 1.")


class ReasoningContextProcessor:
    """Prepares reasoning-specific context from Context Manager output and input evidence."""

    def __init__(self, evidence_manager: EvidenceManager):
        self._evidence_manager = evidence_manager

    def process_context(
        self, input_data: ReasoningInput
    ) -> Tuple[List[EvidenceItem], List[AssumptionItem], List[MissingInformationItem]]:
        """Selects, groups, and enriches evidence items from input and ContextResult."""
        evidence_items, assumption_items, missing_items = self._evidence_manager.prepare_evidence(input_data)

        # Ensure all evidence items preserve scope and trace ID
        for item in evidence_items:
            if not item.trace_id:
                item.trace_id = input_data.trace_id

        # Identify required missing information based on task requirements
        if "soil" in input_data.task.lower() and not any(
            "soil" in str(e.data_reference or "").lower() or "soil" in str(e.content).lower() for e in evidence_items
        ):
            missing_items.append(
                MissingInformationItem(
                    missing_info_id=f"missing_soil_{input_data.request_id}",
                    required_data_type="soil_data",
                    scope=EvidenceScope.FIELD,
                    importance="MEDIUM",
                    impact_on_reasoning="Soil data missing for soil-related reasoning task.",
                    suggested_resolution="Fetch recent soil sensor or lab test data.",
                    trace_id=input_data.trace_id
                )
            )

        return evidence_items, assumption_items, missing_items
