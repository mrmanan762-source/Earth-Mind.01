# EarthMind Phase 2 — RAG Completion Report

**Scope:** Complete the existing RAG (knowledge_base) system, expand the agricultural
corpus, connect RAG to the application/B2 boundary, and verify retrieval operationally.

**Branch:** `phase2-rag-completion` (based on `main`).
**Status:** RAG operational end-to-end; verified by real (non-mocked) retrieval.

---

## 1. Summary of delivered work

| Area | Result |
| --- | --- |
| Embedding consistency | Single canonical model **BAAI/bge-m3**, **1024-dim**, across ingestion, indexing, query, retrieval and evaluation |
| Dense store | Persistent local Qdrant (`path=` filesystem mode), survives restart |
| Sparse store | Persistent on-disk inverted BM25 index (`data/rag_store/sparse_index.json`) |
| Application wiring | `KnowledgeBaseModule` registered in `app/main.py`; RAG provider registered to B2 (`ContextModule`) |
| Corpus | 25 verified sources → 25 documents → **213 chunks** (was 53), 0 ingestion failures |
| Crop coverage | All 15 target crops have a dedicated cultivation package |
| Evaluation | 32-case benchmark; recall@10 = 0.89, MRR = 0.87, nDCG@10 = 0.86, 32/32 reliability success |
| Operationalization | `requirements.txt`, `.env.example` RAG variables, coverage report tooling |

---

## 2. Audit findings and resolutions

Classification of the R1–R16 pipeline after repair:

| Stage | Component | Status |
| --- | --- | --- |
| R1 | Source ingestion | IMPLEMENTED AND VERIFIED |
| R2 | Document processing / extraction | IMPLEMENTED AND VERIFIED |
| R3 | Chunking + metadata | IMPLEMENTED AND VERIFIED |
| R4 | Embedding generation | FIXED (dimension consistency) → VERIFIED |
| R5 | Vector storage (Qdrant) | FIXED (persistent path + close) → VERIFIED |
| R6 | Sparse representation / index | FIXED (persistence) → VERIFIED |
| R7 | Hybrid retrieval | IMPLEMENTED AND VERIFIED |
| R8 | Reranking | IMPLEMENTED AND VERIFIED |
| R9 | Query processing | FIXED (crop dictionary) → VERIFIED |
| R10 | Web search integration | IMPLEMENTED (opt-in; disabled by default) |
| R11 | Evidence builder | IMPLEMENTED AND VERIFIED |
| R12 | Evidence validator | IMPLEMENTED AND VERIFIED |
| R13 | RAG-to-B2 integration | FIXED (bootstrap wiring) → VERIFIED |
| R14 | E2E real retrieval | IMPLEMENTED AND VERIFIED |
| R15 | Evaluation | FIXED (metric correctness) → VERIFIED |
| R16 | Operational management | IMPLEMENTED; report updated |

### Historical risks — verified status

- **RAG provider not registered in bootstrap** — CONFIRMED and FIXED. `KnowledgeBaseModule`
  is now registered in `app/main.py` and registers its `RAGContextProvider` with the
  `ContextModule` (B2) during startup.
- **Embedding dimension inconsistency (384 vs 1024)** — CONFIRMED and FIXED. The provider
  default was MiniLM/384 while configuration and `.env.example` expected BGE-M3/1024. The
  provider now defaults to BGE-M3/1024; legacy MiniLM callers still resolve to 384.
- **Sparse index not persisting across restarts** — CONFIRMED and FIXED. `InvertedSparseIndexAdapter`
  now supports a `persist_path` (atomic write, deferred batch flush, reload on construction).
- **Qdrant local store not reopening after restart** — CONFIRMED and FIXED. Local persistent
  mode now uses the `path=` argument and the adapter exposes `close()`; the module closes it
  on shutdown, releasing the storage lock so a restart reopens the same durable store.
- **Missing dependency declarations** — FIXED. `requirements.txt` added.
- **Mock-heavy tests without real retrieval verification** — ADDRESSED. New integration tests
  (`tests/test_phase2_kb_integration.py`) and the R14 harness assert real readiness and
  persistence against a durable store.
- **Evaluation metric correctness** — CONFIRMED and FIXED. Retrieved chunk IDs embed the
  source id (`chk_ku_ver_src_x_...`) while ground truth uses `doc_src_x_...`; matching now
  normalizes both schemes, and per-document hits are de-duplicated so recall/nDCG stay ≤ 1.0.
- **Shared-config mutation leaking across components** — CONFIRMED and FIXED. The module
  previously assigned `enable_web_search` onto the shared `settings.rag_integration`
  singleton, which leaked `False` into any later consumer (manifesting as
  order-dependent R13 / multi-source failures). The module now builds a per-instance
  `RAGIntegrationConfig`, leaving the singleton untouched.

---

## 3. Corpus (Phase 2 expansion)

- 25 registered sources, each with publisher, original URL/origin, license, publication date
  and SHA-256 artifact checksum in `data/knowledge/manifest/corpus_manifest.json`.
- 15 new ICAR-linked crop cultivation packages plus soil, satellite/remote-sensing and
  general-agriculture references.
- Ingestion is additive and idempotent; the pre-existing corpus is preserved.

Coverage by domain and crop is in `docs/phase2_corpus_coverage.md` (machine-readable:
`docs/phase2_corpus_coverage.json`). Each of the 15 target crops is served by 5–7 source
documents; 12 of 15 crops have all tracked knowledge categories present. Remaining gaps
(e.g. rice/sugarcane visible-symptom text, wheat crop-identification wording) are reported
honestly rather than fabricated.

---

## 4. Evaluation results (real retrieval)

Run over the 32-case benchmark (`ds_earthmind_agri_v1`) with the live stack:

| Metric | K=1 | K=3 | K=5 | K=10 |
| --- | --- | --- | --- | --- |
| Precision@K | 0.833 | 0.344 | 0.213 | 0.107 |
| Recall@K | 0.767 | 0.878 | 0.889 | 0.889 |
| Hit rate@K | 0.833 | 0.900 | 0.900 | 0.900 |
| nDCG@K | 0.833 | 0.859 | 0.865 | 0.865 |

- MRR = 0.867
- Reliability: 32/32 SUCCESS, 0 failures, 0 empty results
- Evidence: valid_evidence_rate = 1.0, provenance_completeness = 1.0

Retrieval quality is measured separately from language-model answer quality (no LLM answer
scoring is claimed here).

---

## 5. Persistence verification

A restart test (`tests/test_phase2_kb_integration.py::test_knowledge_base_survives_restart`
and a manual two-process run) confirms:

1. First start auto-ingests the corpus → 213 records indexed, READY.
2. Shutdown persists the sparse index and closes the dense client.
3. Second start reopens the same durable store → READY with 213 records, **no re-ingestion**.
4. Farmer queries return evidence on both runs.

---

## 6. Test baseline

Full-suite result on this branch: **1248 passed, 0 failed, 35 errors** (1333s). The 35
errors are **pre-existing environmental failures** unrelated to this work — all in
PostgreSQL-backed memory tests (`test_memory_level3_postgres` ×10,
`test_memory_level4_operations_lifecycle` ×1, `test_memory_level6_quality_readiness` ×24)
that require a live PostgreSQL server, which is unavailable in this environment. The
earlier baseline (clean `main`) was 5 failed / 39 errors; this branch removes all 5
failures (the order-dependent R13/multi-source ones) and reduces errors, with no new
failures.

New and touched tests pass:

- `tests/test_phase2_kb_integration.py` — 4 passed (bootstrap registration, real
  retrieval, restart persistence, shared-config isolation)
- `tests/test_r15_rag_evaluation.py` — 32 passed (incl. 2 new regression tests)
- `tests/test_r13_rag_b2_integration.py`, `tests/test_multi_source_web_search_e2e.py`,
  `tests/test_r14_real_retrieval.py`, `tests/test_r7_hybrid_retrieval.py`,
  `tests/test_r8_reranking.py` — passed

---

## 7. Configuration

New/updated environment variables (documented in `.env.example`):

| Variable | Purpose |
| --- | --- |
| `EARTHMIND_EMBEDDING_MODEL` | Canonical embedding model (default `BAAI/bge-m3`) |
| `EARTHMIND_EMBEDDING_DIMENSION` | Must be `1024` for BGE-M3 |
| `EARTHMIND_SPARSE_INDEX_PATH` | Persistent sparse index file path |
| `EARTHMIND_KB_PERSIST_DIR` | Durable local store dir (default `data/rag_store/`) |
| `EARTHMIND_KB_INGEST_ON_STARTUP` | Force corpus ingestion at startup |

Non-production environments auto-ingest when the index is empty; production never
auto-ingests and relies on the explicit ingestion path.

---

## 8. Known limitations

- Remote Qdrant server deployment is configured but not exercised in this environment;
  persistence is verified against the local filesystem-backed store.
- Some per-crop knowledge categories are still missing (see the coverage report); these are
  reported as gaps, not fabricated.
- Web search integration (R10) is implemented but disabled by default.
