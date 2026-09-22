"""Unit tests for Step 6: Metadata, Provenance, and Source Assessment in EarthMind Knowledge Base."""

from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError

from modules.knowledge_base import (
    AccessPolicy,
    Artifact,
    ArtifactStatus,
    CanonicalMetadata,
    Chunk,
    ChunkStatus,
    Document,
    DocumentStatus,
    DocumentVersion,
    EvidenceType,
    KnowledgeContentType,
    KnowledgeUnit,
    ProcessingStatus,
    Provenance,
    QualityStatus,
    ReviewStatus,
    Section,
    Source,
    SourceAssessment,
    SourceStatus,
    Step6ValidationError,
    Visibility,
    validate_canonical_lineage,
    validate_metadata_structure,
    validate_provenance_chain,
    validate_source_assessment,
)


class TestMetadataModel:
    """Test suite covering CanonicalMetadata creation, validation, and attachment."""

    def test_metadata_creation_and_validation(self):
        now = datetime.now(timezone.utc)
        meta = CanonicalMetadata(
            object_id="doc_soil_01",
            object_type="Document",
            source_id="src_fao_01",
            document_id="doc_soil_01",
            content_type="text/markdown",
            language="en",
            domain="AGRICULTURE",
            topic="Soil Management",
            crop="Maize",
            region="East Africa",
            season="Main Rain",
            subject_category="Agronomy",
            relevant_timestamp=now,
            effective_from=now,
            effective_until=now + timedelta(days=365),
            retrieval_tags=["soil", "ph_management", "  liming  ", ""],
            search_terms=["acidic soil", "dolomite"],
            filterable_attributes={"ph_range": [5.5, 6.5], "target_crop": "Maize"},
            quality_status=QualityStatus.HIGH_QUALITY,
            completeness=0.95,
            processing_status=ProcessingStatus.COMPLETED,
            review_status=ReviewStatus.APPROVED,
            access_policy=AccessPolicy.PUBLIC,
            visibility=Visibility.PUBLIC,
            extra_metadata={"custom_flag": True},
        )

        assert meta.object_id == "doc_soil_01"
        assert meta.crop == "Maize"
        assert meta.retrieval_tags == ["soil", "ph_management", "liming"]  # empty string excluded & trimmed
        assert meta.completeness == 0.95
        assert meta.extra_metadata["custom_flag"] is True

    def test_metadata_temporal_ordering_validation(self):
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError, match="effective_until timestamp cannot be earlier"):
            CanonicalMetadata(
                effective_from=now,
                effective_until=now - timedelta(days=1),
            )

    def test_metadata_completeness_range_validation(self):
        with pytest.raises(ValidationError):
            CanonicalMetadata(completeness=1.5)

        with pytest.raises(ValidationError):
            CanonicalMetadata(completeness=-0.1)

    def test_metadata_attachment_to_canonical_objects(self):
        meta = CanonicalMetadata(
            domain="AGRICULTURE",
            crop="Wheat",
            retrieval_tags=["grain", "yield"],
        )

        src = Source(
            source_id="src_01",
            source_name="ICAR",
            source_type="RESEARCH_INSTITUTE",
            metadata=meta,
        )
        assert src.metadata.crop == "Wheat"

        doc = Document(
            document_id="doc_wheat_01",
            source_id="src_01",
            title="Wheat Yield Optimization",
            document_type="RESEARCH_PAPER",
            metadata=meta,
        )
        assert doc.metadata.domain == "AGRICULTURE"

        chunk = Chunk(
            chunk_id="chk_01",
            knowledge_unit_id="ku_01",
            document_id="doc_wheat_01",
            version_id="ver_01",
            content="Wheat sowing depth should be 3-5 cm.",
            metadata=meta,
        )
        assert chunk.metadata.retrieval_tags == ["grain", "yield"]


class TestProvenanceModel:
    """Test suite covering Provenance creation, chain tracking, and incomplete handling."""

    def test_provenance_creation_and_full_chain(self):
        prov = Provenance(
            provenance_id="prov_chk_101",
            source_id="src_fao_01",
            artifact_id="art_pdf_01",
            document_id="doc_soil_01",
            version_id="ver_soil_1.0",
            section_id="sec_liming",
            knowledge_unit_id="ku_liming_01",
            chunk_id="chk_101",
            processing_stage="CHUNKING",
            processing_operation="recursive_character_splitter",
            chunking_operation={"chunk_size": 512, "overlap": 64},
            representation_provider={"provider_id": "sarvam_embed", "model": "mrmanan762/EarthMind", "dimension": 1024},
            operation_id="job_chunk_run_20241010",
            version_identifiers={"chunker": "1.2.0", "pipeline": "0.5.1"},
        )

        assert prov.provenance_id == "prov_chk_101"
        assert prov.is_complete is True
        assert len(prov.missing_fields) == 0
        assert prov.representation_provider["dimension"] == 1024

    def test_explicit_handling_of_incomplete_provenance(self):
        # Missing source_id and version_id when chunk_id and knowledge_unit_id are specified
        prov = Provenance(
            provenance_id="prov_incomplete_01",
            chunk_id="chk_999",
            knowledge_unit_id="ku_999",
            # document_id, version_id, source_id missing!
        )

        assert prov.is_complete is False
        assert "version_id" in prov.missing_fields
        assert "document_id" in prov.missing_fields
        assert "source_id" in prov.missing_fields
        # Confirm no values were fabricated/invented
        assert prov.source_id is None
        assert prov.document_id is None

    def test_replacement_of_representation_provider_preserves_provenance(self):
        prov = Provenance(
            provenance_id="prov_rep_01",
            source_id="src_01",
            document_id="doc_01",
            version_id="ver_01",
            chunk_id="chk_01",
            representation_provider={"provider_id": "v1_dense", "model": "embed-v1"},
        )

        original_source_id = prov.source_id
        original_doc_id = prov.document_id

        # Update representation provider (e.g. migration to Sarvam-105B or new embedding model)
        new_provider = {"provider_id": "sarvam_105b_embed", "model": "mrmanan762/EarthMind", "dimension": 4096}
        prov.update_representation_provider(new_provider, operation_id="job_reindex_2025")

        # Canonical source lineage remains untouched
        assert prov.source_id == original_source_id
        assert prov.document_id == original_doc_id
        assert prov.representation_provider["provider_id"] == "sarvam_105b_embed"
        assert len(prov.processing_steps) == 1
        assert prov.processing_steps[0]["operation"] == "REPLACEMENT_REPRESENTATION_PROVIDER"


class TestSourceAssessmentModel:
    """Test suite covering SourceAssessment model, validation, and principles."""

    def test_source_assessment_creation_and_signals(self):
        assess = SourceAssessment(
            assessment_id="assess_fao_01",
            source_id="src_fao_01",
            authority=0.95,
            reliability=0.92,
            recency=0.88,
            domain_relevance=0.98,
            geographic_relevance=0.90,
            review_status=ReviewStatus.APPROVED,
            evidence_type=EvidenceType.EXTENSION_GUIDE,
            assessment_basis="Official FAO regional extension material published by subject matter experts.",
            assessed_by="inspector_v1",
        )

        assert assess.assessment_id == "assess_fao_01"
        assert assess.authority == 0.95
        assert assess.review_status == ReviewStatus.APPROVED
        assert assess.evidence_type == EvidenceType.EXTENSION_GUIDE

    def test_source_assessment_score_bounds_validation(self):
        with pytest.raises(ValidationError):
            SourceAssessment(
                assessment_id="assess_invalid",
                authority=1.5,  # must be <= 1.0
            )

        with pytest.raises(ValidationError):
            SourceAssessment(
                assessment_id="assess_invalid",
                reliability=-0.2,  # must be >= 0.0
            )

    def test_source_assessment_validation_function(self):
        valid_assess = SourceAssessment(
            assessment_id="assess_01",
            authority=0.8,
        )
        assert validate_source_assessment(valid_assess) is True

        with pytest.raises(Step6ValidationError):
            validate_source_assessment("invalid_string_instead_of_assessment")


class TestLineageAndValidationIntegration:
    """Test suite for integrated lineage and validator behavior."""

    def test_canonical_lineage_with_step6_attachments(self):
        meta = CanonicalMetadata(domain="AGRICULTURE", crop="Maize")
        prov = Provenance(
            provenance_id="prov_01",
            source_id="src_01",
            document_id="doc_01",
            version_id="ver_01",
        )
        assess = SourceAssessment(
            assessment_id="assess_01",
            source_id="src_01",
            authority=0.9,
        )

        src = Source(
            source_id="src_01",
            source_name="FAO",
            source_type="EXT",
            metadata=meta,
            provenance=prov,
            assessment=assess,
        )
        doc = Document(
            document_id="doc_01",
            source_id="src_01",
            title="Maize Guide",
            document_type="GUIDE",
            metadata=meta,
            provenance=prov,
            assessment=assess,
        )
        ver = DocumentVersion(
            version_id="ver_01",
            document_id="doc_01",
            metadata=meta,
            provenance=prov,
        )

        assert validate_canonical_lineage(src, doc, ver) is True

    def test_invalid_provenance_reference_rejection(self):
        prov = Provenance(
            provenance_id="prov_01",
            source_id="src_01",
            document_id="doc_01",
            chunk_id="chk_01",
        )

        # Mismatched entity reference check
        with pytest.raises(Step6ValidationError, match="Provenance entity reference mismatch"):
            validate_provenance_chain(prov, entity_id="chk_DIFFERENT_ID")

    def test_validate_metadata_structure_rejection(self):
        with pytest.raises(Step6ValidationError, match="Metadata must not be None"):
            validate_metadata_structure(None)

        with pytest.raises(Step6ValidationError, match="Invalid metadata object type"):
            validate_metadata_structure(12345)
