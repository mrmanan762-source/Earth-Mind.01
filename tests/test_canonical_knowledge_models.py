"""Unit tests for C.2 Canonical Knowledge Data Model in EarthMind."""

from datetime import datetime, timedelta, timezone
import json
import pytest
from pydantic import ValidationError

from modules.knowledge_base import (
    Artifact,
    ArtifactStatus,
    ChangeType,
    Chunk,
    ChunkStatus,
    Document,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    KnowledgeContentType,
    KnowledgeUnit,
    KnowledgeUnitStatus,
    LineageValidationError,
    Section,
    Source,
    SourceStatus,
    validate_canonical_lineage,
)
from core.schemas.application import ApplicationRequest, ApplicationResponse


class TestSourceModel:
    """Test suite for Source canonical entity."""

    def test_valid_source_creation(self):
        source = Source(
            source_id="src_fao_01",
            source_name="FAO Agricultural Extension",
            source_type="GOVERNMENT_EXTENSION",
            organization="Food and Agriculture Organization",
            origin="https://www.fao.org/land-water",
            language="en",
            region="East Africa",
        )
        assert source.source_id == "src_fao_01"
        assert source.source_name == "FAO Agricultural Extension"
        assert source.source_type == "GOVERNMENT_EXTENSION"
        assert source.status == SourceStatus.ACTIVE
        assert isinstance(source.created_at, datetime)

    def test_source_invalid_empty_fields(self):
        with pytest.raises(ValidationError):
            Source(
                source_id="",
                source_name="FAO Extension",
                source_type="GOVERNMENT_EXTENSION",
            )

        with pytest.raises(ValidationError):
            Source(
                source_id="src_01",
                source_name="  ",
                source_type="GOVERNMENT_EXTENSION",
            )


class TestArtifactModel:
    """Test suite for Artifact canonical entity."""

    def test_valid_artifact_creation(self):
        artifact = Artifact(
            artifact_id="art_pdf_101",
            source_id="src_fao_01",
            location_reference="raw_storage/fao/soil_guide_2024.pdf",
            content_type="application/pdf",
            checksum="a1b2c3d4e5f67890",
            size_bytes=2048500,
        )
        assert artifact.artifact_id == "art_pdf_101"
        assert artifact.source_id == "src_fao_01"
        assert artifact.status == ArtifactStatus.RAW
        assert artifact.size_bytes == 2048500

    def test_artifact_invalid_size_and_empty_reference(self):
        with pytest.raises(ValidationError):
            Artifact(
                artifact_id="art_01",
                source_id="src_01",
                location_reference="path/to/file",
                content_type="application/pdf",
                size_bytes=-100,
            )

        with pytest.raises(ValidationError):
            Artifact(
                artifact_id="art_01",
                source_id="src_01",
                location_reference="",
                content_type="application/pdf",
            )


class TestDocumentModel:
    """Test suite for Document canonical entity."""

    def test_document_stable_identity(self):
        doc = Document(
            document_id="doc_soil_management_01",
            source_id="src_fao_01",
            title="Tropical Soil Management Guidelines",
            document_type="GUIDELINE",
            language="en",
            region="Sub-Saharan Africa",
        )
        assert doc.document_id == "doc_soil_management_01"
        assert doc.status == DocumentStatus.ACTIVE

    def test_document_validation(self):
        with pytest.raises(ValidationError):
            Document(
                document_id="doc_01",
                source_id="src_01",
                title="",
                document_type="GUIDELINE",
            )


class TestDocumentVersionModel:
    """Test suite for DocumentVersion canonical entity."""

    def test_document_version_lineage(self):
        now = datetime.now(timezone.utc)
        v1 = DocumentVersion(
            version_id="ver_soil_1.0",
            document_id="doc_soil_management_01",
            version_number="1.0.0",
            effective_from=now,
            effective_until=now + timedelta(days=365),
            change_type=ChangeType.INITIAL_CREATION,
            change_summary="Initial publication of soil guide",
        )
        assert v1.version_id == "ver_soil_1.0"
        assert v1.status == DocumentVersionStatus.ACTIVE

        v2 = DocumentVersion(
            version_id="ver_soil_2.0",
            document_id="doc_soil_management_01",
            parent_version_id="ver_soil_1.0",
            version_number="2.0.0",
            change_type=ChangeType.MAJOR_REVISION,
            change_summary="Updated pH threshold guidelines for acidic soils",
        )
        assert v2.parent_version_id == "ver_soil_1.0"

    def test_version_self_parent_rejection(self):
        with pytest.raises(ValidationError):
            DocumentVersion(
                version_id="ver_01",
                document_id="doc_01",
                parent_version_id="ver_01",
            )

    def test_version_invalid_date_range(self):
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError):
            DocumentVersion(
                version_id="ver_01",
                document_id="doc_01",
                effective_from=now,
                effective_until=now - timedelta(days=1),
            )


class TestSectionModel:
    """Test suite for Section hierarchical document structure."""

    def test_section_deep_hierarchy(self):
        s1 = Section(
            section_id="sec_01",
            document_id="doc_soil_01",
            version_id="ver_soil_1.0",
            title="Chapter 1: Soil pH Adjustment",
            sequence=1,
            level=1,
        )

        s2 = Section(
            section_id="sec_01_sub01",
            document_id="doc_soil_01",
            version_id="ver_soil_1.0",
            parent_section_id="sec_01",
            title="1.1 Liming Materials",
            sequence=1,
            level=2,
        )

        s3 = Section(
            section_id="sec_01_sub01_sub01",
            document_id="doc_soil_01",
            version_id="ver_soil_1.0",
            parent_section_id="sec_01_sub01",
            title="1.1.1 Dolomitic Limestone Application Rates",
            sequence=1,
            level=3,
        )

        assert s1.level == 1
        assert s2.parent_section_id == "sec_01"
        assert s3.parent_section_id == "sec_01_sub01"
        assert s3.level == 3

    def test_section_self_parent_rejection(self):
        with pytest.raises(ValidationError):
            Section(
                section_id="sec_01",
                document_id="doc_01",
                version_id="ver_01",
                parent_section_id="sec_01",
                title="Invalid Section",
            )

    def test_section_invalid_level_and_sequence(self):
        with pytest.raises(ValidationError):
            Section(
                section_id="sec_01",
                document_id="doc_01",
                version_id="ver_01",
                title="Title",
                level=0,  # level must be >= 1
            )


class TestKnowledgeUnitModel:
    """Test suite for KnowledgeUnit canonical entity across content types."""

    def test_text_knowledge_unit(self):
        ku = KnowledgeUnit(
            knowledge_unit_id="ku_text_01",
            document_id="doc_soil_01",
            version_id="ver_soil_1.0",
            section_id="sec_01",
            content_type=KnowledgeContentType.TEXT,
            content="Application of agricultural lime increases soil pH and improves calcium availability.",
            sequence=1,
        )
        assert ku.content_type == KnowledgeContentType.TEXT
        assert isinstance(ku.content, str)

    def test_table_knowledge_unit(self):
        table_payload = {
            "headers": ["Crop", "Target pH Range", "Lime Requirement (t/ha)"],
            "rows": [
                ["Maize", "6.0 - 6.8", "2.5"],
                ["Wheat", "6.0 - 7.0", "2.0"],
                ["Soybean", "6.2 - 7.0", "3.0"],
            ],
        }
        ku = KnowledgeUnit(
            knowledge_unit_id="ku_table_01",
            document_id="doc_soil_01",
            version_id="ver_soil_1.0",
            section_id="sec_01_sub01",
            content_type=KnowledgeContentType.TABLE,
            content=table_payload,
            sequence=2,
        )
        assert ku.content_type == KnowledgeContentType.TABLE
        assert ku.content["headers"][0] == "Crop"

    def test_multimodal_and_image_units(self):
        img_ku = KnowledgeUnit(
            knowledge_unit_id="ku_img_01",
            document_id="doc_soil_01",
            version_id="ver_soil_1.0",
            content_type=KnowledgeContentType.IMAGE,
            content={"uri": "s3://earthmind-kb/images/soil_profile_acidic.png", "caption": "Acidic soil profile"},
        )
        assert img_ku.content_type == KnowledgeContentType.IMAGE

        mm_ku = KnowledgeUnit(
            knowledge_unit_id="ku_mm_01",
            document_id="doc_soil_01",
            version_id="ver_soil_1.0",
            content_type=KnowledgeContentType.MULTIMODAL,
            content={
                "text": "Diagram showing root stunted growth under low pH.",
                "image_ref": "s3://earthmind-kb/images/root_stunting.jpg",
            },
        )
        assert mm_ku.content_type == KnowledgeContentType.MULTIMODAL

    def test_none_content_rejection(self):
        with pytest.raises(ValidationError):
            KnowledgeUnit(
                knowledge_unit_id="ku_01",
                document_id="doc_01",
                version_id="ver_01",
                content=None,
            )


class TestChunkModel:
    """Test suite for Chunk canonical entity."""

    def test_valid_chunk_creation(self):
        chunk = Chunk(
            chunk_id="chunk_01_001",
            knowledge_unit_id="ku_text_01",
            document_id="doc_soil_01",
            version_id="ver_soil_1.0",
            parent_section_id="sec_01",
            sequence=1,
            content="Application of agricultural lime increases soil pH...",
            content_type=KnowledgeContentType.TEXT,
            language="en",
            size_bytes=52,
            token_count=10,
            status=ChunkStatus.ACTIVE,
        )
        assert chunk.chunk_id == "chunk_01_001"
        assert chunk.knowledge_unit_id == "ku_text_01"
        assert chunk.token_count == 10

    def test_chunk_validation_errors(self):
        with pytest.raises(ValidationError):
            Chunk(
                chunk_id="chk_01",
                knowledge_unit_id="ku_01",
                document_id="doc_01",
                version_id="ver_01",
                content=None,
            )


class TestLineageAndRelationships:
    """Test suite for cross-entity lineage verification."""

    def test_valid_lineage_verification(self):
        src = Source(source_id="src_01", source_name="FAO", source_type="EXT")
        doc = Document(document_id="doc_01", source_id="src_01", title="Soil", document_type="GUIDE")
        ver = DocumentVersion(version_id="ver_01", document_id="doc_01")
        sec = Section(section_id="sec_01", document_id="doc_01", version_id="ver_01", title="Ch 1")
        unit = KnowledgeUnit(knowledge_unit_id="ku_01", document_id="doc_01", version_id="ver_01", section_id="sec_01", content="Soil text")
        chunk = Chunk(chunk_id="chk_01", knowledge_unit_id="ku_01", document_id="doc_01", version_id="ver_01", parent_section_id="sec_01", content="Soil text")

        assert validate_canonical_lineage(src, doc, ver, [sec], [unit], [chunk]) is True

    def test_mismatched_source_lineage_failure(self):
        src = Source(source_id="src_01", source_name="FAO", source_type="EXT")
        doc = Document(document_id="doc_01", source_id="src_OTHER", title="Soil", document_type="GUIDE")
        ver = DocumentVersion(version_id="ver_01", document_id="doc_01")

        with pytest.raises(LineageValidationError, match="source_id"):
            validate_canonical_lineage(src, doc, ver)

    def test_mismatched_document_lineage_failure(self):
        src = Source(source_id="src_01", source_name="FAO", source_type="EXT")
        doc = Document(document_id="doc_01", source_id="src_01", title="Soil", document_type="GUIDE")
        ver = DocumentVersion(version_id="ver_01", document_id="doc_OTHER")

        with pytest.raises(LineageValidationError, match="document_id"):
            validate_canonical_lineage(src, doc, ver)

    def test_unknown_section_reference_failure(self):
        src = Source(source_id="src_01", source_name="FAO", source_type="EXT")
        doc = Document(document_id="doc_01", source_id="src_01", title="Soil", document_type="GUIDE")
        ver = DocumentVersion(version_id="ver_01", document_id="doc_01")
        sec = Section(section_id="sec_01", document_id="doc_01", version_id="ver_01", title="Ch 1")
        unit = KnowledgeUnit(
            knowledge_unit_id="ku_01",
            document_id="doc_01",
            version_id="ver_01",
            section_id="sec_NON_EXISTENT",
            content="Soil text",
        )

        with pytest.raises(LineageValidationError, match="unknown section_id"):
            validate_canonical_lineage(src, doc, ver, sections=[sec], units=[unit])


class TestSerializationAndCompatibility:
    """Test suite for serialization/deserialization and schema integration."""

    def test_source_serialization(self):
        source = Source(
            source_id="src_fao_01",
            source_name="FAO Extension",
            source_type="GOVERNMENT_EXTENSION",
        )
        json_str = source.model_dump_json()
        data = json.loads(json_str)
        assert data["source_id"] == "src_fao_01"

        reconstructed = Source.model_validate_json(json_str)
        assert reconstructed.source_id == source.source_id
        assert reconstructed.source_name == source.source_name

    def test_multimodal_unit_serialization(self):
        ku = KnowledgeUnit(
            knowledge_unit_id="ku_table_01",
            document_id="doc_soil_01",
            version_id="ver_soil_1.0",
            content_type=KnowledgeContentType.TABLE,
            content={"columns": ["pH", "Lime"], "rows": [[5.5, 2.0]]},
        )
        json_data = ku.model_dump_json()
        restored = KnowledgeUnit.model_validate_json(json_data)
        assert restored.content["columns"] == ["pH", "Lime"]

    def test_application_schema_compatibility(self):
        source = Source(
            source_id="src_fao_01",
            source_name="FAO Extension",
            source_type="GOVERNMENT_EXTENSION",
        )
        req = ApplicationRequest(
            request_id="req_kb_001",
            source="test_runner",
            operation="ingest_canonical_source",
            payload=source.model_dump(),
        )
        assert req.payload["source_id"] == "src_fao_01"

        resp = ApplicationResponse(
            request_id="req_kb_001",
            status="SUCCESS",
            response=source.model_dump(),
        )
        assert resp.response["source_name"] == "FAO Extension"
