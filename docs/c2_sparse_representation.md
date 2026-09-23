# C.2 — Knowledge Base Step 10: Sparse Representation

**System:** EarthMind (`Earth-Mind.01`)
**Phase:** Phase C — Knowledge & Retrieval Foundation
**Step:** Step 10 — Sparse Representation
**Status:** IMPLEMENTED & DOCUMENTED

---

## 1. Architectural Blueprint & Responsibility

The Sparse Representation layer provides a provider-independent foundation for generating sparse vector representations (such as BM25, TF-IDF lexical term weights, or learned sparse representations like SPLADE) from canonical retrieval-ready `KnowledgeUnit` and `Chunk` domain entities.

Sparse representations are **DERIVED** representations and must **NEVER** become the canonical source of truth. Deleting, regenerating, or replacing sparse representations leaves original canonical source knowledge intact.

```
                    CANONICAL CHUNK
                           │
                 ┌─────────┴─────────┐
                 ↓                   ↓
          DENSE REPRESENTATION  SPARSE REPRESENTATION
                 │                   │
                 └─────────┬─────────┘
                           ↓
                    FUTURE INDEX LAYER
```

### Architectural Principles:
1. **Provider Independence**: Core system depends on generic interfaces (`ISparseRepresentationProvider`, `SparseRepresentationAdapter`), not vendor SDKs or concrete sparse retrieval algorithms.
2. **Algorithm Compatibility**: Remains open to both lexical sparse (BM25 / TF-IDF) and learned sparse (SPLADE / BGE-M3 / Neural Sparse) representations.
3. **Storage Independence**: Generates purely in-memory domain objects (`SparseRepresentationRecord`). No Qdrant, Elasticsearch, ORM, or vector database lock-in.
4. **Canonical Source Rule**: Sparse representations are derived projections from canonical knowledge.
5. **Traceability & Version Awareness**: Every sparse record retains exact lineage references (`document_id`, `version_id`, `chunk_id`, `knowledge_unit_id`).
6. **Provider / Model / Vocabulary Traceability**: Records track active `provider`, `model`, `model_version`, `vocabulary_id`, `vocabulary_size`, and timestamp.
7. **Dense + Sparse Coexistence**: Sparse representations coexist independently with dense representations created by Step 9 without merging payloads into provider-specific structures.

---

## 2. Canonical-to-Sparse Relationship & Coexistence

Sparse representations are derived projections from canonical knowledge entities and run alongside dense representations:

```
+-------------------------------------------------------------+
|                      Canonical Source                       |
|          (Document, DocumentVersion, KnowledgeUnit, Chunk)  |
+-------------------------------------------------------------+
                               │
            ┌──────────────────┴──────────────────┐
            ↓                                     ↓
+-----------------------+             +-----------------------+
|    EmbeddingRecord    |             |SparseRepresentationRec|
| (Dense Vector Payload)|             |(Sparse Vector Payload)|
+-----------------------+             +-----------------------+
            │                                     │
            └──────────────────┬──────────────────┘
                               ↓
            +------------------------------------+
            |        Future Index Layer          |
            |     (Step 11+ Vector/Sparse DB)    |
            +------------------------------------+
```

When a sparse provider or model changes, existing `SparseRepresentationRecord` entities are marked `SUPERSEDED`, and new records are generated without mutating canonical source content.

---

## 3. Data Model & Sparse Vector Structure

### 3.1 SparseRepresentationRecord Schema (`modules/knowledge_base/sparse/record.py`)
- `representation_id`: Unique identifier (e.g. `sp_chk_...` or `sp_ku_...`)
- `source_id`: Origin source reference
- `document_id`: Logical document identifier
- `version_id`: Document version identifier
- `chunk_id`: Associated retrieval chunk identifier (optional)
- `knowledge_unit_id`: Associated knowledge unit identifier (optional)
- `representation_type`: `SPARSE` (or `LEXICAL`, `LEARNED_SPARSE`)
- `provider`: Active sparse representation provider name
- `model`: Sparse model identifier
- `model_version`: Sparse model version string
- `vocabulary_id`: Vocabulary/index-space identifier
- `vocabulary_size`: Vocabulary dimension integer
- `sparse_vector`: `SparseVector` payload (`indices`, `values`, `terms`)
- `content_type`: `KnowledgeContentType` (`TEXT`, `TABLE`, etc.)
- `status`: Lifecycle status (`ACTIVE`, `SUPERSEDED`, `DEPRECATED`, `FAILED`)
- `created_at`: UTC timestamp
- `metadata`: Extensible `CanonicalMetadata` or dictionary
- `provenance`: Step 6 `Provenance` record with sparse stage step

### 3.2 Sparse Vector Structure (`core/schemas/embedding.py` & `core/schemas/sparse.py`)
Conceptually consists of:
- `indices`: List of non-negative feature/term identifiers (`int`)
- `values`: List of finite numeric weights (`float`, non-NaN/inf)
- `terms`: Dict of term-to-weight mappings (`Dict[str, float]`)
- `dimension`: Optional sparse space dimension (`int`)

Validation rules enforced by `validate_sparse_vector`:
- Index and value list lengths must be aligned (`len(indices) == len(values)`).
- Indices must be non-negative integers (`idx >= 0`) and within `vocabulary_size` bound if configured.
- Values must be finite real numbers (no `NaN` or `infinity`).
- Feature/index ordering is strictly deterministic (ascending index order).

---

## 4. Engine, Adapter & Batch Processing

`KnowledgeSparseEngine` (`modules/knowledge_base/sparse/engine.py`) provides a provider-independent API:
- `generate_sparse_chunk(chunk)`: Single chunk sparse generation.
- `generate_sparse_knowledge_unit(unit)`: Single knowledge unit sparse generation.
- `generate_sparse_chunks_batch(chunks, allow_partial)`: Batch processing for chunks preserving input order.
- `generate_sparse_units_batch(units, allow_partial)`: Batch processing for units preserving input order.
- `regenerate_sparse(target, previous_record)`: Historical replacement without source mutation.

`SparseBatchResult` captures batch outputs:
- `batch_id`: Processing run identifier
- `lifecycle_state`: Set to `KnowledgeLifecycleState.EMBEDDED` on success
- `records`: List of generated `SparseRepresentationRecord`s
- `failed_items`: Per-item failure detail list
- `metrics`: Duration, token count, and vocabulary stats

---

## 5. Failure Handling Rules

1. **Provider Unavailable**: Throws `SparseProviderUnavailableError` or returns `SparseBatchResult` with `lifecycle_state = FAILED`.
2. **Mismatched Indices/Values**: Throws `SparseVectorValidationError`.
3. **Invalid Indices/Weights**: Throws `SparseVectorValidationError` on negative indices, out-of-bounds indices, or `NaN`/`inf` weights.
4. **Empty or Whitespace Content**: Raises `InvalidSparseInputError`.
5. **Partial Batch Failure**: Preserves valid items while recording failed items at their exact input indices.
6. **No Vector Fabrication**: Never returns synthetic default sparse vectors when processing fails.

---

## 6. Provenance & Lifecycle Integration

### 6.1 Provenance Enrichment
During sparse representation generation, the engine attaches a `SPARSE_GENERATION` step to the canonical entity's `Provenance` chain:

```json
{
  "step_id": "step_sparse_a8f912c4",
  "operation": "SPARSE_GENERATION",
  "processor_name": "KnowledgeSparseEngine",
  "parameters": {
    "provider": "fake_sparse",
    "model": "earthmind-sparse-v1",
    "model_version": "1.0.0",
    "vocabulary_id": "agri-vocab-30k",
    "vocabulary_size": 30000
  },
  "timestamp": "2026-09-23T10:15:00Z",
  "status": "COMPLETED"
}
```

### 6.2 Lifecycle Integration
Successful sparse representation generation produces `KnowledgeLifecycleState.EMBEDDED`.
Failure preserves `KnowledgeLifecycleState.FAILED`, `INVALID`, or `REJECTED` state.

---

## 7. Provider Replacement Strategy

Replacing the active sparse provider (e.g. switching from Lexical BM25 to Learned SPLADE):
1. Instantiate new `ISparseRepresentationProvider` implementation.
2. Update `SparseRepresentationAdapter` / `KnowledgeSparseEngine` via `set_provider(new_provider)`.
3. Existing `SparseRepresentationRecord` instances are marked `SUPERSEDED` during regeneration without destroying canonical provenance or raw source material.

---

## 8. Boundary with Step 11 Index Layer

The C.2 Sparse Representation boundary ends at the creation of storage-independent `SparseRepresentationRecord` objects in memory.

It strictly excludes:
- Physical index stores (Qdrant, Elasticsearch, inverted index files)
- Direct database writes
- Sparse / Dense hybrid retrieval router
- Reciprocal Rank Fusion (RRF)
- Reranking or Candidate scoring
- Query expansion or RAG context formatting
