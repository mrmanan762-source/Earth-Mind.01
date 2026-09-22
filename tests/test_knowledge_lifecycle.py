"""Unit tests for C.2 Step 7: Versioning and Lifecycle in EarthMind Knowledge Base."""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from modules.knowledge_base import (
    CanonicalMetadata,
    Document,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    InvalidLifecycleTransitionError,
    KnowledgeLifecycleEngine,
    KnowledgeLifecycleState,
    Provenance,
    Source,
    SourceAssessment,
    validate_canonical_lineage,
)


class TestVersionIdentityAndLineage:
    """Test suite covering Document identity stability and version lineage."""

    def test_document_retains_stable_identity_across_versions(self):
        doc = Document(
            document_id="doc_soil_01",
            source_id="src_fao_01",
            title="Tropical Soil Management",
            document_type="GUIDELINE",
        )

        v1 = DocumentVersion(
            version_id="ver_soil_1.0",
            document_id=doc.document_id,
            version_number="1.0.0",
        )

        v2 = DocumentVersion(
            version_id="ver_soil_2.0",
            document_id=doc.document_id,
            parent_version_id=v1.version_id,
            version_number="2.0.0",
        )

        assert v1.document_id == doc.document_id
        assert v2.document_id == doc.document_id
        assert v1.version_id != v2.version_id
        assert v2.parent_version_id == "ver_soil_1.0"

    def test_parent_child_version_lineage_and_numbering(self):
        v1 = DocumentVersion(
            version_id="ver_01",
            document_id="doc_01",
            version_number="1.0.0",
        )
        v2 = DocumentVersion(
            version_id="ver_02",
            document_id="doc_01",
            parent_version_id="ver_01",
            version_number="1.1.0",
        )

        assert v2.parent_version_id == v1.version_id
        assert v2.version_number == "1.1.0"


class TestLifecycleStateTransitions:
    """Test suite covering lifecycle state transitions and publication rules."""

    def test_valid_pipeline_lifecycle_transitions(self):
        engine = KnowledgeLifecycleEngine()
        ver = DocumentVersion(
            version_id="ver_01",
            document_id="doc_01",
            lifecycle_state=KnowledgeLifecycleState.RECEIVED,
        )

        assert ver.lifecycle_state == KnowledgeLifecycleState.RECEIVED

        engine.transition_lifecycle_state(ver, KnowledgeLifecycleState.PROCESSING)
        assert ver.lifecycle_state == KnowledgeLifecycleState.PROCESSING

        engine.transition_lifecycle_state(ver, KnowledgeLifecycleState.PROCESSED)
        assert ver.lifecycle_state == KnowledgeLifecycleState.PROCESSED

        engine.transition_lifecycle_state(ver, KnowledgeLifecycleState.EMBEDDED)
        assert ver.lifecycle_state == KnowledgeLifecycleState.EMBEDDED

        engine.transition_lifecycle_state(ver, KnowledgeLifecycleState.INDEXED)
        assert ver.lifecycle_state == KnowledgeLifecycleState.INDEXED

        engine.transition_lifecycle_state(ver, KnowledgeLifecycleState.PENDING_REVIEW)
        assert ver.lifecycle_state == KnowledgeLifecycleState.PENDING_REVIEW

        # Publication requires explicit transition
        engine.transition_lifecycle_state(ver, KnowledgeLifecycleState.PUBLISHED)
        assert ver.lifecycle_state == KnowledgeLifecycleState.PUBLISHED
        assert ver.status == DocumentVersionStatus.ACTIVE

    def test_invalid_lifecycle_transition_rejection(self):
        engine = KnowledgeLifecycleEngine()
        ver = DocumentVersion(
            version_id="ver_01",
            document_id="doc_01",
            lifecycle_state=KnowledgeLifecycleState.RECEIVED,
        )

        # Direct transition from RECEIVED to PUBLISHED must be rejected
        with pytest.raises(InvalidLifecycleTransitionError, match="Illegal state transition"):
            engine.transition_lifecycle_state(ver, KnowledgeLifecycleState.PUBLISHED)

    def test_pending_review_transitions(self):
        engine = KnowledgeLifecycleEngine()
        ver_approved = DocumentVersion(
            version_id="ver_app",
            document_id="doc_01",
            lifecycle_state=KnowledgeLifecycleState.PENDING_REVIEW,
        )
        engine.transition_lifecycle_state(ver_approved, KnowledgeLifecycleState.PUBLISHED)
        assert ver_approved.lifecycle_state == KnowledgeLifecycleState.PUBLISHED

        ver_rejected = DocumentVersion(
            version_id="ver_rej",
            document_id="doc_01",
            lifecycle_state=KnowledgeLifecycleState.PENDING_REVIEW,
        )
        engine.reject_version(ver_rejected, reason="Inaccurate nitrogen application rate")
        assert ver_rejected.lifecycle_state == KnowledgeLifecycleState.REJECTED
        assert ver_rejected.status == DocumentVersionStatus.INVALID

    def test_failed_or_rejected_cannot_silently_become_published(self):
        engine = KnowledgeLifecycleEngine()
        ver = DocumentVersion(
            version_id="ver_fail",
            document_id="doc_01",
            lifecycle_state=KnowledgeLifecycleState.PROCESSING,
        )
        engine.fail_version(ver, reason="Ingestion parsing syntax error")
        assert ver.lifecycle_state == KnowledgeLifecycleState.FAILED

        # FAILED state cannot move directly to PUBLISHED
        with pytest.raises(InvalidLifecycleTransitionError):
            engine.transition_lifecycle_state(ver, KnowledgeLifecycleState.PUBLISHED)


class TestSupersessionAndRetirement:
    """Test suite covering version supersession, retirement, and history preservation."""

    def test_version_supersession_preserves_history(self):
        engine = KnowledgeLifecycleEngine()

        v1 = DocumentVersion(
            version_id="ver_1.0",
            document_id="doc_soil_01",
            version_number="1.0.0",
            status=DocumentVersionStatus.ACTIVE,
            lifecycle_state=KnowledgeLifecycleState.PUBLISHED,
        )

        v2 = DocumentVersion(
            version_id="ver_2.0",
            document_id="doc_soil_01",
            version_number="2.0.0",
            status=DocumentVersionStatus.PENDING_REVIEW,
            lifecycle_state=KnowledgeLifecycleState.PENDING_REVIEW,
        )

        rec_old, rec_new = engine.supersede_version(v1, v2, reason="Updated pH threshold tables")

        # Old version is SUPERSEDED, not deleted
        assert v1.status == DocumentVersionStatus.SUPERSEDED
        assert v1.lifecycle_state == KnowledgeLifecycleState.SUPERSEDED
        assert v1.version_id == "ver_1.0"

        # New version is active/published and references v1 as parent
        assert v2.status == DocumentVersionStatus.ACTIVE
        assert v2.lifecycle_state == KnowledgeLifecycleState.PUBLISHED
        assert v2.parent_version_id == "ver_1.0"

    def test_version_retirement(self):
        engine = KnowledgeLifecycleEngine()
        v1 = DocumentVersion(
            version_id="ver_outdated",
            document_id="doc_soil_01",
            status=DocumentVersionStatus.ACTIVE,
            lifecycle_state=KnowledgeLifecycleState.PUBLISHED,
        )

        engine.retire_version(v1, reason="Guidelines replaced by regional regulation")
        assert v1.status == DocumentVersionStatus.RETIRED
        assert v1.lifecycle_state == KnowledgeLifecycleState.RETIRED


class TestStep6AndCanonicalIntegration:
    """Test suite covering integration with Step 5 canonical models and Step 6 Metadata/Provenance/Assessment."""

    def test_historical_metadata_provenance_and_assessment_remain_intact(self):
        meta = CanonicalMetadata(domain="AGRICULTURE", crop="Maize")
        prov = Provenance(
            provenance_id="prov_v1",
            source_id="src_01",
            document_id="doc_01",
            version_id="ver_v1",
        )
        assess = SourceAssessment(
            assessment_id="assess_01",
            source_id="src_01",
            authority=0.9,
        )

        src = Source(source_id="src_01", source_name="FAO", source_type="EXT", assessment=assess)
        doc = Document(document_id="doc_01", source_id="src_01", title="Maize", document_type="GUIDE")

        v1 = DocumentVersion(
            version_id="ver_v1",
            document_id="doc_01",
            metadata=meta,
            provenance=prov,
            status=DocumentVersionStatus.ACTIVE,
            lifecycle_state=KnowledgeLifecycleState.PUBLISHED,
        )

        v2 = DocumentVersion(
            version_id="ver_v2",
            document_id="doc_01",
            metadata=meta,
            provenance=prov,
            lifecycle_state=KnowledgeLifecycleState.PENDING_REVIEW,
        )

        engine = KnowledgeLifecycleEngine()
        engine.supersede_version(v1, v2)

        # Lineage check
        assert validate_canonical_lineage(src, doc, v2) is True

        # v1 Metadata and Provenance remain intact
        assert v1.metadata.crop == "Maize"
        assert v1.provenance.provenance_id == "prov_v1"
        assert len(v1.provenance.processing_steps) > 0  # transition recorded in provenance
        assert src.assessment.authority == 0.9

    def test_storage_independence_no_external_dependencies(self):
        engine = KnowledgeLifecycleEngine()
        history = engine.get_transition_history()
        assert isinstance(history, list)
