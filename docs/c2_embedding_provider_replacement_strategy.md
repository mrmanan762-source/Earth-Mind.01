# C.2 — Embedding Provider Abstraction & Replacement Strategy

**System:** EarthMind (`Earth-Mind.01`)
**Phase:** Phase B — Storage Foundation
**Step:** Step 4 — Embedding Provider Setup
**Status:** IMPLEMENTED & DOCUMENTED

---

## 1. Executive Summary

This document specifies the embedding provider abstraction, replacement strategy, configuration framework, and error contracts for the EarthMind C.2 Knowledge Base.

The C.2 embedding layer establishes a generic, vendor-agnostic foundation for vector generation. It ensures that embedding providers, models, dimensions, and SDKs can be swapped seamlessly without modifying C.2 knowledge base domain logic, RAG retrieval pipelines, or downstream EarthMind engines (B2 Context, B3 Reasoning, B4 Planning, B5 Orchestration).

---

## 2. Architectural Blueprint

The embedding system strictly enforces the three-tier adapter pattern:

```
+-------------------------------------------------------------+
|             C.2 Knowledge Base Domain Logic                 |
|             (Knowledge Units, Chunks, Metadata)             |
+-------------------------------------------------------------+
                              │
                              ▼
+-------------------------------------------------------------+
|                    EmbeddingAdapter                         |
|  (Validation, Dimension Checks, Dynamic Provider Swapping)  |
+-------------------------------------------------------------+
                              │
                              ▼
+-------------------------------------------------------------+
|                   IEmbeddingProvider                        |
|        (Generic Protocol Interface / Contract)              |
+-------------------------------------------------------------+
                              │
                              ▼
+-------------------------------------------------------------+
|            Concrete Provider Implementation                 |
|   (FakeEmbeddingProvider / External API / Local HF Model)   |
+-------------------------------------------------------------+
```

### Key Architectural Guarantee:
C.2 domain models and downstream callers depend solely on `IEmbeddingProvider` and `EmbeddingAdapter`. No vendor-specific SDK objects (e.g., OpenAI, Jina, Hugging Face, Cohere) are ever leaked across the boundary.

---

## 3. Representation Boundaries

### 3.1 Dense Embedding Representation
- **Contract Payload**: `EmbeddingRequest` -> `EmbeddingResponse` containing `dense_vectors: List[DenseEmbeddingVector]` and `embeddings: List[List[float]]`.
- **Dynamic Dimensioning**: Dimension is configured dynamically via `IEmbeddingProvider.get_dimension()`. No fixed dimension is hardcoded into domain logic.
- **Traceability Metadata**: Every response carries `ProviderMetadata`, `ModelMetadata`, and `EmbeddingMetadata` (recording provider, model, model_version, dimension, processing_time_ms, source_id, and timestamp).

### 3.2 Sparse Representation Boundary
- **Contract Boundary**: `SparseVector` schema supporting `indices: List[int]`, `values: List[float]`, and `terms: Dict[str, float]`.
- **Multi-Modal / Hybrid RAG**: Prepares C.2 for future sparse retrieval systems (BM25 / SPLADE) without locking in a specific sparse engine.

---

## 4. Provider Replacement Strategy

### 4.1 Swapping Providers at Runtime
Providers can be replaced dynamically using `EmbeddingAdapter.set_provider()`:

```python
# Initial deployment with Provider A
provider_a = FakeEmbeddingProvider(provider_name="vendor_a", dimension=384)
adapter = EmbeddingAdapter(provider_a)

# Dynamic runtime replacement to Provider B
provider_b = FakeEmbeddingProvider(provider_name="vendor_b", dimension=768)
adapter.set_provider(provider_b)
```

### 4.2 Swapping Providers via Configuration
Providers can be initialized dynamically from environment variables without code modification:

```python
from core.config.settings import settings
from modules.knowledge_base.embedding.adapter import EmbeddingAdapter

adapter = EmbeddingAdapter.from_config(settings.embedding)
```

---

## 5. Configuration Framework

Configuration is managed via `EmbeddingConfig` in `core/config/settings.py` and supports the following environment variables:

| Environment Variable | Description | Default |
|---|---|---|
| `EARTHMIND_EMBEDDING_PROVIDER` | Active provider name | `"fake"` |
| `EARTHMIND_EMBEDDING_MODEL` | Active model identifier | `"earthmind-embed-v1"` |
| `EARTHMIND_EMBEDDING_MODEL_VERSION` | Active model version string | `"1.0.0"` |
| `EARTHMIND_EMBEDDING_DIMENSION` | Vector dimension integer | `384` |
| `EARTHMIND_EMBEDDING_ENDPOINT` | Provider API endpoint URL | `None` |
| `EARTHMIND_EMBEDDING_CREDENTIAL_REFERENCE` | Reference key string (NO raw secrets) | `None` |
| `EARTHMIND_EMBEDDING_BATCH_SIZE` | Default batch text size | `32` |
| `EARTHMIND_EMBEDDING_TIMEOUT` | Request timeout in seconds | `30.0` |
| `EARTHMIND_EMBEDDING_LICENSE` | License terms of embedding model | `"Apache-2.0"` |
| `EARTHMIND_EMBEDDING_PROVENANCE` | Model provenance string | `"EarthMind Prototype Vector Standard"` |

### Security & Secret Isolation Rule:
Raw API keys, tokens, or credentials **MUST NEVER** be hardcoded or stored in configuration files or source code. `credential_reference` holds symbolic references (e.g., `"ENV:EARTHMIND_EMBEDDING_API_KEY"`) resolved strictly at runtime.

---

## 6. Commercial Safety & License Verification

To prevent accidental inclusion of models with non-commercial, research-only restrictions, every provider must expose `ModelMetadata.license` and `ModelMetadata.commercial_use_allowed`.

Before promoting a concrete embedding provider to production:
1. Verify license terms (e.g., Apache-2.0, MIT, CC-BY-4.0).
2. Explicitly verify that commercial fine-tuning, embedding generation, and commercial hosting are permitted.
3. Record license and provenance details in `ModelMetadata`.

---

## 7. Error Handling Contract

Embedding failures are explicit and raise distinguishable custom exceptions derived from `EmbeddingError` (`EarthMindException`):

| Exception Class | Conditions | Retryable |
|---|---|---|
| `InvalidEmbeddingInputError` | Empty texts, non-string input, or mismatched chunk IDs | `False` |
| `EmbeddingProviderUnavailableError` | Provider service unreachable or offline | `True` |
| `EmbeddingConfigurationError` | Missing credentials reference or invalid dimension config | `False` |
| `EmbeddingRateLimitError` | Provider rate limit exceeded | `True` |
| `EmbeddingTimeoutError` | Processing exceeded request timeout | `True` |
| `EmbeddingExecutionError` | Internal provider backend error | `False` |
| `InvalidEmbeddingResponseError` | Response format or count mismatch | `False` |
| `EmbeddingDimensionMismatchError` | Generated vector length differs from configured dimension | `False` |

*Fallback Enforcement Rule*: The embedding adapter **must never** silently generate random fake embeddings when a production provider fails, nor silently substitute another provider without explicit orchestration intervention.

---

## 8. Separation from Sarvam-105B Main Model

Sarvam-105B is the designated primary AI model for EarthMind reasoning and generation.
- **Sarvam-105B**: Main Model (Causal LLM for B3 Reasoning, B4 Planning, B5 Generation).
- **Embedding Provider**: Independent, replaceable vector generation capability (e.g., small dense embedding models).

Sarvam-105B is **not** hardcoded as the C.2 embedding provider.

---

## 9. Boundary Enforcement Checklist

The C.2 Embedding Layer **MAY**:
- Request and receive vector representations.
- Validate embedding dimensions and schema contracts.
- Attach provenance and traceability metadata.
- Expose dense and sparse abstraction boundaries.

The C.2 Embedding Layer **MUST NOT**:
- Perform domain reasoning or truth evaluation.
- Access database handles directly.
- Execute RAG retrieval routing, dense/sparse candidate search, or reranking.
- Assemble B2 model-ready context packages.
- Manage Memory or farmer-specific records.
- Download large ML weight files directly.
- Store real credentials in Git repository files.
