from typing import List
from modules.reasoning.enums import ConflictType
from modules.reasoning.schemas import EvidenceConflict, EvidenceItem


class ConflictAnalyzer:
    """Detects and preserves evidence conflicts without auto-resolving or discarding them.

    Core Rule 3 Enforced: Conflicting evidence must remain represented.
    Core Rule 4 Enforced: Priority/reliability influences analysis but does not automatically establish truth.
    """

    def analyze_conflicts(self, evidence_items: List[EvidenceItem]) -> List[EvidenceConflict]:
        conflicts: List[EvidenceConflict] = []

        for i in range(len(evidence_items)):
            for j in range(i + 1, len(evidence_items)):
                item_a = evidence_items[i]
                item_b = evidence_items[j]

                # Explicitly marked conflict status
                if item_a.conflict_status == "CONFLICTED" or item_b.conflict_status == "CONFLICTED":
                    conflicts.append(
                        EvidenceConflict(
                            conflict_id=f"conflict_{item_a.evidence_id}_{item_b.evidence_id}",
                            evidence_ids=[item_a.evidence_id, item_b.evidence_id],
                            sources=[item_a.source, item_b.source],
                            timestamps=[t for t in [item_a.event_time, item_b.event_time] if t],
                            conflict_type=ConflictType.VALUE_DISCREPANCY,
                            description=f"Direct conflict between evidence {item_a.evidence_id} and {item_b.evidence_id}",
                            confidence_delta=0.25,
                            is_resolved=False,  # Core Rule 3: Conflict preserved
                            trace_id=item_a.trace_id or item_b.trace_id
                        )
                    )

                # Value discrepancy for matching data reference
                elif item_a.data_reference and item_a.data_reference == item_b.data_reference:
                    val_a = item_a.content
                    val_b = item_b.content
                    if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                        if abs(val_a - val_b) > 0.01:
                            conflicts.append(
                                EvidenceConflict(
                                    conflict_id=f"conflict_val_{item_a.evidence_id}_{item_b.evidence_id}",
                                    evidence_ids=[item_a.evidence_id, item_b.evidence_id],
                                    sources=[item_a.source, item_b.source],
                                    timestamps=[t for t in [item_a.event_time, item_b.event_time] if t],
                                    conflict_type=ConflictType.VALUE_DISCREPANCY,
                                    description=f"Discrepancy for reference '{item_a.data_reference}': {val_a} vs {val_b}",
                                    confidence_delta=0.30,
                                    is_resolved=False,  # Core Rule 3: Preserve conflict
                                    trace_id=item_a.trace_id or item_b.trace_id
                                )
                            )

        return conflicts
