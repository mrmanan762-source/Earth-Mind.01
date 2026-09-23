"""Comprehensive unit tests for Step 12 — Knowledge Collections & Publication Layer."""

from datetime import datetime, timezone
import pytest

from core.errors.exceptions import (
    CollectionError,
    CollectionNotFoundError,
    DuplicateCollectionError,
    InvalidCollectionError,
    PublicationEligibilityError,
    PublicationValidationError,
)
from modules.knowledge_base.enums import (
    AccessPolicy,
    KnowledgeContentType,
    KnowledgeLifecycleState,
    Visibility,
)
from modules.knowledge_base.metadata import CanonicalMetadata
from modules.knowledge_base.provenance import ProcessingStep, Provenance
from modules.knowledge_base.canonical_models import DocumentVersion, Source
from modules.knowledge_base.collections import (
    CollectionMembership,
    CollectionStatus,
    CollectionType,
    KnowledgeCollection,
    KnowledgeCollectionEngine,
    KnowledgeObjectType,
    MembershipStatus,
)
from modules.knowledge_base.publication import (
    KnowledgePublicationEngine,
    PublicationEligibilityValidator,
    PublicationRecord,
    PublicationStatus,
)
from modules.knowledge_base.index import (
    FakeIndexAdapter,
    KnowledgeIndexEngine,
)
from modules.knowledge_base.embedding import EmbeddingRecord
from modules.knowledge_base.sparse import SparseRepresentationRecord


@pytest.fixture
def collection_engine():
    return KnowledgeCollectionEngine()


@pytest.fixture
def fake_index_adapter():
    return FakeIndexAdapter()


@pytest.fixture
def index_engine(fake_index_adapter):
    return KnowledgeIndexEngine(adapter=fake_index_adapter)


@pytest.fixture
def publication_engine(collection_engine, index_engine):
    return KnowledgePublicationEngine(collection_engine=collection_engine, index_engine=index_engine)


@pytest.fixture
def valid_provenance():
    return Provenance(
        provenance_id="prov_001",
        source_id="src_001",
        artifact_id="art_001",
        document_id="doc_001",
        version_id="ver_1_0",
        processing_steps=[
            {
                "step_id": "step_1",
                "operation": "ingest",
                "processor_name": "test_processor",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )


@pytest.fixture
def valid_metadata():
    return CanonicalMetadata(
        domain="CROPS",
        topic="Maize Disease Management",
        crop="Maize",
        region="East Africa",
        language="en",
    )


# =====================================================================
# 1. KNOWLEDGE COLLECTION CREATION & LIFECYCLE TESTS
# =====================================================================

def test_create_knowledge_collection(collection_engine):
    col = collection_engine.create_collection(
        collection_name="Crops-General",
        collection_type=CollectionType.CROPS,
        description="General crop production guidelines",
        domain="CROPS",
        language_scope=["en", "sw"],
        region_scope=["East Africa"],
        visibility=Visibility.PUBLIC,
        access_policy=AccessPolicy.PUBLIC,
    )
    assert col.collection_id.startswith("col_")
    assert col.collection_name == "Crops-General"
    assert col.collection_type == CollectionType.CROPS
    assert col.status == CollectionStatus.ACTIVE
    assert col.language_scope == ["en", "sw"]

    retrieved = collection_engine.get_collection(col.collection_id)
    assert retrieved == col

    by_name = collection_engine.get_collection_by_name("Crops-General")
    assert by_name == col


def test_duplicate_collection_name_fails(collection_engine):
    collection_engine.create_collection("Soil Health")
    with pytest.raises(DuplicateCollectionError):
        collection_engine.create_collection("Soil Health")


def test_update_collection_and_status(collection_engine):
    col = collection_engine.create_collection("Diseases")
    updated = collection_engine.update_collection(
        col.collection_id,
        description="Pest and disease management",
        domain="PLANT_PATHOLOGY",
    )
    assert updated.description == "Pest and disease management"
    assert updated.domain == "PLANT_PATHOLOGY"

    # Status update
    archived = collection_engine.update_collection_status(col.collection_id, CollectionStatus.ARCHIVED)
    assert archived.status == CollectionStatus.ARCHIVED


def test_collection_not_found(collection_engine):
    assert collection_engine.get_collection("nonexistent") is None
    with pytest.raises(CollectionNotFoundError):
        collection_engine.update_collection("nonexistent", description="test")


# =====================================================================
# 2. COLLECTION MEMBERSHIP TESTS (MULTIPLE & MULTIMODAL)
# =====================================================================

def test_assign_membership_and_multi_collection_support(collection_engine):
    col1 = collection_engine.create_collection("Crops")
    col2 = collection_engine.create_collection("Regional")

    mem1 = collection_engine.assign_membership(
        collection_id=col1.collection_id,
        knowledge_object_type=KnowledgeObjectType.DOCUMENT_VERSION,
        knowledge_object_id="ver_1_0",
        document_id="doc_001",
        version_id="ver_1_0",
    )
    assert mem1.membership_id.startswith("mem_")
    assert mem1.status == MembershipStatus.ACTIVE

    # Assign same object to second collection
    mem2 = collection_engine.assign_membership(
        collection_id=col2.collection_id,
        knowledge_object_type=KnowledgeObjectType.DOCUMENT_VERSION,
        knowledge_object_id="ver_1_0",
        document_id="doc_001",
        version_id="ver_1_0",
    )

    # Object belongs to both collections
    object_mems = collection_engine.get_memberships_for_object("ver_1_0")
    assert len(object_mems) == 2
    assert {m.collection_id for m in object_mems} == {col1.collection_id, col2.collection_id}

    assert collection_engine.is_object_in_collection(col1.collection_id, "ver_1_0") is True
    assert collection_engine.is_object_in_collection(col2.collection_id, "ver_1_0") is True


def test_multimodal_knowledge_membership(collection_engine):
    col = collection_engine.create_collection("Multimodal-Figures")
    mem = collection_engine.assign_membership(
        collection_id=col.collection_id,
        knowledge_object_type=KnowledgeObjectType.CHUNK,
        knowledge_object_id="chk_img_101",
        metadata={"content_type": KnowledgeContentType.IMAGE.value, "image_url": "s3://bucket/fig1.png"}
    )
    assert mem.knowledge_object_type == KnowledgeObjectType.CHUNK
    assert mem.metadata["content_type"] == "IMAGE"


def test_inactive_collection_cannot_accept_membership(collection_engine):
    col = collection_engine.create_collection("Deprecating")
    collection_engine.update_collection_status(col.collection_id, CollectionStatus.INACTIVE)

    with pytest.raises(InvalidCollectionError):
        collection_engine.assign_membership(
            collection_id=col.collection_id,
            knowledge_object_type=KnowledgeObjectType.DOCUMENT_VERSION,
            knowledge_object_id="ver_99",
        )


# =====================================================================
# 3. PUBLICATION ELIGIBILITY & VALIDATION TESTS
# =====================================================================

def test_publication_eligibility_success(valid_provenance, valid_metadata):
    validator = PublicationEligibilityValidator()
    result = validator.evaluate_eligibility(
        knowledge_object_id="ver_1_0",
        knowledge_object_type=KnowledgeObjectType.DOCUMENT_VERSION,
        source_id="src_001",
        document_id="doc_001",
        version_id="ver_1_0",
        provenance=valid_provenance,
        metadata=valid_metadata,
        lifecycle_state=KnowledgeLifecycleState.PROCESSED,
        representations_available=True,
    )
    assert result.eligible is True
    assert len(result.missing_prerequisites) == 0


def test_missing_provenance_blocks_publication(valid_metadata):
    validator = PublicationEligibilityValidator()
    result = validator.evaluate_eligibility(
        knowledge_object_id="ver_1_0",
        source_id="src_001",
        document_id="doc_001",
        version_id="ver_1_0",
        provenance=None,
        metadata=valid_metadata,
        lifecycle_state=KnowledgeLifecycleState.PROCESSED,
    )
    assert result.eligible is False
    assert "provenance_exists" in result.missing_prerequisites


def test_invalid_lifecycle_state_blocks_publication(valid_provenance, valid_metadata):
    validator = PublicationEligibilityValidator()
    for forbidden_state in [
        KnowledgeLifecycleState.FAILED,
        KnowledgeLifecycleState.REJECTED,
        KnowledgeLifecycleState.INVALID,
        KnowledgeLifecycleState.SUPERSEDED,
        KnowledgeLifecycleState.RETIRED,
    ]:
        result = validator.evaluate_eligibility(
            knowledge_object_id="ver_1_0",
            source_id="src_001",
            document_id="doc_001",
            version_id="ver_1_0",
            provenance=valid_provenance,
            metadata=valid_metadata,
            lifecycle_state=forbidden_state,
        )
        assert result.eligible is False
        assert "valid_lifecycle_state" in result.missing_prerequisites


def test_web_search_non_publication_rule(valid_provenance, valid_metadata):
    validator = PublicationEligibilityValidator()

    # Web search result NOT reviewed -> BLOCKED
    result_unreviewed = validator.evaluate_eligibility(
        knowledge_object_id="web_res_123",
        source_id="src_web",
        document_id="doc_web",
        version_id="ver_web",
        provenance=valid_provenance,
        metadata=valid_metadata,
        lifecycle_state=KnowledgeLifecycleState.PROCESSED,
        is_web_result=True,
        is_web_result_reviewed=False,
    )
    assert result_unreviewed.eligible is False
    assert "web_result_explicit_review" in result_unreviewed.missing_prerequisites

    # Web search result explicitly reviewed -> ELIGIBLE
    result_reviewed = validator.evaluate_eligibility(
        knowledge_object_id="web_res_123",
        source_id="src_web",
        document_id="doc_web",
        version_id="ver_web",
        provenance=valid_provenance,
        metadata=valid_metadata,
        lifecycle_state=KnowledgeLifecycleState.PROCESSED,
        is_web_result=True,
        is_web_result_reviewed=True,
    )
    assert result_reviewed.eligible is True


# =====================================================================
# 4. KNOWLEDGE PUBLICATION WORKFLOW & INDEX INTERACTION
# =====================================================================

def test_publish_knowledge_successful_workflow(publication_engine, collection_engine, valid_provenance, valid_metadata):
    col = collection_engine.create_collection("Crops")

    record = publication_engine.publish_knowledge(
        knowledge_object_id="ver_1_0",
        knowledge_object_type=KnowledgeObjectType.DOCUMENT_VERSION,
        collection_id=col.collection_id,
        source_id="src_001",
        document_id="doc_001",
        version_id="ver_1_0",
        provenance=valid_provenance,
        metadata=valid_metadata,
        previous_lifecycle_state=KnowledgeLifecycleState.PROCESSED,
    )

    assert record.publication_status == PublicationStatus.PUBLISHED
    assert record.new_lifecycle_state == KnowledgeLifecycleState.PUBLISHED
    assert record.collection_id == col.collection_id

    # Verify collection membership automatically registered
    assert collection_engine.is_object_in_collection(col.collection_id, "ver_1_0") is True

    # Audit history recorded
    history = publication_engine.get_publication_history("ver_1_0")
    assert len(history) == 1
    assert history[0].publication_id == record.publication_id


def test_publish_knowledge_ineligible_raises_error(publication_engine):
    with pytest.raises(PublicationEligibilityError):
        publication_engine.publish_knowledge(
            knowledge_object_id="ver_failed",
            source_id="src_001",
            document_id="doc_001",
            version_id="ver_failed",
            provenance=None,  # Missing provenance causes error
        )

    # Failed audit history preserved
    history = publication_engine.get_publication_history("ver_failed")
    assert len(history) == 1
    assert history[0].publication_status in {PublicationStatus.FAILED, PublicationStatus.REJECTED}


def test_publish_when_index_unavailable(publication_engine, fake_index_adapter, valid_provenance, valid_metadata):
    fake_index_adapter.set_availability(False)  # Simulate offline vector store

    record = publication_engine.publish_knowledge(
        knowledge_object_id="ver_offline",
        source_id="src_001",
        document_id="doc_001",
        version_id="ver_offline",
        provenance=valid_provenance,
        metadata=valid_metadata,
    )

    # Distinction between canonical publication state vs index availability
    assert record.publication_status == PublicationStatus.PUBLISHED_INDEX_UNAVAILABLE
    assert record.new_lifecycle_state == KnowledgeLifecycleState.PUBLISHED


# =====================================================================
# 5. VERSION SUPERSESSION & AUDIT HISTORY
# =====================================================================

def test_version_supersession_workflow(publication_engine, collection_engine, valid_provenance, valid_metadata):
    col = collection_engine.create_collection("Guidelines")

    # Publish v1
    pub1 = publication_engine.publish_knowledge(
        knowledge_object_id="ver_1_0",
        collection_id=col.collection_id,
        source_id="src_001",
        document_id="doc_001",
        version_id="ver_1_0",
        provenance=valid_provenance,
        metadata=valid_metadata,
    )
    assert pub1.publication_status == PublicationStatus.PUBLISHED

    # Publish v2
    pub2 = publication_engine.publish_knowledge(
        knowledge_object_id="ver_2_0",
        collection_id=col.collection_id,
        source_id="src_001",
        document_id="doc_001",
        version_id="ver_2_0",
        provenance=valid_provenance,
        metadata=valid_metadata,
    )
    assert pub2.publication_status == PublicationStatus.PUBLISHED

    # Supersede v1 with v2
    sup_record = publication_engine.supersede_version(
        old_version_id="ver_1_0",
        new_version_id="ver_2_0",
        document_id="doc_001",
        reason="Updated pest control recommendations in v2.0.",
    )

    assert sup_record.publication_status == PublicationStatus.SUPERSEDED
    assert sup_record.new_lifecycle_state == KnowledgeLifecycleState.SUPERSEDED

    # History of v1 is preserved completely
    v1_history = publication_engine.get_publication_history("ver_1_0")
    assert len(v1_history) == 2
    assert v1_history[0].publication_status == PublicationStatus.PUBLISHED
    assert v1_history[1].publication_status == PublicationStatus.SUPERSEDED


# =====================================================================
# 6. RETRIEVABILITY & SEPARATION TESTS
# =====================================================================

def test_strict_retrievability_rule(publication_engine, fake_index_adapter, valid_provenance, valid_metadata):
    # Unpublished knowledge -> NOT retrievable
    assert publication_engine.is_retrievable("ver_unpub") is False

    # Publish knowledge
    publication_engine.publish_knowledge(
        knowledge_object_id="ver_pub",
        source_id="src_001",
        document_id="doc_001",
        version_id="ver_pub",
        provenance=valid_provenance,
        metadata=valid_metadata,
    )
    assert publication_engine.is_retrievable("ver_pub") is True

    # If index adapter drops offline -> NOT retrievable
    fake_index_adapter.set_availability(False)
    assert publication_engine.is_retrievable("ver_pub") is False


def test_collection_publication_independence(collection_engine, publication_engine, valid_provenance, valid_metadata):
    col = collection_engine.create_collection("Soil")

    # 1. Collection exists empty
    assert len(collection_engine.get_memberships_for_collection(col.collection_id)) == 0

    # 2. Object assigned to collection without being published
    collection_engine.assign_membership(
        collection_id=col.collection_id,
        knowledge_object_type=KnowledgeObjectType.DOCUMENT_VERSION,
        knowledge_object_id="ver_draft",
    )
    assert collection_engine.is_object_in_collection(col.collection_id, "ver_draft") is True
    # Object in collection is NOT retrievable because publication engine hasn't published it
    assert publication_engine.is_retrievable("ver_draft") is False


def test_qdrant_provider_independence(publication_engine, valid_provenance, valid_metadata):
    # Ensures test suite runs completely with FakeIndexAdapter without needing live Qdrant
    res = publication_engine.publish_knowledge(
        knowledge_object_id="ver_standalone",
        source_id="src_001",
        document_id="doc_001",
        version_id="ver_standalone",
        provenance=valid_provenance,
        metadata=valid_metadata,
    )
    assert res.publication_status == PublicationStatus.PUBLISHED
