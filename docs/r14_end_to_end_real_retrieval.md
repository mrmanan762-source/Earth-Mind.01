# EarthMind — Stage R14 End-to-End Real Retrieval Documentation

## 1. Objective

Stage R14 executes and proves the complete EarthMind RAG pipeline using **REAL retrieval components** and **REAL knowledge data** from the R3 agricultural corpus (`data/knowledge/raw/`). It bridges Stages R3 through R13 into a operational retrieval system feeding the B2 Context Manager without using mocks, fake vectors, or hardcoded search results in the primary execution path.

---

## 2. Real Execution Architecture & Flow

```
Real Query
   ↓
Stage R9 Query Processing (Normalization, Classification, Agri-Metadata, Expansion)
   ↓
Real Query Representation (SelfHostedEmbeddingProvider 384d + BM25SparseProvider)
   ↓
Stage R7 Hybrid Retrieval (R5 Dense Qdrant + R6 Sparse Inverted BM25)
   ↓
Stage R8 Reranking (CrossEncoder / RerankEngine with Fallback Preservation)
   ↓
Stage R10 Web Search (Optional / Configurable API Provider)
   ↓
Stage R11 Evidence Builder (Unified EvidencePackage Construction)
   ↓
Stage R12 Evidence Validator Gate (Structural, Lineage, Consistency Validation)
   ↓
Stage R13 RAG Context Provider (Boundary Contract Generation)
   ↓
B2 Context Manager (ContextItem Prioritization & Building)
```

---

## 3. Real Knowledge Data & Corpus Used

R14 executes directly over the R3 canonical agricultural knowledge corpus located in `data/knowledge/raw/`:

1. `icar_gap_guidelines_2023.txt` (ICAR Good Agricultural Practices)
2. `icar_rice_cultivation_package_2023.txt` (Package of Practices for Rice Cultivation)
3. `iiss_balanced_fertilizer_recommendations_2023.txt` (Site-Specific Balanced Fertilizer Application)
4. `ncipm_wheat_pests_diseases_2023.txt` (Pest & Disease Management for Wheat)
5. `pmkisan_kvk_extension_advisory_2023.txt` (KVK Extension Advisories)
6. `pmksy_micro_irrigation_manual_2022.txt` (Micro Irrigation & Drip System Guidelines)
7. `soil_health_card_guidelines_2022.txt` (Soil Health Card Testing & Sampling Procedures)
8. `tnau_icar_dryland_rainfed_farming_2022.txt` (Dryland & Rainfed Farming Guidelines)

All 39 canonical `Chunk`s produced by `CorpusIngestionEngine` are converted into real dense embeddings and sparse representations, indexed into `QdrantIndexAdapter` and `InvertedSparseIndexAdapter`, preserving 100% of canonical lineage (`Source` → `Document` → `Version` → `Section` → `KnowledgeUnit` → `Chunk`).

---

## 4. Subsystem & Component Mapping

| Stage | Subsystem | Real Execution Component | Primary Responsibility |
|---|---|---|---|
| **R3** | Corpus Ingestion | `CorpusIngestionEngine` | Loads raw agricultural texts and produces canonical chunks & metadata |
| **R4** | Dense Embeddings | `SelfHostedEmbeddingProvider` | Computes 384-dimensional dense vectors using `MiniLM-L12-v2` |
| **R6** | Sparse Vectors | `BM25SparseProvider` | Generates index-ordered BM25 sparse vectors and multilingual terms |
| **R5** | Dense Vector Index | `QdrantIndexAdapter` | Persists and searches dense vectors in Qdrant |
| **R6** | Sparse Vector Index | `InvertedSparseIndexAdapter` / `QdrantSparseIndexAdapter` | In-memory inverted sparse dot-product index and Qdrant sparse lookup |
| **R7** | Hybrid Fusion | `HybridRetrievalEngine` | Fuses dense and sparse candidate branches via RRF / relative score fusion |
| **R8** | Reranking | `RerankEngine` / `CrossEncoderRerankerProvider` | Reranks hybrid candidates while preserving upstream scores & identity |
| **R9** | Query Processing | `QueryProcessingEngine` | Validates, normalizes, classifies, and extracts agricultural query metadata |
| **R10** | Web Search | `WebSearchEngine` | Optional external web search provider (never auto-published) |
| **R11** | Evidence Builder | `EvidenceBuilderEngine` | Assembles traceable `EvidencePackage` payloads from KB and Web results |
| **R12** | Evidence Validator | `EvidenceValidatorEngine` | Validates package structure, lineage, completeness, and score sanity |
| **R13** | RAG → B2 Bridge | `RAGContextProvider` | Maps validated evidence to `RAGContextContract` boundary contracts |
| **B2** | Context Manager | `ContextBuilder` / `ContextCollector` | Prepares model-ready `ContextItem`s for B3 Reasoning Engine |

---

## 5. Execution Setup & Harness

Integration module `modules/knowledge_base/integration/e2e_setup.py` provides `ingest_and_index_real_corpus()`, which automates corpus ingestion, embedding generation, sparse indexing, and adapter setup.

Execution harness `modules/knowledge_base/integration/harness.py` provides `R14RealRetrievalHarness` and `R14ExecutionResult`:

```python
from modules.knowledge_base.integration.harness import R14RealRetrievalHarness

harness = R14RealRetrievalHarness(enable_web_search=False)
result = harness.execute_query(
    query_text="What are the recommended fertilizer doses for rice cultivation?",
    request_id="req_001",
)

print(result.query_processing_status)   # SUCCESS
print(result.context_items_count)        # 4
print(result.final_context_items[0])     # ContextItem
```

---

## 6. Failure Handling & Resilience

1. **Empty Retrieval**:
   Returns empty context list with status `SUCCESS` and explicit warnings without silent failure or fake candidate fabrication.
2. **Dense / Qdrant Backend Failure**:
   If dense vector search fails or Qdrant connection is unavailable, pipeline falls back to sparse branch execution (`status=PARTIAL`) and proceeds safely.
3. **Sparse Backend Failure**:
   If sparse index is unavailable, pipeline falls back to dense branch execution.
4. **Reranker Timeout / Failure**:
   If reranker provider fails, `RerankEngine` uses configured `PRESERVE_FUSED_ORDER` fallback strategy (`status=FALLBACK`), preserving R7 fused candidate ordering without score fabrication.
5. **Metadata Filter Relaxation**:
   If strict query metadata filters produce 0 candidates, `RAGContextProvider` automatically retries without hard filters to allow semantic/lexical vector matching.

---

## 7. Traceability & Safety

- **Trace Identifiers**: Every execution carries `request_id` and `trace_id` propagated across all stages (R9 → R7 → R8 → R11 → R12 → R13 → B2).
- **C.3 Boundary Safety**: RAG context items carry `ownership="RAG_OWNED"`, `classification="GENERAL_KNOWLEDGE"`, and `scope="QUERY_TRANSIENT"`. Zero memory system writes or automatic database mutations occur during retrieval.
- **Mock/Fake Isolation**: Primary R14 execution path uses real providers (`SelfHostedEmbeddingProvider`, `BM25SparseProvider`, `QdrantIndexAdapter`, `InvertedSparseIndexAdapter`). Mocks remain strictly isolated in offline unit tests.

---

## 8. Test Methodology & Results

The R14 test suite (`tests/test_r14_real_retrieval.py`) verifies 26 test cases covering all 22 required prompt dimensions:

- Real end-to-end retrieval, R9 query processing, dense, sparse, hybrid, reranking, evidence building, evidence validation, R13→B2 integration.
- Real agricultural query categories (crop, disease, soil, region, season, practice).
- Multilingual Devanagari Hindi execution.
- Provenance, source-type, and traceability preservation.
- Failure handling (empty retrieval, backend failure, partial branch failure, reranker fallback, optional web search).
- Deterministic result contract and downstream B2 Context Manager compatibility.

**Test Results:** 26 / 26 tests passed (100% pass rate).

---

## 9. Adherence to 5 EarthMind Principles

1. **Extensibility / Rubber-Band Principle**: Clean protocol interfaces (`IRAGContextProvider`, `IKnowledgeIndexAdapter`, `ISparseIndexAdapter`, `IEmbeddingProvider`) allow swapping backends without altering core retrieval flow.
2. **Loose Coupling**: Components communicate exclusively via typed Pydantic contracts (`RetrievalQuery`, `HybridRetrievalRequest`, `RerankRequest`, `EvidencePackage`, `RAGContextContract`, `ContextItem`).
3. **Single Responsibility**: Each stage owns a single function (R9 query preparation, R7 retrieval fusion, R8 reranking, R11 evidence assembly, R12 validation, R13 boundary mapping).
4. **Controlled Dependencies**: Downstream B2 Context Manager depends on R13 provider contracts without direct database or Qdrant access.
5. **Replaceability + Evolution**: Providers (embedding, sparse, vector index, reranker) are decoupled from orchestration logic.
