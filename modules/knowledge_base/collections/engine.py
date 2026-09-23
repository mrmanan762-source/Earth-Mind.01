"""Knowledge Collection Engine for C.2 Knowledge Base.

Manages logical Knowledge Collections, metadata, membership assignments,
and collection lifecycle state independently from physical index storage and
publication lifecycle state.
"""

from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional, Union

from core.errors.exceptions import (
    CollectionNotFoundError,
    DuplicateCollectionError,
    InvalidCollectionError,
)
from modules.knowledge_base.enums import AccessPolicy, Visibility
from modules.knowledge_base.collections.models import (
    CollectionMembership,
    CollectionStatus,
    CollectionType,
    KnowledgeCollection,
    KnowledgeObjectType,
    MembershipStatus,
)


class KnowledgeCollectionEngine:
    """Engine responsible for logical Knowledge Collection lifecycle and membership management."""

    def __init__(self):
        self._collections: Dict[str, KnowledgeCollection] = {}
        self._collection_names: Dict[str, str] = {}  # lowercase name -> collection_id
        self._memberships: Dict[str, CollectionMembership] = {}  # membership_id -> CollectionMembership
        self._object_memberships: Dict[str, List[str]] = {}  # object_id -> list of membership_ids
        self._collection_memberships: Dict[str, List[str]] = {}  # collection_id -> list of membership_ids

    def create_collection(
        self,
        collection_name: str,
        collection_type: Union[CollectionType, str] = CollectionType.AGRICULTURE_GENERAL,
        description: Optional[str] = None,
        domain: Optional[str] = "AGRICULTURE",
        language_scope: Optional[List[str]] = None,
        region_scope: Optional[List[str]] = None,
        visibility: Visibility = Visibility.PUBLIC,
        access_policy: AccessPolicy = AccessPolicy.PUBLIC,
        metadata: Optional[Dict[str, Any]] = None,
        collection_id: Optional[str] = None,
    ) -> KnowledgeCollection:
        """Create and register a new logical Knowledge Collection."""
        clean_name = collection_name.strip()
        if not clean_name:
            raise InvalidCollectionError("Collection name cannot be empty.")

        name_key = clean_name.lower()
        if name_key in self._collection_names:
            raise DuplicateCollectionError(f"Collection with name '{clean_name}' already exists.")

        cid = collection_id.strip() if collection_id else f"col_{uuid.uuid4().hex[:12]}"
        if cid in self._collections:
            raise DuplicateCollectionError(f"Collection with ID '{cid}' already exists.")

        collection = KnowledgeCollection(
            collection_id=cid,
            collection_name=clean_name,
            description=description,
            collection_type=collection_type,
            domain=domain,
            language_scope=language_scope or ["en"],
            region_scope=region_scope or [],
            status=CollectionStatus.ACTIVE,
            visibility=visibility,
            access_policy=access_policy,
            metadata=metadata or {},
        )

        self._collections[cid] = collection
        self._collection_names[name_key] = cid
        self._collection_memberships[cid] = []
        return collection

    def get_collection(self, collection_id: str) -> Optional[KnowledgeCollection]:
        """Retrieve a KnowledgeCollection by collection_id."""
        return self._collections.get(collection_id.strip())

    def get_collection_by_name(self, collection_name: str) -> Optional[KnowledgeCollection]:
        """Retrieve a KnowledgeCollection by name."""
        cid = self._collection_names.get(collection_name.strip().lower())
        return self._collections.get(cid) if cid else None

    def update_collection(
        self,
        collection_id: str,
        description: Optional[str] = None,
        domain: Optional[str] = None,
        language_scope: Optional[List[str]] = None,
        region_scope: Optional[List[str]] = None,
        visibility: Optional[Visibility] = None,
        access_policy: Optional[AccessPolicy] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> KnowledgeCollection:
        """Update metadata or scope attributes of an existing collection."""
        collection = self.get_collection(collection_id)
        if not collection:
            raise CollectionNotFoundError(collection_id)

        updated_dict = collection.model_dump()
        if description is not None:
            updated_dict["description"] = description
        if domain is not None:
            updated_dict["domain"] = domain
        if language_scope is not None:
            updated_dict["language_scope"] = language_scope
        if region_scope is not None:
            updated_dict["region_scope"] = region_scope
        if visibility is not None:
            updated_dict["visibility"] = visibility
        if access_policy is not None:
            updated_dict["access_policy"] = access_policy
        if metadata is not None:
            merged_meta = dict(collection.metadata)
            merged_meta.update(metadata)
            updated_dict["metadata"] = merged_meta

        updated_dict["updated_at"] = datetime.now(timezone.utc)
        new_collection = KnowledgeCollection(**updated_dict)
        self._collections[collection.collection_id] = new_collection
        return new_collection

    def update_collection_status(
        self, collection_id: str, status: CollectionStatus
    ) -> KnowledgeCollection:
        """Update explicit collection lifecycle status (ACTIVE, INACTIVE, ARCHIVED, DEPRECATED)."""
        collection = self.get_collection(collection_id)
        if not collection:
            raise CollectionNotFoundError(collection_id)

        updated_dict = collection.model_dump()
        updated_dict["status"] = status
        updated_dict["updated_at"] = datetime.now(timezone.utc)

        new_collection = KnowledgeCollection(**updated_dict)
        self._collections[collection.collection_id] = new_collection
        return new_collection

    def list_collections(
        self,
        status: Optional[CollectionStatus] = None,
        collection_type: Optional[Union[CollectionType, str]] = None,
        domain: Optional[str] = None,
    ) -> List[KnowledgeCollection]:
        """List logical collections filtered by status, collection_type, or domain."""
        results = list(self._collections.values())
        if status is not None:
            results = [c for c in results if c.status == status]
        if collection_type is not None:
            results = [c for c in results if str(c.collection_type) == str(collection_type)]
        if domain is not None:
            results = [c for c in results if c.domain and c.domain.lower() == domain.lower()]
        return results

    def assign_membership(
        self,
        collection_id: str,
        knowledge_object_type: KnowledgeObjectType,
        knowledge_object_id: str,
        document_id: Optional[str] = None,
        version_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        traceability: Optional[Dict[str, Any]] = None,
        membership_id: Optional[str] = None,
    ) -> CollectionMembership:
        """Assign a canonical knowledge object (document, version, unit, chunk) to a logical collection."""
        cid = collection_id.strip()
        collection = self.get_collection(cid)
        if not collection:
            raise CollectionNotFoundError(cid)

        if collection.status != CollectionStatus.ACTIVE:
            raise InvalidCollectionError(
                f"Cannot assign membership to collection '{cid}' with status '{collection.status}'."
            )

        oid = knowledge_object_id.strip()
        mid = membership_id.strip() if membership_id else f"mem_{uuid.uuid4().hex[:12]}"

        # Check if already assigned active membership in this specific collection
        existing_mids = self._collection_memberships.get(cid, [])
        for existing_id in existing_mids:
            mem = self._memberships.get(existing_id)
            if mem and mem.knowledge_object_id == oid and mem.status == MembershipStatus.ACTIVE:
                return mem

        membership = CollectionMembership(
            membership_id=mid,
            collection_id=cid,
            knowledge_object_type=knowledge_object_type,
            knowledge_object_id=oid,
            document_id=document_id,
            version_id=version_id,
            status=MembershipStatus.ACTIVE,
            metadata=metadata or {},
            traceability=traceability or {},
        )

        self._memberships[mid] = membership
        self._collection_memberships.setdefault(cid, []).append(mid)
        self._object_memberships.setdefault(oid, []).append(mid)
        return membership

    def update_membership_status(
        self, membership_id: str, status: MembershipStatus
    ) -> CollectionMembership:
        """Update status of a collection membership record."""
        mid = membership_id.strip()
        mem = self._memberships.get(mid)
        if not mem:
            raise InvalidCollectionError(f"Membership record '{mid}' not found.")

        updated_dict = mem.model_dump()
        updated_dict["status"] = status
        updated_dict["updated_at"] = datetime.now(timezone.utc)

        new_mem = CollectionMembership(**updated_dict)
        self._memberships[mid] = new_mem
        return new_mem

    def get_memberships_for_object(
        self, knowledge_object_id: str, status: Optional[MembershipStatus] = None
    ) -> List[CollectionMembership]:
        """Get all collection memberships for a given canonical object ID across collections."""
        oid = knowledge_object_id.strip()
        mids = self._object_memberships.get(oid, [])
        memberships = [self._memberships[m] for m in mids if m in self._memberships]
        if status is not None:
            memberships = [m for m in memberships if m.status == status]
        return memberships

    def get_memberships_for_collection(
        self, collection_id: str, status: Optional[MembershipStatus] = None
    ) -> List[CollectionMembership]:
        """Get all memberships belonging to a target logical collection."""
        cid = collection_id.strip()
        mids = self._collection_memberships.get(cid, [])
        memberships = [self._memberships[m] for m in mids if m in self._memberships]
        if status is not None:
            memberships = [m for m in memberships if m.status == status]
        return memberships

    def is_object_in_collection(
        self, collection_id: str, knowledge_object_id: str, active_only: bool = True
    ) -> bool:
        """Check if an object belongs to a collection."""
        mems = self.get_memberships_for_object(knowledge_object_id)
        for m in mems:
            if m.collection_id == collection_id.strip():
                if not active_only or m.status == MembershipStatus.ACTIVE:
                    return True
        return False

    def validate_collection_eligibility(self, collection_id: str) -> bool:
        """Validate whether a collection is eligible to accept or serve published knowledge."""
        cid = collection_id.strip()
        collection = self.get_collection(cid)
        if not collection:
            raise CollectionNotFoundError(cid)
        if collection.status != CollectionStatus.ACTIVE:
            return False
        return True
