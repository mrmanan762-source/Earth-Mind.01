# Stage R12 — Evidence Validator Architecture & Implementation Documentation

## Executive Summary & Objective

Stage R12 **Evidence Validator** is the validation gate in EarthMind's RAG Query Pipeline. Positioned directly between **Stage R11 Evidence Builder** and **B2 Context Manager**, R12 ensures that evidence packages delivered to downstream context and reasoning engines are structurally sound, taxonomy-compliant, traceable, and free from critical corruption or malformed identifiers.

```
R7 Hybrid Retrieval
        ↓
R8 Reranking
        ↓
R10 Web Search
        ↓
R11 Evidence Builder
        ↓
R12 Evidence Validator
        ↓
Validated Evidence Package
        ↓
B2 Context Manager
        ↓
B3 Reasoning Engine
```

R12 **validates** evidence packages and individual evidence items. R12 **does not** perform agricultural reasoning, evaluate truth, rewrite scores, query databases/Qdrant, promote data into Memory, or execute model inference.

---

## 1. Architectural Boundary & Single Responsibility

### In Scope for R12
- Structural validation of `EvidencePackage` and `EvidenceItem` fields, types, and timestamps.
- ID taxonomy validation (verifying presence and format of `evidence_id`, `chunk_id`, `knowledge_unit_id`, `document_id`, `web_result_id`).
- Lineage & provenance traceability checks (verifying KB origin chain and request correlation IDs).
- Web evidence structural checks (verifying URL format, provider, and transient classification).
- Source assessment metadata structure validation without evaluating underlying truth.
- Rank and score checks (verifying rank positivity and float score finiteness without modifying score values).
- Completeness and consistency validation (detecting missing fields, header/item count mismatches, and contradictory cross-field IDs).
- Duplicate ID and duplicate content detection.
- Preserved conflict indicator detection and reporting.
- Multimodal and agricultural metadata structure validation.
- Deterministic finding ordering and overall status computation (`VALID`, `PARTIALLY_VALID`, `INVALID`, `MALFORMED`, `UNTRACEABLE`, `CONFLICTING`, `EMPTY`).
- Package sanitization filtering valid items into `validated_package` for B2 Context Manager consumption.

### Strict Out of Scope for R12
- **No Retrieval or Reranking**: R12 accepts constructed packages from R11.
- **No Domain / Agricultural Reasoning**: R12 does not decide whether a treatment is effective or whether a source is correct.
- **No Score Rewriting**: R12 preserves dense, sparse, fused, and rerank scores exactly as calculated upstream.
- **No Storage / Database Access**: R12 does not query SQLite, Qdrant, or any underlying store.
- **No Memory Writes**: R12 does not promote evidence to Memory or alter user context persistence.
- **No Knowledge Base Publication**: R12 does not publish items into permanent collections.
- **No Model Inference**: R12 operates via deterministic, bounded rule-based evaluation.

---

## 2. Core Data Contracts

Located in `core/schemas/evidence_validator.py`:

1. **`ValidationSeverity` (Enum)**:
   - `INFO`: Informational finding (e.g., missing optional title or duplicate content notice).
   - `WARNING`: Non-fatal defect (e.g., empty provenance dictionary or negative rank value).
   - `ERROR`: Item-invalidation defect (e.g., missing content or invalid ID taxonomy).
   - `CRITICAL`: Package-invalidation or malformed defect (e.g., missing evidence_id or None package).

2. **`EvidenceValidationStatus` (Enum)**:
   - `VALID`: Package and all items passed validation cleanly.
   - `PARTIALLY_VALID`: Some items invalid/filtered out, or non-fatal warnings present while valid items remain.
   - `INVALID`: Entire package or strict mode invalidated due to errors/critical findings.
   - `MALFORMED`: Package or items severely structurally broken.
   - `UNTRACEABLE`: KB provenance or lineage missing or untraceable.
   - `CONFLICTING`: Preserved conflict indicators detected across evidence items.
   - `EMPTY`: Package contains zero evidence items.

3. **`EvidenceValidationFinding` (Model)**:
   - `finding_id`: Unique identifier (`fnd_...`).
   - `rule_code`: Specific check code (e.g., `R12_STRUCT_01`, `R12_ID_01`, `R12_SCORE_02`).
   - `severity`: Severity level.
   - `evidence_id`: Optional affected item ID.
   - `field_path`: Field name where finding occurred.
   - `reason`: Rationale explanation.
   - `metadata`: Additional contextual details.

4. **`EvidenceItemValidationOutcome` (Model)**:
   - `evidence_id`: Evidence item identifier.
   - `is_valid`: Boolean indicator whether item passed validation.
   - `status`: Item-level `EvidenceValidationStatus`.
   - `findings`: List of findings specific to this item.
   - `item`: Sanitized/preserved `EvidenceItem` if valid.

5. **`EvidenceValidationRequest` (Model)**:
   - `package`: Input `EvidencePackage` produced by R11.
   - `request_id`: Tracing correlation ID.
   - `strict_mode`: Boolean flag (if True, any ERROR/CRITICAL finding invalidates the entire package).
   - `policy_config`: Runtime policy parameters.

6. **`EvidenceValidationResult` (Model)**:
   - `validation_id`: Execution ID (`val_...`).
   - `overall_status`: Computed package validation status.
   - `validated_package`: Sanitized `EvidencePackage` containing valid items ready for B2.
   - `item_outcomes`: Per-item outcomes.
   - `findings`: All validation findings.
   - `valid_items_count`, `invalid_items_count`, `total_items_count`.
   - `has_conflicts`: Boolean flag indicating conflict indicators presence.

7. **`EvidenceValidationResponse` (Model)**:
   - Wrapper payload with `request_id`, `status`, `result`, `warnings`, and `execution_time_ms`.

---

## 3. Modular Validation Rules

Stage R12 implements 10 distinct rule categories in `modules/knowledge_base/evidence/validator.py`:

| Category | Check Codes | Description |
|---|---|---|
| **Structure** | `R12_STRUCT_01..08` | Package non-nullness, mandatory fields (`evidence_id`, `source_type`, `content`), positive timestamps, truncation checks. |
| **Identity** | `R12_ID_01..03` | KB canonical ID presence (`chunk_id`, `knowledge_unit_id`, `document_id`, `candidate_id`), Web result/URL presence, duplicate ID detection. |
| **Provenance** | `R12_PROV_01..03` | Provenance dictionary format, KB lineage completeness, request correlation ID matching. |
| **Web Evidence** | `R12_WEB_01..02` | Valid URL reference format, provider/source identification, transient classification. |
| **Source Assessment** | `R12_SRC_01` | Source assessment metadata dictionary structure validation without truth evaluation. |
| **Ranks & Scores** | `R12_SCORE_01..02` | Positive rank checks, finite float score checks (prohibiting NaN/Inf), score preservation. |
| **Completeness** | `R12_CMPL_01` | Downstream context requirements (title/reference presence). |
| **Consistency** | `R12_CONS_01..05` | Count header vs actual list length alignment, KB vs Web cross-field taxonomy consistency. |
| **Conflicts** | `R12_CNFL_01..02` | Duplicate content detection, preserved conflict indicator detection without conflict resolution. |
| **Metadata** | `R12_META_01..02` | Multimodal structure dictionary checks, agricultural metadata key preservation (`crop`, `region`, `season`, `soil`, `disease`). |

---

## 4. Downstream Integration & B2 Compatibility

The validated package produced by R12 (`result.validated_package`) maintains direct compatibility with B2 Context Manager through the standard conversion method:

```python
contracts = validated_package.to_rag_context_contracts()
```

This generates `RAGContextContract` objects with:
- `ownership`: `ContextOwnership.RAG_OWNED`
- `scope`: `ContextScope.GLOBAL`
- `persistence_intent`: `TEMPORARY` for Web search evidence, `PERSISTENT` for KB evidence
- `publication_state`: `TRANSIENT` for Web evidence, `PUBLISHED` for KB evidence

---

## 5. Five EarthMind Principles Compliance

1. **Rubber-Band / Extensibility Principle**: Policy rules, findings, and check categories are modular and extensible via configuration without breaking signatures.
2. **Loose Coupling**: R12 interacts exclusively via Pydantic data contracts (`EvidencePackage`, `EvidenceValidationRequest`, `EvidenceValidationResponse`) and the `IEvidenceValidatorEngine` interface protocol.
3. **Single Responsibility**: R12 strictly owns evidence package validation. It delegates retrieval to R7/R8/R10, packaging to R11, context collection to B2, and reasoning to B3.
4. **Controlled Dependencies**: R12 has zero external dependencies on Qdrant, databases, or model runtimes, relying entirely on core schemas and standard python libraries.
5. **Replaceability & Evolution**: `EvidenceValidatorEngine` can be swapped or upgraded seamlessly as long as it adheres to `IEvidenceValidatorEngine`.

---

## 6. Implementation Verification

- Unit Test Suite: `tests/test_r12_evidence_validator.py` (30 tests passing).
- Full Repository Test Suite: 567 tests passing cleanly with zero regressions.
