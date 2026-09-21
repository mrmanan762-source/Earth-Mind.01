# C.2 — Knowledge Base Storage Strategy & Environment Setup

**System:** EarthMind (`Earth-Mind.01`)
**Phase:** Phase B — Storage Foundation
**Step:** Step 3 — Storage Strategy & Environment Setup
**Status:** IMPLEMENTED & DOCUMENTED

---

## 1. Overview & Strategy

This document specifies the storage strategy, storage boundaries, and environment setup for **C.2 — Knowledge Base** in EarthMind (`Earth-Mind.01`).

The storage foundation establishes three distinct storage boundaries:
1. **Canonical Structured Knowledge Records**: Stored in relational persistence via the EarthMind Database Module (`DatabaseInterface`).
2. **Raw Source Artifacts**: Stored via a replaceable artifact storage interface (`IArtifactStorage`) using local filesystem (`LocalArtifactStorage`) for the prototype.
3. **Derived Retrieval Index**: Managed via a placeholder index boundary (`IKnowledgeIndex`) where physical vector engines (such as Qdrant) are deferred to future phases.

---

## 2. Source of Truth Rule

**Canonical Knowledge Base Records are the sole authoritative source of truth.**

```
Canonical Records (Database) ──► Index Builder ──► Retrieval Index (Vector DB)
       ▲                                                 │
       │ (Sole Source of Truth)                          ▼
       └────────────────────────────────── (Rebuildable / Derived)
```

- **Rule**: The retrieval index is a derived, rebuildable data structure generated from canonical records.
- **Rule**: The retrieval index (vector store) must **never** become the authoritative source of truth.
- **Rule**: C.2 architecture must never query the vector database as the primary store for knowledge records.

---

## 3. Storage Boundaries & Interfaces

### A. Database Boundary (Canonical Records)
- **Interface**: `IKnowledgeRecordRepository` (`modules/knowledge_base/storage/interfaces.py`).
- **Implementation**: `CanonicalKnowledgeRepository` (`modules/knowledge_base/storage/canonical_repository.py`).
- **Underlying Engine**: EarthMind Database Module (`core/interfaces/module.py` `DatabaseInterface` → `SQLiteDatabaseService`).
- **Isolation**: C.2 contains **zero** direct imports of SQLite connection objects, cursor objects, or driver-specific handles. All SQL queries are executed cleanly through `db_service.execute()`, `fetch_one()`, and `fetch_all()`.

### B. Raw Artifact Storage
- **Interface**: `IArtifactStorage` (`core/interfaces/storage.py`).
- **Implementation**: `LocalArtifactStorage` (`modules/knowledge_base/storage/local_artifact_storage.py`).
- **Storage Layout**: Raw binary/text artifact content is stored alongside separate JSON metadata (`{artifact_id}.bin` and `{artifact_id}.meta.json`).
- **Replaceability**: The `IArtifactStorage` contract supports replacing the local filesystem backend with S3/cloud object storage in the future without changing C.2 domain logic.

### C. Derived Retrieval Index Boundary
- **Interface**: `IKnowledgeIndex` (`core/interfaces/storage.py`).
- **Implementation**: `KnowledgeIndexPlaceholder` (`modules/knowledge_base/storage/index_placeholder.py`).
- **Deferral**: Physical vector databases (e.g. Qdrant) are intentionally deferred in Step 3. No vector collections or external cloud resources are created.

---

## 4. Storage Types Distinction

| Storage Type | Boundary | Authority Level | Prototype Backend | Future Backend |
|---|---|---|---|---|
| **Canonical Structured Records** | Database Module | **Authoritative (Source of Truth)** | SQLite (`earthmind.db`) via `DatabaseInterface` | PostgreSQL / Cloud SQL |
| **Raw Source Artifacts** | Artifact Storage | **Immutable Primary Origin** | Local Filesystem (`data/artifacts/raw/`) | AWS S3 / Cloud Object Store |
| **Derived Retrieval Index Data** | Knowledge Index | **Derived & Rebuildable** | `KnowledgeIndexPlaceholder` | Qdrant / Vector Engine |

Canonical records managed by `CanonicalKnowledgeRepository` include:
- `Source`
- `SourceArtifact` metadata
- `Document`
- `DocumentVersion`
- `Section`
- `KnowledgeUnit`
- `Chunk`
- `Metadata`
- `Provenance`
- `SourceAssessment`
- `EmbeddingRecord`
- `IndexRecord`
- `KnowledgeCollection`
- `ProcessingRecord`

---

## 5. Environment & Configuration Foundation

Configuration is centralized in `core/config/settings.py` within `KnowledgeBaseStorageSettings`:

```python
class KnowledgeBaseStorageSettings(BaseModel):
    kb_raw_artifact_dir: str = os.getenv("EARTHMIND_KB_RAW_ARTIFACT_DIR", "data/artifacts/raw")
    kb_storage_backend: str = os.getenv("EARTHMIND_KB_STORAGE_BACKEND", "local_filesystem")
    kb_index_backend: str = os.getenv("EARTHMIND_KB_INDEX_BACKEND", "placeholder")
    kb_db_path: str = os.getenv("EARTHMIND_KB_DB_PATH", os.getenv("EARTHMIND_DB_PATH", "earthmind.db"))
```

### Environment Overrides
- `EARTHMIND_KB_RAW_ARTIFACT_DIR`: Path to raw artifact storage directory.
- `EARTHMIND_KB_STORAGE_BACKEND`: Selected artifact storage provider (`local_filesystem`).
- `EARTHMIND_KB_INDEX_BACKEND`: Selected index provider (`placeholder`).
- `EARTHMIND_KB_DB_PATH`: Database file path or connect string.

### Local Development Directory Layout
```
data/
  ├── artifacts/
  │   └── raw/              # Local raw artifact content (.bin & .meta.json)
  ├── raw/                  # Ingestion temp directory
  └── processed/            # Staging directory for extraction
```

### `.gitignore` Protection
`data/raw/`, `data/artifacts/`, `data/processed/`, and `*.db` are protected by `.gitignore` to prevent committing local generated runtime artifacts.

---

## 6. EarthMind Five Principles Compliance

1. **Extensibility / Rubber-Band Principle**: Artifact storage and index engines are defined via Python `Protocol` interfaces, enabling seamless replacement.
2. **Loose Coupling**: C.2 communicates with Database Module via generic `DatabaseInterface` and with storage via `IArtifactStorage`.
3. **Single Responsibility**: `LocalArtifactStorage` handles filesystem I/O, `CanonicalKnowledgeRepository` handles structured record SQL operations, `KnowledgeIndexPlaceholder` manages index registration status.
4. **Controlled Dependencies**: Strict interface boundaries prevent direct dependencies on SQLite internals, cloud SDKs, or vector DB clients.
5. **Replaceability + Evolution**: Database and filesystem prototype backends can be swapped for PostgreSQL and Cloud Object Storage without changing downstream C.2 contracts.

---

## 7. Error Safety

- Storage failures raise explicit, structured exceptions (`StorageError`, `ArtifactNotFoundError`, `RecordNotFoundError`, `StorageConfigurationError`).
- Missing artifact directories are created automatically on initialization in local filesystem mode.
- Storage operations do not silently fall back between storage backends or swallow I/O exceptions.

---
*C.2 Storage Strategy & Environment Setup documented and verified.*
