"""Canonical Versioning and Lifecycle Engine for EarthMind Knowledge Base.

Manages knowledge versioning, explicit publication state transitions, supersession,
retirement, failure/rejection handling, and historical auditability without storage or
retrieval engine dependencies.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field, field_validator

from modules.knowledge_base.enums import DocumentVersionStatus, KnowledgeLifecycleState
from modules.knowledge_base.canonical_models import DocumentVersion


class InvalidLifecycleTransitionError(Exception):
    """Raised when an invalid or illegal lifecycle state transition is attempted."""
    pass


class LifecycleTransitionRecord(BaseModel):
    """Auditable record of a knowledge lifecycle state transition."""

    transition_id: str = Field(..., description="Unique transition record identifier")
    object_id: str = Field(..., description="Identifier of canonical object transitioning state")
    object_type: str = Field("DocumentVersion", description="Type of object transitioning state")
    previous_state: KnowledgeLifecycleState = Field(..., description="State prior to transition")
    new_state: KnowledgeLifecycleState = Field(..., description="Target state after transition")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Transition timestamp")
    reason: Optional[str] = Field(None, description="Reason or justification for state transition")
    actor: Optional[str] = Field(None, description="Actor or system process initiating state transition")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context or metadata")

    @field_validator("transition_id", "object_id", "object_type")
    @classmethod
    def validate_non_empty_strings(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("String fields in LifecycleTransitionRecord must be non-empty.")
        return v.strip()


class KnowledgeLifecycleEngine:
    """Manages knowledge versioning, state transitions, supersession, and retirement.

    Enforces explicit publication state transition rules (e.g., PENDING_REVIEW -> PUBLISHED)
    and guarantees version immutability and historical traceability.
    """

    ALLOWED_TRANSITIONS: Dict[KnowledgeLifecycleState, Set[KnowledgeLifecycleState]] = {
        KnowledgeLifecycleState.RECEIVED: {
            KnowledgeLifecycleState.PROCESSING,
            KnowledgeLifecycleState.FAILED,
            KnowledgeLifecycleState.INVALID,
        },
        KnowledgeLifecycleState.PROCESSING: {
            KnowledgeLifecycleState.PROCESSED,
            KnowledgeLifecycleState.FAILED,
            KnowledgeLifecycleState.REJECTED,
            KnowledgeLifecycleState.INVALID,
        },
        KnowledgeLifecycleState.PROCESSED: {
            KnowledgeLifecycleState.EMBEDDED,
            KnowledgeLifecycleState.FAILED,
            KnowledgeLifecycleState.REJECTED,
            KnowledgeLifecycleState.INVALID,
        },
        KnowledgeLifecycleState.EMBEDDED: {
            KnowledgeLifecycleState.INDEXED,
            KnowledgeLifecycleState.FAILED,
            KnowledgeLifecycleState.REJECTED,
            KnowledgeLifecycleState.INVALID,
        },
        KnowledgeLifecycleState.INDEXED: {
            KnowledgeLifecycleState.PENDING_REVIEW,
            KnowledgeLifecycleState.FAILED,
            KnowledgeLifecycleState.REJECTED,
            KnowledgeLifecycleState.INVALID,
        },
        KnowledgeLifecycleState.PENDING_REVIEW: {
            KnowledgeLifecycleState.PUBLISHED,
            KnowledgeLifecycleState.REJECTED,
            KnowledgeLifecycleState.INVALID,
        },
        KnowledgeLifecycleState.PUBLISHED: {
            KnowledgeLifecycleState.SUPERSEDED,
            KnowledgeLifecycleState.RETIRED,
            KnowledgeLifecycleState.INVALID,
        },
        KnowledgeLifecycleState.FAILED: {
            KnowledgeLifecycleState.RECEIVED,
            KnowledgeLifecycleState.PROCESSING,
            KnowledgeLifecycleState.INVALID,
        },
        KnowledgeLifecycleState.REJECTED: {
            KnowledgeLifecycleState.PENDING_REVIEW,
            KnowledgeLifecycleState.PROCESSING,
            KnowledgeLifecycleState.INVALID,
        },
        KnowledgeLifecycleState.SUPERSEDED: {
            KnowledgeLifecycleState.RETIRED,
            KnowledgeLifecycleState.INVALID,
        },
        KnowledgeLifecycleState.RETIRED: {
            KnowledgeLifecycleState.INVALID,
        },
        KnowledgeLifecycleState.INVALID: set(),
    }

    def __init__(self) -> None:
        self._transition_history: List[LifecycleTransitionRecord] = []

    def can_transition(self, current_state: KnowledgeLifecycleState, target_state: KnowledgeLifecycleState) -> bool:
        """Checks if transitioning from current_state to target_state is allowed by rules."""
        if current_state == target_state:
            return True
        allowed = self.ALLOWED_TRANSITIONS.get(current_state, set())
        return target_state in allowed

    def transition_lifecycle_state(
        self,
        version: DocumentVersion,
        target_state: KnowledgeLifecycleState,
        reason: Optional[str] = None,
        actor: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LifecycleTransitionRecord:
        """Transitions a DocumentVersion to a target KnowledgeLifecycleState.

        Validates legal transition rules and logs an auditable transition record.
        Raises InvalidLifecycleTransitionError for illegal state moves.
        """
        current_state = version.lifecycle_state

        if not self.can_transition(current_state, target_state):
            raise InvalidLifecycleTransitionError(
                f"Illegal state transition for version '{version.version_id}': "
                f"cannot move from '{current_state.value}' to '{target_state.value}'."
            )

        previous_state = current_state
        version.lifecycle_state = target_state

        # Align DocumentVersionStatus with KnowledgeLifecycleState where appropriate
        if target_state == KnowledgeLifecycleState.PUBLISHED:
            version.status = DocumentVersionStatus.ACTIVE
        elif target_state == KnowledgeLifecycleState.SUPERSEDED:
            version.status = DocumentVersionStatus.SUPERSEDED
        elif target_state == KnowledgeLifecycleState.RETIRED:
            version.status = DocumentVersionStatus.RETIRED
        elif target_state in (KnowledgeLifecycleState.FAILED, KnowledgeLifecycleState.REJECTED, KnowledgeLifecycleState.INVALID):
            version.status = DocumentVersionStatus.INVALID

        transition_id = f"trans_{version.version_id}_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        record = LifecycleTransitionRecord(
            transition_id=transition_id,
            object_id=version.version_id,
            object_type="DocumentVersion",
            previous_state=previous_state,
            new_state=target_state,
            reason=reason,
            actor=actor or "KnowledgeLifecycleEngine",
            metadata=metadata or {},
        )

        self._transition_history.append(record)

        # Record step in version provenance if attached
        if version.provenance is not None:
            version.provenance.processing_steps.append({
                "step_id": transition_id,
                "operation": "LIFECYCLE_STATE_TRANSITION",
                "processor_name": actor or "KnowledgeLifecycleEngine",
                "parameters": {
                    "previous_state": previous_state.value,
                    "new_state": target_state.value,
                    "reason": reason,
                },
                "timestamp": record.timestamp.isoformat(),
                "status": "COMPLETED",
            })

        return record

    def supersede_version(
        self,
        old_version: DocumentVersion,
        new_version: DocumentVersion,
        reason: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> Tuple[LifecycleTransitionRecord, LifecycleTransitionRecord]:
        """Supersedes an existing version with a new active version.

        Preserves historical version identity, content, metadata, and provenance intact.
        """
        if old_version.document_id != new_version.document_id:
            raise ValueError(
                f"Cannot supersede version across different documents: "
                f"old doc '{old_version.document_id}' vs new doc '{new_version.document_id}'."
            )

        new_version.parent_version_id = old_version.version_id

        # Supersede old version
        rec_old = self.transition_lifecycle_state(
            version=old_version,
            target_state=KnowledgeLifecycleState.SUPERSEDED,
            reason=reason or f"Superseded by new version '{new_version.version_id}'",
            actor=actor,
        )

        # Publish/activate new version
        rec_new = self.transition_lifecycle_state(
            version=new_version,
            target_state=KnowledgeLifecycleState.PUBLISHED,
            reason=reason or f"Published as replacement for superseded version '{old_version.version_id}'",
            actor=actor,
        )

        return rec_old, rec_new

    def retire_version(
        self,
        version: DocumentVersion,
        reason: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> LifecycleTransitionRecord:
        """Retires a version, removing it from active availability while preserving historical record."""
        return self.transition_lifecycle_state(
            version=version,
            target_state=KnowledgeLifecycleState.RETIRED,
            reason=reason or "Retired from active availability",
            actor=actor,
        )

    def fail_version(
        self,
        version: DocumentVersion,
        reason: str,
        actor: Optional[str] = None,
    ) -> LifecycleTransitionRecord:
        """Marks a version as FAILED during processing."""
        return self.transition_lifecycle_state(
            version=version,
            target_state=KnowledgeLifecycleState.FAILED,
            reason=reason,
            actor=actor,
        )

    def reject_version(
        self,
        version: DocumentVersion,
        reason: str,
        actor: Optional[str] = None,
    ) -> LifecycleTransitionRecord:
        """Marks a version as REJECTED during review."""
        return self.transition_lifecycle_state(
            version=version,
            target_state=KnowledgeLifecycleState.REJECTED,
            reason=reason,
            actor=actor,
        )

    def get_transition_history(self, object_id: Optional[str] = None) -> List[LifecycleTransitionRecord]:
        """Retrieves recorded transition history, optionally filtered by object_id."""
        if object_id is None:
            return list(self._transition_history)
        return [rec for rec in self._transition_history if rec.object_id == object_id]
