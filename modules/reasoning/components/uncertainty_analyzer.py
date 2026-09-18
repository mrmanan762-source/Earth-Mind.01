from typing import List, Optional
from modules.reasoning.enums import UncertaintyLevel
from modules.reasoning.schemas import (
    EvidenceConflict,
    EvidenceItem,
    MissingInformationItem,
    UncertaintyItem,
)


class UncertaintyAnalyzer:
    """Analyzes evidence, conflicts, and missing items to make uncertainty explicit.

    Core Rule 2 Enforced: Uncertainty must remain visible.
    Differentiates UNCERTAINTY, MISSING_INFORMATION, CONFLICT, CAPABILITY_UNAVAILABLE, TECHNICAL_FAILURE.
    """

    def analyze_uncertainty(
        self,
        evidence_items: List[EvidenceItem],
        conflicts: List[EvidenceConflict],
        missing_items: List[MissingInformationItem],
        trace_id: Optional[str] = None
    ) -> List[UncertaintyItem]:
        uncertainties: List[UncertaintyItem] = []

        # 1. Uncertainty from conflicts
        if conflicts:
            unc_conf = UncertaintyItem(
                uncertainty_id=f"unc_conf_{trace_id or '0'}",
                level=UncertaintyLevel.MEDIUM if len(conflicts) == 1 else UncertaintyLevel.HIGH,
                reason=f"Reasoning findings subject to uncertainty due to {len(conflicts)} active evidence conflict(s).",
                supporting_evidence_ids=[ev_id for c in conflicts for ev_id in c.evidence_ids],
                trace_id=trace_id
            )
            uncertainties.append(unc_conf)

        # 2. Uncertainty from missing required information
        if missing_items:
            unc_miss = UncertaintyItem(
                uncertainty_id=f"unc_miss_{trace_id or '0'}",
                level=UncertaintyLevel.CRITICAL if not evidence_items else UncertaintyLevel.MEDIUM,
                reason=f"Reasoning incomplete due to {len(missing_items)} missing required information item(s).",
                missing_information_refs=[m.missing_info_id for m in missing_items],
                insufficient_evidence_flag=len(evidence_items) == 0,
                trace_id=trace_id
            )
            uncertainties.append(unc_miss)

        # 3. Uncertainty from low evidence confidence
        low_conf_items = [e for e in evidence_items if e.confidence < 0.6]
        if low_conf_items:
            unc_qual = UncertaintyItem(
                uncertainty_id=f"unc_qual_{trace_id or '0'}",
                level=UncertaintyLevel.LOW,
                reason=f"Lower confidence detected in {len(low_conf_items)} evidence item(s).",
                supporting_evidence_ids=[e.evidence_id for e in low_conf_items],
                trace_id=trace_id
            )
            uncertainties.append(unc_qual)

        return uncertainties
