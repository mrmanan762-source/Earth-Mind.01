# EarthMind Memory Module: Level 4 — Memory Operations & Lifecycle

## 1. Overview & Architectural Role

Level 4 of the EarthMind Memory Module implements comprehensive **Memory Operations and Record Lifecycle Management** as specified by the **EarthMind Memory Module Architecture Specification v1.0**.

It integrates and expands upon:
- **Level 1 (Foundation & Contracts)**: The canonical 17-field `MemoryRecord`, `IMemoryStorageAdapter`, fail-closed `AuthorizationContext`, `PayloadSchemaRegistry`, and UTC timestamp invariants.
- **Level 2 (Memory Domains & Security)**: Logical domain separation (`USER` vs `GENERAL`), user ownership enforcement, scope boundary validation, General Memory governance, and zero-payload audit logging.
- **Level 3 (Supabase PostgreSQL Persistence)**: High-performance, provider-independent persistent storage backed by PostgreSQL 15+ without introducing Supabase Auth or direct database exposure.

### Locked Architectural Boundaries
1. **Zero Vector/Semantic Search**: Structured retrieval relies purely on exact criteria matching, typed metadata filtering, bounded pagination, and deterministic sorting. No pgvector, embeddings, or semantic index is introduced.
2. **Provider Independence**: Operations, lifecycle management, and validation remain decoupled from physical storage technology behind `IMemoryStorageAdapter`.
3. **Fail-Closed Security**: Every memory operation mandates a trusted `AuthorizationContext`. Role names such as `admin` or `system` cannot bypass user ownership without explicit delegation.

---

## 2. Completed Memory API Operations

The unified `MemoryService` in `modules/memory/memory_service.py` provides the full suite of approved Level 4 operations:

| API Method | Alias | Description | Error Handling |
| :--- | :--- | :--- | :--- |
| `store_record(context, record)` | `store(context, record)` | Validates record schemas, enforces authorization, applies retention policies, and inserts new record. | Raises `MemoryConflictError` if ID exists, `MemoryInvalidRecordSchemaError` if payload fails validation. |
| `get_record(context, record_id)` | `retrieve(context, record_id)` | Retrieves record by immutable ID, verifying user ownership / scope permissions before data return. | Raises `MemoryNotFoundError` if missing, `MemoryForbiddenError` on cross-user attempt. |
| `search_records(context, criteria)` | `search(context, criteria)` | Executes structured multi-parameter search bound strictly to authorized owner and scopes. | Enforces query limits and pagination; strips unauthorized results via secondary filtering. |
| `update_record(context, record, expected_version)` | `update(context, record, expected_version)` | Enforces immutable identity fields, validates updated payload schema, checks optimistic lock, increments version. | Raises `MemoryConflictError` on version mismatch, `MemoryForbiddenError` on tampered identity fields. |
| `delete_record(context, record_id, soft)` | `delete(context, record_id, soft)` | Executes authorized soft deletion (`status = DELETED`) or hard removal under governance. | Idempotent; returns `False` if record does not exist. |
| `get_record_metadata(context, record_id)` | `get_metadata(context, record_id)` | Retrieves lightweight record metadata projection omitting payload to protect buffers. | Raises `MemoryNotFoundError` if missing, enforces owner authorization. |
| `check_health()` | `health_check()` | Verifies storage availability and operational metrics. | Returns `StorageHealthResult(is_healthy=...)` without leaking credentials. |

---

## 3. Structured Retrieval & Filtering

Implemented in `modules/memory/memory_retriever.py` (`StructuredMemoryRetriever`):

- **Query Parameters (`MemorySearchCriteria`)**:
  - `domain`: `USER` or `GENERAL`.
  - `owner_id`: Required / automatically injected for `USER` queries.
  - `scope_type` and `scope_id`: Exact logical scope filtering.
  - `record_type`: Typed domain classification filter.
  - `status`: Default filter `status = ACTIVE` (excluding `DELETED` and `EXPIRED` unless requested).
  - `include_expired`: Boolean flag defaulting to `False`.
  - `retention_policy_id`: Filter by applied retention policy.
  - `correlation_id`: Traceability filtering.
- **Deterministic Sorting**:
  - Primary sort keys supported: `created_at`, `updated_at`, `record_id`.
  - Order: `ASC` or `DESC`.
  - Secondary tie-breaker: `record_id ASC` ensuring deterministic page boundaries across identical timestamps.
- **Bounded Pagination**:
  - `limit`: Validated with constraint `1 <= limit <= 1000` (default 50).
  - `offset`: Non-negative integer offset.

---

## 4. Record-Type Validation (`PayloadSchemaRegistry`)

Implemented in `core/schemas/memory.py` and enforced via `modules/memory/memory_validator.py` (`MemoryRecordValidator`):
- Registrable schema validators via `PayloadSchemaRegistry.register_schema(record_type, validator_or_model)`.
- Validates payload dictionaries during `MemoryRecord` model creation and updates.
- Controlled via `PayloadSchemaRegistry.set_allow_unregistered(bool)`:
  - If unregistered types are disallowed, unapproved record types are rejected fail-closed with `MemoryInvalidRecordSchemaError`.
- Separated cleanly from agricultural advice synthesis and business logic.

---

## 5. Versioning & Concurrency Control

- **Immutable Identity Fields**:
  - `record_id`, `domain`, `owner_id`, and `scope_type` cannot be modified after initial creation. Attempting to alter them raises `MemoryForbiddenError`.
- **Version Progression**:
  - Stored records start at `record_version = 1`.
  - Updates increment `record_version` monotonically.
  - Timestamps are maintained in UTC: `updated_at` is set to `datetime.now(timezone.utc)`.
- **Optimistic Concurrency**:
  - The caller can specify `expected_version: Optional[int]`.
  - If the database/in-memory version does not match `expected_version`, `MemoryConflictError` is raised immediately. Silent overwrites are prevented.

---

## 6. Retention Policy & Lifecycle Management

Implemented in `modules/memory/memory_lifecycle.py` (`MemoryLifecycleManager`):

### 6.1 Lifecycle Stages
1. **Creation**: Initial validation, schema verification, and assignment of `retention_policy_id`.
2. **Active State**: `status = ACTIVE`.
3. **Version Progression**: Monotonically increasing version on authorized updates.
4. **Expiry Identification**: Records exceeding `expires_at` are automatically identified via `identify_expired_records()`.
5. **Retention Enforcement**: `enforce_retention()` transitions expired records to `status = EXPIRED`.
6. **Logical Deletion**: `delete(soft=True)` sets `status = DELETED` and increments version; excluded from normal search.
7. **Physical Purge**: `purge_records(criteria)` physically deletes eligible records permanently.
8. **Deletion Verification**: `verify_deletion(record_id)` accurately distinguishes `LOGICALLY_DELETED` vs `PHYSICALLY_PURGED`.

### 6.2 Pre-Configured Retention Policies
- `pol_transient_session`: `TRANSIENT_SESSION`, TTL 24 hours (86,400s), auto-purgeable.
- `pol_seasonal_crop`: `OPERATIONAL_SEASONAL`, TTL 180 days (~6 months), allows extensions on update.
- `pol_permanent_farm`: `LONG_TERM_FARM`, permanent profile records, no TTL.
- `pol_general_advisory`: `GENERAL_REGULATORY`, TTL 365 days (1 year), governed General Memory.

---

## 7. Test Verification & Results

Level 4 implementation and regression testing were executed with 100% pass rate:

```bash
python -m pytest tests/test_memory*.py
============================== 68 passed in 0.78s ==============================
```

### Breakdown of Executed Test Suites:
1. `tests/test_memory_level1_foundation.py` (14 tests passed):
   - Record validation, UTC timestamps, domain invariants, storage adapter protocol.
2. `tests/test_memory_level2_domains_security.py` (24 tests passed):
   - Ownership isolation, scope boundaries, anti-promotion protection, audit logging.
3. `tests/test_memory_level3_postgres.py` (10 tests passed):
   - Live PostgreSQL 16 persistence, table migrations, connection pooling, SQL constraints.
4. `tests/test_memory_level4_operations_lifecycle.py` (20 tests passed):
   - Full CRUD API operations and aliases (`store`, `retrieve`, `update`, `delete`, `metadata`, `health`).
   - Structured search, pagination, deterministic sorting, empty queries.
   - Optimistic concurrency, version increments, stale update conflict detection, immutable identity enforcement.
   - Retention policy registration, expiry calculation, retention enforcement.
   - Soft deletion vs physical purge, deletion verification.
   - Real PostgreSQL 16 integration testing of complete Level 4 lifecycle operations.

---

## 8. Deferred Scope & Known Boundaries

- **Level 5 Work Deferred**: Integration with external orchestration or automated agricultural advice pipelines is strictly out of scope for Level 4.
- **No Vector Search**: Semantic search and vector retrieval remain exclusive to canonical RAG pipelines and are not part of the Memory Module.
