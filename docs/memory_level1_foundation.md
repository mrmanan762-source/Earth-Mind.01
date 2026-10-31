# EarthMind Memory Module — Level 1 Foundation & Contracts

## 1. Executive Summary

This document specifies the foundational contracts, record models, storage abstractions, authorization protocols, payload validation mechanisms, and architectural compatibility boundaries for the EarthMind Memory Module as defined in the **EarthMind Memory Module Architecture Specification v1.0**.

The Memory Module provides structured, persistent, and verifiable memory representation for farmer, farm, field, and shared non-user-specific agricultural knowledge without performing autonomous AI reasoning, context assembly, or authentication authority.

---

## 2. Repository & Architecture Compatibility Audit (Phase A)

### 2.1 Existing Interfaces Discovered
- **`core/interfaces/services.py: MemoryInterface`**: Legacy service contract exposing `store_memory(key: str, value: Any) -> bool` and `retrieve_memory(key: str) -> Optional[Any]`. Made `@runtime_checkable` for clean protocol validation without modifying signature.
- **`modules/memory/memory_module.py: MemoryModule`**: Implementation of `MemoryInterface` and `ModuleInterface` currently registered in `app/main.py` and tested in `tests/test_modules.py`.
- **`core/interfaces/boundary.py: IMemoryContextProvider`**: High-level protocol for returning `MemoryContextContract` objects to the B2 Context Manager.
- **`modules/context/boundary/models.py: MemoryContextContract` & `MemoryContextRequest`**: Executable boundary contracts used across B2, C.3.1, C.3.2, and C.3.3.
- **`modules/context/boundary/adapters.py: MemoryContextProviderAdapter`**: Bridges `IMemoryContextProvider` to B2 `ContextProvider`.
- **`modules/context/boundary/enums.py`**: Canonical boundary enums (`KnowledgeClassification`, `ContextScope`, `ContextOwnership`, `PersistenceIntent`, `PrivacyLevel`).
- **`core/interfaces/module.py: DatabaseInterface`**: Prototype database abstraction with `connect()`, `disconnect()`, `execute()`, `fetch_all()`, `fetch_one()`.

### 2.2 Compatibility Decisions & Reuse Strategy
1. **Preserve Legacy Functionality**:
   - `MemoryInterface` and `MemoryModule` remain intact and functional with no breaking changes to `store_memory()` or `retrieve_memory()`.
   - Existing integration points in `app/main.py` and `tests/test_modules.py` continue to work seamlessly.
2. **Reuse Existing Boundary Models**:
   - Existing C.3 boundary enums (`KnowledgeClassification`, `PrivacyLevel`) are directly integrated into Level 1 memory schemas to ensure zero divergence across subsystems.
   - `MemoryContextContract` compatibility is maintained with explicit mapping methods (`MemoryRecord.to_context_contract()` and `MemoryRecord.from_context_contract()`).
3. **Architectural Boundaries**:
   - **User Memory vs. General Memory**: Supported as two distinct logical domains (`USER` vs `GENERAL`).
   - `USER` records mandate an immutable `owner_id`.
   - `GENERAL` records strictly prohibit `owner_id` (must be `None`), ensuring shared records never inherit user ownership.
   - **Zero AI Reasoning**: Memory Module never performs AI generation or agricultural advice synthesis.
   - **Authentication Decoupling**: Separate `AuthorizationContext` is defined; Memory does not implement auth or Supabase Auth.
   - **Provider Independence**: Storage contract `IMemoryStorageAdapter` is fully decoupled from underlying physical databases (e.g. Supabase, PostgreSQL, SQLite).

---

## 3. Core Memory Contracts & Record Models (Phase B)

### 3.1 All 17 Approved Record Fields
Every `MemoryRecord` (`core/schemas/memory.py`) contains all 17 approved fields:
1. `record_id`: Unique immutable record identifier (e.g. `mem_...`).
2. `domain`: Logical domain (`USER` or `GENERAL`).
3. `record_type`: Non-empty domain-specific classification.
4. `owner_id`: Owner identity; required for `USER`, must be `None` for `GENERAL`.
5. `scope_type`: Logical scope (`USER`, `CONVERSATION`, `FARM`, `FIELD`, `CROP_CYCLE`, `GENERAL`).
6. `scope_id`: Non-empty specific identifier for the assigned scope.
7. `payload`: Structured dictionary validated against `PayloadSchemaRegistry`.
8. `source`: Provenance producer or input origin.
9. `created_at`: Timezone-aware UTC datetime.
10. `updated_at`: Timezone-aware UTC datetime.
11. `schema_version`: Version string of payload structure (default `"1.0"`).
12. `record_version`: Positive integer (`>= 1`) for optimistic concurrency control.
13. `status`: Lifecycle status (`ACTIVE`, `ARCHIVED`, `DELETED`, `EXPIRED`, `PENDING`).
14. `retention_policy_id`: Optional policy identifier.
15. `expires_at`: Optional timezone-aware UTC datetime (must be strictly greater than `created_at`).
16. `classification`: C.3 classification (`KnowledgeClassification.FARMER_KNOWLEDGE`, etc.).
17. `correlation_id`: Optional system traceability correlation ID.

### 3.2 Authorization Context & Security Contract
`AuthorizationContext` (`core/schemas/memory.py`):
- Encapsulates `principal_id`, `principal_type` (`USER`, `SERVICE`, `SYSTEM`, `ANONYMOUS`), `roles`, `owner_id`, `accessible_scopes`, `allowed_operations`, `requested_operation`, and `policy_context`.
- **Fail-Closed Security**: Rejects unauthenticated principals (e.g. `ANONYMOUS`).
- **No Blind Privilege Escalation**: Role named `"admin"` or `"system"` alone does not bypass permissions without explicit allowed operations.
- **Cross-User Protection**: Prohibits User A from accessing User B's records.
- **Distinction**: Clearly distinguishes between unauthenticated (`UNAUTHORIZED`) and unauthorized access (`FORBIDDEN`).

### 3.3 Payload Schema Registry
`PayloadSchemaRegistry` (`core/schemas/memory.py`):
- Provides an extensible registry for validating record payloads using Pydantic models or validation functions.
- Supports configurable policy for unregistered types (`set_allow_unregistered(bool)`).
- Raises `ValueError` detailing the schema failure when payload validation fails.

### 3.4 Error Contracts
Specialized exception hierarchy defined in `core/errors/exceptions.py` and re-exported in `modules/memory/errors.py`:
- `MemoryError` (Base class inheriting from `EarthMindException`)
- `MemoryInvalidArgumentError` (`INVALID_ARGUMENT`)
- `MemoryInvalidRecordSchemaError` (`INVALID_RECORD_SCHEMA`)
- `MemoryUnauthorizedError` (`UNAUTHORIZED`)
- `MemoryForbiddenError` (`FORBIDDEN`)
- `MemoryNotFoundError` (`NOT_FOUND`)
- `MemoryConflictError` (`CONFLICT`)
- `MemoryStorageUnavailableError` (`STORAGE_UNAVAILABLE`)
- `MemoryStorageError` (`STORAGE_ERROR`)
- `MemoryRetentionPolicyViolationError` (`RETENTION_POLICY_VIOLATION`)
- `MemoryIntegrityError` (`INTEGRITY_ERROR`)
- `MemoryInternalError` (`INTERNAL_ERROR`)

---

## 4. Storage Adapter Abstraction (Phase C)

### 4.1 `IMemoryStorageAdapter` Protocol
Defined in `core/interfaces/memory_storage.py` and exported in `core/interfaces/__init__.py`:
- `store_record(record: MemoryRecord) -> MemoryRecord`: Stores record; raises `MemoryConflictError` on duplicate.
- `get_record(record_id: str) -> Optional[MemoryRecord]`: Retrieves record; returns None if missing.
- `search_records(criteria: MemorySearchCriteria) -> List[MemoryRecord]`: Structured filtering, deterministic ordering, and pagination.
- `update_record(record: MemoryRecord, expected_version: Optional[int] = None) -> MemoryRecord`: Optimistic concurrency check rejecting stale versions.
- `delete_record(record_id: str, soft: bool = True) -> bool`: Soft delete (marks DELETED and increments version) or hard delete.
- `get_record_metadata(record_id: str) -> Optional[Dict[str, Any]]`: Fast metadata retrieval without full payload.
- `check_health() -> StorageHealthResult`: Health check reporting operational readiness.

### 4.2 Reference In-Memory Storage Adapter
`InMemoryMemoryStorageAdapter` (`modules/memory/storage_adapter.py`):
- Deep-copies records on storage and retrieval to enforce complete object isolation.
- Enforces strict optimistic concurrency control: updates require `record_version > existing.record_version` and check `expected_version` when specified.
- Implements deterministic sorting by `(created_at DESC, record_id ASC)` with offset and limit pagination.
- Provides explicit failure simulation (`simulate_unavailable=True`) for deterministic error testing without silent fallbacks.

---

## 5. Context Manager & C.3 Compatibility

Bidirectional conversion between `MemoryRecord` and `MemoryContextContract`:
- `MemoryRecord.to_context_contract()`: Maps all 6 scopes (`USER` -> `FARMER`, `CONVERSATION` -> `SESSION`, `FARM` -> `FARM`, `FIELD` -> `FIELD`, `CROP_CYCLE` -> `CROP_CYCLE`, `GENERAL` -> `GLOBAL`) and maps scope IDs to corresponding entity references (`farmer_id`, `farm_id`, `field_id`, `crop_cycle_id`, `session_id`).
- `MemoryRecord.from_context_contract()`: Maps C.3 context contracts back into `MemoryRecord` instances.
- **Ownership Integrity**: Strictly rejects USER record conversion if `farmer_id` is missing; never fabricates dummy owner identities.

---

## 6. Level 2 Readiness

Level 1 establishes the complete foundation, contracts, and in-memory reference implementation. It is fully ready for Level 2 (User Memory and General Memory operational domains, access-control policies, and indexing interfaces).
