# Stage R11 — Evidence Builder Documentation

## 1. Overview and Purpose

Stage R11 Evidence Builder is responsible for **Evidence Construction** in EarthMind RAG.

It receives normalized upstream retrieval outputs from:
- **Stage R8 Reranking** (Knowledge Base evidence candidates with dense, sparse, fused, and reranker scores/ranks)
- **Stage R10 Web Search Integration** (Web search results with provider provenance, snippets, URLs, and rank)

And converts them into a structured, traceable, provider-independent **Evidence Package** for downstream consumption by B2 Context Manager and B3 Reasoning Engine.

```
R8 Reranking
      │
      ├──────────────┐
      │              │
      ▼              ▼
KB Evidence       R10 Web Evidence
      │              │
      └──────┬───────┘
             ▼
       R11 Evidence Builder
             │
             ▼
      Evidence Package
             │
             ▼
        B2 Context Manager
             │
             ▼
        B3 Reasoning
```

### Critical Boundaries
- **R11 DOES NOT perform reasoning, determine truth, or make agricultural decisions.**
- **R11 DOES NOT perform retrieval, query expansion, reranking, or Web Search.**
- **R11 NEVER automatically publishes Web Search results into permanent Knowledge Base.**
- **R11 NEVER writes to Memory (C.3 boundary).**
- **R11 NEVER accesses Qdrant vector index or SQLite database internals directly.**

---

## 2. Core Contracts and Schemas

Defined in `core/schemas/evidence.py`:

1. **`EvidenceSourceType`**: Enum (`KNOWLEDGE_BASE`, `WEB_SEARCH`).
2. **`EvidenceBuildStatus`**: Enum (`SUCCESS`, `PARTIAL`, `EMPTY`, `INVALID`, `FAILED`, `UNAVAILABLE`).
3. **`EvidenceItem`**: Unified, traceable evidence item model preserving:
   - `evidence_id`
   - `source_type` (`KNOWLEDGE_BASE` or `WEB_SEARCH`)
   - `source_id`, `document_id`, `version_id`, `section_id`, `knowledge_unit_id`, `chunk_id`, `candidate_id`, `web_result_id`
   - `title`, `content`, `url`, `provider`
   - Upstream ranks (`retrieval_rank`, `dense_rank`, `sparse_rank`, `fused_rank`, `rerank_rank`)
   - Upstream scores (`dense_score`, `sparse_score`, `fused_score`, `rerank_score`)
   - Domain `metadata` (crop, disease, region, state)
   - Origin `provenance`
   - `source_assessment` signals
   - `conflict_indicators`
   - `multimodal_data`
   - `is_truncated` and `truncation_reason`
4. **`EvidencePackage`**: Container holding `items`, counts (`kb_items_count`, `web_items_count`, `total_items_count`), execution metrics, and `to_rag_context_contracts()` conversion for B2 Context Manager.
5. **`EvidenceBuildRequest`** and **`EvidenceBuildResponse`**.

---

## 3. Evidence Builder Engine Architecture

Implemented in `modules/knowledge_base/evidence/engine.py`:

- **`EvidenceBuilderEngine`**: Implements `IEvidenceBuilderEngine` protocol.
- **Conservative Deduplication**: Deduplicates items only when explicit, definitive identity matches exist (`chunk_id`, `candidate_id`, `web_result_id`, normalized URL). Preserves distinct items if uncertain.
- **Bounded Content Truncation**: Enforces max content length per item and max total items per package, recording explicit truncation warning state without destroying source identity or provenance.
- **Partial Failure Handling**: Explicitly tracks partial upstream failures (e.g. R8 SUCCESS + R10 FAILED or vice versa), setting status to `PARTIAL` while preserving valid evidence items.
- **B2 Context Manager Compatibility**: `EvidencePackage.to_rag_context_contracts()` bridges evidence items into B2 `RAGContextContract` objects with `RAG_OWNED` ownership, preserving all evidence and retrieval metadata.

---

## 4. Five EarthMind Principles Compliance

1. **Extensibility / Rubber-Band Principle**:
   - New evidence source categories or upstream providers can be added without changing the `IEvidenceBuilderEngine` interface or downstream B2/B3 consumers.
2. **Loose Coupling**:
   - R11 operates strictly on data contracts (`RerankResponse`, `WebSearchResponse`, `EvidencePackage`, `RAGContextContract`). It has zero dependency on R8/R10 provider internals, Qdrant, or SQLite.
3. **Single Responsibility**:
   - R11 is solely responsible for evidence package construction and normalization.
4. **Controlled Dependencies**:
   - R11 imports only schema contracts and configuration, avoiding unnecessary infrastructure packages.
5. **Replaceability + Evolution**:
   - Upstream rerankers or search providers and downstream context managers can evolve independently behind contract boundaries.

---

## 5. Verification and Test Coverage

Verified via `tests/test_r11_evidence_builder.py` across 28 audit requirements:
- KB evidence construction
- Web evidence construction
- Mixed KB + Web evidence packages
- Score and rank preservation
- Conservative deduplication
- C.2 Lineage and Provenance preservation
- Source assessment & conflict indicator preservation
- Multimodal and agricultural metadata propagation
- Partial / Empty / Malformed upstream response handling
- Content truncation and item count limits
- Deterministic ordering
- B2 Context Manager compatibility
- C.2/C.3 governance boundary (transient Web Search, no Memory writes, zero DB access)
