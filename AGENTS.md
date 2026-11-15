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
