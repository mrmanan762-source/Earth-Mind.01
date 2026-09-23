"""Document Processing & Chunking Pipeline for C.2 Knowledge Base.

This module orchestrates the transformation:
Source/Artifact -> Document -> DocumentVersion -> Content Processing -> Structure Detection ->
KnowledgeUnit Creation -> Semantic + Structural Chunking -> Chunk Creation ->
Metadata / Provenance / Lifecycle Preservation -> Processing Result.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type, Union
from pydantic import BaseModel, Field

from modules.knowledge_base.enums import (
    KnowledgeContentType,
    KnowledgeLifecycleState,
    ProcessingStatus,
)
from modules.knowledge_base.metadata import CanonicalMetadata
from modules.knowledge_base.provenance import ProcessingStep, Provenance
from modules.knowledge_base.assessment import SourceAssessment
from modules.knowledge_base.canonical_models import (
    Chunk,
    Document,
    DocumentVersion,
    KnowledgeUnit,
    Section,
    Source,
    validate_canonical_lineage,
)
from modules.knowledge_base.processor import (
    DocumentProcessingError,
    IDocumentProcessor,
    MalformedDocumentError,
    NormalizedBlock,
    NormalizedDocument,
    NormalizedSection,
    PlainTextProcessor,
    ProcessorConfig,
    StructuredDocumentProcessor,
    UnsupportedFormatError,
)
from modules.knowledge_base.chunker import (
    ChunkingConfig,
    IChunker,
    SemanticStructuralChunker,
)


class DocumentProcessingResult(BaseModel):
    """Execution output from DocumentProcessingPipeline."""
    pipeline_run_id: str = Field(..., description="Unique processing job execution ID")
    lifecycle_state: KnowledgeLifecycleState = Field(..., description="Resulting lifecycle state")
    source_id: str = Field(..., description="Associated Source identifier")
    document_id: str = Field(..., description="Associated Document identifier")
    version_id: str = Field(..., description="Associated DocumentVersion identifier")
    sections: List[Section] = Field(default_factory=list, description="Generated canonical Sections")
    knowledge_units: List[KnowledgeUnit] = Field(default_factory=list, description="Generated KnowledgeUnits")
    chunks: List[Chunk] = Field(default_factory=list, description="Generated retrieval Chunks")
    processing_status: ProcessingStatus = Field(ProcessingStatus.COMPLETED, description="Status code")
    error_message: Optional[str] = Field(None, description="Detailed failure description if failed")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Execution metrics (counts, durations)")


class DocumentProcessingPipeline:
    """Orchestrates document processing, section hierarchy detection, KU creation, and chunking."""

    def __init__(
        self,
        processors: Optional[List[IDocumentProcessor]] = None,
        chunker: Optional[IChunker] = None,
    ):
        self.processors = processors or [PlainTextProcessor(), StructuredDocumentProcessor()]
        self.chunker = chunker or SemanticStructuralChunker()

    def process_document(
        self,
        source: Source,
        document: Document,
        version: DocumentVersion,
        content: Any,
        content_type: str,
        processor_config: Optional[ProcessorConfig] = None,
        chunking_config: Optional[ChunkingConfig] = None,
        pipeline_run_id: Optional[str] = None,
    ) -> DocumentProcessingResult:
        run_id = pipeline_run_id or f"run_proc_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        start_time = datetime.now(timezone.utc)

        # Basic pre-validation
        if content is None:
            return DocumentProcessingResult(
                pipeline_run_id=run_id,
                lifecycle_state=KnowledgeLifecycleState.INVALID,
                source_id=source.source_id,
                document_id=document.document_id,
                version_id=version.version_id,
                processing_status=ProcessingStatus.FAILED,
                error_message="Document content is None.",
            )

        # Find supporting processor
        matched_processor = None
        for proc in self.processors:
            if proc.supports_content_type(content_type):
                matched_processor = proc
                break

        if not matched_processor:
            return DocumentProcessingResult(
                pipeline_run_id=run_id,
                lifecycle_state=KnowledgeLifecycleState.REJECTED,
                source_id=source.source_id,
                document_id=document.document_id,
                version_id=version.version_id,
                processing_status=ProcessingStatus.FAILED,
                error_message=f"Unsupported document content type: '{content_type}'.",
            )

        # Step: Content Processing -> Structure Detection
        try:
            norm_doc = matched_processor.process(
                content=content,
                content_type=content_type,
                config=processor_config,
            )
        except UnsupportedFormatError as e:
            return DocumentProcessingResult(
                pipeline_run_id=run_id,
                lifecycle_state=KnowledgeLifecycleState.REJECTED,
                source_id=source.source_id,
                document_id=document.document_id,
                version_id=version.version_id,
                processing_status=ProcessingStatus.FAILED,
                error_message=f"Unsupported format: {str(e)}",
            )
        except (MalformedDocumentError, DocumentProcessingError) as e:
            return DocumentProcessingResult(
                pipeline_run_id=run_id,
                lifecycle_state=KnowledgeLifecycleState.INVALID,
                source_id=source.source_id,
                document_id=document.document_id,
                version_id=version.version_id,
                processing_status=ProcessingStatus.FAILED,
                error_message=f"Document parsing/structure error: {str(e)}",
            )
        except Exception as e:
            return DocumentProcessingResult(
                pipeline_run_id=run_id,
                lifecycle_state=KnowledgeLifecycleState.FAILED,
                source_id=source.source_id,
                document_id=document.document_id,
                version_id=version.version_id,
                processing_status=ProcessingStatus.FAILED,
                error_message=f"Unexpected processing error: {str(e)}",
            )

        sections: List[Section] = []
        knowledge_units: List[KnowledgeUnit] = []
        chunks: List[Chunk] = []

        section_counter = 0
        unit_counter = 0

        # Helper: Create Base Provenance
        base_prov = (
            version.provenance.model_copy(deep=True)
            if version.provenance
            else Provenance(
                provenance_id=f"prov_{version.version_id}",
                source_id=source.source_id,
                document_id=document.document_id,
                version_id=version.version_id,
                processing_stage="DOCUMENT_PROCESSING",
            )
        )

        # Recursively process sections and convert blocks to KnowledgeUnits
        def process_norm_section(norm_sec: NormalizedSection, parent_sec_id: Optional[str] = None) -> Optional[str]:
            nonlocal section_counter, unit_counter

            section_counter += 1
            sec_id = norm_sec.section_id or f"sec_{version.version_id}_{section_counter:03d}"

            sec_prov = base_prov.model_copy(deep=True)
            sec_prov.section_id = sec_id
            sec_prov.processing_steps.append({
                "step_id": f"step_sec_{len(sec_prov.processing_steps) + 1}",
                "operation": "STRUCTURE_DETECTION",
                "processor_name": "DocumentProcessingPipeline",
                "parameters": {"description": f"Detected section '{norm_sec.title}' at level {norm_sec.level}"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "COMPLETED",
            })

            sec_meta = (
                version.metadata.model_copy(deep=True)
                if isinstance(version.metadata, CanonicalMetadata)
                else (version.metadata or {})
            )

            canonical_sec = Section(
                section_id=sec_id,
                document_id=document.document_id,
                version_id=version.version_id,
                parent_section_id=parent_sec_id,
                title=norm_sec.title,
                sequence=norm_sec.sequence,
                level=norm_sec.level,
                metadata=sec_meta,
                provenance=sec_prov,
            )
            sections.append(canonical_sec)

            # Process direct blocks within section
            for blk in norm_sec.blocks:
                unit_counter += 1
                ku_id = f"ku_{version.version_id}_{unit_counter:03d}"

                ku_prov = sec_prov.model_copy(deep=True)
                ku_prov.knowledge_unit_id = ku_id
                ku_prov.processing_steps.append({
                    "step_id": f"step_ku_{len(ku_prov.processing_steps) + 1}",
                    "operation": "KNOWLEDGE_UNIT_CREATION",
                    "processor_name": "DocumentProcessingPipeline",
                    "parameters": {"description": f"Created {blk.content_type.value} KnowledgeUnit"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "COMPLETED",
                })

                ku = KnowledgeUnit(
                    knowledge_unit_id=ku_id,
                    document_id=document.document_id,
                    version_id=version.version_id,
                    section_id=sec_id,
                    content_type=blk.content_type,
                    content=blk.content,
                    sequence=blk.sequence,
                    metadata=sec_meta,
                    provenance=ku_prov,
                )
                knowledge_units.append(ku)

            # Recurse subsections
            for sub_norm in norm_sec.subsections:
                process_norm_section(sub_norm, parent_sec_id=sec_id)

            return sec_id

        for top_sec in norm_doc.sections:
            process_norm_section(top_sec)

        # Process unsectioned blocks
        for blk in norm_doc.unsectioned_blocks:
            unit_counter += 1
            ku_id = f"ku_{version.version_id}_{unit_counter:03d}"

            ku_prov = base_prov.model_copy(deep=True)
            ku_prov.knowledge_unit_id = ku_id
            ku_prov.processing_steps.append({
                "step_id": f"step_ku_{len(ku_prov.processing_steps) + 1}",
                "operation": "KNOWLEDGE_UNIT_CREATION",
                "processor_name": "DocumentProcessingPipeline",
                "parameters": {"description": f"Created unsectioned {blk.content_type.value} KnowledgeUnit"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "COMPLETED",
            })

            ku_meta = (
                version.metadata.model_copy(deep=True)
                if isinstance(version.metadata, CanonicalMetadata)
                else (version.metadata or {})
            )

            ku = KnowledgeUnit(
                knowledge_unit_id=ku_id,
                document_id=document.document_id,
                version_id=version.version_id,
                section_id=None,
                content_type=blk.content_type,
                content=blk.content,
                sequence=blk.sequence,
                metadata=ku_meta,
                provenance=ku_prov,
            )
            knowledge_units.append(ku)

        # Step: Semantic + Structural Chunking
        chunking_cfg = chunking_config or ChunkingConfig()
        for ku in knowledge_units:
            unit_chunks = self.chunker.chunk_unit(ku, config=chunking_cfg)
            for chk in unit_chunks:
                # Update chunk provenance
                if chk.provenance:
                    chk.provenance.chunk_id = chk.chunk_id
                    chk.provenance.chunking_operation = {
                        "max_chunk_size": chunking_cfg.max_chunk_size,
                        "overlap_size": chunking_cfg.overlap_size,
                    }
                    chk.provenance.processing_steps.append({
                        "step_id": f"step_chk_{len(chk.provenance.processing_steps) + 1}",
                        "operation": "CHUNKING",
                        "processor_name": "SemanticStructuralChunker",
                        "parameters": {"description": f"Generated chunk {chk.chunk_id}"},
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "status": "COMPLETED",
                    })
                chunks.append(chk)

        # Lineage Verification
        try:
            validate_canonical_lineage(
                source=source,
                document=document,
                version=version,
                sections=sections if sections else None,
                units=knowledge_units if knowledge_units else None,
                chunks=chunks if chunks else None,
            )
        except Exception as e:
            return DocumentProcessingResult(
                pipeline_run_id=run_id,
                lifecycle_state=KnowledgeLifecycleState.INVALID,
                source_id=source.source_id,
                document_id=document.document_id,
                version_id=version.version_id,
                processing_status=ProcessingStatus.FAILED,
                error_message=f"Canonical lineage verification failed: {str(e)}",
            )

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        return DocumentProcessingResult(
            pipeline_run_id=run_id,
            lifecycle_state=KnowledgeLifecycleState.PROCESSED,
            source_id=source.source_id,
            document_id=document.document_id,
            version_id=version.version_id,
            sections=sections,
            knowledge_units=knowledge_units,
            chunks=chunks,
            processing_status=ProcessingStatus.COMPLETED,
            metrics={
                "duration_seconds": duration,
                "sections_count": len(sections),
                "knowledge_units_count": len(knowledge_units),
                "chunks_count": len(chunks),
            },
        )
