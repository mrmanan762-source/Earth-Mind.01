"""Publication Eligibility Validator for C.2 Knowledge Base.

Validates whether a canonical knowledge object satisfies all prerequisites for
publication into retrievable Knowledge Collections.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from modules.knowledge_base.enums import KnowledgeLifecycleState
from modules.knowledge_base.collections.models import KnowledgeObjectType
from modules.knowledge_base.publication.models import PublicationEligibilityResult
from modules.knowledge_base.provenance import Provenance
from modules.knowledge_base.assessment import SourceAssessment

# Forbidden lifecycle states that permanently block publication
FORBIDDEN_PUBLICATION_STATES = {
    KnowledgeLifecycleState.FAILED,
    KnowledgeLifecycleState.REJECTED,
    KnowledgeLifecycleState.INVALID,
    KnowledgeLifecycleState.RETIRED,
    KnowledgeLifecycleState.SUPERSEDED,
}

# Permitted prerequisite states eligible for publication transition
PERMITTED_PREREQUISITE_STATES = {
    KnowledgeLifecycleState.PROCESSED,
    KnowledgeLifecycleState.EMBEDDED,
    KnowledgeLifecycleState.INDEXED,
    KnowledgeLifecycleState.PENDING_REVIEW,
    KnowledgeLifecycleState.PUBLISHED,
}


class PublicationEligibilityValidator:
    """Validator enforcing publication eligibility requirements across canonical knowledge entities."""

    def evaluate_eligibility(
        self,
        knowledge_object_id: str,
        knowledge_object_type: KnowledgeObjectType = KnowledgeObjectType.DOCUMENT_VERSION,
        canonical_object: Optional[Any] = None,
        source_id: Optional[str] = None,
        document_id: Optional[str] = None,
        version_id: Optional[str] = None,
        provenance: Optional[Union[Provenance, Dict[str, Any]]] = None,
        metadata: Optional[Any] = None,
        source_assessment: Optional[Union[SourceAssessment, Dict[str, Any]]] = None,
        lifecycle_state: Optional[KnowledgeLifecycleState] = None,
        representations_available: bool = True,
        is_web_result: bool = False,
        is_web_result_reviewed: bool = False,
        is_blocked: bool = False,
        block_reason: Optional[str] = None,
        require_source_assessment: bool = False,
    ) -> PublicationEligibilityResult:
        """Evaluate if a canonical object is eligible for publication based on EarthMind publication rules."""
        reasons: List[str] = []
        missing_prerequisites: List[str] = []

        oid = knowledge_object_id.strip()

        # 1. Check if canonical object or identity exists
        if canonical_object is None and not oid:
            missing_prerequisites.append("canonical_object_exists")
            reasons.append("Canonical knowledge object or identity does not exist.")

        # Extract lineage fields from canonical_object if provided
        obj_source_id = source_id or getattr(canonical_object, "source_id", None)
        obj_document_id = document_id or getattr(canonical_object, "document_id", None)
        obj_version_id = version_id or getattr(canonical_object, "version_id", None)

        # 2. Source lineage validation
        if not obj_source_id or not str(obj_source_id).strip():
            missing_prerequisites.append("source_lineage_exists")
            reasons.append("Missing source lineage: source_id is required.")

        if knowledge_object_type in {KnowledgeObjectType.DOCUMENT_VERSION, KnowledgeObjectType.KNOWLEDGE_UNIT, KnowledgeObjectType.CHUNK}:
            if not obj_document_id or not str(obj_document_id).strip():
                missing_prerequisites.append("document_lineage_exists")
                reasons.append("Missing document lineage: document_id is required.")

        # 3. Provenance validation
        obj_provenance = provenance or getattr(canonical_object, "provenance", None)
        if obj_provenance is None:
            missing_prerequisites.append("provenance_exists")
            reasons.append("Missing processing provenance chain.")
        else:
            if isinstance(obj_provenance, Provenance):
                if not obj_provenance.is_complete:
                    missing_prerequisites.append("provenance_complete")
                    missing_fields = getattr(obj_provenance, "missing_fields", [])
                    reasons.append(f"Provenance chain is incomplete. Missing fields: {missing_fields}")

        # 4. Metadata validation
        obj_metadata = metadata or getattr(canonical_object, "metadata", None)
        if obj_metadata is None:
            missing_prerequisites.append("metadata_exists")
            reasons.append("Missing canonical metadata.")

        # 5. Source Assessment validation if required or present
        obj_assessment = source_assessment or getattr(canonical_object, "assessment", None)
        if require_source_assessment and obj_assessment is None:
            missing_prerequisites.append("source_assessment_exists")
            reasons.append("Source assessment is explicitly required for publication but missing.")

        # 6. Index representations check
        if not representations_available:
            missing_prerequisites.append("representations_available")
            reasons.append("Required vector or sparse representations are unavailable.")

        # 7. Lifecycle state validation
        active_state = lifecycle_state or getattr(canonical_object, "lifecycle_state", None) or getattr(canonical_object, "status", None)
        if isinstance(active_state, str):
            try:
                active_state = KnowledgeLifecycleState(active_state)
            except ValueError:
                pass

        if active_state in FORBIDDEN_PUBLICATION_STATES:
            missing_prerequisites.append("valid_lifecycle_state")
            reasons.append(f"Lifecycle state '{active_state}' strictly blocks publication.")
        elif active_state is not None and active_state not in PERMITTED_PREREQUISITE_STATES:
            missing_prerequisites.append("permitted_prerequisite_state")
            reasons.append(f"Lifecycle state '{active_state}' is not an eligible prerequisite state for publication.")

        # 8. Web Search Rule
        if is_web_result and not is_web_result_reviewed:
            missing_prerequisites.append("web_result_explicit_review")
            reasons.append("Web search results cannot be published automatically into permanent Knowledge Collections without explicit review and approval.")

        # 9. Explicit block rule
        if is_blocked:
            missing_prerequisites.append("unblocked_status")
            block_msg = block_reason or "Knowledge object is explicitly blocked from publication."
            reasons.append(block_msg)

        eligible = len(missing_prerequisites) == 0

        if eligible:
            reasons.append("Knowledge object satisfied all publication prerequisites.")

        return PublicationEligibilityResult(
            eligible=eligible,
            knowledge_object_id=oid,
            knowledge_object_type=knowledge_object_type,
            reasons=reasons,
            missing_prerequisites=missing_prerequisites,
            checked_at=datetime.now(timezone.utc),
        )
