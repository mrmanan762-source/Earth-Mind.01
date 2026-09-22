# C.2 — Knowledge Base: Versioning and Lifecycle

**System:** EarthMind (`Earth-Mind.01`)
**Phase:** Phase B — Storage Foundation
**Step:** Step 7 — Versioning & Lifecycle
**Status:** COMPLETE & DOCUMENTED

---

## 1. Executive Summary

This document specifies the canonical versioning and lifecycle system for the EarthMind **C.2 Knowledge Base**.

Step 7 builds directly on Step 5 Canonical Knowledge Data Models (`Document`, `DocumentVersion`) and Step 6 Metadata, Provenance, and Source Assessment structures. It provides explicit document version lineage, controlled state machine transitions, publication rule enforcement, version supersession, retirement, failure/rejection handling, and historical auditability without dependencies on storage engines or retrieval SDKs.

---

## 2. Versioning Model & Lineage

### 2.1 Identity Stability
A logical `Document` retains a stable `document_id` across all revisions over time. Updating or revising knowledge content creates new `DocumentVersion` records with distinct `version_id` values.

```
Document A (doc_soil_01)
 ├── Version 1.0 (ver_soil_1.0) -> SUPERSEDED
 └── Version 2.0 (ver_soil_2.0) -> ACTIVE / PUBLISHED (parent_version_id: ver_soil_1.0)
```

### 2.2 Unbroken Lineage & Immutability
Each child version explicitly references its parent (`parent_version_id`). Historical version records are immutable and are never silently overwritten, mutated, or deleted.

---

## 3. Lifecycle States & Transition Architecture

The system clearly distinguishes between **Document Version Status** (`DocumentVersionStatus`) and **Processing/Publication Lifecycle State** (`KnowledgeLifecycleState`).

### 3.1 Lifecycle State Diagram

```
                 RECEIVED
                    │
                    ▼
               PROCESSING ──────► FAILED / INVALID / REJECTED
                    │
                    ▼
               PROCESSED  ──────► FAILED / INVALID / REJECTED
                    │
                    ▼
                EMBEDDED  ──────► FAILED / INVALID / REJECTED
                    │
                    ▼
                 INDEXED  ──────► FAILED / INVALID / REJECTED
                    │
                    ▼
              PENDING_REVIEW ───► REJECTED / INVALID
                    │
                    ▼
                PUBLISHED
                 │     │
                 │     └──► RETIRED
                 │
                 └──► SUPERSEDED
```

### 3.2 Controlled State Machine Rules

State transitions are governed by `KnowledgeLifecycleEngine`:

| Previous State | Allowed Target States |
| :--- | :--- |
| `RECEIVED` | `PROCESSING`, `FAILED`, `INVALID` |
| `PROCESSING` | `PROCESSED`, `FAILED`, `REJECTED`, `INVALID` |
| `PROCESSED` | `EMBEDDED`, `FAILED`, `REJECTED`, `INVALID` |
| `EMBEDDED` | `INDEXED`, `FAILED`, `REJECTED`, `INVALID` |
| `INDEXED` | `PENDING_REVIEW`, `FAILED`, `REJECTED`, `INVALID` |
| `PENDING_REVIEW` | `PUBLISHED`, `REJECTED`, `INVALID` |
| `PUBLISHED` | `SUPERSEDED`, `RETIRED`, `INVALID` |
| `FAILED` | `RECEIVED`, `PROCESSING`, `INVALID` |
| `REJECTED` | `PENDING_REVIEW`, `PROCESSING`, `INVALID` |
| `SUPERSEDED` | `RETIRED`, `INVALID` |
| `RETIRED` | `INVALID` |

Illegal transitions (e.g., `RECEIVED` $\rightarrow$ `PUBLISHED` or `FAILED` $\rightarrow$ `PUBLISHED`) raise `InvalidLifecycleTransitionError`.

---

## 4. Publication Rule

**Knowledge objects do NOT automatically become published or retrievable merely because processing succeeded.**

A knowledge object must explicitly transition through review (`PENDING_REVIEW` $\rightarrow$ `PUBLISHED`). Processing steps (`PROCESSED`, `EMBEDDED`, `INDEXED`) are mandatory prerequisites, but publication requires an explicit state machine approval event.

---

## 5. Version Supersession, Retirement, & Failure Handling

### 5.1 Supersession
When a new version replaces an existing active version (`supersede_version`):
1. Old version transitions to `SUPERSEDED` (`DocumentVersionStatus.SUPERSEDED`).
2. New version references `parent_version_id` and transitions to `PUBLISHED` (`DocumentVersionStatus.ACTIVE`).
3. Historical version identity, content, metadata, provenance, and source assessment remain completely intact without physical deletion.

### 5.2 Retirement
When knowledge is retired (`retire_version`), its status becomes `RETIRED`. It is removed from active usage while remaining preserved in canonical records for audit and historical lineage.

### 5.3 Failure & Rejection
Failed (`FAILED`) or rejected (`REJECTED`) versions transition to `DocumentVersionStatus.INVALID` with explicit reasons recorded in auditable `LifecycleTransitionRecord` instances and `Provenance` step logs.

---

## 6. Integration & Storage Independence

- **Step 6 Integration**: Lifecycle state transitions record auditable steps in `Provenance` without destroying `CanonicalMetadata` or `SourceAssessment`.
- **Storage Independence**: Built strictly as storage-independent Pydantic domain models and state machine logic. Zero dependencies on SQLite, PostgreSQL, Qdrant, or embedding SDKs.
- **Scope Boundaries**: Strictly excludes retrieval execution, vector searching, chunking execution, or AI reasoning.
