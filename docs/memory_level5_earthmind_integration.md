# EarthMind Memory Module: Level 5 — EarthMind Integration

## 1. Overview & Primary Objective

Level 5 integrates the completed Memory Module (Levels 1–4) into the broader EarthMind system architecture.
The primary objective is to supply authorized user-specific and approved shared memory records to downstream EarthMind components through stable, controlled interfaces, while preserving all established architectural boundaries:
- **Memory Module** remains strictly independent: it does NOT become a reasoning engine, planning engine, knowledge base, or workflow orchestrator.
- **B2 Context Manager** prepares, filters, prioritizes, and organizes context from multiple providers including Memory.
- **B3 Reasoning Engine** and **B4 Planning & Decision Engine** consume structured context from B2 without directly accessing Memory storage.
- **B5 Workflow Orchestration** executes workflows without circular dependencies.
- **ULPU (Universal Language Processing Unit)** preserves Indic and multilingual original text, scripts, and provenance end-to-end.

---

## 2. Integration Architecture & Data Flow

```
+-------------------------------------------------------------------------------+
|                             EarthMind Application                             |
|                        LifecycleManager & WorkflowEngine                      |
+-------------------------------------------------------------------------------+
                                        |
     +----------------------------------+----------------------------------+
     |                                                                     |
     v                                                                     v
+-----------------------+                                       +-----------------------+
|     MemoryModule      |                                       |     ContextModule     |
| (Hosting MemoryService|                                       |  (B2 Context Manager) |
| & MemoryContextProv.) |                                       +-----------------------+
+-----------------------+                                                   |
            |                                                               |
            | (IMemoryContextProvider)                                      |
            +---------------------------------------------------------------+
                                        |
                     MemoryContextProviderAdapter (B2 Provider)
                                        |
                                        v
                            B2 Context Pipeline Stages:
                 [COLLECTING] -> [VALIDATING] -> [DEDUPLICATING] ->
                 [FILTERING]  -> [RELEVANCE]  -> [ORGANIZING]    -> [LIMITING]
                                        |
                           Prepared ContextResult
                                        |
                 +----------------------+----------------------+
                 |                                             |
                 v                                             v
     +-----------------------+                     +-----------------------+
     |  B3 Reasoning Engine  |                     |  B4 Planning & Dec.   |
     | (EvidenceItem inputs) |                     |  (Context references) |
     +-----------------------+                     +-----------------------+
```

---

## 3. Module Registration & Lifecycle Initialization

The Memory Module integrates into EarthMind via `LifecycleManager` in `app/lifecycle.py` and bootstrap in `app/main.py`:
1. `MemoryModule` implements `MemoryInterface` (conforming to `ModuleInterface`).
2. Upon initialization:
   - Sets up `IMemoryStorageAdapter` (`InMemoryMemoryStorageAdapter` by default, or configured persistent storage adapter).
   - Initializes `MemoryService` with security enforcers and audit handlers.
   - Instantiates `MemoryContextProvider` conforming to `IMemoryContextProvider`.
   - Maintains legacy methods (`store_memory`, `retrieve_memory`, `handle`) for backward compatibility.
3. `ContextModule` accepts `memory_provider=memory_module.context_provider`, wrapping it into `MemoryContextProviderAdapter` and registering it with `B2ContextManager`.
4. Clean shutdown: `lifecycle.shutdown_all()` gracefully terminates resources in reverse topological dependency order.

---

## 4. B2 Context Manager Integration

Context retrieval from Memory adheres strictly to C.3 boundary contracts:
- **Interface Protocol**: `IMemoryContextProvider` (`get_memory_context(request: MemoryContextRequest) -> List[MemoryContextContract]`).
- **Adapter**: `MemoryContextProviderAdapter` translates B2 `ContextRequest` to `MemoryContextRequest`, invokes the provider, validates returned contracts against `BoundaryValidator`, and constructs typed `ContextItem`s.
- **Scope Mapping**:
  - `ContextScope.FARMER` -> `MemoryScope.USER`
  - `ContextScope.SESSION` -> `MemoryScope.CONVERSATION`
  - `ContextScope.FARM` -> `MemoryScope.FARM`
  - `ContextScope.FIELD` -> `MemoryScope.FIELD`
  - `ContextScope.CROP_CYCLE` -> `MemoryScope.CROP_CYCLE`
  - `ContextScope.GLOBAL` -> `MemoryScope.GENERAL`

---

## 5. Downstream Context Flows (B3, B4, B5)

### 5.1 B3 Reasoning Engine
- Consumes memory context solely through `prepared_context` (`ContextResult`).
- `EvidenceManager.prepare_evidence()` converts `ContextItem` records into `EvidenceItem` instances preserving source ID, reliability score, and entity references.
- Zero direct database queries or storage calls occur within B3.

### 5.2 B4 Planning & Decision Engine
- Receives relevant context summaries and references via `PlanningInput.relevant_context`.
- Stores context identifiers in `PlanningResult.decision.context_references`.
- Preserves explicit boundaries between historical user memory and general agricultural planning constraints.

### 5.3 B5 Workflow Orchestration
- Workflow tasks dispatch through `WorkflowEngine` to registered capability handlers.
- Memory context is requested during context preparation phases rather than ad-hoc orchestrator state mutations, preventing circular dependencies.

---

## 6. ULPU Compatibility & Multilingual Preservation

- Memory records retain original scripts (e.g., Devanagari for Hindi, Telugu, Tamil) and arbitrary structured payload formats.
- Zero translation or destructive normalizations are performed during storage or context boundary mapping.
- Provenance attributes trace the source transcript or input language.

---

## 7. Memory Context Governance & Security Boundaries

1. **Mandatory Authorization Context**: All memory queries require a trusted `AuthorizationContext`. Farmer IDs cannot be forged.
2. **Cross-User Isolation**: A query for `farmer_202` strictly cannot retrieve records owned by `farmer_101`. Any cross-user query attempt fails closed (returning 0 records).
3. **General Memory Governance**: Writing to the General Memory domain requires explicit curator/admin roles. Ordinary user write attempts raise `MemoryForbiddenError`.
4. **Lifecycle Exclusions**: Records with status `DELETED` or `EXPIRED` are filtered out before reaching B2 Context items.
5. **PII and Privacy Controls**: User memory records are assigned `PrivacyLevel.FARM_PRIVATE` and `is_pii=True`, filtered by B2's `PrivacyFilter` according to request `PolicyConfig(allow_pii=...)`.

---

## 8. Failure Handling & Reliability

- **Storage Unavailability**: `MemoryStorageUnavailableError` is caught gracefully; when partial results are permitted (`PolicyConfig.allow_partial=True`), B2 completes with state `PARTIAL` and records the error in telemetry.
- **Missing / Invalid Authentication**: Memory provider fails closed safely (returning empty lists or raising `MemoryUnauthorizedError`).
- **Empty Memory Results**: Return empty lists without throwing unexpected errors or synthesizing false memories.

---

## 9. Verification & Test Suite Summary

The Level 5 integration test suite in `tests/test_memory_level5_integration.py` verifies all integration facets:
- **Category A (Module Integration)**: Lifecycle registration, startup, shutdown, and legacy API support (`test_a01`, `test_a02`).
- **Category B (B2 Context Manager Integration)**: Scoped retrieval (USER, FARM, FIELD), empty result handling, expired/deleted exclusion, auth failure, storage failure (`test_b01` to `test_b06`).
- **Category C (B3/B4 Context Flow)**: ContextResult flow into B3 `EvidenceManager` and B4 `PlanningModule` (`test_c01`, `test_c02`).
- **Category D (B5 Workflow Orchestration)**: Workflow engine request dispatch without circular dependencies (`test_d01`).
- **Category E (ULPU Multilingual)**: Multilingual Indic text and script preservation (`test_e01`).
- **Category F (Security & Regression)**: Cross-user isolation and General Memory write denial (`test_f01`, `test_f02`).

**Total Test Results**:
- `tests/test_memory_level5_integration.py`: 14 passed.
- `tests/test_memory_level1_foundation.py`: 14 passed.
- `tests/test_memory_level2_domains_security.py`: 24 passed.
- `tests/test_context_manager.py`: 20 passed.
- `tests/test_rag_memory_integration.py`: 20 passed.
- `tests/test_rag_memory_boundary.py`: 20 passed.
- Overall regression suite: 100% pass rate.

---

## 10. Known Limitations & Next Steps

- **PostgreSQL in Sandbox**: While `SupabasePostgresMemoryStorageAdapter` is fully implemented and tested (Level 3), running live PostgreSQL tests requires a running PostgreSQL server daemon in the execution environment. The default runtime adapter is `InMemoryMemoryStorageAdapter`.
- **Level 6**: Advanced production optimizations (e.g., connection pooling tuning, distributed cache replication) are deferred to Level 6 per specification lock.
