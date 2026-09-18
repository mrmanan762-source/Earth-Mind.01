from typing import List
from modules.reasoning.enums import RelationshipType
from modules.reasoning.schemas import EvidenceItem, EvidenceRelationship


class EvidenceComparisonAnalyzer:
    """Analyzes evidence items to detect supporting, contradicting, temporal, and source relationships."""

    def analyze_relationships(self, evidence_items: List[EvidenceItem]) -> List[EvidenceRelationship]:
        relationships: List[EvidenceRelationship] = []

        for i in range(len(evidence_items)):
            for j in range(i + 1, len(evidence_items)):
                item_a = evidence_items[i]
                item_b = evidence_items[j]

                # 1. Source correlation
                if item_a.source == item_b.source:
                    relationships.append(
                        EvidenceRelationship(
                            relationship_id=f"rel_src_{item_a.evidence_id}_{item_b.evidence_id}",
                            source_evidence_ids=[item_a.evidence_id],
                            target_evidence_ids=[item_b.evidence_id],
                            relationship_type=RelationshipType.SOURCE_CORRELATION,
                            strength=0.9,
                            description=f"Common origin source: '{item_a.source}'",
                            trace_id=item_a.trace_id or item_b.trace_id
                        )
                    )

                # 2. Scope match supporting
                if item_a.scope == item_b.scope:
                    relationships.append(
                        EvidenceRelationship(
                            relationship_id=f"rel_scope_{item_a.evidence_id}_{item_b.evidence_id}",
                            source_evidence_ids=[item_a.evidence_id],
                            target_evidence_ids=[item_b.evidence_id],
                            relationship_type=RelationshipType.SUPPORTING,
                            strength=0.85,
                            description=f"Matching granularity scope: '{item_a.scope.value}'",
                            trace_id=item_a.trace_id or item_b.trace_id
                        )
                    )

                # 3. Temporal delta relationship
                if item_a.event_time and item_b.event_time:
                    relationships.append(
                        EvidenceRelationship(
                            relationship_id=f"rel_temp_{item_a.evidence_id}_{item_b.evidence_id}",
                            source_evidence_ids=[item_a.evidence_id],
                            target_evidence_ids=[item_b.evidence_id],
                            relationship_type=RelationshipType.TEMPORAL,
                            strength=0.75,
                            description=f"Temporal sequence between timestamps {item_a.event_time} and {item_b.event_time}",
                            trace_id=item_a.trace_id or item_b.trace_id
                        )
                    )

        return relationships
