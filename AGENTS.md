# AGENTS.md — EarthMind repository notes

## Project
EarthMind System Skeleton — an AI-driven agricultural architecture system.
Python 3.13. Entry point: `main.py` → `app/main.py::create_app()` returns
`(LifecycleManager, WorkflowEngine)`.

## Layout
- `app/` — bootstrap (`main.py`), `lifecycle.py` (LifecycleManager),
  `workflow.py` (WorkflowEngine, dispatches `ApplicationRequest` by
  `metadata["target_module"]`).
- `core/` — cross-cutting contracts: `core/schemas/`, `core/interfaces/`,
  `core/config/settings.py` (all config via `EARTHMIND_*` env vars),
  `core/errors/exceptions.py` (`EarthMindException` + `error_contract`),
  `core/logging/logger.py` (`get_logger`).
- `modules/` — loosely-coupled modules implementing `ModuleInterface`
  (`initialize`/`handle`/`shutdown`): ai, memory, context, satellite, drone
  (feature-frozen), knowledge_base (RAG Stages R1–R16), tools (Phase 3),
  external_services, etc.
- `docs/` — per-stage documentation (`r*` = RAG stages, `phase3_*` = tools).
- `tests/` — pytest; `tests/conftest.py` adds repo root to `sys.path`.

## Commands
- Run all tests: `python3 -m pytest` (use `python3 -m`, not bare `pytest`).
- Phase 3 tools only:
  `python3 -m pytest tests/test_tools_infrastructure.py tests/test_tools_integration.py`.

## Environment / test caveats (important)
The full suite has **pre-existing environmental failures** unrelated to code:
missing `qdrant_client`, unavailable PostgreSQL, and missing model weights.
Baseline on a clean checkout: ~22 failed, 79 errors. These are concentrated in
`test_memory_level3_postgres`, `test_memory_level4_operations_lifecycle`,
`test_memory_level6_quality_readiness`, `test_r12_evidence_validator`,
`test_r13_rag_b2_integration`, `test_r14_real_retrieval`,
`test_real_hybrid_retrieval_reranking`, `test_step12_final_acceptance`,
`test_embedding_layer`, `test_index_layer`, `test_production_configuration`,
`test_r15_rag_evaluation`, `test_r5_qdrant_deployment`.
When checking regressions, compare the **set of failing node IDs** against this
baseline — do not treat these as new breakage.

## Conventions
- Secrets are backend-only, loaded from `EARTHMIND_*` env vars, never hardcoded
  and never exposed to frontend responses. `Settings.to_safe_dict()` masks them.
- Providers are replaceable adapters behind `core/interfaces/*` protocols
  (e.g. `IWebSearchProvider`, `IWeatherProvider`).
- Errors raise `EarthMindException` subclasses carrying an `error_contract`
  (`error_code`, `module`, `operation`, `retryable`, `metadata`).
- Config additions: define a `*Config(BaseModel)` before `class Settings` using
  `os.getenv("EARTHMIND_...")`, add the field to `Settings`, register timeout in
  the timeout map, and mask any secret in `to_safe_dict()`.

## Phase 3 (backend tool infrastructure)
- `modules/tools/` — Registry, Dispatcher, ExecutionManager, ResultNormalizer,
  security helpers, `request_parser.parse_model_tool_call`, `ToolService`,
  `ToolModule` (registered in `app/main.py` as module `"tools"`).
- `modules/tools/catalog/` — calculator, web_search, weather, satellite.
- `modules/tools/weather_providers/` — open_meteo (free/keyless default),
  openweather (keyed, opt-in), fake (tests).
- Contracts: `core/schemas/tools.py` (`ToolCallRequest`, `ToolCallResult`,
  `ToolDefinition`, `ToolPermission`, ...), `core/schemas/weather.py`.
- B5 orchestration is NOT duplicated: tools execute single atomic calls only.
- Permissions for tool calls come only from trusted `request.metadata`
  (`granted_permissions`), never from model output or `payload`.
- Sarvam-105B integration is deferred to Phase 5 (use `parse_model_tool_call`).

## Phase 2 (RAG completion — knowledge_base)
- `modules/knowledge_base/kb_module.py` — `KnowledgeBaseModule` owns the RAG stack
  (embedding, sparse, dense/sparse adapters, hybrid retriever, reranker,
  evidence builder/validator, `RAGContextProvider`) and is registered in
  `app/main.py` as module `"knowledge_base"`. It registers the RAG provider with
  B2 (`ContextModule.register_rag_provider`) during `initialize()`.
- Operational-by-default: in non-production, an empty index is auto-ingested from
  the canonical corpus; production never auto-ingests. Durable store defaults to
  `data/rag_store/` (gitignored). `EARTHMIND_KB_PERSIST_DIR`,
  `EARTHMIND_KB_INGEST_ON_STARTUP` control this.
- Embedding is canonical **BAAI/bge-m3, 1024-dim** everywhere (ingestion, index,
  query, retrieval, evaluation). MiniLM/384 is only honoured when a caller
  explicitly requests a `minilm` model.
- Sparse index persists to `data/rag_store/sparse_index.json`
  (`EARTHMIND_SPARSE_INDEX_PATH`). Qdrant local persistent mode uses `path=`;
  `QdrantIndexAdapter.close()` releases the storage lock so restarts reopen it.
- Evaluation: `QualityEvaluator` normalizes chunk IDs (`chk_ku_ver_src_x_...`)
  against ground-truth doc IDs (`doc_src_x_...`) and de-duplicates per-document
  hits so recall/nDCG stay ≤ 1.0.
- Corpus: 25 verified sources / 213 chunks in `data/knowledge/manifest/corpus_manifest.json`.
  Coverage report: `python3 scripts/corpus_coverage_report.py` →
  `docs/phase2_corpus_coverage.{md,json}`.
- Phase 2 completion report: `docs/phase2_completion_report.md`.

## Phase 4 (integration — B2–B5 in one workflow)
- `app/integration/` composes the completed modules into one application flow and
  is registered in `app/main.py` as module `"application"` (`IntegratedApplicationModule`).
  - `capabilities.py` — typed B5 `ICapability` adapters (B2/B3/B4/Inspector/Memory/
    ULPU/Satellite/Tools). They only marshal data; no module logic is duplicated.
  - `tool_selection.py` — deterministic, request-dependent tool selection. Never
    calls every tool for every request.
  - `tool_evidence_provider.py` — B2 `ContextProvider` surfacing request-scoped
    tool results (registered on `context_module.manager`).
  - `workflow.py` — `IntegratedWorkflow` (normalise → tool selection → B5
    orchestration → ULPU localisation → structured response) + duplicate
    protection + controlled/partial failure handling.
- B5 remains the sole coordinator; the tools step calls the existing `ToolService`
  (no duplicate dispatcher). Tool results reach B2 through a provider, not via B5.
- Tool permissions come only from trusted `request.metadata`
  (`granted_permissions`); payload/model output can never self-grant.
- Memory PII is excluded from B2 unless the caller passes `policy.allow_pii=True`
  (privacy boundary); verified in `tests/test_phase4_integration.py`.
- Sarvam runs in stub mode (`Sarvam105BAdapter.load()`), shared by the AI module
  and B3's `ModelLayerReasoningCapability`. Real Sarvam-105B inference is Phase 5.
- RAG→B2 provenance: `EvidenceItem.from_rerank_candidate` now reconstructs the
  provenance dict from the ingestion-persisted index payload when upstream lineage
  objects are absent. Without this, B2's boundary validator rejected every real
  RAG contract ("Missing or empty mandatory field: provenance") — a pre-existing
  gap (R13 tests only passed because their mocks supplied provenance).
- Phase 4 tests: `tests/test_phase4_integration.py` (26 tests). Full-suite
  baseline with `qdrant_client`/`psycopg2` installed: 3 failed / 1270 passed /
  1 skipped / 35 errors, all environmental (Postgres, model weights, network).
