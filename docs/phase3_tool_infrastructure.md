# Phase 3 — Backend Tool Infrastructure

Status: **Implemented and tested (mocked providers).** No Sarvam-105B integration
is performed in this phase; that is deferred to Phase 5.

This document describes the secure, modular, reusable backend tool system added
in Phase 3. It is deliberately a *system*, not a collection of scripts: the
registry, dispatcher, execution manager and normalizer are reusable core
infrastructure, and tools are pluggable.

---

## 1. Architecture overview

```
Model adapter / B5 / API
        │  (ToolCallRequest — validated, model-independent)
        ▼
  ToolDispatcher ──► ToolRegistry ──► ITool implementation (adapter)
        │                                   │
        │  permission + payload checks       │ execute()
        ▼                                   ▼
  ToolExecutionManager  (timeout, retries, concurrency, rate limit, cancel)
        │
        ▼
  ToolResultNormalizer ──► ToolCallResult (consistent contract)
```

Components:

| Component | File | Responsibility |
|---|---|---|
| Contracts | `core/schemas/tools.py` | Request/response/definition contracts |
| Interfaces | `modules/tools/interfaces.py` | `ITool`, `IToolRegistry`, `IToolDispatcher` |
| Registry | `modules/tools/registry.py` | Register tools, schemas, availability |
| Dispatcher | `modules/tools/dispatcher.py` | Validate, authorize, route, normalize |
| Execution Manager | `modules/tools/execution_manager.py` | Timeouts, retries, concurrency, rate limits, cancellation, status |
| Normalizer | `modules/tools/normalizer.py` | Consistent `ToolCallResult` |
| Security | `modules/tools/security.py` | Redaction, size limits |
| Request parser | `modules/tools/request_parser.py` | Model-independent tool-call parsing |
| Service / Module | `modules/tools/tool_service.py`, `tool_module.py` | Integration container + `ModuleInterface` entry point |
| Catalogue | `modules/tools/catalog/` | Calculator, Web Search, Weather, Satellite |

### Integration boundaries (unchanged responsibilities)

- **B5 Orchestrator** retains workflow coordination. The tool layer executes a
  single atomic tool call and never orchestrates multi-step workflows.
- **External Services** provider-adapter boundaries are reused (web search uses
  the existing `modules/knowledge_base/web_search` subsystem).
- **B2 Context Manager** consumes the normalized `ToolCallResult` contract;
  B2 is not redesigned.
- **B3 / B4** reasoning and planning responsibilities are not moved into tools.
- **Satellite Intelligence** is reused as-is through an adapter; the module is
  not rebuilt and the feature-frozen Drone Module is not touched.
- **RAG (Phase 2)** is untouched; the tool layer exposes clean interfaces for
  future integration without duplicating retrieval.

---

## 2. Tool registration

A tool implements `ITool`:

```python
class MyTool:
    def get_definition(self) -> ToolDefinition: ...   # id, schemas, permissions, config
    def validate_arguments(self, arguments: dict) -> dict: ...
    def is_available(self) -> bool: ...
    def execute(self, arguments: dict, request: ToolCallRequest): ...
```

Register it with the service (new tools require no core changes):

```python
from modules.tools.tool_service import ToolService
service = ToolService()          # registers the default catalogue
service.register_tool(MyTool())  # pluggable extension point
```

The registry validates the definition on registration (unique id, non-empty
input/output schemas, at least one error contract) and probes availability.

### Tool definition fields

- `tool_id`, `name`, `description`, `version`
- `input_schema`, `output_schema` (JSON-schema style)
- `required_permissions` (list of `ToolPermission`)
- `execution` (`ToolExecutionConfig`: timeout, retries, idempotency, concurrency,
  rate limit, cancellability, request/result byte limits)
- `error_contract` (documented error codes)
- `available` / `unavailable_reason`

---

## 3. Request and response contracts

### Request (`ToolCallRequest`)

```json
{
  "tool_id": "calculator",
  "request_id": "tool_req_ab12cd34ef56",
  "arguments": {"operation": "evaluate", "expression": "2+3*4"},
  "caller": "model_adapter",
  "permissions": ["COMPUTE"],
  "source": "model",
  "timeout_override": null,
  "dry_run": false
}
```

### Response (`ToolCallResult`)

```json
{
  "tool_id": "calculator",
  "request_id": "tool_req_ab12cd34ef56",
  "status": "SUCCESS",
  "payload": {"operation": "evaluate", "result": 14},
  "sources": [],
  "execution": {"duration_ms": 1.2, "attempts": 1, "retries": 0, "timed_out": false},
  "error": null,
  "warnings": []
}
```

Statuses: `SUCCESS`, `PARTIAL`, `INVALID_REQUEST`, `NOT_FOUND`,
`PERMISSION_DENIED`, `UNAVAILABLE`, `VALIDATION_ERROR`, `TIMEOUT`, `CANCELLED`,
`RATE_LIMITED`, `CONCURRENCY_LIMIT`, `EXECUTION_ERROR`,
`PAYLOAD_LIMIT_EXCEEDED`, `INTERNAL_ERROR`.

Source references (`sources[]`) preserve provenance: `source_type`, `title`,
`url`, `provider`, `publication_date`, `observed_at`, `is_forecast`.

---

## 4. Tool calling compatibility (model-independent)

`modules/tools/request_parser.py::parse_model_tool_call` converts a
model-generated tool call (JSON string or dict) into a validated
`ToolCallRequest`. Design guarantees:

- Model output is separated from execution: the parser only *builds a request*;
  the dispatcher decides whether to run it.
- Arbitrary model-generated code is never executed.
- A model cannot self-grant permissions: permission fields in model output are
  rejected, and grants come only from the trusted caller
  (`granted_permissions`).

Future Sarvam-105B integration (Phase 5) will call this function from a model
adapter. It is not implemented in Phase 3.

---

## 5. Provider configuration

### Web Search

Reuses the existing Stage R10 configuration (`EARTHMIND_WEB_SEARCH_*`). Tavily is
the primary provider, Gemini Google Search Grounding the secondary provider,
with supplementary public providers. No new credentials are introduced.

### Weather

| Variable | Default | Notes |
|---|---|---|
| `EARTHMIND_WEATHER_PROVIDER` | `open_meteo` | `open_meteo` (free, keyless), `openweather` (keyed), `fake` (tests) |
| `EARTHMIND_WEATHER_API_KEY` | — | Backend only; required only for `openweather` |
| `EARTHMIND_WEATHER_TIMEOUT` | `10.0` | Per-request timeout (seconds) |
| `EARTHMIND_WEATHER_FORECAST_DAYS` | `3` | Default forecast days |
| `EARTHMIND_WEATHER_STALE_AFTER_MINUTES` | `180` | Observation freshness window |
| `EARTHMIND_WEATHER_UNITS` | `metric` | `metric` or `imperial` |
| `EARTHMIND_WEATHER_MAX_CONCURRENCY` | `5` | Concurrency limit |
| `EARTHMIND_WEATHER_RPM` | `60` | Requests per minute |

The default Open-Meteo provider is free and keyless (no cost). OpenWeather is
optional and must not be enabled without authorization.

---

## 6. Security boundary

- All external API credentials remain backend-only; none are exposed to React,
  browser JavaScript or frontend responses.
- No credentials are hardcoded; secrets load from environment configuration.
- Secrets are redacted from logs and errors (`modules/tools/security.py`,
  applied by the normalizer to messages, warnings and error metadata).
- Tool inputs are validated; request and result byte limits are enforced.
- Arbitrary code execution is prevented (the calculator uses an AST whitelist,
  never `eval`).
- Unauthorized invocation is prevented (permission checks in the dispatcher;
  permissions come only from trusted metadata, never from model output).

---

## 7. Error handling

All tool failures are normalized into `ToolCallResult.error` with an
`error_code`, redacted `message`, `retryable` flag and redacted `metadata`.
The tool exception hierarchy lives in `core/errors/exceptions.py`
(`ToolError` and subclasses). Transient failures (`TOOL_TIMEOUT`,
`TOOL_RATE_LIMITED`, provider unavailable) are marked retryable; the execution
manager retries only idempotent tools and never retries timeouts.

---

## 8. Testing instructions

```bash
python3 -m pytest tests/test_tools_infrastructure.py tests/test_tools_integration.py
python3 -m pytest          # full suite
```

- `tests/test_tools_infrastructure.py` — unit + security tests (registration,
  schema validation, routing, calculator, normalization, execution manager).
- `tests/test_tools_integration.py` — integration + provider-adapter tests
  (registry→dispatcher→adapter, satellite compatibility, mocked Tavily/Gemini
  and Open-Meteo/OpenWeather, security redaction).

All provider tests are **mocked or deterministic**. No live external network
calls are made by the test suite. Live connectivity is not verified here.

---

## 9. Future Sarvam integration interface

Phase 5 will:

1. Add a Sarvam-105B model adapter that emits tool calls.
2. Translate those calls via `parse_model_tool_call(...)` with
   `granted_permissions` supplied by the trusted adapter (not the model).
3. Dispatch through `ToolService.execute(...)` and feed the normalized
   `ToolCallResult` back to the model / B2.

No model integration is implemented in Phase 3.
