# C.2 Step 8: Document Processing & Chunking Pipeline Architecture

## Overview

The Document Processing and Chunking Pipeline forms the intake foundation for EarthMind's Knowledge Base (C.2). It transforms raw canonical documents and versions into structured `KnowledgeUnit`s and retrieval-ready `Chunk`s while preserving canonical identity, metadata, provenance, section hierarchy, and lifecycle state.

```
DOCUMENT
   ↓
PROCESSOR
   ↓
STRUCTURED CONTENT (NormalizedDocument)
   ↓
KNOWLEDGE UNIT
   ↓
SEMANTIC / STRUCTURAL CHUNKING
   ↓
CHUNK
   ↓
FUTURE EMBEDDING LAYER
```

---

## Processing Architecture & Replaceable Interfaces

The pipeline uses replaceable interfaces adhering to EarthMind's Rubber-Band and Loose Coupling principles:

### 1. Document Processor Interface (`IDocumentProcessor`)
Defines the contract for parsing document content into a normalized internal structure:

```python
class IDocumentProcessor(ABC):
    @abstractmethod
    def supports_content_type(self, content_type: str) -> bool: ...

    @abstractmethod
    def process(
        self,
        content: Any,
        content_type: str,
        config: Optional[ProcessorConfig] = None,
    ) -> NormalizedDocument: ...
```

Built-in implementations:
- `PlainTextProcessor`: Parses Markdown/plain text, heading structure (`#`, `##`, `###`), paragraph boundaries, and inline Markdown tables.
- `StructuredDocumentProcessor`: Parses structured JSON/dictionary documents with explicit section hierarchies, blocks of `TEXT`, `TABLE`, `IMAGE`, `FIGURE`, `STRUCTURED_DATA`, and `MULTIMODAL` modalities.

### 2. Normalized Representation
Intermediate internal model before canonical entity creation:
- `NormalizedBlock`: Atomic block (`TEXT`, `TABLE`, `IMAGE`, `FIGURE`, `STRUCTURED_DATA`, `MULTIMODAL`).
- `NormalizedSection`: Hierarchical section containing child blocks and nested subsections.
- `NormalizedDocument`: Complete document model containing top-level sections and unsectioned blocks.

### 3. Chunking Interface (`IChunker`)
Defines the contract for transforming `KnowledgeUnit`s into retrieval `Chunk`s:

```python
class IChunker(ABC):
    @abstractmethod
    def chunk_unit(
        self,
        unit: KnowledgeUnit,
        config: Optional[ChunkingConfig] = None,
    ) -> List[Chunk]: ...
```

---

## Semantic & Structural Chunking Strategy

`SemanticStructuralChunker` prioritizes natural content boundaries over fixed token slicing:

1. **Section Boundaries**: Section hierarchy (`parent_section_id`, `level`, `sequence`) is maintained.
2. **Subsection Boundaries**: Nested subsections remain linked to parent sections.
3. **Paragraph/Semantic Boundaries**: Text units are kept coherent per paragraph or semantic thought.
4. **Table / Figure Boundaries**: `TABLE`, `IMAGE`, `FIGURE`, `STRUCTURED_DATA`, and `MULTIMODAL` units remain atomic without arbitrary splitting.
5. **Token/Size Limits**: Slicing only occurs when a text unit exceeds `max_chunk_size` or `max_tokens`.

### Configurable Limits (`ChunkingConfig`)
- `max_chunk_size`: Maximum character length per chunk (default 1500).
- `preferred_chunk_size`: Target character length (default 800).
- `min_chunk_size`: Minimum threshold (default 50).
- `max_tokens`: Maximum estimated token limit per chunk (default 512).
- `overlap_size`: Optional character overlap for sub-split text chunks (default 0).

---

## Multimodal Preservation

Multimodal representations are never forced into plain text:
- **TABLE**: Structured dict (`headers`, `rows`) preserved.
- **IMAGE / FIGURE**: Media references, URI, caption, and dimensions preserved.
- **STRUCTURED_DATA**: Complete key-value payload retained.
- **MULTIMODAL**: Linked text, media, and structural attributes kept associated.

---

## Metadata & Provenance Propagation

Processing automatically propagates Step 6 metadata and records processing stages in Step 6 `Provenance`:
1. `STRUCTURE_DETECTION`: Logs section hierarchy detection.
2. `KNOWLEDGE_UNIT_CREATION`: Logs `KnowledgeUnit` generation per content type.
3. `CHUNKING`: Logs chunk creation with size/token metrics and `chunking_operation` details.

All generated entities undergo `validate_canonical_lineage` checks prior to pipeline completion.

---

## Lifecycle State Integration & Error Handling

Integrates with Step 7 `KnowledgeLifecycleState`:
- **`PROCESSED`**: Successfully processed, chunked, and validated lineage.
- **`REJECTED`**: Unsupported document content type.
- **`INVALID`**: Malformed content, empty text, or lineage validation failure.
- **`FAILED`**: Unhandled runtime exception or parsing failure.

Failure results return explicit `DocumentProcessingResult` objects with detailed `error_message` strings rather than fabricating content.
