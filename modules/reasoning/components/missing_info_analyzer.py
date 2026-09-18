from typing import List, Optional
from modules.reasoning.enums import EvidenceScope
from modules.reasoning.schemas import EvidenceItem, MissingInformationItem


class MissingInformationAnalyzer:
    """Identifies missing required evidence types and suggested resolutions."""

    def analyze_missing_info(
        self,
        task: str,
        evidence_items: List[EvidenceItem],
        trace_id: Optional[str] = None
    ) -> List[MissingInformationItem]:
        missing: List[MissingInformationItem] = []

        if not evidence_items:
            missing.append(
                MissingInformationItem(
                    missing_info_id=f"missing_primary_{trace_id or '0'}",
                    required_data_type="primary_context_data",
                    scope=EvidenceScope.FIELD,
                    importance="HIGH",
                    impact_on_reasoning="No primary evidence items provided for analysis.",
                    suggested_resolution="Supply field observation or sensor reading.",
                    trace_id=trace_id
                )
            )

        return missing
