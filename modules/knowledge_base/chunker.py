"""Semantic and Structural Chunking Engine for C.2 Knowledge Base.

This module implements semantic and structural chunking over canonical KnowledgeUnits and
normalized document structures, ensuring deterministic chunk generation and canonical lineage.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from modules.knowledge_base.enums import ChunkStatus, KnowledgeContentType
from modules.knowledge_base.canonical_models import Chunk, KnowledgeUnit


class ChunkingConfig(BaseModel):
    """Configurable boundaries and constraints for semantic/structural chunking."""
    max_chunk_size: int = Field(1500, ge=50, description="Maximum character length allowed per chunk")
    preferred_chunk_size: int = Field(800, ge=20, description="Target preferred character length per chunk")
    min_chunk_size: int = Field(50, ge=1, description="Minimum character length threshold")
    max_tokens: int = Field(512, ge=10, description="Maximum estimated token limit per chunk")
    overlap_size: int = Field(0, ge=0, description="Optional semantic overlap character count")

    def estimate_tokens(self, content: Any) -> int:
        """Estimate token count using standardized word/whitespace heuristic."""
        if isinstance(content, str):
            words = content.strip().split()
            return int(len(words) * 1.3) + 1 if words else 0
        elif isinstance(content, dict):
            import json
            text = json.dumps(content)
            words = text.split()
            return int(len(words) * 1.3) + 1 if words else 0
        return 1


class IChunker(ABC):
    """Abstract contract for replaceable chunking strategies."""

    @abstractmethod
    def chunk_unit(
        self,
        unit: KnowledgeUnit,
        config: Optional[ChunkingConfig] = None,
    ) -> List[Chunk]:
        """Transform a KnowledgeUnit into one or more retrieval Chunks."""
        pass


class SemanticStructuralChunker(IChunker):
    """Chunking engine prioritizing semantic and structural boundaries.

    Boundaries prefer:
    1. Section boundaries
    2. Subsection boundaries
    3. Paragraph/semantic boundaries
    4. Table/figure atomic boundaries
    5. Token/size constrained sub-splits when required.
    """

    def chunk_unit(
        self,
        unit: KnowledgeUnit,
        config: Optional[ChunkingConfig] = None,
    ) -> List[Chunk]:
        cfg = config or ChunkingConfig()
        chunks: List[Chunk] = []

        # Atomic handling for non-TEXT content types (TABLE, IMAGE, FIGURE, STRUCTURED_DATA, MULTIMODAL)
        if unit.content_type in {
            KnowledgeContentType.TABLE,
            KnowledgeContentType.IMAGE,
            KnowledgeContentType.FIGURE,
            KnowledgeContentType.STRUCTURED_DATA,
            KnowledgeContentType.MULTIMODAL,
        }:
            # Preserve atomic structure without splitting unless explicitly oversized in string form
            content_str = str(unit.content) if not isinstance(unit.content, str) else unit.content
            size_bytes = len(content_str.encode("utf-8"))
            tokens = cfg.estimate_tokens(unit.content)

            chunk = Chunk(
                chunk_id=f"chk_{unit.knowledge_unit_id}_001",
                knowledge_unit_id=unit.knowledge_unit_id,
                document_id=unit.document_id,
                version_id=unit.version_id,
                parent_section_id=unit.section_id,
                sequence=1,
                content=unit.content,
                content_type=unit.content_type,
                language="en",
                size_bytes=size_bytes,
                token_count=tokens,
                status=ChunkStatus.ACTIVE,
                metadata=unit.metadata.model_dump() if hasattr(unit.metadata, "model_dump") else (unit.metadata or {}),
                provenance=unit.provenance,
            )
            return [chunk]

        # Handling for TEXT content units
        text_content = str(unit.content) if unit.content is not None else ""
        if not text_content.strip():
            return []

        tokens = cfg.estimate_tokens(text_content)
        char_len = len(text_content)

        # If within size and token bounds, keep as single semantic chunk
        if char_len <= cfg.max_chunk_size and tokens <= cfg.max_tokens:
            chunk = Chunk(
                chunk_id=f"chk_{unit.knowledge_unit_id}_001",
                knowledge_unit_id=unit.knowledge_unit_id,
                document_id=unit.document_id,
                version_id=unit.version_id,
                parent_section_id=unit.section_id,
                sequence=1,
                content=text_content,
                content_type=KnowledgeContentType.TEXT,
                language="en",
                size_bytes=len(text_content.encode("utf-8")),
                token_count=tokens,
                status=ChunkStatus.ACTIVE,
                metadata=unit.metadata.model_dump() if hasattr(unit.metadata, "model_dump") else (unit.metadata or {}),
                provenance=unit.provenance,
            )
            return [chunk]

        # Oversized text unit: split along paragraph / sentence / word boundaries deterministically
        sub_segments = self._split_oversized_text(text_content, cfg)
        for idx, sub_text in enumerate(sub_segments, start=1):
            sub_tokens = cfg.estimate_tokens(sub_text)
            chunk = Chunk(
                chunk_id=f"chk_{unit.knowledge_unit_id}_{idx:03d}",
                knowledge_unit_id=unit.knowledge_unit_id,
                document_id=unit.document_id,
                version_id=unit.version_id,
                parent_section_id=unit.section_id,
                sequence=idx,
                content=sub_text,
                content_type=KnowledgeContentType.TEXT,
                language="en",
                size_bytes=len(sub_text.encode("utf-8")),
                token_count=sub_tokens,
                status=ChunkStatus.ACTIVE,
                metadata=unit.metadata.model_dump() if hasattr(unit.metadata, "model_dump") else (unit.metadata or {}),
                provenance=unit.provenance,
            )
            chunks.append(chunk)

        return chunks

    def _split_oversized_text(self, text: str, cfg: ChunkingConfig) -> List[str]:
        """Deterministically split oversized text into chunks meeting size and token limits."""
        # 1. Try paragraph boundaries
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        segments: List[str] = []

        current_buf: List[str] = []
        current_len = 0

        for p in paragraphs:
            p_len = len(p)
            p_tokens = cfg.estimate_tokens(p)

            # If paragraph itself is too large, split paragraph by sentence
            if p_len > cfg.max_chunk_size or p_tokens > cfg.max_tokens:
                if current_buf:
                    segments.append("\n\n".join(current_buf))
                    current_buf = []
                    current_len = 0

                s_segments = self._split_paragraph_by_sentences(p, cfg)
                segments.extend(s_segments)
                continue

            if current_len + p_len + 2 <= cfg.max_chunk_size:
                current_buf.append(p)
                current_len += p_len + 2
            else:
                if current_buf:
                    segments.append("\n\n".join(current_buf))
                current_buf = [p]
                current_len = p_len

        if current_buf:
            segments.append("\n\n".join(current_buf))

        # Handle optional semantic overlap if configured
        if cfg.overlap_size > 0 and len(segments) > 1:
            segments = self._apply_overlap(segments, cfg.overlap_size)

        return segments

    def _split_paragraph_by_sentences(self, paragraph: str, cfg: ChunkingConfig) -> List[str]:
        """Split a large paragraph along sentence boundaries."""
        import re
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", paragraph) if s.strip()]
        result: List[str] = []

        buf: List[str] = []
        buf_len = 0

        for s in sentences:
            s_len = len(s)
            if s_len > cfg.max_chunk_size:
                # Fallback to hard word wrapping for extreme sentences
                if buf:
                    result.append(" ".join(buf))
                    buf = []
                    buf_len = 0
                result.extend(self._split_string_hard(s, cfg.max_chunk_size))
                continue

            if buf_len + s_len + 1 <= cfg.max_chunk_size:
                buf.append(s)
                buf_len += s_len + 1
            else:
                if buf:
                    result.append(" ".join(buf))
                buf = [s]
                buf_len = s_len

        if buf:
            result.append(" ".join(buf))

        return result

    def _split_string_hard(self, text: str, max_size: int) -> List[str]:
        """Hard chunking fallback for oversized sentences/words."""
        chunks = []
        start = 0
        while start < len(text):
            chunks.append(text[start : start + max_size])
            start += max_size
        return chunks

    def _apply_overlap(self, segments: List[str], overlap_size: int) -> List[str]:
        """Prefix subsequent segments with overlap_size characters from the end of the prior segment."""
        overlapped = [segments[0]]
        for i in range(1, len(segments)):
            prev = segments[i - 1]
            overlap_text = prev[-overlap_size:] if len(prev) >= overlap_size else prev
            overlapped.append(f"{overlap_text}\n{segments[i]}")
        return overlapped
