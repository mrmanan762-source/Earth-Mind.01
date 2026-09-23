# C.2 Step 11 — Index Layer + Qdrant Adapter Architecture

**System:** EarthMind (Earth-Mind.01)
**Module:** C.2 — Knowledge Base
**Component:** Index Layer & Vector Persistence Adapter
**Status:** IMPLEMENTED & VERIFIED

---

## 1. Executive Summary

The **Index Layer** in C.2 Knowledge Base is responsible for converting validated derived representations (dense vector embeddings and sparse term weight representations) into searchable, provider-independent index records (`IndexRecord`) and persisting them via an abstract, replaceable index interface (`IKnowledgeIndexAdapter`).

**Qdrant** is implemented as the first concrete index adapter (`QdrantIndexAdapter`).

---

## 2. Core Architectural Principles

```
Canonical Knowledge (Source, Document, Chunk)
        ↓
Dense Representation (EmbeddingRecord)
        ↓
Sparse Representation (SparseRepresentationRecord)
        ↓
Index Layer Engine (KnowledgeIndexEngine)
        ↓
Index Interface (IKnowledgeIndexAdapter Protocol)
        ↓
Concrete Adapter (QdrantIndexAdapter / FakeIndexAdapter)
        ↓
Physical Index / Storage (Qdrant Vector Database)
```

### Critical Rules:
1. **Canonical Source of Truth**: Qdrant is NOT the source of truth. Canonical Knowledge records (Sources, Documents, Chunks) are authoritative. Index records are derived, rebuildable artifacts.
2. **Qdrant is an Implementation Detail**: The rest of EarthMind interacts exclusively with the abstract `IKnowledgeIndexAdapter` protocol. No other module imports or depends directly on `qdrant_client`.
3. **Representation Separation**: Dense and sparse representations remain independently generated and replaceable derived artifacts.

---

## 3. Index Layer Responsibilities

The Index Layer owns the following capabilities:
- Receiving validated derived dense (`EmbeddingRecord`) and sparse (`SparseRepresentationRecord`) representations.
- Building index-ready records (`IndexRecord`).
- Preserving canonical knowledge lineage (`source_id`, `artifact_id`, `document_id`, `version_id`, `section_id`, `knowledge_unit_id`, `chunk_id`).
- Preserving representation lineage (`dense_embedding_id`, `sparse_representation_id`, providers, models, versions).
- Mapping dense representations to dense index vector fields.
- Mapping sparse representations to sparse index vector fields.
- Extracting and attaching filterable payload metadata (crop, region, season, topic, domain, content type, quality/review status).
- Creating, updating, deleting, and querying index records through the abstract `IKnowledgeIndexAdapter`.
- Managing index-level operational state (`IndexStatus`: `PENDING`, `INDEXING`, `INDEXED`, `FAILED`, `PARTIAL`, `STALE`).
- Validating index records before persistence.
- Supporting deterministic index-record generation.
- Supporting batch indexing with partial failure tracking (`IndexBatchResult`).
- Maintaining complete backward traceability to canonical knowledge records.
- Supporting rebuildability from canonical records.

---

## 4. Generic Index Interface Contract

The generic index contract is defined in `core/interfaces/index.py`:

```python
@runtime_checkable
class IKnowledgeIndexAdapter(Protocol):
    """Generic, provider-agnostic interface for physical/derived index persistence and management."""

    def create_collection(self, collection_name: str, config: Optional[Dict[str, Any]] = None) -> bool: ...
    def ensure_collection_exists(self, collection_name: str, dense_dim: int, config: Optional[Dict[str, Any]] = None) -> bool: ...
    def index_record(self, collection_name: str, record: Any) -> Any: ...
    def index_batch(self, collection_name: str, records: List[Any]) -> Any: ...
    def update_record(self, collection_name: str, record: Any) -> Any: ...
    def delete_record(self, collection_name: str, record_id: str) -> bool: ...
    def get_record(self, collection_name: str, record_id: str) -> Optional[Any]: ...
    def get_status(self, collection_name: str) -> Dict[str, Any]: ...
    def health_check(self) -> bool: ...
    def is_available(self) -> bool: ...
```

---

## 5. Domain Models

### `IndexRecord` (`modules/knowledge_base/index/record.py`)
- **Traceability & Lineage**: `index_record_id`, `source_id`, `artifact_id`, `document_id`, `version_id`, `section_id`, `knowledge_unit_id`, `chunk_id`.
- **Representation Reference**: `dense_embedding_id`, `sparse_representation_id`, providers, models, versions.
- **Payload Vectors**: `dense_dimension`, `dense_vector`, `sparse_vector` (`SparseVector` model).
- **Metadata**: `payload_metadata` (filterable dictionary), `metadata` (`CanonicalMetadata`), `provenance` (`Provenance`).
- **Operational State**: `knowledge_collection`, `physical_collection_name`, `content_type`, `lifecycle_state`, `status` (`IndexStatus`), `index_version`, `created_at`, `updated_at`.

### `IndexBatchResult` (`modules/knowledge_base/index/record.py`)
- Tracks `total_records`, `successful_records`, `failed_records` (with error details and retryable flags), `status` (`INDEXED`, `PARTIAL`, `FAILED`), and `processing_time_ms`.

---

## 6. Qdrant Concrete Adapter (`QdrantIndexAdapter`)

Implemented in `modules/knowledge_base/index/qdrant_adapter.py`.

- Encapsulates `qdrant-client` SDK interactions completely.
- Configuration-driven via `QdrantConfig` (`EARTHMIND_QDRANT_*` environment variables). Supports in-memory testing (`EARTHMIND_QDRANT_LOCATION=":memory:"`).
- **Point ID Mapping**: Converts string `index_record_id` into deterministic Qdrant UUID v5 strings, preserving original ID in payload metadata (`_index_record_id`).
- **Named Vectors**:
  - Dense vector: stored under named vector `"dense"`.
  - Sparse vector: stored under named vector `"sparse"` using `models.SparseVector`.
- **Payload Indexing**: Stores filterable metadata along with internal lineage reserved fields (`_source_id`, `_document_id`, `_chunk_id`, etc.).
- **Exception Wrapping**: Wraps Qdrant SDK errors into provider-aware EarthMind exceptions (`QdrantAdapterError`, `CollectionOperationError`, `IndexProviderUnavailableError`).

---

## 7. Collection Strategy & Lifecycle Integration

- **`KnowledgeCollectionMapper`** (`modules/knowledge_base/index/collection_strategy.py`): Abstracts logical domain Knowledge Collections (e.g., "Crops", "Soil") to physical index collection names.
- **Lifecycle Enforcement**: `KnowledgeIndexEngine` checks `KnowledgeLifecycleState`. Failed, rejected, invalid, retired, or superseded knowledge cannot be indexed into retrievable publication collections.

---

## 8. Provider Replacement Strategy

Because the rest of EarthMind depends strictly on `IKnowledgeIndexAdapter`:
- Testing uses `FakeIndexAdapter` for ultra-fast, zero-dependency unit tests.
- Physical vector databases (Qdrant, Milvus, PGVector, Elasticsearch) can be swapped or upgraded without modifying downstream RAG, Reasoning, Planning, or Context components.

---

## 9. Explicitly Out-of-Scope (Deferred Items)

The following capabilities belong to subsequent RAG steps and are intentionally NOT implemented in this step:
- Online query execution and vector search execution.
- Retrieval routing and hybrid search.
- Reciprocal Rank Fusion (RRF) candidate fusion.
- Reranking and cross-encoder scoring.
- Web search query execution.
- Context package building and reasoning handoff.
