# R4 — Real Embedding Pipeline Implementation & Architecture

**System:** EarthMind (`Earth-Mind.01`)
**Phase:** EarthMind RAG Operationalization
**Stage:** R4 — Real Embedding Pipeline
**Status:** IMPLEMENTED, VALIDATED & OPERATIONALIZED

---

## 1. Executive Summary & R4 Responsibility

The R4 Real Embedding Pipeline converts processed canonical knowledge entities (Chunks and KnowledgeUnits produced by R3 Ingestion) into real vector representations using a self-hosted open-source embedding model.

```
+------------------------------------+
|   R3 Processed Canonical Knowledge |
|       (Chunks & KnowledgeUnits)    |
+------------------------------------+
                  │
                  ▼
+------------------------------------+
|     R4 Real Embedding Pipeline     |
|   (Preparation, Model Inference,   |
|   Validation, Persistence Record)  |
+------------------------------------+
                  │
                  ▼
+------------------------------------+
|         READY FOR INDEXING         |
|   (R5 Vector Indexing Boundary)    |
+------------------------------------+
```

### R4 Core Responsibilities:
- Input transformation and embedding preparation from R3 canonical objects.
- Self-hosted embedding provider loading and model execution.
- Incremental batching with memory-safe execution.
- Vector numerical validation (dimension verification, non-null, finite values, NaN/Inf detection, L2 normalization).
- Lineage, metadata, provenance, and provider/model version tracking.
- Storage-independent embedding persistence (`IEmbeddingRepository`).
- Explicit report generation confirming output state as `READY_FOR_INDEXING`.

### Strict Boundaries (What R4 Does NOT Own):
- Vector database deployment or Qdrant population (R5 Index Layer).
- Dense/sparse vector retrieval execution or candidate search.
- RRF, candidate fusion, reranking, or query expansion.
- B2 Context Manager integration or agricultural reasoning/decision logic.

---

## 2. Selected Embedding Model Strategy & Licensing

### Primary Self-Hosted Embedding Model
- **Model Name:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- **HuggingFace Source:** `https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- **Model Version:** `1.0.0`
- **License:** `Apache-2.0` (Fully clean and compatible with commercial production use)
- **Embedding Dimension:** `384`
- **Supported Languages:** 50+ languages including English, Hindi, Bengali, Gujarati, Marathi, Tamil, Telugu, Malayalam, Punjabi, Kannada, etc.
- **Suitability for EarthMind:** Excellent multilingual semantic representation, fast CPU/GPU inference footprint (~470MB weights), high sentence/chunk pair retrieval accuracy, ideal for Indian agricultural domain advisories and guidelines.
- **Hardware & Runtime Requirements:** CPU execution requires ~1GB RAM; GPU acceleration (CUDA) supported natively.

---

## 3. Provider Architecture & Replacement Strategy

The architecture enforces strict provider independence through the adapter pattern:

```
                  +--------------------------+
                  |    IEmbeddingProvider    |
                  +--------------------------+
                               ▲
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
+─────────────────+  +──────────────────+  +──────────────────+
|   SelfHosted    |  |       API        |  |       Fake       |
|EmbeddingProvider|  |EmbeddingProvider |  |EmbeddingProvider |
+─────────────────+  +──────────────────+  +──────────────────+
```

### Provider Implementation Classes:
1. `SelfHostedEmbeddingProvider`: Primary self-hosted provider using local open-source models via `sentence-transformers`.
2. `APIEmbeddingProvider`: Optional/future API provider behind the same interface using symbolic credential references (`ENV:...`). No raw secrets in source code.
3. `FakeEmbeddingProvider`: Mock provider reserved for fast offline test fixtures.

### Dynamic Provider Replacement
Providers can be swapped at runtime or via environment variables without breaking R3 knowledge schemas, C.2 metadata/provenance, or downstream B2/B3/B4/B5 engines:

```python
from core.config.settings import settings
from modules.knowledge_base.embedding.adapter import EmbeddingAdapter

adapter = EmbeddingAdapter.from_config(settings.embedding)
```

---

## 4. Configuration Framework

Managed via `EmbeddingConfig` in `core/config/settings.py` supporting environment variables:

| Environment Variable | Description | Default |
|---|---|---|
| `EARTHMIND_EMBEDDING_PROVIDER` | Active provider name (`self_hosted`, `api`, `fake`) | `"self_hosted"` |
| `EARTHMIND_EMBEDDING_MODEL` | Hugging Face model repository ID | `"sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"` |
| `EARTHMIND_EMBEDDING_MODEL_VERSION` | Model version string | `"1.0.0"` |
| `EARTHMIND_EMBEDDING_DIMENSION` | Vector dimension integer | `384` |
| `EARTHMIND_EMBEDDING_DEVICE` | Execution device (`cpu`, `cuda`, `mps`, `auto`) | `"cpu"` |
| `EARTHMIND_EMBEDDING_BATCH_SIZE` | Max batch size for inference | `32` |
| `EARTHMIND_EMBEDDING_MAX_LENGTH` | Max sequence input token length | `512` |
| `EARTHMIND_EMBEDDING_NORMALIZE` | L2 vector normalization flag | `true` |
| `EARTHMIND_EMBEDDING_ALLOW_DOWNLOAD` | Allow remote weight download | `false` |
| `EARTHMIND_EMBEDDING_EXECUTION_MODE` | Execution mode | `"self_hosted"` |
| `EARTHMIND_EMBEDDING_CREDENTIAL_REFERENCE` | Symbolic credential reference | `None` |

---

## 5. Embedding Record & Versioning

### EmbeddingRecord Schema (`modules/knowledge_base/embedding/record.py`)
- `embedding_id`: Unique identifier (`emb_chk_...` or `emb_ku_...`).
- `source_id`, `document_id`, `version_id`: Upstream canonical lineage references.
- `chunk_id` / `knowledge_unit_id`: Granular chunk/unit associations.
- `provider`, `model`, `model_version`: Exact generator metadata.
- `dimension`, `dense_vector`: Vector payload.
- `status`: Lifecycle status (`ACTIVE`, `SUPERSEDED`, `DEPRECATED`).
- `metadata`, `provenance`: Enriched traceability records.

### Model Replacement & Lineage Preservation
When a model is updated or replaced, existing `EmbeddingRecord`s are marked `SUPERSEDED`. The canonical source text remains untouched, preserving complete historical provenance.

---

## 6. Persistence & Boundary

Stored via `IEmbeddingRepository` / `CanonicalEmbeddingRepository` (`modules/knowledge_base/embedding/repository.py`), providing thread-safe, decoupled storage for `EmbeddingRecord` objects without database handles or Qdrant dependencies.

---

## 7. R4 Execution & Output Verification

Executing the pipeline produces an `R4PipelineSummary` report:

```python
from modules.knowledge_base.embedding.pipeline import R4EmbeddingPipeline

pipeline = R4EmbeddingPipeline()
summary = pipeline.embed_corpus_ingestion(r3_ingestion_engine)

assert summary.status == "COMPLETED"
assert summary.readiness_state == "READY_FOR_INDEXING"
```

The output explicitly confirms that vector embeddings are generated, validated, and persisted, ready for consumption by R5 (Index Layer & Qdrant population).
