# Stage R7 — Hybrid Retrieval Specification & Implementation Architecture

**System:** EarthMind (`Earth-Mind.01`)
**Phase:** Phase RAG Operationalization
**Stage:** Stage R7 — Hybrid Retrieval
**Status:** IMPLEMENTED, VALIDATED & LOCKED (`READY_FOR_RERANKING`)

---

## Executive Summary

Stage R7 connects R5 Dense Vector Retrieval and R6 Sparse Vector Retrieval into a unified **Hybrid Retrieval Pipeline**, producing merged, deduplicated, and ranked candidates ready for Stage R8 Reranking.

```
                R7 HYBRID RETRIEVAL ENGINE
                           │
              ┌────────────┴────────────┐
              ↓                         ↓
       Dense Retrieval            Sparse Retrieval
    (R5 Qdrant / Fake)           (R6 BM25 Inverted)
              │                         │
              └────────────┬────────────┘
                           ↓
               Candidate Identity Resolution
                           ↓
                    Candidate Fusion
          (Reciprocal Rank Fusion - RRF k=60)
                           ↓
               Unified Hybrid Candidates
                           ↓
                  READY_FOR_RERANKING
```

---

## 1. Implemented Components & File Structure

### 1.1 Dense Index Interface Primitive (`core/interfaces/index.py`)
- Added `DenseSearchResult` container (`record_id`, `score`, `record`, `payload`).
- Extended `IKnowledgeIndexAdapter` protocol with `search_dense(collection_name, query_vector, top_k, filters, with_record)`.
- Updated `QdrantIndexAdapter` (`modules/knowledge_base/index/qdrant_adapter.py`) and `FakeIndexAdapter` (`modules/knowledge_base/index/fake_adapter.py`) with cosine similarity dense search implementation.

### 1.2 Data Contracts (`core/schemas/hybrid.py`)
- `HybridRetrievalStatus`: `SUCCESS`, `PARTIAL`, `FAILED`, `TIMEOUT`, `UNAVAILABLE`.
- `RetrievalSourceType`: `DENSE`, `SPARSE`, `HYBRID`.
- `CandidateRetrievalSource`: Tracks rank, score, provider, and model for each branch contribution.
- `HybridCandidate`: Unified candidate model holding merged score, fused rank, dense/sparse ranks, payload metadata, and provenance.
- `HybridRetrievalRequest`: Query string, dense vector, sparse indices/values, top-k limits, filters, fusion strategy, and timeouts.
- `HybridRetrievalResponse`: Fused candidates, count totals, status, warnings, and processing latency.

### 1.3 Candidate Fusion Engine (`modules/knowledge_base/retrieval/fusion.py`)
- `IFusionStrategy`: Protocol for fusion algorithms.
- `ReciprocalRankFusionStrategy`: Reciprocal Rank Fusion (RRF) algorithm computing $RRF\_Score = \sum \frac{1}{k + rank}$ (default $k=60$).
- `RelativeScoreFusionStrategy`: Relative Min-Max score normalization fusion.
- `CandidateFusionEngine`: Strategy registry and candidate merger. Matches candidate identities via `chunk_id` / `knowledge_unit_id` / `record_id`.

### 1.4 Hybrid Retrieval Coordinator (`modules/knowledge_base/retrieval/hybrid_engine.py`)
- `HybridRetrievalEngine`: Coordinates independent R5 dense and R6 sparse searches, enforces top-k bounds, applies metadata filters, tracks partial failure states, preserves provenance, and constructs R8-ready payloads.

---

## 2. Architectural Principles Compliance

1. **Extensibility / Rubber-Band Principle**: Fusion strategies (`IFusionStrategy`) and index backends can evolve or be swapped without affecting downstream engines.
2. **Loose Coupling**: R7 communicates strictly through interface protocols (`IKnowledgeIndexAdapter`, `ISparseIndexAdapter`). No Qdrant SDK types leak outside adapter boundaries.
3. **Single Responsibility**: R7 only performs candidate retrieval, identity resolution, duplicate merging, and fusion. Reranking is reserved for Stage R8.
4. **Controlled Dependencies**: Pure Python algorithms without requiring paid external API credentials or C-extensions.
5. **Replaceability & Evolution**: Dense retrieval, sparse retrieval, and fusion strategies can evolve independently.

---

## 3. Test Coverage & Verification

Executed test suite via `PYTHONPATH=. python -m pytest tests/test_r7_hybrid_retrieval.py`:
- **5 unit & integration test suites passed**:
  1. `test_rrf_fusion_correctness`: Verified mathematical accuracy of RRF scoring and tie handling.
  2. `test_relative_score_fusion`: Verified min-max score normalization fusion.
  3. `test_hybrid_engine_end_to_end`: Verified complete hybrid retrieval pipeline across fake dense and inverted sparse adapters.
  4. `test_partial_failure_handling`: Verified `PARTIAL` status when dense adapter is unavailable.
  5. `test_complete_failure_handling`: Verified explicit `FAILED` status and error messages when both retrieval branches fail.
