# EarthMind Memory Module — Level 2 Memory Domains & Security

## 1. Executive Summary

This document specifies the architecture, implementation, security governance, and validation of **Level 2: Memory Domains & Security** of the EarthMind Memory Module as defined in the **EarthMind Memory Module Architecture Specification v1.0**.

Level 2 establishes strict logical separation between **User Memory** and **General Memory**, comprehensive user ownership enforcement, scope boundary enforcement across all approved memory scopes, centralized fail-closed security decision making, and auditability without sensitive data exposure.

---

## 2. Logical Domain Separation

The Memory Module provides two distinct logical domains:

### 2.1 User Memory (`USER`)
- **Purpose**: Stores private, user-specific records.
- **Allowed Scopes**:
  - `USER`: Farmer-level preferences, identity, and personal metadata.
  - `CONVERSATION`: Session-bound dialog memory.
  - `FARM`: Farm boundaries, acreage, and farm profiles.
  - `FIELD`: Plot/field characteristics, soil test data, and geolocation.
  - `CROP_CYCLE`: Seasonal sowing, fertilization, scouting, and harvesting records.
- **Ownership Invariant**: Mandatory non-empty `owner_id`.
- **Scope Restriction**: Cannot be assigned scope `GENERAL`.
- **Access Boundary**: Accessible strictly to the verified owner or explicitly delegated principals.

### 2.2 General Memory (`GENERAL`)
- **Purpose**: Stores approved shared records that are outside the canonical C.2 Knowledge Base.
- **Allowed Scopes**:
  - `GENERAL`: Regional calendars, agromet advisories, and shared agricultural guidelines.
- **Ownership Invariant**: Mandatory `owner_id is None`. Cannot have an owner.
- **Scope Restriction**: Cannot be assigned scopes `USER`, `CONVERSATION`, `FARM`, `FIELD`, or `CROP_CYCLE`.
- **Anti-Promotion Rule**: Private User Memory records can **never** be automatically promoted, copied, or stored into General Memory.

---

## 3. Security & Governance Architecture

### 3.1 Centralized Security Enforcement (`MemorySecurityEnforcer`)
Centralized in `modules/memory/security.py`, all access requests across CRUD and Search paths pass through a single, fail-closed enforcement engine:
- Evaluates trusted `AuthorizationContext` (supplied by external identity boundary).
- Missing, empty, or unauthenticated contexts immediately fail closed with `MemoryUnauthorizedError`.
- Unknown scopes or incompatible domain/scope combinations fail closed with `MemoryInvalidArgumentError`.
- Cross-user access attempts fail closed with `MemoryForbiddenError`.

### 3.2 User Ownership Enforcement
- Record IDs, scope IDs, or client-supplied metadata **never** establish authorization on their own.
- Access requires that `context.principal_id == record.owner_id` or `context.owner_id == record.owner_id` (or explicitly enumerated in `context.policy_context["authorized_owners"]`).
- Cross-user access attempts are immediately blocked and logged as `CROSS_USER_ATTEMPT`.
- Principle of least privilege is strictly enforced: `admin` or `system` roles do not grant blanket bypass to private farmer data without explicit delegation claims.

### 3.3 Scope-Aware Access Enforcement
- Valid ownership does not automatically grant access to all scopes.
- For `USER` scope: `scope_id` must match `owner_id` or `principal_id`.
- For `CONVERSATION`, `FARM`, `FIELD`, `CROP_CYCLE`: `scope_id` must exist in `context.accessible_scopes[scope_type]`.
- Attempts to supply arbitrary client scope IDs without corresponding trusted claims fail closed with `MemoryForbiddenError`.

### 3.4 General Memory Governance
- General Memory writes (`CREATE`, `UPDATE`, `DELETE`) require explicit governance permissions:
  - Role matching approved governance roles (`curator`, `knowledge_admin`, `general_memory_manager`), OR
  - Explicit policy context claim (`policy_context["allow_general_write"] == True`).
- Ordinary user operations attempting to modify General Memory are denied with `MemoryForbiddenError` and logged as `UNAUTHORIZED_GENERAL_WRITE`.
- General Memory reads are permitted for authenticated subjects under governed policy.

---

## 4. Security Auditability (`MemorySecurityAuditor`)

Security audit logging is handled by `MemorySecurityAuditor` emitting structured `MemorySecurityAuditEvent` objects:
- **Audit Actions**:
  - `ACCESS_ALLOWED`: Authorized memory operations.
  - `ACCESS_DENIED`: Unauthorized or forbidden attempts.
  - `CROSS_USER_ATTEMPT`: Prohibited cross-user data access attempts.
  - `INVALID_DOMAIN_SCOPE`: Invalid domain/scope combinations.
  - `UNAUTHORIZED_GENERAL_WRITE`: Unprivileged modification attempts on shared records.
  - `INVALID_OR_MISSING_AUTH_CONTEXT`: Calls with missing/malformed auth context.
  - `PRIVATE_TO_GENERAL_PROMOTION_BLOCKED`: Attempts to promote or store private records into General Memory.
- **Privacy & Safety Guarantee**:
  - Record payloads, credentials, tokens, secrets, and private values are **strictly omitted/redacted**.
  - Events only track correlation metadata: `event_id`, `timestamp`, `action`, `decision`, `principal_id`, `domain`, `scope_type`, `scope_id`, `record_id`, `operation`, and `reason`.

---

## 5. Secure Domain Service Layer (`MemoryService`)

Implemented in `modules/memory/memory_service.py`:
- `store_record(context, record)`: Governed record creation with domain, scope, and ownership checks.
- `get_record(context, record_id)`: Governed retrieval enforcing fail-closed auth before data exposure.
- `search_records(context, criteria)`: Scoped searches bound strictly to authenticated owner and allowed scopes. Secondary filtering prevents data leakage.
- `update_record(context, record, expected_version)`: Prevents record tampering, ownership re-assignment, or domain mutation, with optimistic locking.
- `delete_record(context, record_id, soft)`: Governed soft or hard deletion.
- `get_record_metadata(context, record_id)`: Safe metadata retrieval without payload exposure, subject to authorization.

---

## 6. Verification and Test Results

Level 2 implementation was validated against a 24-test comprehensive suite in `tests/test_memory_level2_domains_security.py` alongside all existing Level 1 and boundary tests:

```bash
python3 -m pytest tests/test_memory_level1_foundation.py tests/test_memory_level2_domains_security.py tests/test_rag_memory_boundary.py tests/test_rag_memory_integration.py tests/test_c3_end_to_end_validation.py tests/test_cross_domain_governance.py tests/test_modules.py
============================= 129 passed in 1.56s ==============================
```

### Test Coverage Highlights:
1. `test_01` – `test_04`: Domain separation (USER vs GENERAL, invalid combinations, anti-promotion).
2. `test_05` – `test_09`: User ownership enforcement, cross-user denial, immutable ownership, missing/empty context handling.
3. `test_10` – `test_13`: Scope enforcement across USER, CONVERSATION, FARM, FIELD, CROP_CYCLE, and GENERAL.
4. `test_14` – `test_18`: General Memory governance, curator/role policies, ordinary user write rejection, anti-promotion protection.
5. `test_19` – `test_21`: Operation-level enforcement across store, retrieve, search, update, delete, and metadata access.
6. `test_22` – `test_24`: No blanket admin bypass, zero payload leakage in audit logs, and optimistic locking concurrency.

---

## 7. Deferred Items & Boundaries

- **Level 3 Scope (Storage Engines & Persistence)**: Physical Supabase/PostgreSQL adapters, database migration scripts, connection pooling, and SQL indexing will be introduced in Level 3.
- **Zero Vector/RAG Duplication**: General Memory does not perform vector search, semantic embeddings, or replace canonical RAG Knowledge Base.
