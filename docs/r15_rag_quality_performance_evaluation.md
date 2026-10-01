# Stage R15 — RAG Quality & Performance Evaluation

## Overview

Stage R15 implements the **RAG Quality & Performance Evaluation** layer for EarthMind. It sits **outside** the production RAG query execution path (R9 → R7 → R8 → R10 → R11 → R12 → R13 → B2), observing production behavior, evaluating retrieval/reranking/evidence quality, measuring stage latencies and throughput, tracking system reliability, running controlled baseline comparisons, detecting regressions, and generating structured evaluation reports.

R15 strictly adheres to the principle that **R15 measures and reports only**—it does not perform agricultural reasoning, generate recommendations, retrain models, or automatically modify production configuration.

---

## 1. Strict Boundary & Architecture

```
Production Execution Path:

Query → R9 Query Processing → R7 Hybrid Retrieval → R8 Reranking → R11 Evidence Builder → R12 Evidence Validator → R13 RAG Provider → B2 Context Manager

Evaluation Execution Path:

                    ┌───────────────────────────────────┐
                    │  R15 Evaluation Runner            │
                    │  (EvaluationRunner)               │
                    └─────────────────┬─────────────────┘
                                      │
                         Executes Benchmark Cases
                                      │
                 ┌────────────────────┼────────────────────┐
                 ▼                    ▼                    ▼
        QualityEvaluator    PerformanceEvaluator   ReliabilityEvaluator
        (Precision, Recall,   (P50/P90/P99, QPS,    (Success, Empty,
         MRR, nDCG@K, Rerank)  Stage Latencies)      Failure Breakdown)
                 │                    │                    │
                 └────────────────────┼────────────────────┘
                                      │
                        EvaluationReportGenerator
                                      │
                                      ▼
                        EvaluationReport (JSON & MD)
```

### Strict Architectural Boundaries
- **No Agricultural Reasoning:** R15 evaluates retrieved candidate IDs, ground-truth alignments, stage latencies, and reliability statuses. It never generates domain conclusions or advice.
- **No Direct Mutation:** R15 never modifies production retrieval weights, thresholds, Qdrant indices, or configuration settings.
- **Traceability:** Preserves `request_id`, `trace_id`, model versions, corpus versions, and full environment metadata across all evaluation runs.

---

## 2. R15 Components

1. **Evaluation Contracts & Schemas (`core/schemas/evaluation.py`):**
   - `EvaluationRun`, `EvaluationCase`, `EvaluationDataset`, `EvaluationMeasurement`, `QualityMetrics`, `PerformanceMetrics`, `ReliabilityMetrics`, `BaselineResult`, `RegressionResult`, `EvaluationReport`.
2. **Dataset & Query Set Repository (`modules/knowledge_base/evaluation/dataset.py`):**
   - `EvaluationDatasetRepository` manages benchmark datasets. Includes pre-seeded `ds_earthmind_agri_v1` with 10 multilingual (English, Devanagari/Hindi) agricultural benchmark cases covering GAP, Rice/Wheat pests, Soil Health, PMKSY, KVK advice, and negative control queries.
3. **Quality Evaluator (`modules/knowledge_base/evaluation/quality.py`):**
   - Calculates Precision@K, Recall@K, Hit Rate@K, MRR, nDCG@K, reranking position movement, and evidence package validation pass rates. Returns `NOT_EVALUABLE` or `INSUFFICIENT_DATA` when ground truth labels are absent.
4. **Performance Evaluator (`modules/knowledge_base/evaluation/performance.py`):**
   - Computes P50, P90, P95, P99, mean, min, and max latencies across the pipeline and per stage (R9, R7, R8, R10, R11, R12, R13, B2). Measures throughput (QPS and cases/sec) and captures process RSS memory usage.
5. **Reliability Evaluator (`modules/knowledge_base/evaluation/reliability.py`):**
   - Classifies case execution statuses (`SUCCESS`, `VALID_EMPTY_RESULT`, `SYSTEM_FAILURE`, `TIMEOUT`, `PARTIAL_RESULT`) and computes success, failure, and empty result rates.
6. **Baseline Comparator (`modules/knowledge_base/evaluation/baseline.py`):**
   - Summarizes and compares controlled retrieval configurations (Dense-only, Sparse-only, Hybrid, Hybrid+Reranker).
7. **Regression Evaluator (`modules/knowledge_base/evaluation/regression.py`):**
   - Compares previous vs current evaluation runs and flags metrics exceeding configured regression thresholds (default 5.0%).
8. **Evaluation Runner (`modules/knowledge_base/evaluation/runner.py`):**
   - Executes evaluation runs using the real `R14RealRetrievalHarness`. Preserves complete request/trace IDs, model/index version tags, and environment metadata.
9. **Evaluation Report Generator (`modules/knowledge_base/evaluation/report.py`):**
   - Compiles structured JSON `EvaluationReport`s and human-readable Markdown summaries. Automatically redacts API keys, credentials, and tokens.

---

## 3. How to Run R15 Evaluation

### Python API Example

```python
from modules.knowledge_base.evaluation import (
    EvaluationDatasetRepository,
    EvaluationRunner,
    EvaluationReportGenerator,
)

# 1. Load benchmark dataset
repo = EvaluationDatasetRepository()
dataset = repo.get_dataset("ds_earthmind_agri_v1")

# 2. Execute evaluation run against real R14 harness
runner = EvaluationRunner()
eval_run = runner.run_evaluation(dataset, max_results=10)

# 3. Generate structured evaluation report
report_gen = EvaluationReportGenerator()
report = report_gen.generate_report(eval_run, dataset=dataset)

# 4. Render Markdown summary
markdown_summary = report_gen.render_markdown_summary(report)
print(markdown_summary)
```

---

## 4. Five EarthMind Principles Verification

1. **Extensibility / Rubber-Band Principle:** All evaluators, dataset repositories, and report generators implement `core/interfaces/evaluation.py` protocols and can be swapped independently.
2. **Loose Coupling:** R15 interacts with production solely through `R14RealRetrievalHarness` and standard request/contract interfaces.
3. **Single Responsibility:** R15 evaluates, measures, and reports. It does not perform agricultural reasoning or context building.
4. **Controlled Dependencies:** R15 relies solely on core contracts, standard evaluation math, and `R14RealRetrievalHarness` without introducing external dependencies.
5. **Replaceability + Evolution:** Benchmark datasets, metrics algorithms, and reporting formats evolve independently from production RAG components.

---

## 5. Implementation Status

- **R15 Quality & Performance Evaluation:** Complete, tested (29 tests in `tests/test_r15_rag_evaluation.py`), and validated across the full 649-test repository suite.
- **Status:** `R15 IMPLEMENTATION COMPLETE`
