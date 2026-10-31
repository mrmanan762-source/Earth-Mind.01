# EarthMind Memory Module — Level 1 Foundation & Contracts

## 1. Executive Summary

This document specifies the foundational contracts, record models, storage abstractions, and architectural compatibility boundaries for the EarthMind Memory Module as defined in the **EarthMind Memory Module Architecture Specification v1.0**.

The Memory Module provides structured, persistent, and verifiable memory representation for farmer, farm, field, and shared non-user-specific agricultural knowledge without performing autonomous AI reasoning, context assembly, or authentication authority.

---

## 2. Repository & Architecture Compatibility Audit (Phase A)

### 2.1 Existing Interfaces Discovered
- **`core/interfaces/services.py: MemoryInterface`**: Legacy service contract exposing `store_memory(key: str, value: Any) -> bool` and `retrieve_memory(key: str) -> Optional[Any]`.
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
