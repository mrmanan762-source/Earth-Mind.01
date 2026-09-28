# Stage R8 — Reranking Architecture & Implementation

**Status:** ACTIVE & VALIDATED
**Upstream Dependency:** Stage R7 Hybrid Retrieval
**Downstream Consumer:** Stage R11 Evidence Builder

---

## 1. Executive Summary

Stage R8 Reranking takes the fused candidate set produced by Stage R7 Hybrid Retrieval, applies an independent, provider-replaceable reranking process (e.g., cross-encoders or custom relevance scoring), produces a deterministic relevance-ranked candidate set, preserves all upstream provenance and scoring information, and exposes a stable contract for downstream Stage R11 Evidence Builder.

R8 operates as an independent candidate scoring engine. It does **not** perform query expansion, retrieval, direct vector index access, hybrid fusion, web search, evidence synthesis, agricultural reasoning, or agricultural decision-making.

---

## 2. R8 Boundary & Flow

```
R7 Hybrid Retrieval (fused candidates)
         ↓
R8 Input Validation (query & candidate verification)
         ↓
R8 Reranker Provider (IRerankerProvider protocol)
         ↓
R8 Score Processing & Normalization
         ↓
R8 Deterministic Ordering & Tie-Breaking
         ↓
R8 Reranked Candidates (RerankResponse)
         ↓
R11 Evidence Builder
```

### R8 DOES:
- Consume `R7 HybridRetrievalResponse` / `HybridCandidate`
- Validate query text and candidate input constraints
- Enforce candidate limits (`max_candidate_count`, `top_k`)
- Prepare reranker inputs (query text + candidate text representation)
- Invoke `IRerankerProvider` implementations
- Compute independent `rerank_score` metrics
- Apply deterministic score normalization (`NONE`, `MIN_MAX`, `SIGMOID`)
- Deterministically order candidates by `rerank_score` descending, with `fused_rank` and `candidate_id` as tie-breakers
- Assign 1-based `rerank_rank`
- Preserve all upstream R7 dense, sparse, and fused scores/ranks
- Preserve candidate identity, provenance, and payload metadata
- Execute transparent fallback handling (`PRESERVE_FUSED_ORDER`) on provider failure without score fabrication
- Provide structured `RerankResponse` outputs for Stage R11 Evidence Builder

### R8 DOES NOT:
- Perform query expansion or rewriting
- Execute dense/sparse index retrieval or direct Qdrant access
- Perform hybrid fusion (R7 responsibility)
- Execute Web Search or external retrieval
- Build evidence or perform evidence synthesis (R11 responsibility)
- Perform context management (B2 responsibility), reasoning (B3 responsibility), or planning (B4 responsibility)
- Perform agricultural diagnosis or decision-making
- Access SQLite or Memory databases directly

---

## 3. Data Contracts

Defined in `core/schemas/rerank.py`:

### `RerankStatus`
Execution status enum: `SUCCESS`, `PARTIAL`, `FAILED`, `TIMEOUT`, `UNAVAILABLE`, `FALLBACK`.

### `RerankCandidate`
Reranked candidate representation preserving complete upstream R7 lineage and adding R8 metrics:
- **Identity & Lineage:** `candidate_id`, `record_id`, `chunk_id`, `knowledge_unit_id`, `source_id`, `document_id`, `version_id`
- **R7 Upstream Scores & Ranks:** `fused_score`, `fused_rank`, `dense_rank`, `dense_score`, `sparse_rank`, `sparse_score`
- **R8 Reranking Metrics:** `rerank_score` (Optional[float]), `rerank_rank` (Optional[int]), `rerank_provider` (str), `rerank_model` (str), `is_fallback` (bool)
- **Metadata & Provenance:** `retrieval_sources`, `payload_metadata`, `provenance`, `record`

### `RerankRequest`
Input payload for reranking:
- `query_text`: User query string
- `candidates`: List of `HybridCandidate`s
- `top_k`: Number of top candidates requested
- `request_id`: Tracing correlation ID
- `timeout`: Per-request execution timeout
- `allow_fallback`: Whether to fall back to R7 fused ordering on failure
- Factory method: `from_hybrid_response(response: HybridRetrievalResponse, top_k: Optional[int] = None)`

### `RerankResponse`
Output payload for Stage R11 Evidence Builder:
- `request_id`, `query_text`, `status`, `candidates`, `total_candidates_received`, `total_candidates_reranked`, `provider_used`, `model_used`, `is_fallback`, `processing_time_ms`, `warnings`, `error_message`

---

## 4. Provider Interface & Adapters

### `IRerankerProvider` Protocol (`core/interfaces/reranker.py`)
```python
@runtime_checkable
class IRerankerProvider(Protocol):
    def rerank(self, query_text: str, documents: List[Dict[str, Any]], top_k: Optional[int] = None, timeout: Optional[float] = None) -> List[RerankScoreResult]: ...
    def is_available(self) -> bool: ...
    def get_provider_info(self) -> Dict[str, Any]: ...
```

### Implementations (`modules/knowledge_base/reranking/providers/`):
1. **`FakeRerankerProvider`**: Fully deterministic offline fake provider for unit testing and offline execution.
2. **`CrossEncoderRerankerProvider`**: Self-hosted cross-encoder model adapter using `sentence_transformers`. Implemented in a resource-safe manner: if dependencies or model weights are missing, `is_available()` returns `False` and `RerankerProviderUnavailableError` is raised without fabricating fake model outputs.

---

## 5. Configuration Settings

Defined in `RerankConfig` (`core/config/settings.py`):

| Setting | Default | Description |
|---|---|---|
| `provider` | `"fake"` | Active provider identifier (`fake`, `cross_encoder`, `self_hosted`) |
| `model` | `"BAAI/bge-reranker-base"` | Cross-encoder model identifier |
| `model_version` | `"1.0.0"` | Model schema/version string |
| `batch_size` | `32` | Batch size for model evaluation |
| `max_candidate_count` | `100` | Maximum candidate limit accepted for reranking |
| `max_input_length` | `512` | Token/character sequence limit |
| `timeout` | `10.0` | Request timeout in seconds |
| `candidate_limit` | `10` | Default top-k reranked limit |
| `fallback_policy` | `"PRESERVE_FUSED_ORDER"` | Fallback policy on provider failure (`PRESERVE_FUSED_ORDER`, `FAIL`) |
| `score_normalization_policy` | `"NONE"` | Score normalization method (`NONE`, `MIN_MAX`, `SIGMOID`) |
| `deterministic_ordering_policy` | `"HIGHER_SCORE_FIRST"` | Primary candidate sorting rule |
| `allow_download` | `False` | Allow remote model weight downloads |
| `device` | `"cpu"` | Execution device (`cpu`, `cuda`, `mps`, `auto`) |

---

## 6. Score & Rank Semantics

### Score Semantics
- **Preservation:** Upstream `fused_score`, `dense_score`, and `sparse_score` are **never** overwritten or destroyed.
- **Direction:** Higher `rerank_score` = higher relevance.
- **Independent Score:** `rerank_score` is stored as an explicit, separate field.
- **Normalization:** Configurable normalization (`MIN_MAX` rescales scores to `[0, 1]`, `SIGMOID` applies standard logistic curve).

### Rank Semantics
- **`fused_rank`:** Upstream R7 candidate position (1-based).
- **`rerank_rank`:** Final R8 candidate position (1-based).
- **Deterministic Tie-Breaking:**
  1. `rerank_score` DESCENDING
  2. `fused_rank` ASCENDING (lower rank = stronger R7 contribution)
  3. `candidate_id` ASCENDING (alphabetical stability)

---

## 7. Failure & Fallback Policy

When the reranker provider fails, times out, or is unavailable:
1. If `fallback_policy == "PRESERVE_FUSED_ORDER"` and `allow_fallback == True`:
   - Output `status` is set to `RerankStatus.FALLBACK`
   - `is_fallback` is set to `True` for response and each candidate
   - Original R7 fused candidate ordering is preserved (`rerank_rank = fused_rank`)
   - `rerank_score` is set to `None` (**NEVER** fabricate fake scores!)
   - Operational warning is appended
2. If fallback is disabled (`allow_fallback == False` or `fallback_policy == "FAIL"`):
   - Output `status` is set to `FAILED`, `UNAVAILABLE`, or `TIMEOUT`

---

## 8. Multilingual & Indian Language Readiness

R8 handles query and document text neutrally without English-only assumptions. Tested against Devanagari Hindi, Marathi, and mixed Indic agricultural knowledge text. Text transformations and translation remain the exclusive responsibility of ULPU.

---

## 9. Adherence to 5 EarthMind Principles

1. **Extensibility / Rubber-Band Principle:** Custom or commercial rerankers can be introduced by implementing `IRerankerProvider` without modifying R7 or R11.
2. **Loose Coupling:** R8 interacts strictly through `RerankRequest` / `RerankResponse` and `IRerankerProvider` protocols.
3. **Single Responsibility:** R8 only performs candidate relevance scoring and ranking.
4. **Controlled Dependencies:** R8 depends solely on standard contracts (`core/schemas/rerank.py`, `core/schemas/hybrid.py`) and configuration.
5. **Replaceability & Evolution:** Providers and scoring algorithms evolve independently behind `IRerankerProvider`.
