# EarthMind Production Configuration Specification

## 1. Overview & Architecture Compliance

Step 8 Production Configuration establishes strict environment-driven configuration management, startup validation, credential protection, and hardware/storage mode controls for the EarthMind RAG ecosystem.

This specification ensures full alignment across all retrieval and reasoning stages:
- **Dense Embeddings**: BAAI/bge-m3 1024-dimensional vector standard (`SelfHostedEmbeddingProvider`)
- **Sparse Vectors**: BM25 lexical sparse vector index (`BM25SparseProvider`)
- **Vector Storage**: Qdrant vector database (`QdrantIndexAdapter`, collection `earthmind_knowledge`)
- **Hybrid Retrieval**: Reciprocal Rank Fusion (RRF, $k=60$) in Stage R7 (`HybridRetrievalEngine`)
- **Neural Reranking**: BAAI/bge-reranker-base cross-encoder in Stage R8 (`RerankEngine`)
- **Live Integration**: Stage R13 RAG Provider → B2 Context Manager → B3 Reasoning Engine

---

## 2. Environment Variables Summary

All configuration parameters support explicit environment variable overrides:

| Category | Environment Variable | Default Value | Description |
| :--- | :--- | :--- | :--- |
| **System** | `EARTHMIND_ENV` | `development` | Execution environment (`production`, `development`, `test`, `staging`) |
| | `EARTHMIND_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| | `EARTHMIND_DB_PATH` | `earthmind.db` | Path to core SQLite metadata database |
| | `EARTHMIND_MODEL_CACHE_DIR` | `None` (falls back to `HF_HOME`) | Local directory path for caching neural model weights |
| **Qdrant** | `EARTHMIND_QDRANT_MODE` | Inferred (`remote`, `local_persistent`, `memory`) | Storage/connection mode |
| | `EARTHMIND_QDRANT_URL` | `None` | Remote Qdrant cluster HTTP/gRPC endpoint URL |
| | `EARTHMIND_QDRANT_HOST` | `localhost` | Qdrant host address |
| | `EARTHMIND_QDRANT_PORT` | `6333` | Qdrant HTTP port |
| | `EARTHMIND_QDRANT_GRPC_PORT` | `6334` | Qdrant gRPC port |
| | `EARTHMIND_QDRANT_API_KEY` | `None` | Authentication secret key for Qdrant |
| | `EARTHMIND_QDRANT_LOCATION` | `None` | Local persistent directory path or `:memory:` |
| | `EARTHMIND_QDRANT_COLLECTION` | `earthmind_knowledge` | Target physical vector collection name |
| | `EARTHMIND_QDRANT_DISTANCE` | `COSINE` | Vector distance metric (`COSINE`, `DOT`, `EUCLID`) |
| | `EARTHMIND_QDRANT_TIMEOUT` | `30.0` | Connection and request timeout in seconds |
| | `EARTHMIND_QDRANT_AUTO_CREATE` | `false` (in prod), `true` (in dev) | Allow auto-creating collection if non-existent |
| **Embedding** | `EARTHMIND_EMBEDDING_PROVIDER` | `self_hosted` | Dense embedding provider identifier |
| | `EARTHMIND_EMBEDDING_MODEL` | `BAAI/bge-m3` | Open-source embedding model name |
| | `EARTHMIND_EMBEDDING_DIMENSION` | `1024` | Vector dimension size |
| | `EARTHMIND_EMBEDDING_DEVICE` | `cpu` | Device execution target (`cpu`, `cuda`, `mps`, `auto`) |
| | `EARTHMIND_EMBEDDING_TIMEOUT` | `30.0` | Request processing timeout in seconds |
| | `EARTHMIND_EMBEDDING_ALLOW_DOWNLOAD` | `true` | Download weights if not in local cache |
| **Sparse** | `EARTHMIND_SPARSE_PROVIDER` | `bm25` | Sparse vector provider (`bm25`, `fake`) |
| | `EARTHMIND_SPARSE_MODEL` | `earthmind-bm25-v1` | Sparse model identifier |
| | `EARTHMIND_SPARSE_TIMEOUT` | `10.0` | Sparse processing timeout in seconds |
| **Fusion** | `EARTHMIND_FUSION_STRATEGY` | `rrf` | Candidate fusion algorithm (`rrf`, `relative_score`) |
| | `EARTHMIND_FUSION_RRF_K` | `60` | RRF constant parameter |
| | `EARTHMIND_FUSION_TIMEOUT` | `10.0` | Fusion execution timeout in seconds |
| **Reranker** | `EARTHMIND_RERANK_PROVIDER` | `cross_encoder` | Neural reranker provider |
| | `EARTHMIND_RERANK_MODEL` | `BAAI/bge-reranker-base` | Reranker model identifier |
| | `EARTHMIND_RERANK_DEVICE` | `cpu` | Device execution target (`cpu`, `cuda`, `mps`, `auto`) |
| | `EARTHMIND_RERANK_TIMEOUT` | `10.0` | Reranker timeout in seconds |
| | `EARTHMIND_RERANK_FALLBACK_POLICY` | `PRESERVE_FUSED_ORDER` | Fallback policy on error |

---

## 3. Production Rules & Fallback Safeguards

When `EARTHMIND_ENV` is set to `production` (or `prod`), the system automatically enforces strict production rules during startup validation (`settings.validate_config()`):

1. **No Fake Providers in Production**:
   - `EARTHMIND_EMBEDDING_PROVIDER` must NOT be `fake`, `mock`, or `dummy`.
   - `EARTHMIND_RERANK_PROVIDER` must NOT be `fake`, `mock`, or `dummy`.
   - Violation raises `ConfigurationError`.

2. **No Ephemeral In-Memory Qdrant Storage in Production**:
   - `EARTHMIND_QDRANT_LOCATION` cannot be set to `:memory:`.
   - Production deployments must specify a remote Qdrant URL or a local persistent disk storage directory.
   - Violation raises `ConfigurationError`.

3. **Collection Creation Prevention**:
   - `EARTHMIND_QDRANT_AUTO_CREATE` defaults to `false` in production.
   - If the target collection (`earthmind_knowledge`) is missing, `ensure_collection_exists()` raises `CollectionOperationError` rather than silently initializing an empty collection.

4. **Timeout Enforcement**:
   - All module timeout values (`qdrant`, `embedding`, `sparse`, `fusion`, `rerank`, `query_processing`, `web_search`, `rag_integration`, `context`) must be positive floating point numbers ($> 0.0$).

---

## 4. Qdrant Storage Modes

EarthMind supports two production Qdrant modes and one testing mode:

- **Remote Mode (`EARTHMIND_QDRANT_MODE=remote`)**:
  Connects to a standalone or clustered Qdrant service via HTTP or gRPC using `EARTHMIND_QDRANT_URL` or `EARTHMIND_QDRANT_HOST`/`PORT`. Supports `EARTHMIND_QDRANT_API_KEY` authentication and TLS/SSL.

- **Local Persistent Mode (`EARTHMIND_QDRANT_MODE=local_persistent`)**:
  Uses Qdrant's embedded storage backed by a local filesystem directory path configured via `EARTHMIND_QDRANT_LOCATION` (e.g. `/data/qdrant_storage`). Persists vectors and metadata across process restarts.

- **In-Memory Mode (`EARTHMIND_QDRANT_MODE=memory`)**:
  Ephemeral storage using `:memory:`. Allowed ONLY in `development` or `test` environments. Strictly prohibited in `production`.

---

## 5. Model Caching & Hardware Acceleration

The open-source models (`BAAI/bge-m3` and `BAAI/bge-reranker-base`) do NOT require vendor API keys or remote authentication.

- **Model Weight Caching**:
  By specifying `EARTHMIND_MODEL_CACHE_DIR` or `HF_HOME`, weights downloaded during setup or first run are stored locally.
- **Hardware Device Selection**:
  The `EARTHMIND_EMBEDDING_DEVICE` and `EARTHMIND_RERANK_DEVICE` settings accept:
  - `cpu`: Default CPU execution with multi-threading.
  - `cuda`: NVIDIA GPU acceleration.
  - `mps`: Apple Silicon Metal Performance Shaders.
  - `auto`: Automatic device resolution based on PyTorch availability.

---

## 6. Secret Masking & Security

To prevent secret leakage in logs, error reporting, and diagnostic dumps:
- `Settings.to_safe_dict()` automatically sanitizes `qdrant.api_key`, `web_search.api_key`, and `embedding.credential_reference`.
- `QdrantConfig.get_masked_api_key()` returns masked string representations (e.g., `sk-***123`).
- API keys and secrets are never logged or stored in version control.

---

## 7. Startup Validation Integration

Startup validation is integrated directly into the application lifecycle manager (`app.lifecycle.LifecycleManager.initialize_all()`):

```python
# Startup flow
lifecycle = LifecycleManager()
# ... register modules ...
lifecycle.initialize_all()  # Executes settings.validate_config() first!
```

If any configuration parameter is invalid or violates production rules, startup aborts immediately with a descriptive, actionable `ConfigurationError`.

---

## 8. Remaining Deployment Prerequisites

Before deploying to a production server:
1. Provision a remote Qdrant service or persistent filesystem directory.
2. Verify that pre-embedded 1024D vectors exist in the Qdrant `earthmind_knowledge` collection.
3. Pre-download `BAAI/bge-m3` and `BAAI/bge-reranker-base` weights into `EARTHMIND_MODEL_CACHE_DIR` if offline execution is required.
4. Export environment variables using `.env.example` as a template.
