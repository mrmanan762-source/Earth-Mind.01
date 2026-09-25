# C.3.3 — Cross-Domain Context Governance & Promotion Control

## 1. Overview & Purpose

**C.3.3 Cross-Domain Context Governance & Promotion Control** defines and implements the governance layer controlling whether and how information moves or is promoted between EarthMind's two primary knowledge domains:

- **RAG Domain**: General agronomic, scientific, and regional world knowledge ("What do we know about the world?").
- **Memory Domain**: Specific farmer, farm, field, and historical interaction knowledge ("What do we know about this farmer, farm, field, and their history?").

RAG and Memory are independent knowledge domains. Information must **never** silently change ownership, domain, or privacy scope. Any cross-domain movement must pass through an explicit, policy-controlled, traceable, and lifecycle-safe governance process.

C.3.3 governs the cross-domain transition. It does **NOT** perform target-domain storage (no direct write to SQLite, Qdrant, or RAG/Memory indexes), nor does it perform agricultural reasoning or evaluate scientific validity.

---

## 2. Target Governance Architecture

```
                         C.3 GOVERNANCE
                              │
                ┌─────────────┴─────────────┐
                │                           │
                ▼                           ▼
        RAG → Memory                  Memory → RAG
        Promotion Path                Promotion Path
                │                           │
                ▼                           ▼
        Promotion Candidate         Knowledge Candidate
                │                           │
                └─────────────┬─────────────┘
                              ▼
                    Governance / Policy Check
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
        AUTO_ALLOWED     REQUIRES_REVIEW   BLOCKED
             │                │                │
             ▼                ▼                ▼
       Target Lifecycle   Review Process    No Transfer
             │
             ▼
      Target Domain System
```

The governance layer acts as a gatekeeper. Upon candidate submission:
1. `ContextGovernanceEngine` evaluates the candidate against cross-domain transition policies.
2. A provider-independent `GovernanceDecision` is generated with explicit decision outcomes (`AUTO_ALLOWED`, `REQUIRES_REVIEW`, `BLOCKED`, `INVALID`).
3. If approved (`AUTO_ALLOWED` or approved `REQUIRES_REVIEW`), a `PromotionRecord` is created specifying `target_lifecycle_requirements`.
4. The target domain system consumes the promotion record and executes its native ingestion/storage lifecycle.

---

## 3. Core Promotion Contracts & Models

### 3.1 Transition Types (`TransitionType`)

- `RAG_TO_MEMORY`: Promotion of RAG or external evidence into farmer-specific Memory context.
- `MEMORY_TO_RAG`: Promotion of farmer or field knowledge into broader general RAG knowledge.

### 3.2 Governance Outcomes (`GovernanceOutcome`)

- `AUTO_ALLOWED`: Candidate satisfies all policy prerequisites; automatically eligible for target system lifecycle.
- `REQUIRES_REVIEW`: Candidate requires explicit human/curator review or automated anonymization before target promotion.
- `BLOCKED`: Candidate violates boundary, privacy, scope, or persistence policy; promotion denied.
- `INVALID`: Candidate structure or provenance chain is corrupt or incomplete.

### 3.3 Governance States (`GovernanceState`)

`CANDIDATE` → `VALIDATING` → `EVALUATING_POLICY` → (`AUTO_ALLOWED` | `REQUIRES_REVIEW` | `BLOCKED` | `INVALID`) → (`APPROVED` | `REJECTED`) → `EXECUTION_PENDING` → `COMPLETED` / `FAILED`

### 3.4 Promotion Candidate Contract (`PromotionCandidate`)

Provider-independent contract encapsulating the item offered for cross-domain transition. Preserves:
- `candidate_id`: Standardized EarthMind identifier (`cand_...`).
- `source_id`, `source_type`, `ownership`, `classification`, `scope`, `persistence_intent`.
- `content`: Payloads or evidence object.
- `provenance`: Traceable source origin chain.
- `privacy_level`, `is_pii`.
- `requested_transition`: `RAG_TO_MEMORY` or `MEMORY_TO_RAG`.
- `target_domain`, `target_ownership`, `target_scope`, `target_persistence_intent`.
- Entity references: `farmer_id`, `farm_id`, `field_id`, `crop_cycle_id`, `session_id`.

Factory constructors `from_rag_contract()` and `from_memory_contract()` convert C.3.1/C.3.2 contracts into `PromotionCandidate` objects seamlessly.

### 3.5 Governance Decision & Record (`GovernanceDecision`, `PromotionRecord`)

`GovernanceDecision` captures the detailed policy evaluation outcome, including:
- `outcome`, `state`, `reason`, `violations`, `failure_reason`, `applicable_policy`.
- Evaluated source/target ownership, scope, and persistence intents.
- Preserved provenance and `target_lifecycle_requirements`.

`PromotionRecord` provides full auditability and correlation tracking across system boundaries.

---

## 4. Governance Policies & Transition Controls

### 4.1 Default Deny Policy
All cross-domain transitions are denied by default unless an explicit policy rule permits the transition.

### 4.2 Ownership Transition Control
Ownership changes (`RAG_OWNED` ↔ `MEMORY_OWNED`) are never implicit. Both source and target ownership are explicitly recorded in candidate, decision, and promotion records.

### 4.3 Scope Transition Control
- **`GLOBAL` → `FARMER` / `FARM` / `FIELD` (`RAG_TO_MEMORY`)**: Allowed if target `farmer_id` (and farm/field ID if applicable) is provided and persistence policy permits.
- **`FARMER` / `FIELD` / `FARM` → `GLOBAL` / `REGIONAL` (`MEMORY_TO_RAG`)**: Unsafe scope widening! Farmer and field scoped private data cannot be automatically promoted to global RAG. Such requests are assigned `REQUIRES_REVIEW` (for curation/anonymization) or `BLOCKED` if PII is present.

### 4.4 Persistence Transition Control
- **`TEMPORARY` → `PERSISTENT`**: Strictly `BLOCKED`.
- **`SESSION_SCOPED` → `PERSISTENT`**: Requires explicit review (`REQUIRES_REVIEW`).

### 4.5 Privacy Protection
- Privacy level (`PUBLIC`, `FARM_PRIVATE`, `FARMER_PII`) and `is_pii` flag survive transition unaltered.
- Any candidate with `is_pii=True` or `privacy_level=FARMER_PII` is strictly `BLOCKED` from general RAG promotion.

### 4.6 Observation & Web Evidence Controls
- **`OBSERVATION`**: Drone, vision, and sensor observations are temporary evidence. Promoting an observation to persistent Memory or RAG requires explicit review (`REQUIRES_REVIEW`).
- **`EXTERNAL_CURRENT_DATA`**: Live web search evidence or weather data cannot automatically become permanent Memory or published RAG knowledge without formal review or C.2 ingestion pipeline processing (`REQUIRES_REVIEW`).

---

## 5. Target Lifecycle Protection

C.3.3 strictly enforces target domain lifecycle boundaries:
- **`RAG_TO_MEMORY`**: Approved promotions emit `target_lifecycle_requirements = "MEMORY_INGESTION_AND_PERSISTENCE_LIFECYCLE"`.
- **`MEMORY_TO_RAG`**: Approved promotions emit `target_lifecycle_requirements = "C2_INGESTION_VALIDATION_AND_PUBLICATION_PIPELINE"`.

C.3.3 **never** performs direct database insertions or index modifications.

---

## 6. Review Process

Candidates requiring review (`REQUIRES_REVIEW`) enter a controlled state where authorized reviewers can execute:
- `engine.approve_review(candidate, reviewer_id, reason)` → transitions to `APPROVED` / `AUTO_ALLOWED` status.
- `engine.reject_review(candidate, reviewer_id, reason)` → transitions to `REJECTED` / `BLOCKED` status.

---

## 7. Compliance with the Five EarthMind Principles

1. **Extensibility / Rubber-Band Principle**:
   `TransitionType`, `GovernanceOutcome`, and `ContextGovernanceEngine` policies can be extended with new transition types or custom domain policies without modifying core boundary interfaces.
2. **Loose Coupling**:
   Governance interacts strictly via provider-independent contracts (`PromotionCandidate`, `GovernanceDecision`, `PromotionRecord`) and protocol interface (`IPromotionGovernanceEngine`).
3. **Single Responsibility**:
   Governance solely evaluates cross-domain movement policies; it does not perform agricultural reasoning, retrieval, or storage.
4. **Controlled Dependencies**:
   Strict unidirectional contracts: `Source Contract` → `PromotionCandidate` → `Governance Engine` → `PromotionRecord` → `Target System Lifecycle`.
5. **Replaceability + Evolution**:
   Governance policies and storage backends (Qdrant, SQLite, memory tables) can evolve independently without breaking boundary governance contracts.
