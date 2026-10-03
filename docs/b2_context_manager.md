# B2 Context Manager — Architecture, Implementation & Operational Guide

> **Core Responsibility Rule:**
> «B2 Context Manager prepares context; B2 does NOT perform final intelligence, agricultural diagnosis, or AI reasoning.»

---

## 1. Overview & Core Responsibility

The **B2 Context Manager** is EarthMind's central orchestration engine for context aggregation, normalization, policy enforcement, prioritization, token budgeting, and model payload preparation. Downstream intelligence engines (such as the B3 Reasoning Engine or B5 AI Orchestrator) rely on B2 to deliver structured, scope-safe, privacy-validated, and token-bounded context packages.

```
Raw Context Sources (RAG, Memory, Sensors, External, ULPU)
                         │
                         ▼
             ┌───────────────────────┐
             │ B2 Context Manager    │
             │ (12-Stage Pipeline)   │
             └───────────────────────┘
                         │
                         ▼
          Controlled B2 Context Package
                         │
                         ▼
        Downstream EarthMind Intelligence (B3 / B5)
```

---

## 2. Strictly Enforced Non-Reasoning Boundaries

To preserve EarthMind's principle of **Single Responsibility**, B2 strictly refrains from taking over domain responsibilities belonging to other modules:

| Prohibited Action inside B2 | Responsible Subsystem |
| :--- | :--- |
| Agricultural diagnosis, disease classification, treatment recommendations | **B3 Reasoning Engine** |
| Language translation, speech-to-text (STT), text-to-speech (TTS) | **ULPU (Universal Language Processing Unit)** |
| Direct dense/sparse vector retrieval & knowledge indexing | **Stage R5/R6 Index & Stage R7 Hybrid Engine** |
| Reranking candidate vectors | **Stage R8 Reranking Engine** |
| Query expansion, intent classification, dictionary mapping | **Stage R9 Query Processing Engine** |
| External web retrieval execution | **Stage R10 Web Search Layer** |
| Raw evidence building & deduplication | **Stage R11 Evidence Builder Engine** |
| Evidence validation gate checks | **Stage R12 Evidence Validator** |
| Visual crop symptom interpretation | **Vision Module** |
| Autonomous drone path execution | **Drone Module** |

---

## 3. The 12-Stage Context Lifecycle Pipeline

`B2ContextManager.prepare_context(request)` executes context processing through 12 deterministic lifecycle stages:

```
Stage 1: REQUESTED & VALIDATING ──► Validate request_id and request parameters
Stage 2: CACHE_CHECK ────────────► Return cached ContextResult if hit
Stage 3: COLLECTING ─────────────► Concurrently fetch from ContextProvider implementations
Stage 4: VALIDATING_CONTEXT ──────► Validate incoming ContextItem schemas via ItemValidator
Stage 5: DEDUPLICATING ──────────► Drop exact duplicate items using stable identity signals
Stage 6: FILTERING ──────────────► Enforce ScopeFilter, PrivacyFilter, and TimeFilter
Stage 7: EVALUATING_RELEVANCE ───► Score relevance against task objectives & requested types
Stage 8: DETECTING_CONFLICTS ────► Flag conflicting observations across sources (no item drop)
Stage 9: ORGANIZING ─────────────► Assign PriorityLevel and sort deterministically
Stage 10: LIMITING ──────────────► Enforce token budget through policy-driven reduction
Stage 11: BUILDING ──────────────► Construct structured JSON payload & observability metrics
Stage 12: VALIDATING_OUTPUT ─────► Validate scope isolation & budget compliance via OutputValidator
```

---

## 4. Input & Output Contracts

### 4.1 ContextRequest
`ContextRequest` defines the upstream request parameters for context preparation:
* `request_id` (str, required): Unique request trace identifier.
* `farmer_id`, `farm_id`, `field_id`, `crop_cycle_id`, `session_id` (str, optional): Target scope boundaries.
* `task` (str, optional): Objectives or user prompt text.
* `requested_context_types` (List[str]): Context entity types requested (e.g., `["field", "crop"]`).
* `time_range` (Dict, optional): Start/end ISO timestamp bounds for temporal filtering.
* `token_limit` (int): Maximum token budget permitted (default: `4096`).
* `relevance_threshold` (float): Minimum relevance score threshold (default: `0.5`).
* `policy` (`PolicyConfig`): Governance policy specifying mandatory item/type constraints, allow_pii, allow_partial, and timeout.

### 4.2 ContextResult
`ContextResult` delivers the model-ready context package:
* `request_id` (str): Identifier matching `ContextRequest`.
* `state` (`ContextState`): Final lifecycle state (`COMPLETED`, `PARTIAL`, `INSUFFICIENT_CONTEXT`, `FAILED`).
* `items` (List[`ContextItem`]): Model-ready filtered, prioritized, and token-bounded context items.
* `structured_context` (Dict): JSON-serializable dictionary containing scope, items, and conflict flags.
* `total_tokens` (int): Total token count across included items.
* `is_compressed` (bool): Whether compression was applied during budgeting.
* `warnings`, `errors` (List[str]): Execution warnings and non-fatal/fatal errors.
* `metadata` (Dict): Production observability metrics.

---

## 5. Context Item Model & C.3 Boundary Classification

Every item processed by B2 is represented by `ContextItem`, supporting C.3 RAG–Memory Boundary classifications:
* `context_id`: Unique context item identifier.
* `entity_type`, `entity_id`, `data_type`: Domain taxonomy attributes.
* `content`: Raw content payload (string, dict, or structured object).
* `source`, `source_id`: Origin system identifier.
* `confidence` (float): Provider confidence score (0.0 to 1.0).
* `conflict_status`: `NORMAL` or `CONFLICTED`.
* `privacy_level`: `PUBLIC`, `FARM_PRIVATE`, `FARMER_PII`.
* `relevance_score` (float): Calculated relevance score (0.0 to 1.0).
* `priority`: `HIGH`, `MEDIUM`, `LOW`.
* `token_count`: Token cost estimation.
* `source_type`, `ownership`, `classification`, `scope`, `persistence_intent`: C.3 Data boundary classification enums.

---

## 6. Provider Abstractions & Storage Isolation

B2 communicates exclusively through protocol interfaces to prevent coupling with concrete upstream modules:

| Interface Protocol | Module Location | Standard Provider Implementation |
| :--- | :--- | :--- |
| `ContextProvider` | `modules/context/interfaces.py` | `DictContextProvider`, `RAGContextProviderAdapter`, `MemoryContextProviderAdapter` |
| `CacheProvider` | `modules/context/interfaces.py` | `InMemoryCacheProvider` |
| `CompressionProvider` | `modules/context/interfaces.py` | `SimpleCompressionProvider` |

---

## 7. Token Budget Management & Reduction Hierarchy

When total token count across candidate items exceeds `request.token_limit`, `LimitManager` applies a deterministic 6-step reduction hierarchy:

1. **Remove clearly irrelevant optional items** (`relevance_score < 0.3`).
2. **Remove below-threshold optional items** (`relevance_score < request.relevance_threshold`).
3. **Remove LOW priority optional items**.
4. **Remove MEDIUM priority optional items**.
5. **Invoke CompressionProvider** (if registered) to truncate optional item content.
6. **Verify mandatory items**: If mandatory/HIGH priority items alone exceed budget, raise `InsufficientContextError`.

---

## 8. Structured Error Model

B2 exceptions inherit from `ContextError` (`core/errors/exceptions.py`):

```
EarthMindException
 └── ContextError
      ├── InvalidContextRequestError
      ├── InvalidContextItemError
      ├── ContextScopeViolationError
      ├── ContextPrivacyViolationError
      ├── InsufficientContextError
      ├── ContextOutputValidationError
      ├── ContextProviderError
      ├── ContextConfigurationError
      ├── ContextTimeoutError
      └── UnsupportedContextTypeError
```

---

## 9. Centralized Configuration (`ContextConfig`)

Configuration is centralized in `core/config/settings.py` under `settings.context`, supporting environment variables (`EARTHMIND_CONTEXT_*`):

```python
class ContextConfig(BaseModel):
    default_token_limit: int = 4096          # EARTHMIND_CONTEXT_DEFAULT_TOKEN_LIMIT
    default_relevance_threshold: float = 0.5  # EARTHMIND_CONTEXT_RELEVANCE_THRESHOLD
    default_timeout: float = 5.0              # EARTHMIND_CONTEXT_TIMEOUT
    allow_pii_default: bool = False           # EARTHMIND_CONTEXT_ALLOW_PII
    b2_version: str = "1.0.0"                 # EARTHMIND_CONTEXT_B2_VERSION
    context_version: str = "1.0.0"            # EARTHMIND_CONTEXT_VERSION
    enable_cache: bool = True                 # EARTHMIND_CONTEXT_ENABLE_CACHE
    strict_output_validation: bool = True     # EARTHMIND_CONTEXT_STRICT_OUTPUT_VALIDATION
```

---

## 10. Production Observability

Every prepared `ContextResult` includes detailed execution telemetry in `result.metadata`:

* `b2_version`: B2 engine version string (`"1.0.0"`).
* `context_version`: Context package schema version (`"1.0.0"`).
* `items_received`: Count of raw items received from providers.
* `items_retained`: Count of items retained in the final package.
* `items_filtered`: Count of items filtered out (scope/privacy/temporal/relevance).
* `items_dropped_budget`: Count of items dropped during token budget reduction.
* `provider_statuses`: Provider status dictionary (`{"provider_name": "SUCCESS" | "FAILED" | "TIMEOUT"}`).
* `execution_latency_ms`: Total preparation latency in milliseconds.
* `validation_status`: Output validation status (`"PASSED"` or `"FAILED"`).
* `prioritization_summary`: Count of items grouped by priority (`HIGH`, `MEDIUM`, `LOW`).

---

## 11. Testing & Verification

The B2 Context Manager implementation is verified through unit, integration, and rule tests in `tests/test_context_manager.py`:

* **20 B2-specific tests** verifying all 12 pipeline stages, scope isolation, privacy filters, temporal filters, deduplication, conflict detection, token budgeting, ULPU metadata preservation, non-reasoning boundary guarantees, and structured error handling.
* **657 passed tests** across the entire EarthMind repository with zero regressions.
