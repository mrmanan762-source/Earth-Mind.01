# EarthMind — Stage R15 RAG Quality & Performance Evaluation Framework Documentation

## 1. Purpose & Objective

Stage R15 provides a comprehensive, reproducible, and non-intrusive framework for measuring, benchmarking, and reporting the quality, performance, and reliability of the EarthMind RAG pipeline (Stage R14).

R15 operates strictly **OUTSIDE** the production execution path. It measures production behavior and generates structured reports without performing agricultural reasoning, modifying production context, or altering production configuration.

---

## 2. Architecture & Strict Boundary

```
Production RAG Pipeline (Stage R14)
   Query → R9 → R7 → R8 → R10 → R11 → R12 → R13 → B2 → B3
                               ▲
                               │ Evaluates (Non-intrusive)
                    ┌──────────┴──────────┐
                    │    R15 Evaluator    │
                    └──────────┬──────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ↓                  ↓                  ↓
     Quality Metrics      Performance        Reliability
  (Precision, Recall,    (Latency, QPS,       (Success,
    MRR, nDCG@K)        Resource Usage)    Failure Rates)
            │                  │                  │
            └──────────────────┼──────────────────┘
                               ↓
                   Evaluation Report (JSON / MD)
```

### Strict Boundary Rules
- **R15 MAY:** execute benchmark datasets, invoke R14 E2E evaluation path, calculate quality/performance/reliability metrics, compare baselines, evaluate run-to-run regressions, and generate JSON/Markdown reports.
- **R15 MUST NOT:** perform agricultural reasoning, generate recommendations, replace B3, modify B2 Context Manager, retrain models, modify the knowledge corpus, or automatically alter production settings.

---

## 3. Evaluation Contracts & Data Model

Core evaluation schemas are defined in `core/schemas/evaluation.py` and interfaces in `core/interfaces/evaluation.py`:

1. `EvaluationCase`: Query text, language, domain category, expected document/chunk/evidence IDs, relevance judgments (0.0 to 1.0), and difficulty.
2. `EvaluationDataset`: Benchmark dataset container with semantic versioning (`dataset_id`, `dataset_version`, `cases`).
3. `QualityMetrics`: Precision@K, Recall@K, Hit Rate@K, MRR, nDCG@K, and `MetricStatus` (`EVALUATED`, `NOT_EVALUABLE`, `INSUFFICIENT_DATA`).
4. `PerformanceMetrics`: E2E total/avg latency, p50, p90, p99 percentiles, stage latencies (R9, R7, R8, R11, R12, R13), QPS throughput, and resource usage.
5. `ReliabilityMetrics`: Success rate, failure rate, timeout rate, empty result rate, and partial result rate.
6. `BaselineResult`: Controlled benchmarking metrics across retrieval modes (Dense-only, Sparse-only, Hybrid, Hybrid+Reranker).
7. `RegressionResult`: Run-to-run metric diffs, regressions, and improvements.
8. `EvaluationReport`: Master report container holding all aggregated metrics, breakdowns, baseline comparisons, and limitations.

---

## 4. Benchmark Dataset (`data/evaluation/agri_rag_eval_v1.json`)

The default ground-truth dataset `agri_rag_eval_v1.json` contains 12 curated test cases matching the R3 real agricultural corpus (`data/knowledge/raw/`):

- **Rice Cultivation**: Fertilizer dosages & nutrient management
- **Wheat Disease**: Yellow rust / stripe rust control
- **Soil Testing**: Soil health card sampling grid & parameters
- **Irrigation**: Drip lateral flushing & maintenance
- **Fertilizers**: Site-specific balanced fertilizer application
- **Multilingual**: Devanagari Hindi query ("धान की फसल में खाद प्रबंधन")
- **Dryland Farming**: Rainfed moisture conservation
- **Extension Advisories**: PM-Kisan & KVK guidance
- **Negative / Empty Cases**: Query with empty string or non-existent term
- **Ambiguous Queries**: General crop nutrient management

---

## 5. Metrics & Calculation Formulas

### 5.1 Retrieval & Reranking Quality Metrics
- **Precision@K**: $\frac{\text{Number of relevant retrieved items at top-K}}{K}$
- **Recall@K**: $\frac{\text{Number of relevant retrieved items at top-K}}{\text{Total expected relevant items}}$
- **Hit Rate@K**: $1.0$ if at least one relevant item is retrieved in top-K, else $0.0$.
- **MRR (Mean Reciprocal Rank)**: $\frac{1}{\text{Rank of first relevant retrieved item}}$
- **nDCG@K (Normalized Discounted Cumulative Gain)**: $\frac{\text{DCG}@K}{\text{IDCG}@K}$ using relevance judgments ($2^{rel} - 1 / \log_2(\text{rank} + 1)$).

When ground-truth labels are missing or case is empty, `QualityEvaluator` safely handles empty retrieval or assigns `MetricStatus.NOT_EVALUABLE` without fabricating scores.

### 5.2 Performance Metrics
- **Latencies**: Total latency, average latency, p50, p90, p99 percentiles using monotonic timing.
- **Throughput**: Queries per second (QPS) and successful QPS.
- **Resource Usage**: Process RSS memory (MB) and CPU percent via `psutil` or `UNAVAILABLE` if unmeasurable.

### 5.3 Reliability Metrics
Classifies outcomes into `SUCCESS`, `VALID_EMPTY_RESULT`, `PARTIAL_RESULT`, `TIMEOUT`, `SYSTEM_FAILURE`, `UNAVAILABLE` and computes rate fractions.

---

## 6. How to Execute Evaluation

### 6.1 Using `R15EvaluationRunner` in Python
```python
from modules.knowledge_base.evaluation.runner import R15EvaluationRunner
from modules.knowledge_base.evaluation.report import EvaluationReportGenerator

runner = R15EvaluationRunner()
report = runner.run_evaluation(compare_baselines=True)

# Generate Markdown & JSON report files
json_path, md_path = EvaluationReportGenerator.save_report(report)
print(f"Report saved to {json_path} and {md_path}")
```

### 6.2 Running Baseline & Regression Comparison
```python
# Baseline comparison
report_with_baselines = runner.run_evaluation(compare_baselines=True)

# Regression comparison between base run and current run
regression_report = runner.run_evaluation(base_report=previous_report)
print("Regression Status:", regression_report.regression_comparison.overall_status)
```

---

## 7. Adherence to 5 EarthMind Principles

1. **Extensibility / Rubber-Band Principle**: Evaluator protocols (`IQualityEvaluator`, `IPerformanceEvaluator`, `IEvaluationRunner`) allow adding new metrics or dataset formats without touching RAG logic.
2. **Loose Coupling**: R15 interacts with production through R14 public interfaces (`R14RealRetrievalHarness`) and typed Pydantic contracts.
3. **Single Responsibility**: R15 evaluates and reports. It does not retrieve, reason, store memory, or optimize settings automatically.
4. **Controlled Dependencies**: R15 dependencies are isolated in `modules/knowledge_base/evaluation/` without leaking into production modules.
5. **Replaceability + Evolution**: Dataset loaders, evaluators, and report generators evolve independently from production RAG components.
