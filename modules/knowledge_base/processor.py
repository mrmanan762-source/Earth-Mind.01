"""Document Processing Interfaces and Implementation for C.2 Knowledge Base.

This module defines the processing abstraction required to transform supported document content
into a normalized internal representation prior to KnowledgeUnit and Chunk creation.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
import re
from pydantic import BaseModel, Field

from modules.knowledge_base.enums import KnowledgeContentType


class ProcessorConfig(BaseModel):
    """Configuration options for document processing."""
    preserve_structure: bool = Field(True, description="Whether to detect and preserve document structure/hierarchy")
    extract_tables: bool = Field(True, description="Whether to parse and isolate inline tables")
    extract_metadata: bool = Field(True, description="Whether to extract embedded document metadata")
    default_language: str = Field("en", description="Default language code")
    custom_settings: Dict[str, Any] = Field(default_factory=dict, description="Extensible processor settings")


class NormalizedBlock(BaseModel):
    """Atomic content block within a normalized document structure."""
    block_id: str = Field(..., description="Block identifier within document")
    content_type: KnowledgeContentType = Field(KnowledgeContentType.TEXT, description="Content classification")
    content: Any = Field(..., description="Block content (text, table dict, image ref, etc.)")
    title: Optional[str] = Field(None, description="Optional block title or caption")
    sequence: int = Field(0, ge=0, description="Sequential order within section or document")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Block level metadata")


class NormalizedSection(BaseModel):
    """Hierarchical section representation within a normalized document structure."""
    section_id: str = Field(..., description="Unique section identifier")
    title: str = Field(..., description="Section title or heading")
    level: int = Field(1, ge=1, description="Heading depth level (1=top level)")
    sequence: int = Field(0, ge=0, description="Sequential position within structural level")
    parent_section_id: Optional[str] = Field(None, description="Parent section identifier if nested")
    blocks: List[NormalizedBlock] = Field(default_factory=list, description="Content blocks belonging directly to section")
    subsections: List["NormalizedSection"] = Field(default_factory=list, description="Nested child subsections")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Section level metadata")


class NormalizedDocument(BaseModel):
    """Normalized internal representation of a processed document."""
    title: Optional[str] = Field(None, description="Extracted or declared document title")
    content_type: str = Field(..., description="Source format content type")
    language: str = Field("en", description="Document language code")
    sections: List[NormalizedSection] = Field(default_factory=list, description="Top-level document sections")
    unsectioned_blocks: List[NormalizedBlock] = Field(default_factory=list, description="Blocks outside explicit sections")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extracted document metadata")


class DocumentProcessingError(Exception):
    """Raised when document content processing or parsing fails."""
    pass


class UnsupportedFormatError(DocumentProcessingError):
    """Raised when an unsupported document content type is provided."""
    pass


class MalformedDocumentError(DocumentProcessingError):
    """Raised when document content structure is invalid or corrupt."""
    pass


class IDocumentProcessor(ABC):
    """Abstract interface contract for replaceable document processors."""

    @abstractmethod
    def supports_content_type(self, content_type: str) -> bool:
        """Check if this processor supports the given MIME content type."""
        pass

    @abstractmethod
    def process(
        self,
        content: Any,
        content_type: str,
        config: Optional[ProcessorConfig] = None,
    ) -> NormalizedDocument:
        """Parse raw content into a normalized document representation."""
        pass


class PlainTextProcessor(IDocumentProcessor):
    """Processor for plain text and Markdown structured document content."""

    SUPPORTED_TYPES = {"text/plain", "text/markdown", "text/x-markdown", "text/md"}

    def supports_content_type(self, content_type: str) -> bool:
        return content_type.strip().lower() in self.SUPPORTED_TYPES

    def process(
        self,
        content: Any,
        content_type: str,
        config: Optional[ProcessorConfig] = None,
    ) -> NormalizedDocument:
        if not self.supports_content_type(content_type):
            raise UnsupportedFormatError(
                f"PlainTextProcessor does not support content type '{content_type}'."
            )

        if content is None:
            raise MalformedDocumentError("Document content cannot be None.")

        if isinstance(content, bytes):
            try:
                text = content.decode("utf-8")
            except Exception as e:
                raise MalformedDocumentError(f"Failed to decode byte content as UTF-8: {e}")
        elif isinstance(content, str):
            text = content
        else:
            raise MalformedDocumentError(f"Expected str or bytes content, got {type(content).__name__}.")

        if not text.strip():
            raise MalformedDocumentError("Document content is empty.")

        cfg = config or ProcessorConfig()
        lines = text.splitlines()

        # Extract title from first markdown header if present
        doc_title = None
        sections: List[NormalizedSection] = []
        unsectioned_blocks: List[NormalizedBlock] = []

        current_section_stack: List[NormalizedSection] = []
        current_text_lines: List[str] = []
        block_counter = 0
        section_counter = 0

        def flush_current_text(target_section: Optional[NormalizedSection]):
            nonlocal block_counter, current_text_lines
            if not current_text_lines:
                return

            raw_paragraph = "\n".join(current_text_lines).strip()
            current_text_lines = []
            if not raw_paragraph:
                return

            # Check if text is a markdown table
            if cfg.extract_tables and self._is_markdown_table(raw_paragraph):
                table_dict = self._parse_markdown_table(raw_paragraph)
                block = NormalizedBlock(
                    block_id=f"blk_{block_counter + 1}",
                    content_type=KnowledgeContentType.TABLE,
                    content=table_dict,
                    sequence=block_counter,
                )
            else:
                block = NormalizedBlock(
                    block_id=f"blk_{block_counter + 1}",
                    content_type=KnowledgeContentType.TEXT,
                    content=raw_paragraph,
                    sequence=block_counter,
                )

            block_counter += 1
            if target_section:
                target_section.blocks.append(block)
            else:
                unsectioned_blocks.append(block)

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Check heading (Markdown # or numbered heading like '1. CLIMATIC REQUIREMENTS')
            header_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            num_header_match = re.match(r"^(\d+(?:\.\d+)*)\.?\s+([A-Z][A-Za-z0-9\s&,–\-\(\)\.\:\/]{2,})$", stripped) if not header_match else None

            if cfg.preserve_structure and (header_match or num_header_match):
                # Flush pending text
                active_sec = current_section_stack[-1] if current_section_stack else None
                flush_current_text(active_sec)

                if header_match:
                    level = len(header_match.group(1))
                    heading_title = header_match.group(2).strip()
                else:
                    num_prefix = num_header_match.group(1).rstrip(".")
                    level = len(num_prefix.split("."))
                    heading_title = f"{num_header_match.group(1)}. {num_header_match.group(2).strip()}"

                if doc_title is None and level == 1:
                    doc_title = heading_title

                section_counter += 1
                sec_id = f"sec_{section_counter}"

                # Find parent section in stack
                while current_section_stack and current_section_stack[-1].level >= level:
                    current_section_stack.pop()

                parent_id = current_section_stack[-1].section_id if current_section_stack else None
                new_section = NormalizedSection(
                    section_id=sec_id,
                    title=heading_title,
                    level=level,
                    sequence=section_counter,
                    parent_section_id=parent_id,
                )

                if current_section_stack:
                    current_section_stack[-1].subsections.append(new_section)
                else:
                    sections.append(new_section)

                current_section_stack.append(new_section)
                i += 1
                continue

            # Check if paragraph boundary (empty line)
            if not stripped:
                active_sec = current_section_stack[-1] if current_section_stack else None
                flush_current_text(active_sec)
                i += 1
                continue

            current_text_lines.append(line)
            i += 1

        # Flush trailing text
        active_sec = current_section_stack[-1] if current_section_stack else None
        flush_current_text(active_sec)

        return NormalizedDocument(
            title=doc_title or "Untitled Document",
            content_type=content_type,
            language=cfg.default_language,
            sections=sections,
            unsectioned_blocks=unsectioned_blocks,
        )

    def _is_markdown_table(self, text: str) -> bool:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if len(lines) < 2:
            return False
        return lines[0].startswith("|") and lines[0].endswith("|") and ("|" in lines[1]) and ("-" in lines[1])

    def _parse_markdown_table(self, text: str) -> Dict[str, Any]:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        headers = [c.strip() for c in lines[0].strip("|").split("|")]
        rows = []
        for line in lines[2:]:  # skip header and delimiter line
            if line.startswith("|") and line.endswith("|"):
                row = [c.strip() for c in line.strip("|").split("|")]
                rows.append(row)
        return {"headers": headers, "rows": rows}


class StructuredDocumentProcessor(IDocumentProcessor):
    """Processor for structured dictionary or JSON document representations."""

    SUPPORTED_TYPES = {"application/json", "application/x-json", "structured/dict"}

    def supports_content_type(self, content_type: str) -> bool:
        return content_type.strip().lower() in self.SUPPORTED_TYPES

    def process(
        self,
        content: Any,
        content_type: str,
        config: Optional[ProcessorConfig] = None,
    ) -> NormalizedDocument:
        if not self.supports_content_type(content_type):
            raise UnsupportedFormatError(
                f"StructuredDocumentProcessor does not support content type '{content_type}'."
            )

        if content is None:
            raise MalformedDocumentError("Structured document content cannot be None.")

        if isinstance(content, str):
            import json
            try:
                data = json.loads(content)
            except Exception as e:
                raise MalformedDocumentError(f"Failed to parse JSON content: {e}")
        elif isinstance(content, dict):
            data = content
        else:
            raise MalformedDocumentError(
                f"Expected dict or JSON string content, got {type(content).__name__}."
            )

        if not isinstance(data, dict):
            raise MalformedDocumentError("Root structured content must be a dictionary.")

        cfg = config or ProcessorConfig()
        doc_title = data.get("title")
        language = data.get("language", cfg.default_language)
        metadata = data.get("metadata", {})

        sections: List[NormalizedSection] = []
        unsectioned_blocks: List[NormalizedBlock] = []

        # Parse sections if present
        raw_sections = data.get("sections", [])
        if not isinstance(raw_sections, list):
            raise MalformedDocumentError("'sections' field must be a list.")

        sec_counter = 0
        block_counter = 0

        def parse_section_dict(sec_dict: dict, parent_id: Optional[str] = None) -> NormalizedSection:
            nonlocal sec_counter, block_counter
            if not isinstance(sec_dict, dict):
                raise MalformedDocumentError("Section item must be a dict.")

            title = sec_dict.get("title")
            if not title or not isinstance(title, str):
                raise MalformedDocumentError("Section must have a non-empty string title.")

            sec_counter += 1
            sec_id = sec_dict.get("section_id", f"sec_{sec_counter}")
            level = sec_dict.get("level", 1)
            sequence = sec_dict.get("sequence", sec_counter)

            blocks = []
            raw_blocks = sec_dict.get("blocks", [])
            if not isinstance(raw_blocks, list):
                raise MalformedDocumentError("Section 'blocks' must be a list.")

            for b in raw_blocks:
                block_counter += 1
                blocks.append(self._parse_block_dict(b, block_counter))

            subsections = []
            raw_subs = sec_dict.get("subsections", [])
            if not isinstance(raw_subs, list):
                raise MalformedDocumentError("Section 'subsections' must be a list.")

            sec_obj = NormalizedSection(
                section_id=sec_id,
                title=title,
                level=level,
                sequence=sequence,
                parent_section_id=parent_id,
                blocks=blocks,
                metadata=sec_dict.get("metadata", {}),
            )

            for sub in raw_subs:
                subsections.append(parse_section_dict(sub, parent_id=sec_id))

            sec_obj.subsections = subsections
            return sec_obj

        for sec in raw_sections:
            sections.append(parse_section_dict(sec))

        # Parse unsectioned blocks if present
        raw_blocks = data.get("blocks", [])
        if isinstance(raw_blocks, list):
            for b in raw_blocks:
                block_counter += 1
                unsectioned_blocks.append(self._parse_block_dict(b, block_counter))

        if not sections and not unsectioned_blocks:
            raise MalformedDocumentError("Structured document contains no sections or content blocks.")

        return NormalizedDocument(
            title=doc_title or "Untitled Structured Document",
            content_type=content_type,
            language=language,
            sections=sections,
            unsectioned_blocks=unsectioned_blocks,
            metadata=metadata,
        )

    def _parse_block_dict(self, b_dict: Any, default_seq: int) -> NormalizedBlock:
        if not isinstance(b_dict, dict):
            raise MalformedDocumentError("Block item must be a dictionary.")

        raw_ct = b_dict.get("content_type", "TEXT")
        try:
            content_type = KnowledgeContentType(raw_ct)
        except ValueError:
            raise MalformedDocumentError(f"Invalid block content type: {raw_ct}")

        content = b_dict.get("content")
        if content is None:
            raise MalformedDocumentError("Block content must not be None.")

        block_id = b_dict.get("block_id", f"blk_{default_seq}")
        title = b_dict.get("title")
        sequence = b_dict.get("sequence", default_seq)

        return NormalizedBlock(
            block_id=block_id,
            content_type=content_type,
            content=content,
            title=title,
            sequence=sequence,
            metadata=b_dict.get("metadata", {}),
        )
