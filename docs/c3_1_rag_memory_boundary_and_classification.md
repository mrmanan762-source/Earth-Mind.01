# C.3.1 — RAG–Memory Boundary Contracts & Data Classification

## 1. Executive Overview

This document specifies the executable architectural boundary contract and data classification layer between **RAG** (Retrieval-Augmented Generation) and **Memory** within EarthMind (Earth-Mind.01).

### The Fundamental Rule
- **RAG answers**: *"What do we know about the world?"*
- **Memory answers**: *"What do we know about this farmer, farm, field, and their history?"*

Content topic alone does NOT determine subsystem ownership. Ownership decisions incorporate origin, scope, persistence intent, entity subject, lifecycle, intended use, privacy, and provenance chain.

---

## 2. Architecture & Data Flow

Communication between RAG and Memory follows strict interface-only access through B2 Context Manager without direct cross-subsystem coupling:

```
+-------------------------------------------------------------------+
|                        B2 Context Manager                         |
+-------------------------------------------------------------------+
           |                                         |
           v                                         v
+-----------------------+                 +-------------------------+
| IRAGContextProvider   |                 | IMemoryContextProvider  |
+-----------------------+                 +-------------------------+
           |                                         |
           v                                         v
+-----------------------+                 +-------------------------+
|   RAG Subsystem       |                 |    Memory Subsystem     |
| (General / Curated /  |                 | (Farmer / Farm / Field  |
|  External Knowledge)  |                 |  History & Context)     |
+-----------------------+                 +-------------------------+
```

### Direct Dependency Prohibitions
- **NO** direct imports or calls: `RAG -> Memory` or `Memory -> RAG`.
- Neither subsystem may access the other's database, index (Qdrant), repository, internal classes, or provider implementation.

---

## 3. Data Classification Model

The provider-independent classification model defines five primary dimensions:

### 3.1 Knowledge Classification (`KnowledgeClassification`)
- `GENERAL_KNOWLEDGE`: Universal agricultural, agronomic, scientific, or regulatory information.
- `FARMER_KNOWLEDGE`: Farmer-specific attributes, preferences, interactions, and identity.
- `FIELD_KNOWLEDGE`: Spatial, soil, crop-cycle, and field-specific historical data.
- `SESSION_CONTEXT`: Active interaction state and temporal runtime conversation variables.
- `OBSERVATION`: Sensor, drone, satellite, or user field observations captured at a point in time.
- `EXTERNAL_CURRENT_DATA`: Live external service evidence (weather forecasts, market prices, current web evidence).

### 3.2 Context Source Type (`ContextSourceType`)
- `RAG`: RAG retrieval engine / Knowledge Base.
- `MEMORY`: Memory retrieval service / persistent memory store.
- `SESSION`: Active runtime session manager.
- `OBSERVATION`: Observation pipeline / sensor ingestion.
- `EXTERNAL_SERVICE`: Live third-party API / Web Search adapter.

### 3.3 Context Ownership (`ContextOwnership`)
- `RAG_OWNED`: Lifecycle and meaning owned by C.2 Knowledge Base / RAG pipeline.
- `MEMORY_OWNED`: Lifecycle and meaning owned by Memory subsystem.
- `RUNTIME_OWNED`: Ephemeral lifecycle owned by B2 Context Manager or active runtime session.
- `EXTERNAL_OWNED`: Owned by external provider / current third-party service.

### 3.4 Context Scope (`ContextScope`)
- `GLOBAL`: Universal applicability across all domains and users.
- `REGIONAL`: Applicable within a specific geographical or agro-climatic region.
- `FARMER`: Bound to a specific farmer entity (`farmer_id`).
- `FARM`: Bound to a specific farm property (`farm_id`).
- `FIELD`: Bound to a specific agricultural plot (`field_id`).
- `CROP_CYCLE`: Bound to a specific seasonal crop cycle (`crop_cycle_id`).
- `SESSION`: Bound to an active session (`session_id`).
- `EVENT`: Bound to a discrete event instance.

### 3.5 Persistence Intent (`PersistenceIntent`)
- `TEMPORARY`: Non-persistent, single-request lifespan.
- `SESSION_SCOPED`: Persists only for the duration of the active session.
- `PERSISTENT`: Long-term persistent store intent.

---

## 4. Boundary Contracts

### 4.1 RAG Context Contract (`RAGContextContract`)
Executable contract for general/curated/external knowledge returned by RAG context providers:
- `source_type`: `RAG` or `EXTERNAL_SERVICE`
- `ownership`: `RAG_OWNED` or `EXTERNAL_OWNED`
- `classification`: `GENERAL_KNOWLEDGE` or `EXTERNAL_CURRENT_DATA`
- `scope`: `GLOBAL` or `REGIONAL`
- `persistence_intent`: `PERSISTENT` or `TEMPORARY`/`SESSION_SCOPED`
- `publication_state`: Must be `"PUBLISHED"` for general RAG knowledge.
- Preserves C.2 lineage: `collection_id`, `document_id`, `document_version_id`, `knowledge_unit_id`, `chunk_id`, `evidence_metadata`, `retrieval_metadata`, and `provenance`.
- **Constraint**: RAG contracts MUST NOT contain farmer-private scopes (`FARMER`, `FARM`, `FIELD`, `CROP_CYCLE`) or private farmer Memory.

### 4.2 Memory Context Contract (`MemoryContextContract`)
Executable contract for farmer/farm/field specific context returned by Memory context providers:
- `memory_id`: Unique memory record identifier.
- `source_type`: `MEMORY`, `SESSION`, or `OBSERVATION`
- `ownership`: `MEMORY_OWNED` or `RUNTIME_OWNED`
- `classification`: `FARMER_KNOWLEDGE`, `FIELD_KNOWLEDGE`, `SESSION_CONTEXT`, or `OBSERVATION`
- `scope`: `FARMER`, `FARM`, `FIELD`, `CROP_CYCLE`, `SESSION`, or `EVENT`
- `persistence_intent`: `PERSISTENT`, `SESSION_SCOPED`, or `TEMPORARY`
- `privacy_level`: `FARM_PRIVATE` or `FARMER_PII`
- `is_pii`: Boolean flag indicating PII presence.
- Preserves scope entity references (`farmer_id`, `farm_id`, `field_id`, `crop_cycle_id`, `session_id`), `lifecycle_status`, `relevance_score`, and `provenance`.
- **Constraint**: Memory contracts MUST NOT be classified as `GLOBAL` or `REGIONAL` general RAG knowledge.

---

## 5. B2 Integration & Compatibility

B2 Context Manager integrates boundary contracts without flattening them into anonymous text. `ContextItem` schema (`modules/context/schemas.py`) provides:

1. **Boundary Fields**: Optional `source_type`, `ownership`, `classification`, `scope`, `persistence_intent`, and `boundary_metadata`.
2. **Factory Constructors**:
   - `ContextItem.from_rag_contract(rag_contract)`
   - `ContextItem.from_memory_contract(memory_contract)`
3. **Conversion**: `context_item.to_boundary_record()` returns a `ContextSourceRecord` for machine-readable verification.

---

## 6. Validation & Promotion Rules

The `BoundaryValidator` (`modules/context/boundary/validator.py`) enforces strict rules and raises explicit exceptions (`BoundaryValidationError`, `PromotionNotAllowedError`, `ScopeViolationBoundaryError`, `PrivacyBoundaryError`):

1. **Cross-Domain Promotion Block**:
   - `RAG -> Memory` = NOT ALLOWED
   - `Memory -> RAG` = NOT ALLOWED
   - Automatic cross-domain promotion raises `PromotionNotAllowedError`.

2. **Web Search / External Current Evidence Rule**:
   - Web search evidence (`EXTERNAL_CURRENT_DATA`) remains classified as current external evidence (`EXTERNAL_OWNED`, `TEMPORARY`/`SESSION_SCOPED`).
   - Must NOT automatically become permanent RAG knowledge (`RAG_OWNED`, `PERSISTENT`, `PUBLISHED`) without formal ingestion and publication.
   - Must NOT automatically become `MEMORY_OWNED`.

3. **Observation Persistence Rule**:
   - Observations (`OBSERVATION`) are runtime-owned and temporary by default.
   - Must NOT automatically become persistent Memory (`MEMORY_OWNED`, `PERSISTENT`) without explicit Memory policy approval.

4. **Privacy Metadata Requirement**:
   - Scope in `FARMER`, `FARM`, `FIELD`, `CROP_CYCLE` or classification in `FARMER_KNOWLEDGE`, `FIELD_KNOWLEDGE` requires non-null `privacy_level`.

---

## 7. Five EarthMind Principles Adherence

1. **Extensibility / Rubber-Band Principle**: Data classification enums and contracts allow new domain categories and metadata without restructuring RAG or Memory.
2. **Loose Coupling**: RAG and Memory remain entirely independent subsystems.
3. **Single Responsibility**: C.3 defines classification and boundary semantics; RAG owns knowledge; Memory owns personal history; B2 owns context assembly.
4. **Controlled Dependencies**: Communication occurs strictly via approved interfaces (`IRAGContextProvider`, `IMemoryContextProvider`, `IBoundaryValidator`).
5. **Replaceability & Evolution**: RAG and Memory implementations can evolve or be replaced independently without breaking boundary contracts.
