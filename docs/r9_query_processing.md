# Stage R9 — Query Processing Documentation

## 1. Overview & Boundary

Stage R9 Query Processing provides the incoming retrieval preparation layer for EarthMind RAG. It transforms raw user queries into structured, provider-independent retrieval representations (`RetrievalQuery` containing `DenseQuery`, `SparseQuery`, and `StructuredQueryFilter`s) ready for execution by R5 Dense Vector Retrieval and R6 Sparse Retrieval via R7 Hybrid Retrieval.

### Responsibilities
- **Incoming Query Validation:** Checks empty/blank queries, size constraints, parameter sanity, and language support.
- **Normalization:** Whitespace, casing, Unicode (NFKC), and punctuation cleaning while preserving pH, dosages, N-P-K formulas, scientific names, and Indic scripts.
- **Classification:** Functional intent categorization (`DIAGNOSIS_RELATED`, `PEST_DISEASE_RELATED`, `CROP_QUERY`, `SOIL_QUERY`, `WEATHER_RELATED`, `FARM_PRACTICE`, `AGRICULTURAL_GUIDANCE`, `GENERAL_AGRICULTURE`).
- **Agricultural Metadata Enrichment:** Extracting explicit domain metadata (`crop`, `crop_stage`, `disease_pest`, `soil_type`, `soil_condition`, `region`, `season`) without hallucinating unmentioned fields.
- **Query Expansion & Reformulation:** Deterministic, bounded synonym/transliteration expansion preserving original query lineage.
- **Retrieval Query Assembly:** Combining normalized queries, expansions, metadata filters, and dense/sparse parameters into a `RetrievalQuery`.

### Non-Responsibilities
- Does NOT execute retrieval (R5/R6/R7).
- Does NOT perform reranking (R8).
- Does NOT call Qdrant or sparse index engines directly.
- Does NOT store or update Memory or Database records.
- Does NOT perform agricultural reasoning or advice synthesis.

---

## 2. Core Architecture & Pipeline

```
Incoming Request (QueryProcessingRequest)
        │
        ▼
 1. QueryValidator ────── (Rejects empty, malformed, or out-of-bounds queries)
        │
        ▼
 2. QueryNormalizer ───── (Unicode NFKC, safe casing, protects pH/dosages/units)
        │
        ▼
 3. QueryClassifier ───── (Metadata intent classification)
        │
        ▼
 4. AgriculturalMetadataExtractor ── (Extracts explicit crop, disease, soil, region, season)
        │
        ▼
 5. QueryExpansionStrategy ── (Bounded, deterministic synonym/transliteration expansion)
        │
        ▼
 6. RetrievalQueryBuilder ─── (Assembles DenseQuery, SparseQuery, and StructuredQueryFilters)
        │
        ▼
 Output Payload (QueryProcessingResponse & RetrievalQuery)
        │
        ▼
 Bridge to Stage R7 HybridRetrievalRequest
```

---

## 3. Interfaces & Contracts

### Data Contracts (`core/schemas/query.py`)
- `QueryProcessingStatus`: `SUCCESS`, `PARTIAL`, `INVALID`, `FAILED`, `TIMEOUT`, `UNAVAILABLE`
- `QueryClassification`: Functional intent enums
- `AgriculturalMetadata`: Domain fields extracted without hallucination
- `QueryMetadata`: Combined classification, agricultural metadata, and language confidence
- `QueryExpansion`: Expansion phrase, type, weight, and source term
- `DenseQuery`: Text, top-k, and optional pre-computed vector
- `SparseQuery`: Text, lexical terms, expanded terms, term weights, and optional sparse indices
- `StructuredQueryFilter`: Field, comparison operator, and filter value
- `RetrievalQuery`: Final container with `to_hybrid_retrieval_request()` bridge method
- `QueryProcessingRequest`: Input request container
- `QueryProcessingResponse`: Output payload container with execution audit logs

### Interfaces (`core/interfaces/query_processor.py`)
- `IQueryValidator`
- `IQueryNormalizer`
- `IQueryClassifier`
- `IQueryMetadataExtractor`
- `IQueryExpansionStrategy`
- `IQueryProcessorEngine`

---

## 4. Five EarthMind Principles Compliance

1. **Extensibility / Rubber-Band Principle:** All pipeline stages (validator, normalizer, classifier, metadata extractor, expansion strategy) implement runtime-checkable protocols and can be swapped independently.
2. **Loose Coupling:** Communicates exclusively via provider-independent Pydantic contracts without direct backend dependencies.
3. **Single Responsibility:** Focuses strictly on query preparation and classification without executing retrieval or reasoning.
4. **Controlled Dependencies:** Zero direct coupling to Qdrant, model weights, or memory storage.
5. **Replaceability + Evolution:** Algorithms and rules can be replaced without breaking downstream R5/R6/R7 retrieval pipelines.

---

## 5. Verification & Testing

Stage R9 is validated via unit and integration tests in `tests/test_r9_query_processing.py` covering:
- Valid query processing & original query preservation
- Empty and malformed query rejection
- Multilingual and Indic query normalization
- Agricultural term & unit preservation (pH, 10kg/acre, *Xanthomonas*)
- Zero hallucination in metadata extraction
- Bounded expansion & expansion failure fallbacks
- Dense/sparse representation and filter generation
- Bridge conversion to Stage R7 `HybridRetrievalRequest`
- Deterministic behavior and execution audit logging
