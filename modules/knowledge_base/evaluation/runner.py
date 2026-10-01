"""Stage R15 Evaluation Execution Runner."""

import os
import platform
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from core.config.settings import settings
from core.logging.logger import get_logger
from core.schemas.evaluation import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationMeasurement,
    EvaluationRun,
    ReliabilityStatus,
)
from modules.knowledge_base.evaluation.performance import PerformanceEvaluator
from modules.knowledge_base.evaluation.quality import QualityEvaluator
from modules.knowledge_base.evaluation.reliability import ReliabilityEvaluator
from modules.knowledge_base.integration.harness import R14RealRetrievalHarness

logger = get_logger("modules.knowledge_base.evaluation.runner")


class EvaluationRunner:
    """Executes evaluation benchmarks using the real R14 E2E harness."""

    def __init__(
        self,
        harness: Optional[R14RealRetrievalHarness] = None,
        quality_evaluator: Optional[QualityEvaluator] = None,
        performance_evaluator: Optional[PerformanceEvaluator] = None,
        reliability_evaluator: Optional[ReliabilityEvaluator] = None,
    ):
        self.harness = harness or R14RealRetrievalHarness()
        self.quality_evaluator = quality_evaluator or QualityEvaluator()
        self.performance_evaluator = performance_evaluator or PerformanceEvaluator()
        self.reliability_evaluator = reliability_evaluator or ReliabilityEvaluator()

    def run_evaluation(
        self,
        dataset: EvaluationDataset,
        max_results: int = 10,
        enable_web_search: bool = False,
    ) -> EvaluationRun:
        """
        Executes an evaluation run over a dataset.

        Returns:
            EvaluationRun containing per-case measurements, quality metrics, performance metrics, and reliability metrics.
        """
        run_id = f"eval_run_{uuid.uuid4().hex[:8]}"
        start_iso = datetime.now(timezone.utc).isoformat()
        start_time = time.perf_counter()

        logger.info(f"Starting evaluation run '{run_id}' on dataset '{dataset.dataset_id}' ({len(dataset.cases)} cases)")

        # Enable/disable web search on harness RAG provider
        if hasattr(self.harness, "rag_provider") and hasattr(self.harness.rag_provider, "config"):
            self.harness.rag_provider.config.enable_web_search = enable_web_search

        measurements: List[EvaluationMeasurement] = []

        for case in dataset.cases:
            req_id = f"req_eval_{uuid.uuid4().hex[:8]}"
            trc_id = f"trc_eval_{uuid.uuid4().hex[:8]}"
            case_start = time.perf_counter()

            try:
                e2e_res = self.harness.execute_query(
                    query_text=case.query_text,
                    request_id=req_id,
                    trace_id=trc_id,
                    max_results=max_results,
                    metadata=case.metadata,
                )
                case_elapsed_ms = round((time.perf_counter() - case_start) * 1000.0, 2)

                # Extract chunk IDs from B2 context items or RAG contracts
                chunk_ids: List[str] = []
                evidence_ids: List[str] = []
                if e2e_res.final_context_items:
                    for item in e2e_res.final_context_items:
                        cid = getattr(item, "chunk_id", None) or (item.metadata.get("chunk_id") if hasattr(item, "metadata") and isinstance(item.metadata, dict) else None)
                        if cid:
                            chunk_ids.append(cid)
                        item_id = getattr(item, "item_id", None) or getattr(item, "id", None)
                        if item_id:
                            evidence_ids.append(str(item_id))

                # Classify status
                if e2e_res.errors:
                    status = ReliabilityStatus.SYSTEM_FAILURE
                    err_code = "R14_PIPELINE_ERROR"
                    err_msg = "; ".join(e2e_res.errors)
                elif e2e_res.context_items_count == 0 and e2e_res.rag_contracts_count == 0:
                    status = ReliabilityStatus.VALID_EMPTY_RESULT
                    err_code = None
                    err_msg = None
                else:
                    status = ReliabilityStatus.SUCCESS
                    err_code = None
                    err_msg = None

                stage_lats: Dict[str, float] = {}
                for step in e2e_res.trace_steps:
                    stg = step.get("stage", "unknown")
                    if "execution_time_ms" in step:
                        stage_lats[stg] = step["execution_time_ms"]

                meas = EvaluationMeasurement(
                    case_id=case.case_id,
                    request_id=req_id,
                    trace_id=trc_id,
                    status=status,
                    error_code=err_code,
                    error_message=err_msg,
                    stage_latencies_ms=stage_lats,
                    total_latency_ms=e2e_res.execution_time_ms or case_elapsed_ms,
                    retrieved_chunk_ids=chunk_ids,
                    reranked_chunk_ids=chunk_ids,
                    evidence_ids=evidence_ids,
                    validation_status=e2e_res.validation_status,
                    context_item_count=e2e_res.context_items_count,
                    resource_usage={},
                )
                measurements.append(meas)

            except Exception as e:
                case_elapsed_ms = round((time.perf_counter() - case_start) * 1000.0, 2)
                logger.error(f"Evaluation case '{case.case_id}' failed: {e}")
                meas = EvaluationMeasurement(
                    case_id=case.case_id,
                    request_id=req_id,
                    trace_id=trc_id,
                    status=ReliabilityStatus.SYSTEM_FAILURE,
                    error_code="EVAL_UNHANDLED_EXCEPTION",
                    error_message=str(e),
                    stage_latencies_ms={},
                    total_latency_ms=case_elapsed_ms,
                    retrieved_chunk_ids=[],
                    reranked_chunk_ids=[],
                    evidence_ids=[],
                    validation_status="INVALID",
                    context_item_count=0,
                    resource_usage={},
                )
                measurements.append(meas)

        total_elapsed_seconds = max(0.001, time.perf_counter() - start_time)

        # Calculate metrics
        quality_res = self.quality_evaluator.evaluate_quality(dataset.cases, measurements)
        perf_res = self.performance_evaluator.evaluate_performance(measurements, total_elapsed_seconds)
        rel_res = self.reliability_evaluator.evaluate_reliability(measurements)

        # Environment metadata
        env_meta = {
            "python_version": platform.python_version(),
            "os_system": platform.system(),
            "os_release": platform.release(),
            "environment": settings.environment,
        }

        # Config snapshot (without credentials)
        config_snap = {
            "embedding_provider": settings.embedding.provider,
            "embedding_model": settings.embedding.model,
            "qdrant_collection": settings.qdrant.default_collection_name,
            "rerank_provider": settings.rerank.provider,
            "rerank_model": settings.rerank.model,
            "query_processing_version": settings.query_processing.processing_version,
            "eval_version": settings.evaluation.eval_version,
        }

        return EvaluationRun(
            run_id=run_id,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version,
            timestamp=start_iso,
            knowledge_base_version="R2_R3_v1.0",
            embedding_model_version=settings.embedding.model_version,
            sparse_version="BM25_v1",
            qdrant_version="1.19.1",
            fusion_strategy_version="R7_RRF_v1",
            reranker_version=settings.rerank.model_version,
            query_processing_version=settings.query_processing.processing_version,
            model_runtime_version=settings.version,
            config_snapshot=config_snap,
            environment_metadata=env_meta,
            measurements=measurements,
            quality_metrics=quality_res,
            performance_metrics=perf_res,
            reliability_metrics=rel_res,
            status="COMPLETED",
        )
