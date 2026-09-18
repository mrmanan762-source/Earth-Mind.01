from typing import Any, Dict, List, Optional, Tuple
from modules.context.schemas import ContextItem, ContextResult
from modules.reasoning.enums import (
    AssumptionType,
    ConflictType,
    EvidenceScope,
    RelationshipType,
)
from modules.reasoning.errors import InvalidEvidenceError
from modules.reasoning.schemas import (
    AssumptionItem,
    EvidenceConflict,
    EvidenceItem,
    EvidenceRelationship,
    MissingInformationItem,
    ReasoningInput,
)


class EvidenceManager:
    """Manages evidence extraction, assumption separation, relationship analysis, and conflict detection."""

    def prepare_evidence(
        self, input_data: ReasoningInput
    ) -> Tuple[List[EvidenceItem], List[AssumptionItem], List[MissingInformationItem]]:
        """Extract evidence items from ReasoningInput and its prepared_context.

        Preserves provenance, distinguishes evidence from assumptions, and identifies missing information.
        """
        evidence_items: List[EvidenceItem] = []
        assumption_items: List[AssumptionItem] = []
        missing_items: List[MissingInformationItem] = []

        # 1. Direct evidence items passed in request
        for item in input_data.evidence_items:
            if not item.evidence_id:
                raise InvalidEvidenceError("unknown", "Evidence item missing evidence_id")

            if item.is_assumption:
                # Direct assumption passed as evidence item
                assumption = AssumptionItem(
                    assumption_id=f"assump_{item.evidence_id}",
                    description=str(item.content),
                    assumption_type=AssumptionType.DEFAULT_BASELINE,
                    rationale="Declared as assumption in input evidence item",
                    trace_id=item.trace_id or input_data.trace_id,
                    metadata=item.metadata
                )
                assumption_items.append(assumption)
            else:
                evidence_items.append(item)

        # 2. Extract evidence items from ContextResult if present
        if input_data.prepared_context and isinstance(input_data.prepared_context, ContextResult):
            context_res: ContextResult = input_data.prepared_context
            for idx, c_item in enumerate(context_res.items):
                ev_id = f"ev_ctx_{c_item.context_id}"

                # Determine scope mapping
                scope = EvidenceScope.FIELD
                if c_item.field_id:
                    scope = EvidenceScope.FIELD
                elif c_item.crop_cycle_id:
                    scope = EvidenceScope.CROP_CYCLE
                elif c_item.farm_id:
                    scope = EvidenceScope.FARM

                # Map conflict status
                conflict_status_str = c_item.conflict_status.value if hasattr(c_item.conflict_status, "value") else str(c_item.conflict_status)

                ev_item = EvidenceItem(
                    evidence_id=ev_id,
                    source=f"context_manager:{c_item.source}",
                    source_id=c_item.source_id or c_item.context_id,
                    data_reference=f"entity:{c_item.entity_type}/{c_item.entity_id}",
                    content=c_item.content,
                    scope=scope,
                    event_time=c_item.event_time,
                    recorded_at=c_item.recorded_at,
                    valid_from=c_item.valid_from,
                    valid_until=c_item.valid_until,
                    confidence=c_item.confidence,
                    reliability=c_item.relevance_score,
                    provenance={
                        "context_id": c_item.context_id,
                        "data_type": c_item.data_type,
                        "entity_type": c_item.entity_type,
                        "entity_id": c_item.entity_id,
                        "transformations": [t.model_dump() for t in c_item.transformation_history],
                    },
                    conflict_status=conflict_status_str,
                    is_assumption=False,
                    trace_id=c_item.trace_id or input_data.trace_id,
                    metadata=c_item.metadata
                )
                evidence_items.append(ev_item)

        # 3. If policy permits assumptions and critical evidence is missing, declare assumption explicitly
        if not evidence_items and input_data.policy.allow_assumptions:
            fallback_assumption = AssumptionItem(
                assumption_id=f"assump_fallback_{input_data.request_id}",
                description="No direct evidence provided; assuming nominal baseline conditions for analysis.",
                assumption_type=AssumptionType.MISSING_DATA_FALLBACK,
                rationale="Fallback assumption declared because no direct evidence items were supplied.",
                affected_claims=["all_findings"],
                confidence_penalty=0.2,
                trace_id=input_data.trace_id
            )
            assumption_items.append(fallback_assumption)

            missing_info = MissingInformationItem(
                missing_info_id=f"missing_{input_data.request_id}_1",
                required_data_type="primary_observation_data",
                scope=EvidenceScope.FIELD,
                importance="HIGH",
                impact_on_reasoning="No primary observational evidence available in input request.",
                suggested_resolution="Supply contextual field observations or sensor data.",
                trace_id=input_data.trace_id
            )
            missing_items.append(missing_info)

        return evidence_items, assumption_items, missing_items

    def identify_relationships(self, evidence_items: List[EvidenceItem]) -> List[EvidenceRelationship]:
        """Analyze evidence items to detect relationships (supporting, temporal, source correlation, etc.)."""
        relationships: List[EvidenceRelationship] = []

        for i in range(len(evidence_items)):
            for j in range(i + 1, len(evidence_items)):
                item_a = evidence_items[i]
                item_b = evidence_items[j]

                # Source correlation relationship
                if item_a.source == item_b.source:
                    rel = EvidenceRelationship(
                        relationship_id=f"rel_src_{item_a.evidence_id}_{item_b.evidence_id}",
                        source_evidence_ids=[item_a.evidence_id],
                        target_evidence_ids=[item_b.evidence_id],
                        relationship_type=RelationshipType.SOURCE_CORRELATION,
                        strength=0.9,
                        description=f"Evidence items share common source provider '{item_a.source}'",
                        trace_id=item_a.trace_id or item_b.trace_id
                    )
                    relationships.append(rel)

                # Scope matching relationship
                if item_a.scope == item_b.scope and item_a.scope != EvidenceScope.GLOBAL:
                    rel = EvidenceRelationship(
                        relationship_id=f"rel_scope_{item_a.evidence_id}_{item_b.evidence_id}",
                        source_evidence_ids=[item_a.evidence_id],
                        target_evidence_ids=[item_b.evidence_id],
                        relationship_type=RelationshipType.SUPPORTING,
                        strength=0.8,
                        description=f"Evidence items share common scope level '{item_a.scope.value}'",
                        trace_id=item_a.trace_id or item_b.trace_id
                    )
                    relationships.append(rel)

        return relationships

    def detect_conflicts(self, evidence_items: List[EvidenceItem]) -> List[EvidenceConflict]:
        """Detect conflicting evidence items without auto-resolving or discarding them."""
        conflicts: List[EvidenceConflict] = []

        for i in range(len(evidence_items)):
            for j in range(i + 1, len(evidence_items)):
                item_a = evidence_items[i]
                item_b = evidence_items[j]

                # Check explicitly flagged conflict status
                if item_a.conflict_status == "CONFLICTED" or item_b.conflict_status == "CONFLICTED":
                    conflict = EvidenceConflict(
                        conflict_id=f"conflict_{item_a.evidence_id}_{item_b.evidence_id}",
                        evidence_ids=[item_a.evidence_id, item_b.evidence_id],
                        sources=[item_a.source, item_b.source],
                        timestamps=[t for t in [item_a.event_time, item_b.event_time] if t],
                        conflict_type=ConflictType.VALUE_DISCREPANCY,
                        description=f"Conflict detected between evidence {item_a.evidence_id} and {item_b.evidence_id}",
                        confidence_delta=0.2,
                        is_resolved=False,  # Core Rule 3: Conflict must be preserved, never silently resolved
                        trace_id=item_a.trace_id or item_b.trace_id
                    )
                    conflicts.append(conflict)

                # Value discrepancy check for numeric content under same data reference
                elif item_a.data_reference and item_a.data_reference == item_b.data_reference:
                    val_a = item_a.content
                    val_b = item_b.content
                    if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                        if abs(val_a - val_b) > 0.01:
                            conflict = EvidenceConflict(
                                conflict_id=f"conflict_val_{item_a.evidence_id}_{item_b.evidence_id}",
                                evidence_ids=[item_a.evidence_id, item_b.evidence_id],
                                sources=[item_a.source, item_b.source],
                                timestamps=[t for t in [item_a.event_time, item_b.event_time] if t],
                                conflict_type=ConflictType.VALUE_DISCREPANCY,
                                description=f"Value discrepancy for reference '{item_a.data_reference}': {val_a} vs {val_b}",
                                confidence_delta=0.3,
                                is_resolved=False,  # Core Rule 3: Preserve conflict
                                trace_id=item_a.trace_id or item_b.trace_id
                            )
                            conflicts.append(conflict)

        return conflicts
