# C.2 — Knowledge Base: Metadata, Provenance, and Source Assessment

**System:** EarthMind (`Earth-Mind.01`)
**Phase:** Phase B — Storage Foundation
**Step:** Step 6 — Metadata + Provenance + Source Assessment
**Status:** COMPLETE & DOCUMENTED

---

## 1. Executive Summary

This document specifies the Metadata, Provenance, and Source Assessment architecture for the EarthMind **C.2 Knowledge Base**.

Step 6 builds directly on the Step 5 Canonical Knowledge Data Model (`Source`, `Artifact`, `Document`, `DocumentVersion`, `Section`, `KnowledgeUnit`, `Chunk`), making every canonical knowledge object describable, traceable, assessable, and auditable before dense/sparse embeddings, indexing, and retrieval are introduced.

This implementation remains strictly storage-provider independent and contains zero direct dependencies on SQLite, PostgreSQL, Qdrant, vector databases, embedding SDKs, web search clients, or cloud providers.

---

## 2. Core Components

### 2.1 Metadata Model (`CanonicalMetadata`)

`CanonicalMetadata` provides a canonical, extensible metadata structure attached to canonical knowledge entities. It structures metadata across six functional dimensions:

1. **Identity**: `object_id`, `object_type`, `source_id`, `document_id`, `version_id`
2. **Content**: `content_type`, `language`, `domain`, `topic`, `crop`, `region`, `season`, `subject_category`
3. **Temporal**: `relevant_timestamp`, `effective_from`, `effective_until`
4. **Retrieval / Filtering**: `retrieval_tags`, `search_terms`, `filterable_attributes`
5. **Quality**: `quality_status` (`QualityStatus`), `completeness`, `processing_status` (`ProcessingStatus`), `review_status` (`ReviewStatus`)
6. **Access**: `access_policy` (`AccessPolicy`), `visibility` (`Visibility`)
7. **Extensibility**: `extra_metadata` dictionary enabling future key-value extensions without altering schema definitions.

> **Architectural Boundary**: Metadata provides descriptive, temporal, quality, and access attributes. Metadata is NOT responsible for reasoning or retrieval decisions.

### 2.2 Provenance Model (`Provenance`)

`Provenance` represents the explicit origin and processing chain of knowledge objects:

$$\text{Source} \rightarrow \text{Artifact} \rightarrow \text{Document} \rightarrow \text{DocumentVersion} \rightarrow \text{Processing Pipeline} \rightarrow \text{Chunking Operation} \rightarrow \text{Representation Provider} \rightarrow \text{Timestamp}$$

Key features:
- **Traceability**: Retains references to `source_id`, `artifact_id`, `document_id`, `version_id`, `section_id`, `knowledge_unit_id`, and `chunk_id`.
- **Explicit Incomplete Handling**: Never silently fabricates missing upstream references. If expected ancestor IDs are absent, `is_complete` is set to `False` and missing attributes are explicitly recorded in `missing_fields`.
- **Representation Replacement**: Supports `update_representation_provider(...)`, allowing future vector embedding models or representation providers to be replaced while preserving canonical source provenance.

### 2.3 Source Assessment Model (`SourceAssessment`)

`SourceAssessment` stores structured metadata assessment signals associated with knowledge sources and evidence.

Fields include:
- **Assessment Scores**: `authority`, `reliability`, `recency`, `domain_relevance`, `geographic_relevance` (all bounded in $[0.0, 1.0]$)
- **Categorization & Context**: `review_status`, `evidence_type`, `assessment_basis`, `assessed_by`, `created_at`, `updated_at`

> **CORE ARCHITECTURAL RULE**:
>
> **Source Assessment is an assessment signal, not a truth judgment.**
>
> The assessment layer does NOT:
> - declare information scientifically true or false
> - perform agricultural reasoning
> - make recommendations
> - replace B3 Reasoning Engine
> - automatically decide which evidence wins in conflicts
>
> It strictly stores structured assessment signals about the source or evidence.

---

## 3. Attachment Strategy & Lineage Preservation

Metadata, Provenance, and SourceAssessment integrate cleanly with canonical Step 5 entities (`Source`, `Artifact`, `Document`, `DocumentVersion`, `Section`, `KnowledgeUnit`, `Chunk`).

```
Chunk
  └──► KnowledgeUnit
         └──► Section
                └──► DocumentVersion
                       └──► Document
                              └──► Source
                                     ├── CanonicalMetadata
                                     ├── Provenance
                                     └── SourceAssessment
```

Every entity carries or references:
- `metadata`: `Union[CanonicalMetadata, Dict[str, Any]]`
- `provenance`: `Optional[Provenance]`
- `assessment`: `Optional[SourceAssessment]` (applicable to `Source`, `Document`, `KnowledgeUnit`)

Traceability is verified using `validate_canonical_lineage()`, ensuring cross-entity lineage remains unbroken.

---

## 4. Validation Rules

1. **Metadata Structure**: `validate_metadata_structure()` ensures metadata is non-None and strictly formatted as a `CanonicalMetadata` or valid `dict`.
2. **Temporal Ordering**: Enforces `effective_until >= effective_from`.
3. **Score Range Boundaries**: `validate_source_assessment()` enforces that all assessment signal scores fall within $[0.0, 1.0]$.
4. **Provenance Chain**: `validate_provenance_chain()` verifies provenance model integrity and entity identifier matching.
5. **No Silent Fabrication**: Missing lineage references trigger `is_complete = False` and populate `missing_fields`.

---

## 5. Scope Boundaries

| Included in Step 6 | Strictly Excluded (Future Steps) |
| :--- | :--- |
| Extensible Metadata Schema | Embeddings & Vector Databases (Qdrant) |
| Provenance Chain & Audit Trail | Dense & Sparse Retrieval |
| Source Assessment Signal Model | Chunking Algorithms & Ingestion Pipelines |
| Storage-Independent Enums & Validators | B2 Context Manager & B3 Reasoning |
| Representation Replacement Mechanism | Agricultural Reasoning & Recommendations |

---

## 6. Relationship to Future Steps

- **Step 7 (Lifecycle Engine)**: Will transition `quality_status`, `processing_status`, and `review_status` enums through automated lifecycle state machines.
- **Step 8+ (Embeddings & Indexing)**: Will populate `representation_provider` in `Provenance` and utilize `retrieval_tags` and `filterable_attributes` from `CanonicalMetadata` for vector filtering without altering canonical models.
