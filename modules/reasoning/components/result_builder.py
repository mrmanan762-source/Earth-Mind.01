from typing import Any, Dict, List, Optional
from modules.reasoning.enums import ReasoningState
from modules.reasoning.schemas import (
    AssumptionItem,
    EvidenceConflict,
    EvidenceItem,
    EvidenceRelationship,
    MissingInformationItem,
    ReasoningFinding,
    ReasoningResult,
    UncertaintyItem,
)


class ReasoningResultBuilder:
    """Assembles all reasoning outputs into a structured ReasoningResult matching the Part 1 contract."""

    def build_result(
        self,
        request_id: str,
        status: ReasoningState,
        findings: List[ReasoningFinding],
        evidence_items: List[EvidenceItem],
        assumptions: List[AssumptionItem],
        relationships: List[EvidenceRelationship],
        conflicts: List[EvidenceConflict],
        uncertainty: List[UncertaintyItem],
        missing_info: List[MissingInformationItem],
        operation_trace: List[Dict[str, Any]],
        iteration_metadata: Dict[str, Any],
        model_metadata: Dict[str, Any],
        trace_id: Optional[str] = None,
        warnings: Optional[List[str]] = None,
        errors: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ReasoningResult:
        evidence_refs = list({e.evidence_id for e in evidence_items})

        return ReasoningResult(
            request_id=request_id,
            status=status,
            findings=findings,
            evidence_references=evidence_refs,
            assumptions=assumptions,
            relationships=relationships,
            conflicts=conflicts,
            uncertainty=uncertainty,
            missing_information=missing_info,
            reasoning_operation_trace=operation_trace,
            iteration_metadata=iteration_metadata,
            model_capability_metadata=model_metadata,
            warnings=warnings or [],
            errors=errors or [],
            trace_id=trace_id,
            metadata=metadata or {}
        )
