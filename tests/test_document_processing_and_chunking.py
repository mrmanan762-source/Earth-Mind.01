"""Comprehensive Unit Tests for Step 8: Document Processing & Chunking Pipeline in EarthMind."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import pytest
from pydantic import ValidationError

from modules.knowledge_base import (
    AccessPolicy,
    Artifact,
    CanonicalMetadata,
    Chunk,
    ChunkingConfig,
    ChunkStatus,
    Document,
    DocumentProcessingError,
    DocumentProcessingPipeline,
    DocumentProcessingResult,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionStatus,
    EvidenceType,
    IDocumentProcessor,
    IChunker,
    KnowledgeContentType,
    KnowledgeLifecycleState,
    KnowledgeUnit,
    KnowledgeUnitStatus,
    MalformedDocumentError,
    NormalizedBlock,
    NormalizedDocument,
    NormalizedSection,
    PlainTextProcessor,
    ProcessingStatus,
    ProcessorConfig,
    Provenance,
    QualityStatus,
    Section,
    SemanticStructuralChunker,
    Source,
    SourceStatus,
    StructuredDocumentProcessor,
    UnsupportedFormatError,
    Visibility,
    validate_canonical_lineage,
)


@pytest.fixture
def sample_source_doc_ver():
    src = Source(
        source_id="src_fao_01",
        source_name="FAO Extension",
        source_type="GOVERNMENT",
    )
    doc = Document(
        document_id="doc_maize_01",
        source_id="src_fao_01",
        title="Maize Cultivation Guide",
        document_type="GUIDE",
    )
    ver = DocumentVersion(
        version_id="ver_maize_1.0",
        document_id="doc_maize_01",
        version_number="1.0.0",
        metadata=CanonicalMetadata(domain="AGRICULTURE", crop="Maize"),
        provenance=Provenance(
            provenance_id="prov_ver_1.0",
            source_id="src_fao_01",
            document_id="doc_maize_01",
            version_id="ver_maize_1.0",
        ),
    )
    return src, doc, ver


class TestDocumentProcessors:
    """Test suite for PlainTextProcessor and StructuredDocumentProcessor."""

    def test_1_plain_text_processing(self):
        processor = PlainTextProcessor()
        text = "This is a simple plain text document paragraph.\n\nSecond paragraph content."
        norm_doc = processor.process(text, "text/plain")

        assert norm_doc.title == "Untitled Document"
        assert len(norm_doc.unsectioned_blocks) == 2
        assert norm_doc.unsectioned_blocks[0].content_type == KnowledgeContentType.TEXT
        assert norm_doc.unsectioned_blocks[0].content == "This is a simple plain text document paragraph."

    def test_2_structured_document_processing(self):
        processor = StructuredDocumentProcessor()
        data = {
            "title": "Soil Management JSON Guide",
            "language": "en",
            "sections": [
                {
                    "section_id": "sec_01",
                    "title": "1. Introduction",
                    "level": 1,
                    "blocks": [
                        {
                            "block_id": "b1",
                            "content_type": "TEXT",
                            "content": "Soil health is essential for crop yields.",
                        }
                    ],
                }
            ],
        }
        norm_doc = processor.process(data, "application/json")
        assert norm_doc.title == "Soil Management JSON Guide"
        assert len(norm_doc.sections) == 1
        assert norm_doc.sections[0].title == "1. Introduction"
        assert norm_doc.sections[0].blocks[0].content == "Soil health is essential for crop yields."

    def test_3_section_hierarchy_preservation(self):
        processor = PlainTextProcessor()
        md_text = (
            "# Main Title\nOverview text.\n\n"
            "## Section 1\nSection 1 text.\n\n"
            "### Subsection 1.1\nSubsection 1.1 text."
        )
        norm_doc = processor.process(md_text, "text/markdown")

        assert norm_doc.title == "Main Title"
        assert len(norm_doc.sections) == 1
        top_sec = norm_doc.sections[0]
        assert top_sec.title == "Main Title"
        assert len(top_sec.subsections) == 1

        sec_1 = top_sec.subsections[0]
        assert sec_1.title == "Section 1"
        assert len(sec_1.subsections) == 1

        subsec_1_1 = sec_1.subsections[0]
        assert subsec_1_1.title == "Subsection 1.1"
        assert subsec_1_1.level == 3

    def test_4_subsection_hierarchy_preservation(self):
        processor = StructuredDocumentProcessor()
        data = {
            "title": "Hierarchical Guide",
            "sections": [
                {
                    "section_id": "sec_1",
                    "title": "Chapter 1",
                    "level": 1,
                    "subsections": [
                        {
                            "section_id": "sec_1_1",
                            "title": "1.1 Subtitle",
                            "level": 2,
                            "blocks": [{"content_type": "TEXT", "content": "Nested content"}],
                        }
                    ],
                }
            ],
        }
        norm_doc = processor.process(data, "application/json")
        assert norm_doc.sections[0].subsections[0].parent_section_id == "sec_1"


class TestKnowledgeUnitCreationAndTypes:
    """Test suite for KnowledgeUnit creation across content types."""

    def test_5_6_knowledge_unit_creation_text(self, sample_source_doc_ver):
        src, doc, ver = sample_source_doc_ver
        pipeline = DocumentProcessingPipeline()
        text = "# Soil Testing\n\nTake core samples at 0-20 cm depth."

        res = pipeline.process_document(src, doc, ver, text, "text/markdown")
        assert res.lifecycle_state == KnowledgeLifecycleState.PROCESSED
        assert len(res.knowledge_units) == 1
        ku = res.knowledge_units[0]
        assert ku.content_type == KnowledgeContentType.TEXT
        assert ku.content == "Take core samples at 0-20 cm depth."

    def test_7_table_knowledge_unit(self, sample_source_doc_ver):
        src, doc, ver = sample_source_doc_ver
        pipeline = DocumentProcessingPipeline()
        md_table = (
            "# Fertilizer Matrix\n\n"
            "| Crop | N (kg/ha) | P (kg/ha) |\n"
            "|---|---|---|\n"
            "| Maize | 120 | 60 |\n"
            "| Wheat | 100 | 50 |"
        )
        res = pipeline.process_document(src, doc, ver, md_table, "text/markdown")
        assert res.lifecycle_state == KnowledgeLifecycleState.PROCESSED
        assert len(res.knowledge_units) == 1
        ku = res.knowledge_units[0]
        assert ku.content_type == KnowledgeContentType.TABLE
        assert isinstance(ku.content, dict)
        assert ku.content["headers"] == ["Crop", "N (kg/ha)", "P (kg/ha)"]

    def test_8_image_figure_references(self, sample_source_doc_ver):
        src, doc, ver = sample_source_doc_ver
        pipeline = DocumentProcessingPipeline()
        structured_data = {
            "title": "Visual Analysis",
            "sections": [
                {
                    "title": "Figures Section",
                    "blocks": [
                        {
                            "content_type": "IMAGE",
                            "content": {"uri": "s3://images/leaf_spot.jpg", "resolution": "1080p"},
                        },
                        {
                            "content_type": "FIGURE",
                            "content": {"uri": "s3://figures/fig1.png", "caption": "Figure 1: Yield Trend"},
                        },
                    ],
                }
            ],
        }
        res = pipeline.process_document(src, doc, ver, structured_data, "application/json")
        assert res.lifecycle_state == KnowledgeLifecycleState.PROCESSED
        assert len(res.knowledge_units) == 2
        assert res.knowledge_units[0].content_type == KnowledgeContentType.IMAGE
        assert res.knowledge_units[1].content_type == KnowledgeContentType.FIGURE

    def test_9_structured_data_handling(self, sample_source_doc_ver):
        src, doc, ver = sample_source_doc_ver
        pipeline = DocumentProcessingPipeline()
        payload = {
            "title": "Sensors Payload",
            "blocks": [
                {
                    "content_type": "STRUCTURED_DATA",
                    "content": {"sensor_id": "sn_001", "moisture_pct": 24.5, "temp_c": 19.2},
                }
            ],
        }
        res = pipeline.process_document(src, doc, ver, payload, "application/json")
        assert res.lifecycle_state == KnowledgeLifecycleState.PROCESSED
        assert res.knowledge_units[0].content_type == KnowledgeContentType.STRUCTURED_DATA
        assert res.knowledge_units[0].content["sensor_id"] == "sn_001"

    def test_10_multimodal_representation_preservation(self, sample_source_doc_ver):
        src, doc, ver = sample_source_doc_ver
        pipeline = DocumentProcessingPipeline()
        payload = {
            "title": "Multimodal Section",
            "blocks": [
                {
                    "content_type": "MULTIMODAL",
                    "content": {
                        "text": "Infrared spectrum showing nitrogen deficiency.",
                        "image_uri": "s3://drone/ir_map_01.tif",
                        "spectral_data": [0.4, 0.7, 0.9],
                    },
                }
            ],
        }
        res = pipeline.process_document(src, doc, ver, payload, "application/json")
        assert res.lifecycle_state == KnowledgeLifecycleState.PROCESSED
        ku = res.knowledge_units[0]
        assert ku.content_type == KnowledgeContentType.MULTIMODAL
        assert ku.content["image_uri"] == "s3://drone/ir_map_01.tif"


class TestChunkingBehavior:
    """Test suite covering chunking policies, oversized limits, and overlap."""

    def test_11_semantic_structural_chunking(self, sample_source_doc_ver):
        src, doc, ver = sample_source_doc_ver
        pipeline = DocumentProcessingPipeline()
        md = "# Section A\nParagraph A1.\n\nParagraph A2.\n\n# Section B\nParagraph B1."

        res = pipeline.process_document(src, doc, ver, md, "text/markdown")
        assert res.lifecycle_state == KnowledgeLifecycleState.PROCESSED
        assert len(res.chunks) == 3
        assert res.chunks[0].content == "Paragraph A1."
        assert res.chunks[1].content == "Paragraph A2."

    def test_12_13_oversized_unit_and_configurable_limits(self, sample_source_doc_ver):
        src, doc, ver = sample_source_doc_ver
        pipeline = DocumentProcessingPipeline()
        long_paragraph = "Sowing depth is crucial. " * 30  # ~720 chars

        cfg = ChunkingConfig(max_chunk_size=200, max_tokens=50)
        res = pipeline.process_document(
            src, doc, ver, long_paragraph, "text/plain", chunking_config=cfg
        )

        assert res.lifecycle_state == KnowledgeLifecycleState.PROCESSED
        assert len(res.chunks) > 1
        for chk in res.chunks:
            assert len(chk.content) <= 200

    def test_14_deterministic_output_ordering(self, sample_source_doc_ver):
        src, doc, ver = sample_source_doc_ver
        pipeline = DocumentProcessingPipeline()
        text = "# Header 1\nText 1.\n\nText 2.\n\n# Header 2\nText 3."

        res1 = pipeline.process_document(src, doc, ver, text, "text/markdown")
        res2 = pipeline.process_document(src, doc, ver, text, "text/markdown")

        assert [s.section_id for s in res1.sections] == [s.section_id for s in res2.sections]
        assert [k.knowledge_unit_id for k in res1.knowledge_units] == [k.knowledge_unit_id for k in res2.knowledge_units]
        assert [c.content for c in res1.chunks] == [c.content for c in res2.chunks]


class TestLineageAndMetadataProvenance:
    """Test suite covering parent-child chunk lineage, metadata, and provenance."""

    def test_15_16_canonical_lineage_preservation(self, sample_source_doc_ver):
        src, doc, ver = sample_source_doc_ver
        pipeline = DocumentProcessingPipeline()
        text = "# Chapter 1\nDetailed agronomic text."

        res = pipeline.process_document(src, doc, ver, text, "text/markdown")
        assert res.lifecycle_state == KnowledgeLifecycleState.PROCESSED

        chunk = res.chunks[0]
        ku = res.knowledge_units[0]
        sec = res.sections[0]

        # Verify lineage chain: Chunk -> KnowledgeUnit -> Section -> Version -> Document -> Source
        assert chunk.knowledge_unit_id == ku.knowledge_unit_id
        assert chunk.document_id == doc.document_id
        assert chunk.version_id == ver.version_id
        assert chunk.parent_section_id == sec.section_id

        assert ku.document_id == doc.document_id
        assert ku.version_id == ver.version_id
        assert ku.section_id == sec.section_id

        assert sec.document_id == doc.document_id
        assert sec.version_id == ver.version_id

        assert validate_canonical_lineage(
            src, doc, ver, sections=res.sections, units=res.knowledge_units, chunks=res.chunks
        ) is True

    def test_17_18_19_metadata_provenance_and_lifecycle(self, sample_source_doc_ver):
        src, doc, ver = sample_source_doc_ver
        pipeline = DocumentProcessingPipeline()
        text = "# Soil Test\nSample pH is 6.2."

        res = pipeline.process_document(src, doc, ver, text, "text/markdown")
        assert res.lifecycle_state == KnowledgeLifecycleState.PROCESSED

        chunk = res.chunks[0]
        assert chunk.metadata.crop == "Maize"  # Propagated from DocumentVersion metadata
        assert chunk.provenance is not None
        assert chunk.provenance.source_id == src.source_id
        assert chunk.provenance.document_id == doc.document_id
        assert chunk.provenance.version_id == ver.version_id
        assert chunk.provenance.chunk_id == chunk.chunk_id


class TestErrorAndFailureHandling:
    """Test suite covering failure scenarios and invalid inputs."""

    def test_20_unsupported_format_handling(self, sample_source_doc_ver):
        src, doc, ver = sample_source_doc_ver
        pipeline = DocumentProcessingPipeline()

        res = pipeline.process_document(src, doc, ver, "some binary content", "application/pdf")
        assert res.lifecycle_state == KnowledgeLifecycleState.REJECTED
        assert res.processing_status == ProcessingStatus.FAILED
        assert "Unsupported document content type" in res.error_message

    def test_21_22_malformed_and_empty_content_handling(self, sample_source_doc_ver):
        src, doc, ver = sample_source_doc_ver
        pipeline = DocumentProcessingPipeline()

        # Empty content
        res_empty = pipeline.process_document(src, doc, ver, "   ", "text/plain")
        assert res_empty.lifecycle_state == KnowledgeLifecycleState.INVALID
        assert "empty" in res_empty.error_message.lower()

        # Malformed JSON
        res_json = pipeline.process_document(src, doc, ver, "{invalid_json: 123", "application/json")
        assert res_json.lifecycle_state == KnowledgeLifecycleState.INVALID
        assert "Failed to parse JSON" in res_json.error_message

    def test_23_processing_failure_handling(self, sample_source_doc_ver):
        src, doc, ver = sample_source_doc_ver

        class FailingProcessor(IDocumentProcessor):
            def supports_content_type(self, content_type: str) -> bool:
                return content_type == "text/failing"

            def process(self, content: Any, content_type: str, config: Optional[ProcessorConfig] = None) -> NormalizedDocument:
                raise RuntimeError("Internal parser exception")

        pipeline = DocumentProcessingPipeline(processors=[FailingProcessor()])
        res = pipeline.process_document(src, doc, ver, "data", "text/failing")

        assert res.lifecycle_state == KnowledgeLifecycleState.FAILED
        assert "Unexpected processing error" in res.error_message

    def test_24_no_direct_database_vector_or_embedding_dependencies(self):
        # Confirm processor and pipeline operate strictly in-memory over pydantic models
        import modules.knowledge_base.processor as proc_mod
        import modules.knowledge_base.chunker as chunk_mod
        import modules.knowledge_base.pipeline as pipe_mod

        for mod in [proc_mod, chunk_mod, pipe_mod]:
            code = open(mod.__file__).read()
            assert "sqlite" not in code.lower()
            assert "qdrant" not in code.lower()
            assert "vector" not in code.lower()
            assert "embedding" not in code.lower()
