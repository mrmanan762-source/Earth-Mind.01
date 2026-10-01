# Stage R13 RAG → B2 Live Integration Architecture Specification

**Status:** IMPLEMENTED & VALIDATED
**Module:** `modules/knowledge_base/integration/`
**Provider:** `RAGContextProvider` (`IRAGContextProvider`)
**Adapter:** `RAGContextProviderAdapter` (`modules/context/boundary/adapters.py`)

---

## 1. Executive Summary & Objective

Stage R13 **RAG → B2 Live Integration** connects EarthMind's 6-stage RAG Retrieval Pipeline (Stage R9 Query Processing → Stage R7 Hybrid Retrieval → Stage R8 Reranking → Stage R10 Web Search → Stage R11 Evidence Builder → Stage R12 Evidence Validator) to the Stage B2 Context Manager through standardized, boundary-checked interfaces (`IRAGContextProvider`, `RAGContextContract`).

```
[B2 Context Manager]
        │
        ▼
[RAGContextProviderAdapter]
        │
        ▼ (IRAGContextProvider)
[RAGContextProvider] (R13 Integration Engine)
        │
        ├──► Stage R9 Query Processing (RetrievalQuery)
        ├──► Stage R7 Hybrid Retrieval (HybridRetrievalResponse)
        ├──► Stage R8 Reranking (RerankResponse)
        ├──► Stage R10 Web Search (WebSearchResponse)
        ├──► Stage R11 Evidence Builder (EvidencePackage)
        └──► Stage R12 Evidence Validator (Validation Gate)
                │
                ▼ (Sanitized Validated Package)
        [RAGContextContracts]
                │
                ▼
        [ContextItems] -> B2 Context Manager -> [B3 Reasoning Engine]
```

Stage R13 is strictly an **integration and transport layer**. It does not perform agricultural reasoning, truth evaluation, token reduction, vector embedding, or direct database/Qdrant persistence.

---

## 2. Core Architecture & Interfaces

### 2.1 Interface & Adapter Architecture

- **`IRAGContextProvider` Protocol (`core/interfaces/boundary.py`)**:
  ```python
  @runtime_checkable
  class IRAGContextProvider(Protocol):
      provider_name: str
      def get_rag_context(self, request: Any) -> List[RAGContextContract]: ...
  ```

- **`RAGContextProvider` (`modules/knowledge_base/integration/provider.py`)**:
  Production implementation of `IRAGContextProvider`. Orchestrates upstream stages R9–R12 via interface injection (`IQueryProcessorEngine`, `HybridRetrievalEngine`, `IRerankerProvider`, `IWebSearchProvider`, `IEvidenceBuilderEngine`, `IEvidenceValidatorEngine`).

- **`RAGContextProviderAdapter` (`modules/context/boundary/adapters.py`)**:
  Adapts `IRAGContextProvider` into B2 `ContextProvider` protocol:
  Translates `ContextRequest` → `RAGContextRequest` → `get_rag_context()` → validates boundary via `BoundaryValidator` → converts `RAGContextContract` → B2 `ContextItem`.

---

## 3. Contract Mapping & Metadata Preservation

Stage R13 converts R12-validated `EvidencePackage` items into `RAGContextContract` objects without losing provenance or domain identity.

| Source Attribute (`EvidenceItem`) | `RAGContextContract` Field | B2 `ContextItem` Mapping |
| :--- | :--- | :--- |
| `evidence_id`, `chunk_id`, `web_result_id` | `source_id`, `chunk_id`, `document_id` | `ContextItem.source_id`, `ContextItem.entity_id` |
| `source_type` (`KNOWLEDGE_BASE` / `WEB_SEARCH`) | `evidence_metadata["source_type"]` | `ContextItem.metadata["evidence_metadata"]["source_type"]` |
| `provenance` (dictionary chain) | `provenance` | `ContextItem.boundary_metadata["provenance"]` |
| `retrieval_rank`, `rerank_rank`, `dense_score` | `retrieval_metadata` | `ContextItem.metadata["retrieval_metadata"]` |
| `content`, `title`, `url`, `multimodal_data` | `content` dict | `ContextItem.content` |
| `conflict_indicators` | `content["conflict_indicators"]` | `ContextItem.content["conflict_indicators"]` |
| `request_id`, `trace_id` | `trace_id` | `ContextItem.trace_id` |

---

## 4. Stage R12 Validation Gate Enforcement

Stage R12 Evidence Validator serves as the mandatory validation gate before R13 produces `RAGContextContract` payloads for B2:

1. **Gate Evaluation**:
   If R12 returns status `INVALID` or `MALFORMED`, or if `validated_package` is `None` or empty, R13 returns an empty list `[]`.
2. **Partial Evidence Handling**:
   If R12 returns `PARTIALLY_VALID`, R13 maps only sanitized, valid evidence items preserved in `validated_package.items`.
3. **No Fabrication**:
   R13 never fabricates context items when retrieval fails or validation fails.

---

## 5. Architectural Safety Boundaries

1. **RAG Knowledge ≠ Farmer Memory Boundary**:
   R13 produces `RAG_OWNED` context contracts with `GLOBAL` scope. R13 never reads, writes, or modifies Memory storage, nor does it perform automatic promotion into Memory.
2. **Database & Qdrant Storage Boundary**:
   R13 accesses zero databases (SQLite) and zero vector databases (Qdrant) directly. All retrieval operations are strictly delegated behind R9–R12 interfaces.
3. **B3 / B4 / B5 Engine Boundary**:
   R13 stops at B2 Context Manager. It does not invoke B3 Reasoning Engine, B4 Planning Engine, or B5 AI Orchestrator directly.
4. **Inspector Boundary**:
   R12 performs item/package validation. Inspector remains responsible for system-level governance and model response verification.

---

## 6. Configuration & Error Hierarchy

### 6.1 Configuration (`RAGIntegrationConfig` in `core/config/settings.py`)
- `enable_web_search`: Toggle Stage R10 Web Search integration (default `True`).
- `max_results`: Default candidate limit requested from RAG pipeline (default `10`).
- `strict_validation`: Enforce strict mode on R12 Evidence Validator gate (default `False`).
- `timeout`: Overall execution timeout in seconds (default `15.0`).
- `provider_name`: RAG Context Provider identifier name (default `"rag_provider"`).

### 6.2 Error Hierarchy (`core/errors/exceptions.py`)
- `RAGIntegrationError` (inherits `EarthMindException`)
  - `RAGPipelineExecutionError`: Upstream pipeline stage execution failure.
  - `RAGContractMappingError`: Validation package to `RAGContextContract` mapping failure.

---

## 7. Compliance with the 5 EarthMind Principles

1. **Extensibility / Rubber-Band Principle**:
   R13 easily accommodates new evidence types or retrieval channels without modifying B2 Context Manager or upstream R9–R12 contracts.
2. **Loose Coupling**:
   R13 interacts exclusively through protocols (`IRAGContextProvider`, `IQueryProcessorEngine`, `IEvidenceValidatorEngine`).
3. **Single Responsibility**:
   R13 focuses solely on orchestrating the RAG pipeline execution and transporting validated evidence contracts to B2.
4. **Controlled Dependencies**:
   All dependencies flow unidirectionally: B2 → R13 → R12 → R11 → R10/R8 → R7 → R9. Zero circular dependencies.
5. **Replaceability + Evolution**:
   `RAGContextProvider` can be replaced or mocked independently without altering B2 Context Manager or RAG retrieval internals.

---

## 8. Verification & Test Suite

The R13 integration implementation is verified via `tests/test_r13_rag_b2_integration.py` covering all 27 specified test scenarios (100% pass rate, 27/27 tests passed; full repository test suite 593/593 passed, 1 skipped).
