# C.2 — Knowledge Base Step 9: Embedding Layer Foundation

**System:** EarthMind (`Earth-Mind.01`)
**Phase:** Phase C — Knowledge & Retrieval Foundation
**Step:** Step 9 — Embedding Layer Foundation
**Status:** IMPLEMENTED & DOCUMENTED

---

## 1. Architectural Blueprint & Responsibility

The Embedding Layer converts canonical retrieval-ready `KnowledgeUnit` and `Chunk` domain entities into traceable vector representations (`EmbeddingRecord`) that can later be ingested by future indexing and retrieval layers.

```
CANONICAL KNOWLEDGE
        ↓
KnowledgeUnit / Chunk
        ↓
EMBEDDING LAYER
        ↓
Embedding Representation
        ↓
FUTURE INDEX LAYER
```

### Architectural Principles:
1. **Provider Independence**: Core domain depends on generic interfaces (`IEmbeddingProvider`, `EmbeddingAdapter`), not vendor SDKs.
2. **Storage Independence**: Generates purely in-memory domain objects (`EmbeddingRecord`). No Qdrant, ORM, or database lock-in.
3. **Canonical Source Rule**: Embeddings are *derived* representations, NOT canonical knowledge. Regeneration or deletion of vector representations leaves canonical source knowledge intact.
4. **Traceability & Version Awareness**: Every vector record retains exact lineage references (`document_id`, `version_id`, `chunk_id`, `knowledge_unit_id`).
5. **Provider / Model / Version Traceability**: Records track active `provider`, `model`, `model_version`, `dimension`, and timestamp.
6. **Multimodal Capability & Boundaries**: Supports extensible input representations (`TEXT`, `TABLE`, `STRUCTURED_DATA`, `IMAGE`, `FIGURE`, `MULTIMODAL`). Non-supported raw binary content types without multimodal providers fail explicitly without vector fabrication.

---

## 2. Canonical-to-Embedding Relationship

Embeddings are derived projections from canonical knowledge entities:

```
+------------------------------------------+
|            Canonical Source              |
|   (Document, DocumentVersion, Chunk)     |
+------------------------------------------+
                     │
                     ▼ (Embedding Generation)
+------------------------------------------+
|            EmbeddingRecord               |
|  (embedding_id, dense_vector, status)    |
+------------------------------------------+
                     │
                     ▼ (Future Step)
+------------------------------------------+
|           Future Index Layer             |
|   (Vector DB / Qdrant / Sparse Index)    |
+------------------------------------------+
```

When an embedding provider or model changes, existing `EmbeddingRecord` entities are marked `SUPERSEDED`, and new records are generated without mutating canonical `Chunk` or `KnowledgeUnit` content.

---

## 3. Data Model & Abstraction

### 3.1 EmbeddingRecord Schema (`modules/knowledge_base/embedding/record.py`)
- `embedding_id`: Unique identifier (e.g. `emb_chk_...`)
- `source_id`: Origin source reference
- `document_id`: Logical document identifier
- `version_id`: Document version identifier
- `chunk_id`: Associated retrieval chunk identifier (optional)
- `knowledge_unit_id`: Associated knowledge unit identifier (optional)
- `representation_type`: `DENSE`, `SPARSE`, or `HYBRID`
- `provider`: Active embedding provider name
- `model`: Embedding model identifier
- `model_version`: Embedding model version string
- `dimension`: Vector dimension integer
- `dense_vector`: Float array representing dense vector payload
- `sparse_vector`: Optional `SparseVector` representation (term indices & weights)
- `content_type`: `KnowledgeContentType` (`TEXT`, `TABLE`, etc.)
- `status`: Lifecycle status (`ACTIVE`, `SUPERSEDED`, `DEPRECATED`, `FAILED`)
- `created_at`: UTC timestamp
- `metadata`: Extensible `CanonicalMetadata` or dictionary
- `provenance`: Step 6 `Provenance` record with embedding stage step

### 3.2 Engine & Batch Processing (`modules/knowledge_base/embedding/engine.py`)
`KnowledgeEmbeddingEngine` provides a provider-independent API for generating embeddings:
- `embed_chunk(chunk, include_sparse)`: Single chunk embedding.
- `embed_knowledge_unit(unit, include_sparse)`: Single knowledge unit embedding.
- `embed_chunks_batch(chunks, include_sparse, allow_partial)`: Batch processing for chunks.
- `embed_units_batch(units, include_sparse, allow_partial)`: Batch processing for units.
- `regenerate_embedding(target, previous_record)`: Historical replacement without source mutation.

`EmbeddingBatchResult` captures batch outputs:
- `batch_id`: Processing run identifier
- `lifecycle_state`: Set to `KnowledgeLifecycleState.EMBEDDED` on success
- `records`: List of generated `EmbeddingRecord`s
- `failed_items`: Per-item failure detail list
- `metrics`: Duration, token count, and dimension stats

---

## 4. Multimodal Support & Failure Handling

### 4.1 Extensible Content Types
- **Supported Textual Content**: `TEXT`, `TABLE`, `STRUCTURED_DATA` strings are serialized and embedded via text provider.
- **Raw Non-Textual Content**: `IMAGE`, `FIGURE`, or `MULTIMODAL` without an active multimodal provider return explicit unsupported errors (`InvalidEmbeddingInputError`) or partial batch failure records.

### 4.2 Failure Handling Rules
1. **Provider Unavailable**: Returns explicit error or `EmbeddingBatchResult` with `lifecycle_state = FAILED`.
2. **Dimension Mismatch**: Throws `EmbeddingDimensionMismatchError`.
3. **Empty or Whitespace Content**: Raises `InvalidEmbeddingInputError`.
4. **Partial Batch Failure**: Preserves valid items while recording failed items at their exact input indices without discarding valid outputs.
5. **No Vector Fabrication**: Never returns synthetic default vectors when processing fails.

---

## 5. Provenance & Lifecycle Integration

### 5.1 Provenance Enrichment
During embedding generation, the engine attaches an explicit `EMBEDDING_GENERATION` step to the canonical entity's `Provenance` chain:

```json
{
  "step_id": "step_embed_1790154803",
  "operation": "EMBEDDING_GENERATION",
  "processor_name": "KnowledgeEmbeddingEngine",
  "parameters": {
    "provider": "fake",
    "model": "earthmind-embed-v1",
    "model_version": "1.0.0",
    "dimension": 384
  },
  "timestamp": "2026-09-23T09:12:33Z",
  "status": "COMPLETED"
}
```

When an embedding provider is replaced, `provenance.update_representation_provider(...)` records the transition audit log.

### 5.2 Lifecycle Integration
Successful embedding generation produces `KnowledgeLifecycleState.EMBEDDED`.
Failure preserves `KnowledgeLifecycleState.FAILED`, `INVALID`, or `REJECTED` state.
The Embedding Layer does NOT produce `INDEXED` or `PUBLISHED` states, which are reserved for Step 10+ Index and Retrieval stages.

---

## 6. Boundary with Future Index & Retrieval Layers

The C.2 Embedding Layer boundary ends at the creation of storage-independent `EmbeddingRecord` objects.

It strictly excludes:
- Vector store drivers (Qdrant, Milvus, Pinecone, PGVector)
- Direct database writes
- Dense/Sparse retrieval candidate search
- Reciprocal Rank Fusion (RRF)
- Reranking
- Query expansion or RAG context formatting
