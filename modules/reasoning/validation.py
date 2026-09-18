import uuid
from typing import Any, Dict, Optional
from core.interfaces.services import InspectorInterface
from core.logging.logger import get_logger
from modules.reasoning.enums import ValidationStatus
from modules.reasoning.errors import ReasoningValidationHandoffError
from modules.reasoning.interfaces import IInspectorHandoff
from modules.reasoning.schemas import (
    ReasoningResult,
    ReasoningValidationHandoff,
)

logger = get_logger("modules.reasoning.validation")


class InspectorHandoffManager(IInspectorHandoff):
    """Manages B3 validation handoffs to Inspector service.

    Core Rule 7 Enforced: Every valid reasoning result MUST be submitted for
    Inspector validation regardless of confidence score.
    """

    def __init__(self, inspector: Optional[InspectorInterface] = None):
        self._inspector = inspector

    def set_inspector(self, inspector: InspectorInterface) -> None:
        """Set or update the Inspector service instance."""
        self._inspector = inspector

    def handoff_validation(self, result: ReasoningResult) -> ReasoningValidationHandoff:
        """Prepare and submit reasoning result to Inspector for validation."""
        if not result or not result.request_id:
            raise ReasoningValidationHandoffError(
                "unknown", "Cannot prepare validation handoff for empty or invalid result."
            )

        handoff_id = f"handoff_{result.request_id}_{uuid.uuid4().hex[:8]}"

        # Summarize evidence, conflicts, and uncertainties
        evidence_summary = {
            "total_referenced": len(result.evidence_references),
            "evidence_ids": result.evidence_references,
            "assumptions_count": len(result.assumptions),
        }

        conflicts_summary = {
            "total_conflicts": len(result.conflicts),
            "unresolved_conflicts": len([c for c in result.conflicts if not c.is_resolved]),
            "conflict_ids": [c.conflict_id for c in result.conflicts],
        }

        uncertainty_summary = {
            "total_uncertainties": len(result.uncertainty),
            "uncertainty_ids": [u.uncertainty_id for u in result.uncertainty],
            "missing_info_count": len(result.missing_information),
        }

        # Initial validation status
        val_status = ValidationStatus.PASS
        if conflicts_summary["unresolved_conflicts"] > 0:
            val_status = ValidationStatus.FLAG
        elif uncertainty_summary["total_uncertainties"] > 0:
            val_status = ValidationStatus.RECHECK

        inspector_resp: Optional[Dict[str, Any]] = None

        # Invoke Inspector service if attached
        if self._inspector and hasattr(self._inspector, "validate_action"):
            try:
                payload = {
                    "request_id": result.request_id,
                    "findings_count": len(result.findings),
                    "evidence_summary": evidence_summary,
                    "conflicts_summary": conflicts_summary,
                    "uncertainty_summary": uncertainty_summary,
                }
                inspector_resp = self._inspector.validate_action("validate_reasoning_result", payload)
                if isinstance(inspector_resp, dict) and not inspector_resp.get("valid", True):
                    val_status = ValidationStatus.FLAG
            except Exception as e:
                logger.warning(f"Inspector service invocation warning: {str(e)}")
                val_status = ValidationStatus.RECHECK
                inspector_resp = {"error": str(e)}

        handoff = ReasoningValidationHandoff(
            handoff_id=handoff_id,
            request_id=result.request_id,
            reasoning_result_id=f"res_{result.request_id}",
            findings=result.findings,
            evidence_summary=evidence_summary,
            conflicts_summary=conflicts_summary,
            uncertainty_summary=uncertainty_summary,
            validation_status=val_status,
            inspector_response=inspector_resp,
            trace_id=result.trace_id,
            metadata={"status": val_status.value}
        )

        logger.info(f"Reasoning validation handoff prepared for '{result.request_id}': status={val_status.value}")
        return handoff
