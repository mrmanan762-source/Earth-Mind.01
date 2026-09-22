# C.2 — Canonical Knowledge Data Model

**System:** EarthMind (`Earth-Mind.01`)
**Phase:** Phase B — Storage Foundation
**Step:** Step 5 — Canonical Knowledge Data Model
**Status:** COMPLETE & DOCUMENTED

---

## 1. Executive Summary

This document specifies the canonical domain data model for the EarthMind **C.2 Knowledge Base**.

The canonical domain model serves as the authoritative source of truth for all domain knowledge within EarthMind. All downstream representations—including metadata attributes, provenance records, dense/sparse embeddings, search index positions, candidate retrieval packages, and publication state records—are derived strictly from this canonical foundation.

The model is strictly **storage-provider independent** and contains zero direct dependencies on physical SQL engines (e.g. SQLite), vector databases (e.g. Qdrant), embedding provider SDKs, or web search clients.

---

## 2. Canonical Knowledge Hierarchy

The canonical data model establishes an unbroken, traceable 7-layer hierarchy:

```
SOURCE
  │
  ├──► ARTIFACT
  │
  └──► DOCUMENT
         │
         └──► DOCUMENT VERSION
                │
                ├──► SECTION (Hierarchical structure)
                │      │
                │      └──► SUBSECTION (Level N)
                │
                └──► KNOWLEDGE UNIT (Atomic semantic unit)
                       │
                       └──► CHUNK (Granular retrieval unit)
```

---

## 3. Core Objects & Purpose

### 3.1 Source
- **Concept**: Represents the logical origin or provider of agricultural domain knowledge (e.g., FAO extension services, university research departments, government agricultural departments, weather services).
- **Key Attributes**: `source_id`, `source_name`, `source_type`, `organization`, `origin`, `language`, `region`, `status`, `created_at`, `updated_at`, `metadata`.
- **Ownership & Identity**: Independently identifiable from individual artifacts or documents. A single `Source` may originate multiple raw `Artifact`s and canonical `Document`s.

### 3.2 Artifact (Source Artifact)
- **Concept**: Represents original or raw source material associated with a `Source` (e.g., raw PDF files, downloaded HTML pages, JSON feeds, satellite raster metadata files).
- **Key Attributes**: `artifact_id`, `source_id`, `location_reference`, `content_type`, `checksum`, `size_bytes`, `ingestion_time`, `version_info`, `status`, `metadata`.
- **Separation Principle**: Raw content binaries and physical storage handles are kept separate from domain records. Raw content is persisted via storage abstractions (`IArtifactStorage`), referencing only storage keys or URIs in `location_reference`.

### 3.3 Document
- **Concept**: Represents the stable logical identity of a domain knowledge document across multiple revisions and updates over time.
- **Key Attributes**: `document_id`, `source_id`, `title`, `document_type`, `content_type`, `language`, `region`, `status`, `created_at`, `updated_at`, `metadata`.
- **Identity Stability**: Updating or re-ingesting a document does NOT create a new `document_id`. The logical `Document` identity remains stable while version increments create new `DocumentVersion` records.

### 3.4 DocumentVersion
- **Concept**: Represents a specific point-in-time version of a `Document`.
- **Key Attributes**: `version_id`, `document_id`, `parent_version_id`, `version_number`, `created_at`, `effective_from`, `effective_until`, `change_type`, `change_summary`, `status`, `metadata`.
- **Version Statuses**: `ACTIVE`, `SUPERSEDED`, `RETIRED`, `INVALID`, `PENDING_REVIEW`.
- **Lineage**: Maintains explicit reference to `parent_version_id` to preserve full revision history as agricultural science and regulations evolve.

### 3.5 Section
- **Concept**: Represents structural sections and sub-sections within a `DocumentVersion` (e.g., chapters, headings, sub-headings).
- **Key Attributes**: `section_id`, `document_id`, `version_id`, `parent_section_id`, `title`, `sequence`, `level`, `content_reference`, `metadata`.
- **Hierarchy Support**: Supports arbitrary nesting depth (`Document → Section → Subsection → Sub-subsection`). Documents are not flattened prematurely, and un-structured documents are not forced to define artificial sections.

### 3.6 KnowledgeUnit
- **Concept**: Represents an atomic, semantically self-contained logical unit of domain knowledge extracted from a document section.
- **Key Attributes**: `knowledge_unit_id`, `document_id`, `version_id`, `section_id`, `content_type`, `content`, `sequence`, `created_at`, `status`, `metadata`.
- **Multimodal Support**: Content types include `TEXT`, `TABLE`, `IMAGE`, `FIGURE`, `STRUCTURED_DATA`, and `MULTIMODAL`. Structured data (tables, JSON schemas) and media references (image URIs, figure captions) are preserved without forcing all knowledge into plain text.

### 3.7 Chunk
- **Concept**: Represents granular units derived from a `KnowledgeUnit` or document structure specifically formatted for downstream search indexing and dense/sparse vector embedding.
- **Key Attributes**: `chunk_id`, `knowledge_unit_id`, `document_id`, `version_id`, `parent_section_id`, `sequence`, `content`, `content_type`, `language`, `size_bytes`, `token_count`, `status`, `metadata`.
- **Relationship Preservation**: Every chunk retains direct references back to its parent `knowledge_unit_id`, `parent_section_id`, `version_id`, `document_id`, and `source_id`.

---

## 4. Architectural Rules & Constraints

### 4.1 Source of Truth Rule
The canonical objects defined in Step 5 (`Source`, `Artifact`, `Document`, `DocumentVersion`, `Section`, `KnowledgeUnit`, `Chunk`) are the single source of truth. Vector database collections (e.g., Qdrant) and search indices are derived artifacts and must **never** be treated as canonical records.

```
Canonical Knowledge Objects (Source of Truth)
        │
        ▼
Metadata & Provenance
        │
        ▼
Embeddings & Vector Representations
        │
        ▼
Search Indexes & Vector Collections
        │
        ▼
Retrieval & Candidate Packaging
```

### 4.2 Storage Independence Rule
Canonical entities are defined as Pydantic domain models using standard Python primitives (`str`, `int`, `datetime`, `dict`, `list`, `Enum`). They have zero direct dependencies on SQLite, Qdrant, ORM classes, embedding provider SDKs, or cloud services.

### 4.3 Identity & Lineage Traceability
Every entity includes stable ID attributes (`source_id`, `artifact_id`, `document_id`, `version_id`, `section_id`, `knowledge_unit_id`, `chunk_id`). The full unbroken lineage (`Chunk → KnowledgeUnit → Section → DocumentVersion → Document → Source`) is verified using `validate_canonical_lineage()`.

---

## 5. Future Extension Points

The canonical data model is designed to support future evolution without breaking existing interface contracts:

1. **Multimodal Payload Expansion**: `KnowledgeUnit` and `Chunk` payloads accept structured dicts, enabling seamless future addition of audio transcripts, drone raster layers, or satellite band arrays.
2. **Pluggable Vector Provider Identifiers**: Embedding and index metadata will attach to `Chunk` records without altering `Chunk` domain definition.
3. **Lifecycle Engine Integration**: Step 7 will introduce automated publication workflows that transition canonical record `status` enums through controlled state machines.
