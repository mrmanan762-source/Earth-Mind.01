import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.logging.logger import get_logger
from core.interfaces.boundary import IPromotionGovernanceEngine
from core.errors.exceptions import (
    BoundaryValidationError,
    PromotionNotAllowedError,
    ScopeViolationBoundaryError,
    PrivacyBoundaryError,
)
from modules.context.schemas import PrivacyLevel
from modules.context.boundary.enums import (
    KnowledgeClassification,
    ContextSourceType,
    ContextOwnership,
    ContextScope,
    PersistenceIntent,
    TransitionType,
    GovernanceOutcome,
    GovernanceState,
    GovernanceFailureReason,
)
from modules.context.boundary.models import (
    PromotionCandidate,
    GovernanceDecision,
    PromotionRecord,
)

logger = get_logger("modules.context.boundary.governance")


class ContextGovernanceEngine(IPromotionGovernanceEngine):
    """
    Executable governance engine controlling cross-domain context promotion between RAG and Memory (C.3.3).

    Enforces:
    - Default-deny policy for cross-domain movement
    - Ownership-transition control
    - Scope-transition control (blocking unsafe scope widening like farmer/field -> global)
    - Persistence-transition control (blocking temporary/session -> persistent without review)
    - Provenance preservation & enrichment
    - Privacy & PII protection
    - Observation & Web evidence controls
    - Lifecycle protection (governance evaluates; target system owns storage lifecycle)
    - Traceability via explicit GovernanceDecision and PromotionRecord
    """

    def __init__(self, policy_name: str = "DEFAULT_EARTHMIND_GOVERNANCE_POLICY"):
        self.policy_name = policy_name

    def evaluate_candidate(self, candidate: PromotionCandidate) -> GovernanceDecision:
        """Evaluate a cross-domain promotion candidate against C.3 governance policies."""
        logger.debug(f"Evaluating promotion candidate '{candidate.candidate_id}' ({candidate.requested_transition.value})")

        violations: List[str] = []

        # 1. Candidate structural validation
        if not candidate.candidate_id or not candidate.candidate_id.strip():
            violations.append("Candidate ID is missing or empty.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.INVALID,
                state=GovernanceState.BLOCKED,
                reason="Invalid candidate structure: Candidate ID is missing.",
                failure_reason=GovernanceFailureReason.INVALID_CANDIDATE,
                violations=violations,
            )

        if not candidate.content and candidate.content != 0 and candidate.content is not False:
            violations.append("Candidate content is empty.")

        # 2. Provenance preservation check
        if candidate.provenance is None or not isinstance(candidate.provenance, dict) or len(candidate.provenance) == 0:
            violations.append("Missing or empty source provenance chain.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.INVALID,
                state=GovernanceState.BLOCKED,
                reason="Invalid candidate: Source provenance chain is missing or empty.",
                failure_reason=GovernanceFailureReason.MISSING_PROVENANCE,
                violations=violations,
            )

        # 3. Transition type dispatch & candidate domain alignment check
        transition = candidate.requested_transition

        if transition == TransitionType.RAG_TO_MEMORY:
            return self._evaluate_rag_to_memory(candidate, violations)
        elif transition == TransitionType.MEMORY_TO_RAG:
            return self._evaluate_memory_to_rag(candidate, violations)
        else:
            violations.append(f"Unsupported transition type '{transition}'.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.BLOCKED,
                state=GovernanceState.BLOCKED,
                reason=f"Transition type '{transition}' is not supported by governance policy.",
                failure_reason=GovernanceFailureReason.OWNERSHIP_TRANSITION_BLOCKED,
                violations=violations,
            )

    def _evaluate_rag_to_memory(
        self, candidate: PromotionCandidate, violations: List[str]
    ) -> GovernanceDecision:
        """Evaluate RAG -> Memory promotion candidate."""
        # Check source ownership
        if candidate.ownership not in {ContextOwnership.RAG_OWNED, ContextOwnership.EXTERNAL_OWNED}:
            violations.append(
                f"RAG_TO_MEMORY transition requires source ownership RAG_OWNED or EXTERNAL_OWNED, got '{candidate.ownership.value}'."
            )
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.BLOCKED,
                state=GovernanceState.BLOCKED,
                reason="Ownership transition blocked: RAG_TO_MEMORY source must be RAG_OWNED or EXTERNAL_OWNED.",
                failure_reason=GovernanceFailureReason.OWNERSHIP_TRANSITION_BLOCKED,
                violations=violations,
            )

        # Target ownership must be MEMORY_OWNED
        target_ownership = candidate.target_ownership or ContextOwnership.MEMORY_OWNED
        if target_ownership != ContextOwnership.MEMORY_OWNED:
            violations.append(f"RAG_TO_MEMORY target ownership must be MEMORY_OWNED, got '{target_ownership.value}'.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.BLOCKED,
                state=GovernanceState.BLOCKED,
                reason="Target ownership for RAG_TO_MEMORY must be MEMORY_OWNED.",
                failure_reason=GovernanceFailureReason.OWNERSHIP_TRANSITION_BLOCKED,
                violations=violations,
            )

        # Target scope validation
        target_scope = candidate.target_scope or ContextScope.FARMER
        farmer_scopes = {ContextScope.FARMER, ContextScope.FARM, ContextScope.FIELD, ContextScope.CROP_CYCLE}

        if target_scope not in farmer_scopes and target_scope != ContextScope.SESSION:
            violations.append(f"Memory target scope must be a farmer/farm/field/session scope, got '{target_scope.value}'.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.BLOCKED,
                state=GovernanceState.BLOCKED,
                reason=f"Scope transition blocked: Memory target scope '{target_scope.value}' is invalid.",
                failure_reason=GovernanceFailureReason.INVALID_SCOPE_TRANSITION,
                violations=violations,
            )

        # Farmer entity reference requirement for farmer/farm/field target scopes
        if target_scope in farmer_scopes and not candidate.farmer_id:
            violations.append(f"Memory promotion to target scope '{target_scope.value}' requires farmer_id reference.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.BLOCKED,
                state=GovernanceState.BLOCKED,
                reason=f"Scope transition blocked: Missing farmer_id for target scope '{target_scope.value}'.",
                failure_reason=GovernanceFailureReason.INVALID_SCOPE_TRANSITION,
                violations=violations,
            )

        # Persistence intent transition check
        source_persistence = candidate.persistence_intent
        target_persistence = candidate.target_persistence_intent or PersistenceIntent.PERSISTENT

        if source_persistence == PersistenceIntent.TEMPORARY:
            violations.append("TEMPORARY RAG/External evidence cannot be automatically promoted to PERSISTENT Memory.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.BLOCKED,
                state=GovernanceState.BLOCKED,
                reason="Persistence transition blocked: TEMPORARY evidence cannot become PERSISTENT Memory.",
                failure_reason=GovernanceFailureReason.PERSISTENCE_TRANSITION_BLOCKED,
                violations=violations,
            )

        if source_persistence == PersistenceIntent.SESSION_SCOPED and target_persistence == PersistenceIntent.PERSISTENT:
            violations.append("SESSION_SCOPED context requires explicit review to promote to PERSISTENT Memory.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.REQUIRES_REVIEW,
                state=GovernanceState.REQUIRES_REVIEW,
                reason="Persistence transition requires review: SESSION_SCOPED context promotion to PERSISTENT Memory.",
                failure_reason=GovernanceFailureReason.REVIEW_REQUIRED,
                violations=violations,
            )

        # Web / External current data non-automatic persistence rule
        if candidate.classification == KnowledgeClassification.EXTERNAL_CURRENT_DATA:
            violations.append("EXTERNAL_CURRENT_DATA (web search / external service) requires review before becoming persistent Memory.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.REQUIRES_REVIEW,
                state=GovernanceState.REQUIRES_REVIEW,
                reason="Web / External current data requires formal review before becoming persistent Memory.",
                failure_reason=GovernanceFailureReason.REVIEW_REQUIRED,
                violations=violations,
            )

        # Observation classification rule
        if candidate.classification == KnowledgeClassification.OBSERVATION:
            violations.append("OBSERVATION evidence requires explicit review before persistent Memory promotion.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.REQUIRES_REVIEW,
                state=GovernanceState.REQUIRES_REVIEW,
                reason="Observation evidence requires review before persistent Memory promotion.",
                failure_reason=GovernanceFailureReason.REVIEW_REQUIRED,
                violations=violations,
            )

        # All checks passed for RAG_TO_MEMORY
        return self._build_decision(
            candidate=candidate,
            outcome=GovernanceOutcome.AUTO_ALLOWED,
            state=GovernanceState.AUTO_ALLOWED,
            reason="RAG to Memory promotion candidate passed all C.3.3 governance checks.",
            target_lifecycle_requirements="MEMORY_INGESTION_AND_PERSISTENCE_LIFECYCLE",
            violations=violations,
        )

    def _evaluate_memory_to_rag(
        self, candidate: PromotionCandidate, violations: List[str]
    ) -> GovernanceDecision:
        """Evaluate Memory -> RAG promotion candidate."""
        # Check source ownership
        if candidate.ownership != ContextOwnership.MEMORY_OWNED:
            violations.append(
                f"MEMORY_TO_RAG transition requires source ownership MEMORY_OWNED, got '{candidate.ownership.value}'."
            )
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.BLOCKED,
                state=GovernanceState.BLOCKED,
                reason="Ownership transition blocked: MEMORY_TO_RAG source must be MEMORY_OWNED.",
                failure_reason=GovernanceFailureReason.OWNERSHIP_TRANSITION_BLOCKED,
                violations=violations,
            )

        # Target ownership must be RAG_OWNED
        target_ownership = candidate.target_ownership or ContextOwnership.RAG_OWNED
        if target_ownership != ContextOwnership.RAG_OWNED:
            violations.append(f"MEMORY_TO_RAG target ownership must be RAG_OWNED, got '{target_ownership.value}'.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.BLOCKED,
                state=GovernanceState.BLOCKED,
                reason="Target ownership for MEMORY_TO_RAG must be RAG_OWNED.",
                failure_reason=GovernanceFailureReason.OWNERSHIP_TRANSITION_BLOCKED,
                violations=violations,
            )

        # Privacy and PII Protection checks
        if candidate.is_pii:
            violations.append("Candidate contains PII and cannot be promoted to general RAG knowledge.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.BLOCKED,
                state=GovernanceState.BLOCKED,
                reason="Privacy policy violation: PII information cannot be promoted to general RAG knowledge.",
                failure_reason=GovernanceFailureReason.PRIVACY_POLICY_VIOLATION,
                violations=violations,
            )

        if candidate.privacy_level == PrivacyLevel.FARMER_PII:
            violations.append(f"Candidate privacy level '{candidate.privacy_level.value}' prohibits general RAG promotion.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.BLOCKED,
                state=GovernanceState.BLOCKED,
                reason=f"Privacy policy violation: Privacy level '{candidate.privacy_level.value}' prohibits RAG promotion.",
                failure_reason=GovernanceFailureReason.PRIVACY_POLICY_VIOLATION,
                violations=violations,
            )

        # Scope Widening Checks (Farmer / Farm / Field -> Global / Regional)
        farmer_scopes = {ContextScope.FARMER, ContextScope.FARM, ContextScope.FIELD, ContextScope.CROP_CYCLE}
        target_scope = candidate.target_scope or ContextScope.GLOBAL

        if candidate.scope in farmer_scopes and target_scope in {ContextScope.GLOBAL, ContextScope.REGIONAL}:
            violations.append(
                f"Scope transition from private scope '{candidate.scope.value}' to general RAG scope '{target_scope.value}' requires curation and anonymization review."
            )
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.REQUIRES_REVIEW,
                state=GovernanceState.REQUIRES_REVIEW,
                reason=f"Scope transition requires review: Private scope '{candidate.scope.value}' promotion to general RAG '{target_scope.value}' requires curation.",
                failure_reason=GovernanceFailureReason.REVIEW_REQUIRED,
                violations=violations,
            )

        # Persistence intent check
        if candidate.persistence_intent == PersistenceIntent.TEMPORARY:
            violations.append("TEMPORARY memory cannot be promoted to persistent RAG knowledge.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.BLOCKED,
                state=GovernanceState.BLOCKED,
                reason="Persistence transition blocked: TEMPORARY memory cannot become persistent RAG knowledge.",
                failure_reason=GovernanceFailureReason.PERSISTENCE_TRANSITION_BLOCKED,
                violations=violations,
            )

        # Observation classification in Memory -> RAG requires review
        if candidate.classification == KnowledgeClassification.OBSERVATION:
            violations.append("Observation memory requires explicit curation review before becoming general RAG knowledge.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.REQUIRES_REVIEW,
                state=GovernanceState.REQUIRES_REVIEW,
                reason="Observation memory requires curation review prior to C.2 RAG knowledge ingestion.",
                failure_reason=GovernanceFailureReason.REVIEW_REQUIRED,
                violations=violations,
            )

        # If classification is FARMER_KNOWLEDGE or FIELD_KNOWLEDGE, promotion to RAG requires curation review
        if candidate.classification in {KnowledgeClassification.FARMER_KNOWLEDGE, KnowledgeClassification.FIELD_KNOWLEDGE}:
            violations.append(f"Classification '{candidate.classification.value}' requires curation review and anonymization for RAG promotion.")
            return self._build_decision(
                candidate=candidate,
                outcome=GovernanceOutcome.REQUIRES_REVIEW,
                state=GovernanceState.REQUIRES_REVIEW,
                reason=f"Memory classification '{candidate.classification.value}' requires review before C.2 knowledge ingestion.",
                failure_reason=GovernanceFailureReason.REVIEW_REQUIRED,
                violations=violations,
            )

        # All checks passed for MEMORY_TO_RAG
        return self._build_decision(
            candidate=candidate,
            outcome=GovernanceOutcome.AUTO_ALLOWED,
            state=GovernanceState.AUTO_ALLOWED,
            reason="Memory to RAG promotion candidate passed all C.3.3 governance checks.",
            target_lifecycle_requirements="C2_INGESTION_VALIDATION_AND_PUBLICATION_PIPELINE",
            violations=violations,
        )

    def execute_governance(self, candidate: PromotionCandidate) -> PromotionRecord:
        """Evaluate candidate and produce a formal traceable PromotionRecord."""
        decision = self.evaluate_candidate(candidate)

        enriched_provenance = dict(candidate.provenance)
        enriched_provenance.update({
            "governance_decision_id": decision.decision_id,
            "governance_outcome": decision.outcome.value,
            "governance_evaluated_at": decision.timestamp,
            "policy_applied": self.policy_name,
        })

        return PromotionRecord(
            candidate_id=candidate.candidate_id,
            transition_type=candidate.requested_transition,
            source_domain=candidate.source_type.value,
            target_domain=candidate.target_domain,
            source_ownership=candidate.ownership,
            target_ownership=decision.target_ownership,
            source_scope=candidate.scope,
            target_scope=decision.target_scope,
            outcome=decision.outcome,
            decision=decision,
            reason=decision.reason,
            policy_reference=self.policy_name,
            created_at=datetime.now(timezone.utc).isoformat(),
            reviewed_at=decision.reviewed_at,
            reviewer=decision.reviewer_id,
            source_provenance=enriched_provenance,
            target_lifecycle_reference=decision.target_lifecycle_requirements,
            trace_id=candidate.trace_id,
            status=decision.state,
            metadata=candidate.metadata,
        )

    def approve_review(
        self,
        candidate: PromotionCandidate,
        reviewer_id: str,
        reason: str = "Approved by authorized review",
    ) -> PromotionRecord:
        """Approve a promotion candidate that required review."""
        if not reviewer_id or not reviewer_id.strip():
            raise BoundaryValidationError("Review approval requires a non-empty reviewer_id.")

        initial_decision = self.evaluate_candidate(candidate)
        if initial_decision.outcome not in {GovernanceOutcome.REQUIRES_REVIEW, GovernanceOutcome.AUTO_ALLOWED}:
            raise PromotionNotAllowedError(
                source_ownership=candidate.ownership.value,
                target_ownership=(candidate.target_ownership or ContextOwnership.MEMORY_OWNED).value,
                reason=f"Cannot approve candidate in state '{initial_decision.state.value}'. Only candidates requiring review can be approved.",
            )

        now_iso = datetime.now(timezone.utc).isoformat()

        target_lifecycle = "MEMORY_INGESTION_AND_PERSISTENCE_LIFECYCLE"
        if candidate.requested_transition == TransitionType.MEMORY_TO_RAG:
            target_lifecycle = "C2_INGESTION_VALIDATION_AND_PUBLICATION_PIPELINE"

        approved_decision = self._build_decision(
            candidate=candidate,
            outcome=GovernanceOutcome.AUTO_ALLOWED,
            state=GovernanceState.APPROVED,
            reason=f"Promotion approved by reviewer '{reviewer_id}': {reason}",
            target_lifecycle_requirements=target_lifecycle,
            reviewed_at=now_iso,
            reviewer_id=reviewer_id,
        )

        enriched_provenance = dict(candidate.provenance)
        enriched_provenance.update({
            "governance_decision_id": approved_decision.decision_id,
            "governance_outcome": approved_decision.outcome.value,
            "reviewed_by": reviewer_id,
            "reviewed_at": now_iso,
            "review_reason": reason,
        })

        return PromotionRecord(
            candidate_id=candidate.candidate_id,
            transition_type=candidate.requested_transition,
            source_domain=candidate.source_type.value,
            target_domain=candidate.target_domain,
            source_ownership=candidate.ownership,
            target_ownership=approved_decision.target_ownership,
            source_scope=candidate.scope,
            target_scope=approved_decision.target_scope,
            outcome=GovernanceOutcome.AUTO_ALLOWED,
            decision=approved_decision,
            reason=approved_decision.reason,
            policy_reference=self.policy_name,
            created_at=now_iso,
            reviewed_at=now_iso,
            reviewer=reviewer_id,
            source_provenance=enriched_provenance,
            target_lifecycle_reference=approved_decision.target_lifecycle_requirements,
            trace_id=candidate.trace_id,
            status=GovernanceState.APPROVED,
            metadata=candidate.metadata,
        )

    def reject_review(
        self,
        candidate: PromotionCandidate,
        reviewer_id: str,
        reason: str = "Rejected during review",
    ) -> PromotionRecord:
        """Reject a promotion candidate that required review."""
        if not reviewer_id or not reviewer_id.strip():
            raise BoundaryValidationError("Review rejection requires a non-empty reviewer_id.")

        now_iso = datetime.now(timezone.utc).isoformat()

        rejected_decision = self._build_decision(
            candidate=candidate,
            outcome=GovernanceOutcome.BLOCKED,
            state=GovernanceState.REJECTED,
            reason=f"Promotion rejected by reviewer '{reviewer_id}': {reason}",
            failure_reason=GovernanceFailureReason.TARGET_POLICY_REJECTED,
            reviewed_at=now_iso,
            reviewer_id=reviewer_id,
        )

        enriched_provenance = dict(candidate.provenance)
        enriched_provenance.update({
            "governance_decision_id": rejected_decision.decision_id,
            "governance_outcome": rejected_decision.outcome.value,
            "rejected_by": reviewer_id,
            "rejected_at": now_iso,
            "rejection_reason": reason,
        })

        return PromotionRecord(
            candidate_id=candidate.candidate_id,
            transition_type=candidate.requested_transition,
            source_domain=candidate.source_type.value,
            target_domain=candidate.target_domain,
            source_ownership=candidate.ownership,
            target_ownership=rejected_decision.target_ownership,
            source_scope=candidate.scope,
            target_scope=rejected_decision.target_scope,
            outcome=GovernanceOutcome.BLOCKED,
            decision=rejected_decision,
            reason=rejected_decision.reason,
            policy_reference=self.policy_name,
            created_at=now_iso,
            reviewed_at=now_iso,
            reviewer=reviewer_id,
            source_provenance=enriched_provenance,
            target_lifecycle_reference=None,
            trace_id=candidate.trace_id,
            status=GovernanceState.REJECTED,
            metadata=candidate.metadata,
        )

    def _build_decision(
        self,
        candidate: PromotionCandidate,
        outcome: GovernanceOutcome,
        state: GovernanceState,
        reason: str,
        failure_reason: Optional[GovernanceFailureReason] = None,
        target_lifecycle_requirements: Optional[str] = None,
        violations: Optional[List[str]] = None,
        reviewed_at: Optional[str] = None,
        reviewer_id: Optional[str] = None,
    ) -> GovernanceDecision:
        """Helper to construct a standard GovernanceDecision contract."""
        target_ownership = candidate.target_ownership or (
            ContextOwnership.MEMORY_OWNED
            if candidate.requested_transition == TransitionType.RAG_TO_MEMORY
            else ContextOwnership.RAG_OWNED
        )
        target_scope = candidate.target_scope or (
            ContextScope.FARMER
            if candidate.requested_transition == TransitionType.RAG_TO_MEMORY
            else ContextScope.GLOBAL
        )
        target_persistence = candidate.target_persistence_intent or PersistenceIntent.PERSISTENT

        return GovernanceDecision(
            candidate_id=candidate.candidate_id,
            transition_type=candidate.requested_transition,
            outcome=outcome,
            state=state,
            reason=reason,
            violations=violations or [],
            failure_reason=failure_reason,
            applicable_policy=self.policy_name,
            source_ownership=candidate.ownership,
            target_ownership=target_ownership,
            source_scope=candidate.scope,
            target_scope=target_scope,
            source_persistence_intent=candidate.persistence_intent,
            target_persistence_intent=target_persistence,
            source_lifecycle=candidate.lifecycle_status,
            target_lifecycle_requirements=target_lifecycle_requirements,
            provenance=dict(candidate.provenance),
            trace_id=candidate.trace_id,
            reviewed_at=reviewed_at,
            reviewer_id=reviewer_id,
            metadata=dict(candidate.metadata),
        )
