"""Knowledge Publication Engine for C.2 Knowledge Base.

Coordinates publication eligibility evaluation, publication state transitions,
logical collection association, document version supersession, publication audit logging,
and retrievability verification via abstract index interfaces.
"""

from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional, Union

from core.errors.exceptions import (
    PublicationEligibilityError,
    PublicationError,
    PublicationValidationError,
)
from modules.knowledge_base.enums import KnowledgeLifecycleState
from modules.knowledge_base.collections.engine import KnowledgeCollectionEngine
from modules.knowledge_base.collections.models import (
    CollectionStatus,
    KnowledgeObjectType,
)
from modules.knowledge_base.index.engine import KnowledgeIndexEngine
from modules.knowledge_base.publication.models import (
    PublicationEligibilityResult,
    PublicationRecord,
    PublicationStatus,
)
from modules.knowledge_base.publication.validator import PublicationEligibilityValidator


class KnowledgePublicationEngine:
    """Engine orchestrating knowledge publication lifecycle and retrievability controls."""

    def __init__(
        self,
        collection_engine: Optional[KnowledgeCollectionEngine] = None,
        index_engine: Optional[KnowledgeIndexEngine] = None,
        validator: Optional[PublicationEligibilityValidator] = None,
    ):
        self.collection_engine = collection_engine or KnowledgeCollectionEngine()
        self.index_engine = index_engine
        self.validator = validator or PublicationEligibilityValidator()
        self._publication_history: Dict[str, List[PublicationRecord]] = {}  # object_id -> list of PublicationRecord
        self._publication_records: Dict[str, PublicationRecord] = {}  # pub_id -> PublicationRecord

    def evaluate_eligibility(
        self,
        knowledge_object_id: str,
        knowledge_object_type: KnowledgeObjectType = KnowledgeObjectType.DOCUMENT_VERSION,
        canonical_object: Optional[Any] = None,
        source_id: Optional[str] = None,
        document_id: Optional[str] = None,
        version_id: Optional[str] = None,
        provenance: Optional[Any] = None,
        metadata: Optional[Any] = None,
        source_assessment: Optional[Any] = None,
        lifecycle_state: Optional[KnowledgeLifecycleState] = None,
        representations_available: bool = True,
        is_web_result: bool = False,
        is_web_result_reviewed: bool = False,
        is_blocked: bool = False,
        block_reason: Optional[str] = None,
        require_source_assessment: bool = False,
    ) -> PublicationEligibilityResult:
        """Evaluate if a canonical object satisfies publication prerequisites."""
        return self.validator.evaluate_eligibility(
            knowledge_object_id=knowledge_object_id,
            knowledge_object_type=knowledge_object_type,
            canonical_object=canonical_object,
            source_id=source_id,
            document_id=document_id,
            version_id=version_id,
            provenance=provenance,
            metadata=metadata,
            source_assessment=source_assessment,
            lifecycle_state=lifecycle_state,
            representations_available=representations_available,
            is_web_result=is_web_result,
            is_web_result_reviewed=is_web_result_reviewed,
            is_blocked=is_blocked,
            block_reason=block_reason,
            require_source_assessment=require_source_assessment,
        )

    def publish_knowledge(
        self,
        knowledge_object_id: str,
        knowledge_object_type: KnowledgeObjectType = KnowledgeObjectType.DOCUMENT_VERSION,
        canonical_object: Optional[Any] = None,
        collection_id: Optional[str] = None,
        source_id: Optional[str] = None,
        document_id: Optional[str] = None,
        version_id: Optional[str] = None,
        provenance: Optional[Any] = None,
        metadata: Optional[Any] = None,
        source_assessment: Optional[Any] = None,
        previous_lifecycle_state: Optional[KnowledgeLifecycleState] = None,
        representations_available: bool = True,
        index_records: Optional[List[Any]] = None,
        actor_id: str = "system",
        reason: Optional[str] = None,
        is_web_result: bool = False,
        is_web_result_reviewed: bool = False,
        is_blocked: bool = False,
        block_reason: Optional[str] = None,
        publication_id: Optional[str] = None,
    ) -> PublicationRecord:
        """Publish a canonical knowledge object, assigning it to collections and syncing index status."""
        oid = knowledge_object_id.strip()

        # 1. Evaluate publication eligibility
        prev_state = previous_lifecycle_state or getattr(canonical_object, "lifecycle_state", None) or KnowledgeLifecycleState.PROCESSED
        if isinstance(prev_state, str):
            try:
                prev_state = KnowledgeLifecycleState(prev_state)
            except ValueError:
                prev_state = KnowledgeLifecycleState.PROCESSED

        eligibility = self.evaluate_eligibility(
            knowledge_object_id=oid,
            knowledge_object_type=knowledge_object_type,
            canonical_object=canonical_object,
            source_id=source_id,
            document_id=document_id,
            version_id=version_id,
            provenance=provenance,
            metadata=metadata,
            source_assessment=source_assessment,
            lifecycle_state=prev_state,
            representations_available=representations_available,
            is_web_result=is_web_result,
            is_web_result_reviewed=is_web_result_reviewed,
            is_blocked=is_blocked,
            block_reason=block_reason,
        )

        pid = publication_id.strip() if publication_id else f"pub_{uuid.uuid4().hex[:12]}"

        if not eligibility.eligible:
            # Record failed/rejected publication attempt
            failed_record = PublicationRecord(
                publication_id=pid,
                knowledge_object_type=knowledge_object_type,
                knowledge_object_id=oid,
                document_id=document_id,
                version_id=version_id,
                collection_id=collection_id,
                previous_lifecycle_state=prev_state,
                new_lifecycle_state=KnowledgeLifecycleState.REJECTED if is_blocked else prev_state,
                publication_status=PublicationStatus.REJECTED if is_blocked else PublicationStatus.FAILED,
                actor_id=actor_id,
                reason=reason or f"Ineligible for publication: {eligibility.reasons}",
                validation_details=eligibility.model_dump(),
            )
            self._record_publication(failed_record)
            raise PublicationEligibilityError(oid, eligibility.missing_prerequisites)

        # 2. Validate collection if collection_id specified
        if collection_id:
            cid = collection_id.strip()
            collection = self.collection_engine.get_collection(cid)
            if not collection:
                raise PublicationValidationError(oid, f"Target collection '{cid}' does not exist.")
            if collection.status != CollectionStatus.ACTIVE:
                raise PublicationValidationError(
                    oid, f"Target collection '{cid}' status '{collection.status}' is not ACTIVE."
                )

        # 3. Synchronize with Index Layer if Index Engine present
        pub_status = PublicationStatus.PUBLISHED
        index_sync_details: Dict[str, Any] = {"indexed": False}

        if self.index_engine is not None:
            try:
                if index_records:
                    batch_res = self.index_engine.index_batch(index_records, logical_collection=collection_id)
                    index_sync_details["index_batch_result"] = batch_res.model_dump()
                    if len(batch_res.failed_records) > 0 and len(batch_res.successful_records) == 0:
                        pub_status = PublicationStatus.PUBLISHED_INDEX_UNAVAILABLE
                    else:
                        index_sync_details["indexed"] = True
                else:
                    # Check if adapter is available
                    if not self.index_engine.adapter.is_available():
                        pub_status = PublicationStatus.PUBLISHED_INDEX_UNAVAILABLE
                        index_sync_details["reason"] = "Index adapter is currently offline or unavailable."
                    else:
                        index_sync_details["indexed"] = True
            except Exception as exc:
                pub_status = PublicationStatus.PUBLISHED_INDEX_UNAVAILABLE
                index_sync_details["error"] = str(exc)

        # 4. Create publication record
        record = PublicationRecord(
            publication_id=pid,
            knowledge_object_type=knowledge_object_type,
            knowledge_object_id=oid,
            document_id=document_id,
            version_id=version_id,
            collection_id=collection_id,
            previous_lifecycle_state=prev_state,
            new_lifecycle_state=KnowledgeLifecycleState.PUBLISHED,
            publication_status=pub_status,
            actor_id=actor_id,
            reason=reason or "Publication prerequisites satisfied.",
            validation_details={
                "eligibility": eligibility.model_dump(),
                "index_sync": index_sync_details,
            },
        )

        # 5. Assign to logical collection if collection_id provided
        if collection_id:
            self.collection_engine.assign_membership(
                collection_id=collection_id,
                knowledge_object_type=knowledge_object_type,
                knowledge_object_id=oid,
                document_id=document_id,
                version_id=version_id,
            )

        self._record_publication(record)
        return record

    def supersede_version(
        self,
        old_version_id: str,
        new_version_id: str,
        document_id: Optional[str] = None,
        actor_id: str = "system",
        reason: Optional[str] = None,
    ) -> PublicationRecord:
        """Handle version supersession: marks old version as SUPERSEDED while preserving history and lineage."""
        old_vid = old_version_id.strip()
        new_vid = new_version_id.strip()

        latest_old_pub = self.get_latest_publication_record(old_vid)
        prev_state = latest_old_pub.new_lifecycle_state if latest_old_pub else KnowledgeLifecycleState.PUBLISHED

        pid = f"pub_sup_{uuid.uuid4().hex[:12]}"
        superseded_record = PublicationRecord(
            publication_id=pid,
            knowledge_object_type=KnowledgeObjectType.DOCUMENT_VERSION,
            knowledge_object_id=old_vid,
            document_id=document_id,
            version_id=old_vid,
            collection_id=latest_old_pub.collection_id if latest_old_pub else None,
            previous_lifecycle_state=prev_state,
            new_lifecycle_state=KnowledgeLifecycleState.SUPERSEDED,
            publication_status=PublicationStatus.SUPERSEDED,
            actor_id=actor_id,
            reason=reason or f"Superseded by document version '{new_vid}'.",
            validation_details={
                "superseded_by_version_id": new_vid,
                "supersession_timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        self._record_publication(superseded_record)
        return superseded_record

    def revoke_publication(
        self,
        knowledge_object_id: str,
        reason: str,
        actor_id: str = "system",
        knowledge_object_type: KnowledgeObjectType = KnowledgeObjectType.DOCUMENT_VERSION,
    ) -> PublicationRecord:
        """Revoke publication status of a published knowledge object."""
        oid = knowledge_object_id.strip()
        latest = self.get_latest_publication_record(oid)
        prev_state = latest.new_lifecycle_state if latest else KnowledgeLifecycleState.PUBLISHED

        pid = f"pub_rev_{uuid.uuid4().hex[:12]}"
        revoked_record = PublicationRecord(
            publication_id=pid,
            knowledge_object_type=knowledge_object_type,
            knowledge_object_id=oid,
            document_id=latest.document_id if latest else None,
            version_id=latest.version_id if latest else None,
            collection_id=latest.collection_id if latest else None,
            previous_lifecycle_state=prev_state,
            new_lifecycle_state=KnowledgeLifecycleState.RETIRED,
            publication_status=PublicationStatus.REVOKED,
            actor_id=actor_id,
            reason=reason,
            validation_details={"revocation_timestamp": datetime.now(timezone.utc).isoformat()},
        )

        self._record_publication(revoked_record)
        return revoked_record

    def get_publication_history(self, knowledge_object_id: str) -> List[PublicationRecord]:
        """Get all publication records for a canonical object ID."""
        return self._publication_history.get(knowledge_object_id.strip(), [])

    def get_latest_publication_record(self, knowledge_object_id: str) -> Optional[PublicationRecord]:
        """Get the most recent publication record for a canonical object ID."""
        history = self.get_publication_history(knowledge_object_id)
        return history[-1] if history else None

    def is_retrievable(
        self,
        knowledge_object_id: str,
        index_record_id: Optional[str] = None,
        logical_collection: Optional[str] = None,
    ) -> bool:
        """Evaluate strict retrievability rule.

        Knowledge is retrievable ONLY if:
        1. Published state is KnowledgeLifecycleState.PUBLISHED.
        2. Publication status is PublicationStatus.PUBLISHED.
        3. Index representation is available in the configured index adapter (if index_engine present).
        """
        oid = knowledge_object_id.strip()
        latest = self.get_latest_publication_record(oid)
        if not latest:
            return False

        if latest.new_lifecycle_state != KnowledgeLifecycleState.PUBLISHED:
            return False

        if latest.publication_status != PublicationStatus.PUBLISHED:
            return False

        # If index engine is available, verify index record existence / adapter health
        if self.index_engine is not None:
            if not self.index_engine.adapter.is_available():
                return False

            if index_record_id:
                rec = self.index_engine.get_record(index_record_id, logical_collection=logical_collection)
                if rec is None:
                    return False

        return True

    def _record_publication(self, record: PublicationRecord) -> None:
        """Internal helper to log publication record into audit history."""
        self._publication_records[record.publication_id] = record
        self._publication_history.setdefault(record.knowledge_object_id, []).append(record)
