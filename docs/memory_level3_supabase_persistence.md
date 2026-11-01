# EarthMind Memory Module: Level 3 — Supabase PostgreSQL Persistence

## 1. Overview & Architecture

Level 3 of the EarthMind Memory Module implements persistent, provider-independent storage using Supabase PostgreSQL (PostgreSQL 15+ compatible). It builds directly upon:
- **Level 1**: Foundation & Contracts (`MemoryRecord`, `IMemoryStorageAdapter`, 17 approved fields, UTC timestamp policy).
- **Level 2**: Memory Domains & Security (`MemoryService`, `MemorySecurityEnforcer`, fail-closed domain and scope boundaries).

### Locked Architectural Boundaries
1. **Underlying Technology**: PostgreSQL.
2. **Provider Independence**: Supabase PostgreSQL access is kept strictly behind the `IMemoryStorageAdapter` protocol (`SupabasePostgresMemoryStorageAdapter`). Memory core business logic contains zero Supabase SDK dependencies.
3. **Authentication Boundary**: **Supabase Auth is strictly NOT used**. Identity and authorization are passed as trusted `AuthorizationContext` supplied by EarthMind's identity boundary.
4. **Physical Database Ownership**: Connection pooling and physical query execution are owned by the Database Module (`modules/database/postgres_db.py`), while memory semantics, record serialization, and query composition are owned by the Memory Module.

---

## 2. PostgreSQL Schema & Field Mapping

The schema is defined in `data/database/migrations/001_create_memory_records.sql` and maps all 17 approved fields:

| Field | PostgreSQL Column | Data Type | Constraints / Policy |
| :--- | :--- | :--- | :--- |
| `record_id` | `record_id` | `VARCHAR(64)` | `PRIMARY KEY` |
| `domain` | `domain` | `VARCHAR(32)` | `NOT NULL`, `CHECK (domain IN ('USER', 'GENERAL'))` |
| `record_type` | `record_type` | `VARCHAR(64)` | `NOT NULL` |
| `owner_id` | `owner_id` | `VARCHAR(128)` | Mandatory for `USER`, `NULL` for `GENERAL` |
| `scope_type` | `scope_type` | `VARCHAR(32)` | `NOT NULL`, `CHECK (scope_type IN ('USER', 'CONVERSATION', 'FARM', 'FIELD', 'CROP_CYCLE', 'GENERAL'))` |
| `scope_id` | `scope_id` | `VARCHAR(128)` | `NOT NULL` |
| `payload` | `payload` | `JSONB` | `NOT NULL` (arbitrary structured JSON) |
| `source` | `source` | `VARCHAR(128)` | `NOT NULL` |
| `created_at` | `created_at` | `TIMESTAMPTZ` | `NOT NULL` (UTC) |
| `updated_at` | `updated_at` | `TIMESTAMPTZ` | `NOT NULL` (UTC) |
| `schema_version` | `schema_version` | `VARCHAR(32)` | `NOT NULL DEFAULT '1.0'` |
| `record_version` | `record_version` | `INT` | `NOT NULL DEFAULT 1`, `CHECK (record_version >= 1)` |
| `status` | `status` | `VARCHAR(32)` | `NOT NULL DEFAULT 'ACTIVE'`, `CHECK (status IN ('ACTIVE', 'ARCHIVED', 'DELETED', 'EXPIRED', 'PENDING'))` |
| `retention_policy_id` | `retention_policy_id`| `VARCHAR(64)` | Optional policy tag |
| `expires_at` | `expires_at` | `TIMESTAMPTZ` | Optional UTC expiration, `CHECK (expires_at > created_at)` |
| `classification` | `classification` | `VARCHAR(64)` | `NOT NULL` |
| `correlation_id` | `correlation_id` | `VARCHAR(128)` | Traceability ID |

### Database Constraints
- **Domain & Ownership Integrity (`chk_memory_domain_ownership`)**:
  ```sql
  CHECK (
      (domain = 'USER' AND owner_id IS NOT NULL AND TRIM(owner_id) != '' AND scope_type != 'GENERAL')
      OR
      (domain = 'GENERAL' AND owner_id IS NULL AND scope_type != 'USER')
  )
  ```
- **Optimistic Locking Version (`chk_memory_record_version`)**: `CHECK (record_version >= 1)`.
- **Expiration Validity (`chk_memory_expiration`)**: `CHECK (expires_at IS NULL OR expires_at > created_at)`.

### Indexes
1. `idx_memory_records_owner_domain` on `(owner_id, domain) WHERE status != 'DELETED'`
2. `idx_memory_records_scope` on `(scope_type, scope_id)`
3. `idx_memory_records_record_type` on `(record_type)`
4. `idx_memory_records_status` on `(status)`
5. `idx_memory_records_correlation_id` on `(correlation_id) WHERE correlation_id IS NOT NULL`
6. `idx_memory_records_expires_at` on `(expires_at) WHERE expires_at IS NOT NULL`

---

## 3. Storage Adapter Architecture

The `SupabasePostgresMemoryStorageAdapter` (`modules/memory/supabase_adapter.py`) implements `IMemoryStorageAdapter`:

1. **`store_record(record: MemoryRecord) -> MemoryRecord`**:
   - Executes parameterized `INSERT ... RETURNING *`.
   - On duplicate `record_id`, catches PostgreSQL unique violation (code `23505`) and raises `MemoryConflictError`.
   - Validates UTC datetimes.

2. **`get_record(record_id: str) -> Optional[MemoryRecord]`**:
   - Parameterized query `SELECT * FROM memory_records WHERE record_id = %s;`.
   - Reconstructs validated `MemoryRecord` model.

3. **`search_records(criteria: MemorySearchCriteria) -> List[MemoryRecord]`**:
   - Dynamically builds parameterized query clauses across domain, owner_id, scope_type, scope_id, record_type, status, classification, correlation_id, and non-expired records.
   - Applies deterministic `ORDER BY created_at DESC LIMIT %s OFFSET %s`.

4. **`update_record(record: MemoryRecord, expected_version: Optional[int]) -> MemoryRecord`**:
   - Checks existing record version in database.
   - If `expected_version` is provided and does not match the stored version, raises `MemoryConflictError`.
   - Executes atomic `UPDATE ... WHERE record_id = %s AND record_version = %s RETURNING *;`.
   - If row is modified concurrently, detects 0 rows updated and raises `MemoryConflictError`.

5. **`delete_record(record_id: str, soft: bool = True) -> bool`**:
   - Soft delete sets `status = 'DELETED'` and updates `updated_at`.
   - Hard delete performs `DELETE FROM memory_records WHERE record_id = %s;`.

6. **`get_record_metadata(record_id: str) -> Optional[Dict[str, Any]]`**:
   - Fast projection query omitting the JSONB `payload` to protect memory buffers and prevent accidental sensitive data retrieval.

7. **`check_health() -> StorageHealthResult`**:
   - Executes `SELECT 1;` and counts table rows, returning latency and operational state.

---

## 4. Connection Configuration & Safe Environment Setup

Configuration is managed via `PostgresConfig` in `core/config/settings.py`.

### Supported Environment Variables
```bash
# Connection URI (recommended for Supabase)
export EARTHMIND_DATABASE_URL="postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres"

# Or discrete connection parameters:
export EARTHMIND_POSTGRES_HOST="127.0.0.1"
export EARTHMIND_POSTGRES_PORT="5432"
export EARTHMIND_POSTGRES_USER="postgres"
export EARTHMIND_POSTGRES_PASSWORD="[YOUR-PASSWORD]"
export EARTHMIND_POSTGRES_DB="postgres"
export EARTHMIND_POSTGRES_SSLMODE="require"

# Timeouts & Pooling
export EARTHMIND_POSTGRES_CONNECT_TIMEOUT="10.0"
export EARTHMIND_POSTGRES_STATEMENT_TIMEOUT_MS="30000"
export EARTHMIND_POSTGRES_MIN_POOL="1"
export EARTHMIND_POSTGRES_MAX_POOL="10"
```

### Credential Protection
- `to_safe_dict()` automatically redacts `password` and masks the URI in `url` (e.g., `postgresql://postgres:***@localhost:5432/postgres`).
- Exception handling in `_handle_db_exception` redacts strings containing `password`, `token`, `secret`, or `key`.

---

## 5. Security Boundaries & Preservation of Level 2

1. **No Supabase Auth**: The storage adapter does not interact with Supabase Auth or client JWTs.
2. **Context Enforced at Service Layer**: `MemoryService` wraps `SupabasePostgresMemoryStorageAdapter` with `MemorySecurityEnforcer`.
3. **Cross-User Protection**: A farmer cannot read, update, delete, or search another farmer's records.
4. **General Memory Governance**: Only authorized principals (system/curator) can store or modify General Memory records; normal users are denied fail-closed.
5. **Anti-Promotion Protection**: Private user records cannot be updated to domain `GENERAL`.
6. **Defense in Depth**: In addition to application layer security checks, PostgreSQL check constraint `chk_memory_domain_ownership` ensures that no corrupted or unowned `USER` records can ever be committed to disk.

---

## 6. Test Results

All test suites were executed against live PostgreSQL 16:
- `tests/test_memory_level1_foundation.py`: 14 passed.
- `tests/test_memory_level2_domains_security.py`: 24 passed.
- `tests/test_memory_level3_postgres.py`: 10 passed.
- **Total Memory Module Tests**: 48 passed, 0 failed.
- Regression suites (`test_production_configuration.py`, `test_database.py`, `test_schemas.py`): 18 passed.
