# C.2 — Knowledge Base Implementation Boundary

**System:** EarthMind (Earth-Mind.01)
**Phase:** Phase A — Preparation
**Step:** Step 2 — C.2 Implementation Boundary Lock
**Status:** LOCKED & DOCUMENTED

---

## A. Purpose

This document establishes and locks the exact implementation boundary, contracts, and lifecycle ownership for **C.2 — Knowledge Base** in EarthMind (`Earth-Mind.01`).

The goal of this boundary lock is to ensure that C.2 owns canonical knowledge records, document structures, chunks, metadata, provenance, source assessments, knowledge representations, and logical indices without overstepping into RAG retrieval routing, agricultural reasoning, context management, plan formation, or workflow orchestration.

This document serves as the mandatory contract lock prior to runtime implementation of C.2.

---

## B. Scope

### In-Scope for C.2 Boundary
- Definition and conceptual ownership of canonical knowledge structures, sources, documents, sections, chunks, metadata, provenance, source assessments, representations, logical indices, logical collections, and knowledge lifecycle states.
- Alignment with the locked C.1 RAG Architecture.
- Interface specification for knowledge base interactions with Database, Embedding, Index, and RAG modules.
- Strict definition of allowed and forbidden dependencies across EarthMind.

### Explicitly Out-of-Scope (No Runtime Implementation in this Step)
- No vector database creation or physical Qdrant integration.
- No embedding provider implementation or vector generation runtime.
- No text chunking runtime pipeline execution.
- No online retrieval routing, dense/sparse search, or reranking execution.
- No live web search execution or web scrapers.
- No database migrations or physical SQLite schema alterations.
- No API keys, credentials, or external cloud infrastructure provisioning.
- No modification of existing runtime logic in C.1, B2, B3, B4, B5, Memory, AI, Vision, Drone, ULPU, or External Services.

---

## C. Responsibilities Owned by C.2

C.2 owns **18 canonical knowledge concepts** and their associated lifecycle transitions:

1. **Source**: External domain information origin (e.g., academic journals, agricultural extensions, government guidelines, manuals).
2. **Source Registry**: Systematic registry tracking all known external knowledge sources and their authority/credibility metrics.
3. **Source Artifact**: Raw physical or digital artifacts (e.g., PDF files, HTML pages, raw text files, JSON feeds) retrieved from a Source.
4. **Document**: Logical representation of a structured domain document extracted from a Source Artifact.
5. **Document Version**: Explicit version tracking for documents as domain guidelines and research evolve over time.
6. **Document Structure**: Structural hierarchy of a document (chapters, sections, subsections, tables, figures, footnotes).
7. **Section**: Discrete structural subsection within a Document.
8. **Knowledge Unit**: Granular, semantically self-contained domain knowledge representation extracted from sections or documents.
9. **Chunk**: Physical text/multimodal unit formatted for indexing and vector embedding.
10. **Metadata**: Comprehensive set of descriptive, administrative, and domain-specific attributes attached to sources, documents, and chunks.
11. **Provenance**: Immutable origin tracing chain from raw Source Artifact down to indexed Chunk and Vector Representation.
12. **Source Assessment**: Metadata evaluating authority, reliability, recency, and geographic/domain relevance of knowledge (distinct from domain reasoning).
13. **Embedding Record**: Logical record tracking dense vector representations, embedding model identifier, version, dimension, and provider.
14. **Index Record**: Logical mapping connecting Chunks and Knowledge Units to their logical index positions and vector representations.
15. **Knowledge Collection**: Logical grouping of related domain knowledge (e.g., Crops, Soil, Diseases, Government Guidelines).
16. **Processing Record**: Audit trail tracking ingestion, normalization, chunking, embedding, and indexing progress.
17. **Knowledge Lifecycle**: Controlled progression of knowledge records from registration to publication or retirement.
18. **Publication State**: Explicit status governing retrievability (e.g., `RECEIVED`, `PROCESSING`, `PROCESSED`, `EMBEDDED`, `INDEXED`, `PENDING_REVIEW`, `PUBLISHED`, `FAILED`, `REJECTED`, `INVALID`).

### Deep Dive: Specific Ownership Areas

#### Source & Document Ownership
- Tracks source identity, authority registry, raw artifacts, extracted documents, structural hierarchies, and explicit versioning.
- Ensures every document maintains strict traceability back to its originating artifact and registered source.

#### Knowledge Unit & Chunk Ownership
- Defines semantic and structural chunking specifications that preserve relationships (parent document, version, section hierarchy, relative sequence, content type, and domain context).
- **Rule**: Chunking in C.2 must preserve semantic and structural integrity. C.2 chunking is **NOT** reduced to naive fixed-size character splitting.

#### Metadata & Provenance Ownership
- C.2 metadata attributes include:
  - **Identity**: `source_id`, `artifact_id`, `document_id`, `version_id`, `chunk_id`, `knowledge_unit_id`, `embedding_id`, `index_id`, `collection_id`, `processing_id`.
  - **Domain Attributes**: `content_type`, `language`, `domain`, `crop`, `region`, `season`, `topic`.
  - **Administrative**: `timestamp`, `retrieval_tags`, `searchable_terms`, `filterable_attributes`, `quality_status`, `completeness`, `processing_status`, `review_status`, `access_policy`, `visibility`.
- Provenance preserves an unbroken chain:
  `Source → Artifact → Document → Version → Processing → Chunk → Representation`.
- Embedding model, version, provider, and generation parameters remain explicitly traceable within representation metadata.

#### Source Assessment Ownership
- **Term**: Must strictly use the term **`SOURCE ASSESSMENT`** (and **NEVER** "Source Reasoning").
- **Attributes**: Authority score, reliability rating, recency, domain relevance, geographic relevance, review status, evidence type, assessment basis.
- **Boundary Rule**: Source Assessment provides static or evaluated metadata regarding source credibility. It **does NOT** perform agricultural reasoning, hypothesis evaluation, or truth determination. Agricultural reasoning is strictly owned by B3.

#### Representation Ownership
- Manages logical records describing dense embedding vectors, sparse term representations, and structured metadata index records.
- Provider/model/version parameters are generic and replaceable. C.2 architecture **must not** hardcode a single embedding provider or model.

#### Index Ownership
- Owns logical Index Records and knowledge-index lifecycle tracking.
- Physical vector storage (e.g., Qdrant) is abstracted behind interfaces:
  `Knowledge Index Interface → Index/Vector Adapter → Physical Index`.
- C.2 does **not** depend directly on physical vector database implementations.

#### Knowledge Collection Ownership
- Logical groupings of domain knowledge such as:
  - `Agriculture-General`
  - `Crops`
  - `Soil`
  - `Diseases`
  - `Government-Guidelines`
  - `Research`
  - `Regional-Knowledge`
  - `Multimodal-Knowledge`
- **Rule**: A logical Knowledge Collection is a domain concept and does **not** map 1:1 to a physical database collection or table.

#### Lifecycle & Publication States
- Knowledge Lifecycle progression:
  `SOURCE → REGISTER → INGEST → VALIDATE → PROCESS → STRUCTURE → CHUNK → METADATA → PROVENANCE → SOURCE ASSESSMENT → GENERATE REPRESENTATIONS → BUILD INDEX → PUBLISH → RETRIEVABLE → UPDATE / VERSION → SUPERSEDE / RETIRE`.
- Explicit publication states:
  - `RECEIVED`: Ingested source artifact.
  - `PROCESSING`: Currently undergoing extraction/chunking.
  - `PROCESSED`: Extracted into structured units and metadata.
  - `EMBEDDED`: Representations generated.
  - `INDEXED`: Vector/sparse indices registered.
  - `PENDING_REVIEW`: Awaiting validation/review.
  - `PUBLISHED`: Retrievable by query pipeline.
- Rejection / Failure states:
  - `FAILED`: Processing or indexing error occurred.
  - `REJECTED`: Assessment or validation failed.
  - `INVALID`: Schema or provenance error.
- **STRICT RULE**: Unpublished (`RECEIVED`, `PROCESSING`, `PROCESSED`, `EMBEDDED`, `INDEXED`, `PENDING_REVIEW`), `FAILED`, `REJECTED`, or `INVALID` knowledge **MUST NOT** silently become retrievable knowledge. Only `PUBLISHED` knowledge is retrievable.

---

## D. Responsibilities Explicitly Outside C.2

To maintain clean architecture and single responsibility:

| Area | Responsible Module | C.2 Non-Responsibility |
|---|---|---|
| **Query & Retrieval Execution** | C.1 RAG Architecture | C.2 does not perform query expansion, retrieval routing, dense/sparse retrieval execution, candidate fusion, reranking, or evidence package building. |
| **Context Assembly** | B2 Context Manager | C.2 does not collect, deduplicate, filter, prioritize, limit, or build model-ready context packages. |
| **Domain Reasoning** | B3 Reasoning Engine | C.2 does not perform agricultural reasoning, truth evaluation, conflict resolution, or hypothesis testing. |
| **Planning & Decisions** | B4 Planning Engine | C.2 does not perform goal interpretation, option evaluation, constraint checking, or plan generation. |
| **Workflow Orchestration** | B5 AI Orchestrator | C.2 does not direct execution flows, handle state machine transitions, manage request lifecycles, or coordinate replanning. |
| **Farmer/Field Memory** | Memory Module | C.2 does not store or manage farmer preferences, farm boundaries, field histories, or past user interactions. |
| **Web Search Execution** | External Services / RAG | C.2 does not execute live web search queries or scrape external websites online. |
| **Physical Storage Engine** | Database Module | C.2 does not manage SQL database connections, transaction locks, SQLite file handles, or low-level storage indexes. |
| **AI Model Execution** | AI Model Layer | C.2 does not load or run Sarvam-105B model weights or direct model inference adapters. |

---

## E. C.2 ↔ RAG Boundary

C.2 and C.1 RAG form the two complementary halves of the EarthMind RAG architecture:

```
========================================================================================
                                EARHTMIND RAG ARCHITECTURE
========================================================================================

KNOWLEDGE PIPELINE (C.2 Knowledge Base Domain)
Data Sources
  └── Ingestion Layer
        └── Processing / Chunking (Semantic & Structural)
              └── Metadata / Provenance / Source Assessment
                    └── Embedding Layer Records
                          └── Logical Knowledge Index & Collections
                                └── [ PUBLISHED State ]

                                        │ (Provides Retrievable Knowledge Records)
                                        ▼

QUERY PIPELINE (C.1 RAG Retrieval Engine Domain)
User / AI Query
  └── Query Preparation & Expansion
        └── Retrieval Router
              ├── Dense Retrieval Execution
              ├── Sparse Retrieval Execution
              ├── Structured Filters
              └── Web Search Execution
                    └── Candidate Fusion
                          └── Reranker
                                └── Evidence Builder & Validator
                                      └── Evidence Package
                                            └── B2 Context Manager → B3 Reasoning
========================================================================================
```

- **C.2 owns**: Storage representation, knowledge lifecycle, canonical metadata, provenance chains, source assessments, logical indices, and publication states.
- **C.1 RAG owns**: Online query expansion, routing, vector execution, sparse execution, reranking, candidate fusion, evidence package generation, and evidence validation.

---

## F. C.2 ↔ Memory Boundary

- **C.2 Knowledge Base**: Stores general, curated, external, authoritative domain knowledge (e.g., agricultural research, crop protection guides, soil chemistry standards, government regulations).
- **Memory Module**: Stores farmer-specific, field-specific, user-specific data (e.g., Farmer John's field #3 soil test result, farmer equipment list, previous chat interactions, farmer risk preferences).
- **Boundary Rule**: C.2 **never** stores memory records, and Memory **never** manages canonical domain knowledge lifecycle. They remain strictly separated.

---

## G. C.2 ↔ B2 Boundary

- B2 Context Manager prepares model-ready context packages for AI/Reasoning components.
- B2 receives validated evidence packages from C.1 RAG (which queries C.2).
- B2 coordinates a 12-state pipeline (collect, validate, deduplicate, filter, evaluate relevance, detect conflict, organize, prioritize, limit, build, validate output).
- B2 **never** accesses C.2 internal storage tables or databases directly.

---

## H. C.2 ↔ B3 Boundary

- B3 Reasoning Engine executes a 13-step bounded reasoning strategy over evidence.
- B3 consumes Evidence Packages containing Source Assessment metadata created by C.2.
- B3 evaluates credibility, recency, and domain applicability during its reasoning process.
- B3 **never** performs direct SQL or table operations on C.2 internal storage. B3 receives evidence strictly via RAG/Context contracts.

---

## I. C.2 ↔ B4 Boundary

- B4 Planning & Decision Engine receives structured context and reasoning outputs to perform goal interpretation, option generation, constraint evaluation (hard vs soft), and decision formation.
- B4 relies on evidence validated by B3/B2.
- B4 **never** accesses C.2 internal storage directly.

---

## J. C.2 ↔ B5 Boundary

- B5 AI Orchestrator manages workflow execution across 20 explicit lifecycle states.
- B5 coordinates C.2 lifecycle actions (e.g., requesting knowledge ingestion or publication status check) via high-level module contracts (`ModuleInterface`).
- B5 **never** accesses C.2 internal database tables or physical storage directly.

---

## K. C.2 ↔ Database Boundary

- C.2 defines domain models and schemas for knowledge entities.
- The **Database Module** (`modules/database`) owns physical persistence, connections, transactions, SQLite prototype tables, and physical storage indexes.
- C.2 interacts with database storage exclusively via the generic `DatabaseInterface` contract (`core/interfaces/module.py`), remaining completely agnostic to SQLite or future relational/NoSQL backends.

---

## L. Web Search Boundary

- Live web search execution is **NOT** a C.2 runtime responsibility.
- Search execution is performed by `External Services` / `C.1 RAG Query Pipeline`.
- Live web search results are temporary **Current Evidence**. They are not automatically permanent Knowledge Base content.
- **Promotion Flow for Web Evidence**:
  ```
  Web Search Execution
    └── Web Evidence (Temporary)
          └── Normalization & Validation
                └── Current Evidence (Used for current query)
                      │
                      ▼ (Optional Future Promotion)
                Candidate Knowledge
                      └── Human / System Review & Validation
                            └── Knowledge Ingestion Pipeline
                                  └── C.2 Permanent Knowledge Base (PUBLISHED)
  ```

---

## M. ID Responsibility

- Existing EarthMind ID attributes documented for C.2 knowledge entities:
  - `source_id`: Unique identifier for external domain knowledge sources.
  - `artifact_id`: Unique identifier for ingested source artifacts.
  - `document_id`: Unique identifier for canonical domain documents.
  - `version_id`: Unique identifier for specific document versions.
  - `chunk_id`: Unique identifier for structural/semantic text chunks.
  - `knowledge_unit_id`: Unique identifier for atomic knowledge units.
  - `embedding_id`: Unique identifier for vector representation records.
  - `index_id`: Unique identifier for logical index mappings.
  - `collection_id`: Unique identifier for logical knowledge collections.
  - `processing_id`: Unique identifier for processing audit records.
- **Identity Rule**: No new ID formats or ID generator redesigns are introduced in this step. Centralized ID generation strategies remain the responsibility of the future Identity/ID system.

---

## N. Allowed Dependency Model

Dependencies involving C.2 must be strictly interface-based:

```
[ C.1 RAG / Workflow ] ─────► [ Knowledge Base Interface ] ─────► [ C.2 Knowledge Base ]
                                                                       │
                               ┌───────────────────────────────────────┼───────────────────────────────────────┐
                               │                                       │                                       │
                               ▼                                       ▼                                       ▼
                     [ Database Interface ]                 [ Embedding Interface ]                  [ Index Interface ]
                               │                                       │                                       │
                               ▼                                       ▼                                       ▼
                     [ Database Module ]                    [ Embedding Provider ]                  [ Index Adapter ]
                                                                                                               │
                                                                                                               ▼
                                                                                                        [ Physical Index ]
```

---

## O. Forbidden Direct Dependencies

The following direct dependencies are strictly **FORBIDDEN** across the codebase:

1. **`B3 → C.2 internal database tables`**: Reasoning Engine must not query C.2 internal tables directly.
2. **`B4 → C.2 internal storage`**: Planning Engine must not query C.2 storage directly.
3. **`B5 → C.2 internal storage`**: AI Orchestrator must not inspect C.2 storage files or tables directly.
4. **`AI → C.2 physical storage`**: AI Model layer must not touch C.2 storage files directly.
5. **`C.2 → Sarvam-105B directly`**: Knowledge Base must not invoke Sarvam-105B directly without model adapters.
6. **`C.2 → B3 reasoning directly`**: C.2 must not call B3 reasoning logic.
7. **`C.2 → B4 planning directly`**: C.2 must not call B4 planning logic.
8. **`C.2 → B5 orchestration directly`**: C.2 must not trigger workflow orchestration directly.
9. **`C.2 → Web Search provider directly`**: C.2 must not directly execute web search queries.
10. **`C.2 → SQLite internals`**: C.2 must not import or depend on SQLite drivers or internal file handles directly.
11. **`C.2 → Memory internals`**: C.2 must not import or depend on Memory module internals.

---

## P. Lifecycle Ownership

C.2 strictly owns the **18-step Knowledge Lifecycle**:

```
 1. SOURCE                  (Identify external source)
 2. REGISTER                (Register source in registry)
 3. INGEST                  (Ingest raw artifact)
 4. VALIDATE                (Validate artifact schema & security)
 5. PROCESS                 (Extract structure & text)
 6. STRUCTURE               (Parse chapters/sections/tables)
 7. CHUNK                   (Perform semantic/structural chunking)
 8. METADATA                (Attach domain & admin metadata)
 9. PROVENANCE              (Build immutable provenance chain)
10. SOURCE ASSESSMENT       (Evaluate authority, recency & applicability)
11. GENERATE REPRESENTATIONS(Generate dense/sparse vector records)
12. BUILD INDEX             (Register logical index records)
13. PUBLISH                 (Transition status to PUBLISHED)
14. RETRIEVABLE             (Expose to RAG query pipeline)
15. UPDATE / VERSION        (Handle document updates & versioning)
16. SUPERSEDE / RETIRE      (Mark legacy documents superseded or retired)
```

### Publication Enforcement Rule
Knowledge items in failure, rejection, or non-published states (`RECEIVED`, `PROCESSING`, `PROCESSED`, `EMBEDDED`, `INDEXED`, `PENDING_REVIEW`, `FAILED`, `REJECTED`, `INVALID`) **must never be accessible** by the RAG query pipeline.

---

## Q. EarthMind Five-Principle Cross-check

| Principle | Verification in C.2 Boundary Lock |
|---|---|
| **1. Extensibility / Rubber-Band Principle** | Logical indices, embedding providers, and database stores are completely abstracted behind generic interfaces (`DatabaseInterface`, `IModel`, `IndexInterface`), allowing effortless expansion or replacement. |
| **2. Loose Coupling** | C.2 communicates with other modules (RAG, B2, B3, B4, B5, Database, Memory) exclusively through explicit contract interfaces and schema models. |
| **3. Single Responsibility** | C.2 strictly owns canonical knowledge storage, metadata, provenance, and lifecycle. Retrieval routing, context assembly, reasoning, planning, and orchestration belong to their respective modules. |
| **4. Controlled Dependencies** | Strict interface directionality enforced. Explicit list of forbidden direct dependencies prevents architectural drift or shortcut coupling. |
| **5. Replaceability + Evolution** | Embedding models, physical vector storage (e.g., Qdrant), and database backends can be swapped out without modifying C.2 domain contracts or downstream consumers. |

---

## R. Implementation Readiness Checklist

- [x] All 18 canonical C.2 concepts defined and assigned clear ownership.
- [x] Alignment with locked C.1 RAG Architecture confirmed.
- [x] Boundary between C.2 (Knowledge) and Memory (Farmer/Field) locked.
- [x] Boundaries with B2, B3, B4, B5, Database, AI, and Web Search locked.
- [x] Complete 18-step Knowledge Lifecycle and publication enforcement rules locked.
- [x] Term `SOURCE ASSESSMENT` locked (strictly prohibiting "Source Reasoning").
- [x] Semantic and structural chunking requirements locked (prohibiting character-split-only chunking).
- [x] Interface dependency model and explicit forbidden direct dependencies locked.
- [x] Existing ID fields documented without introducing new ID formats.
- [x] EarthMind Five-Principle Cross-check complete and verified.
- [x] Zero runtime implementation added in this step.
- [x] Existing test suite verified passing.

---
*C.2 Implementation Boundary Lock successfully finalized and recorded.*
