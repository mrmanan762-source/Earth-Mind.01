from typing import List, Optional
from modules.reasoning.schemas import EvidenceConflict, EvidenceItem, ReasoningHypothesis


class HypothesisAnalyzer:
    """Generates and evaluates bounded causal/explanative hypotheses against evidence.

    Rule Enforcement: Hypotheses are bounded possibilities, NOT facts.
    """

    def generate_hypotheses(
        self,
        task: str,
        evidence_items: List[EvidenceItem],
        conflicts: List[EvidenceConflict],
        trace_id: Optional[str] = None
    ) -> List[ReasoningHypothesis]:
        hypotheses: List[ReasoningHypothesis] = []

        if evidence_items:
            hyp = ReasoningHypothesis(
                hypothesis_id=f"hyp_primary_{trace_id or '0'}",
                description=f"Candidate explanation for task '{task}' based on available evidence.",
                supporting_evidence_ids=[e.evidence_id for e in evidence_items],
                contradicting_evidence_ids=[ev_id for c in conflicts for ev_id in c.evidence_ids],
                confidence_score=0.75 if not conflicts else 0.50,
                status="PROPOSED",
                trace_id=trace_id
            )
            hypotheses.append(hyp)

        return hypotheses
