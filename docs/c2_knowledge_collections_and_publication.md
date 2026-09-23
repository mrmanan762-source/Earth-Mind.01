# C.2 Step 12 — Knowledge Collections & Publication Layer Architecture

**System:** EarthMind (Earth-Mind.01)
**Module:** C.2 — Knowledge Base
**Component:** Logical Knowledge Collections & Publication Layer
**Status:** IMPLEMENTED & VERIFIED

---

## 1. Executive Summary

Step 12 implements the logical **Knowledge Collection** system and explicit **Knowledge Publication** workflow for EarthMind's C.2 Knowledge Base.

It establishes the controlled progression from canonical knowledge to retrievable index records:

```
Canonical Knowledge (Source, Document, Version, Chunk)
        ↓
Knowledge Collection Assignment (Logical Grouping)
        ↓
Publication Validation (PublicationEligibilityValidator)
        ↓
Publication State Transition (KnowledgePublicationEngine)
        ↓
Index Layer Synchronization (IKnowledgeIndexAdapter)
        ↓
Retrievable Knowledge (RAG Query Pipeline Eligible)
```

---

## 2. Core Architectural Rules

1. **Canonical Source of Truth**: Canonical Knowledge entities (`Source`, `Document`, `DocumentVersion`, `KnowledgeUnit`, `Chunk`) remain the single source of truth. Collections, embeddings, sparse representations, and index records are strictly derived/logical artifacts.
2. **PROCESSED ≠ PUBLISHED, EMBEDDED ≠ PUBLISHED, INDEXED ≠ PUBLISHED**: Knowledge does NOT become retrievable merely because processing, embedding, or indexing succeeded, or because it was assigned to a collection. Publication requires explicit eligibility evaluation and state transition.
3. **Logical Collections ≠ Physical Vector Collections**: A logical Knowledge Collection is a domain grouping (e.g. "Crops", "Soil") and does NOT equal a physical Qdrant vector collection.
4. **Strict Retrievability Rule**: Knowledge is retrievable by the normal RAG query pipeline ONLY if its publication status is `PUBLISHED`, its lifecycle state is `PUBLISHED`, and its index representation is verified available.
5. **Web Search Non-Publication Rule**: Live web search results are temporary current query evidence and CANNOT be automatically published into permanent Knowledge Collections without explicit review and validation.
6. **Provider Isolation**: The publication layer interacts with vector databases exclusively via the Step 11 `IKnowledgeIndexAdapter` / `KnowledgeIndexEngine` interface. No direct imports or dependencies on `qdrant_client` exist in the collection or publication layers.

---

## 3. Logical Knowledge Collection Layer

### 3.1 Responsibilities
- Defining logical domain knowledge collections.
- Assigning canonical objects (`DOCUMENT`, `DOCUMENT_VERSION`, `KNOWLEDGE_UNIT`, `CHUNK`) to collections.
- Managing collection metadata (domain, language scope, region scope, visibility, access policy).
- Supporting single and multiple collection membership for a knowledge object.
- Managing collection lifecycle states (`ACTIVE`, `INACTIVE`, `ARCHIVED`, `DEPRECATED`).
- Supporting text, table, figure, and multimodal content types.

### 3.2 Domain Models (`modules/knowledge_base/collections/models.py`)
- **`CollectionType`**: Enum containing `AGRICULTURE_GENERAL`, `CROPS`, `SOIL`, `DISEASES`, `GOVERNMENT_GUIDELINES`, `RESEARCH`, `REGIONAL_KNOWLEDGE`, `MULTIMODAL_KNOWLEDGE`, `CUSTOM`.
- **`CollectionStatus`**: Enum containing `ACTIVE`, `INACTIVE`, `ARCHIVED`, `DEPRECATED`.
- **`KnowledgeCollection`**: Model describing a logical collection with `collection_id`, `collection_name`, `description`, `collection_type`, `domain`, `language_scope`, `region_scope`, `status`, `visibility`, `access_policy`, `metadata`, `created_at`, `updated_at`, `version`, `traceability`.
- **`CollectionMembership`**: Model representing assignment of a canonical object to a collection with `membership_id`, `collection_id`, `knowledge_object_type`, `knowledge_object_id`, `document_id`, `version_id`, `status`, `created_at`, `updated_at`, `metadata`, `traceability`.

### 3.3 Collection Management Engine (`KnowledgeCollectionEngine`)
Implemented in `modules/knowledge_base/collections/engine.py`:
- `create_collection(...)`: Registers logical collections with non-empty name validation and duplicate checks.
- `update_collection(...)` / `update_collection_status(...)`: Manages collection metadata and lifecycle status independently from publication state.
- `assign_membership(...)`: Connects canonical objects to collections without duplicating canonical knowledge. Validates target collection is `ACTIVE`.
- `get_memberships_for_object(...)` / `get_memberships_for_collection(...)`: Enables querying collection membership from either object or collection perspective.

---

## 4. Knowledge Publication Layer

### 4.1 Publication Eligibility Validation (`PublicationEligibilityValidator`)
Implemented in `modules/knowledge_base/publication/validator.py`. Validates prerequisites:
1. Canonical knowledge object / identity exists.
2. Source lineage exists (`source_id`, `document_id`, `version_id`).
3. Provenance chain exists and `is_complete == True`.
4. Metadata exists and is valid.
5. Source assessment exists where explicitly required.
6. Processing and chunking completed successfully.
7. Vector and/or sparse representations required by index are available.
8. Lifecycle state permits publication (`PROCESSED`, `EMBEDDED`, `INDEXED`, `PENDING_REVIEW`, `PUBLISHED`).
9. Object lifecycle state is NOT `FAILED`, `REJECTED`, `INVALID`, `SUPERSEDED`, or `RETIRED`.
10. Web search results satisfy explicit review approval if `is_web_result == True`.
11. Object is not explicitly blocked from publication.

### 4.2 Publication States (`PublicationStatus`)
- `PUBLISHED`: Prerequisites satisfied, publication recorded, index verified and available.
- `PUBLISHED_INDEX_UNAVAILABLE`: Publication approved canonically, but vector index adapter is currently offline/unavailable.
- `PENDING_INDEX`: Publication approved, awaiting index generation.
- `PENDING_REVIEW`: Awaiting manual or expert review.
- `REJECTED`: Publication rejected due to failed eligibility or quality checks.
- `FAILED`: Publication attempt failed due to system/validation errors.
- `REVOKED`: Previously published knowledge revoked.
- `SUPERSEDED`: Replaced by a newer document version.

### 4.3 Publication Engine (`KnowledgePublicationEngine`)
Implemented in `modules/knowledge_base/publication/engine.py`:
- `evaluate_eligibility(...)`: Evaluates publication eligibility prerequisites.
- `publish_knowledge(...)`: Executes publication workflow, coordinates with `KnowledgeCollectionEngine` for membership, syncs with `KnowledgeIndexEngine`, logs an auditable `PublicationRecord`, and transitions lifecycle state.
- `supersede_version(...)`: Transitions previous version to `SUPERSEDED` state while preserving historical lineage, provenance, and publication history without physical deletion.
- `revoke_publication(...)`: Revokes publication status for a knowledge object.
- `get_publication_history(...)`: Retrieves complete publication audit log for an object.
- `is_retrievable(...)`: Enforces the core retrievability check for RAG query pipelines.

---

## 5. Version Supersession

When a new version (`v2.0`) of a document becomes published:
- `v1.0` is transitioned to `KnowledgeLifecycleState.SUPERSEDED` and `PublicationStatus.SUPERSEDED`.
- `v1.0` identity, provenance, and publication history are preserved in full.
- `v1.0` is excluded from current retrievable search results unless historical retrieval is explicitly requested by policy.
- No historical knowledge is physically destroyed upon supersession.

---

## 6. Collection & Publication Independence

- A Knowledge Collection can exist empty.
- A knowledge object can be assigned to a collection before being published (e.g. while in `DRAFT` or `PROCESSED` state).
- A knowledge object can be published into multiple logical collections simultaneously.
- Updating collection status (e.g. archiving a collection) does not erase canonical publication records.

---

## 7. Explicitly Out-of-Scope (Deferred to Later RAG Steps)

The following capabilities belong to subsequent RAG steps and are intentionally NOT implemented in this step:
- Online query execution and vector/sparse retrieval execution.
- Retrieval router and search strategy selection.
- Dense and sparse search scoring.
- Reciprocal Rank Fusion (RRF) candidate fusion.
- Cross-encoder reranking.
- Context package building and B2/B3 handoff.
