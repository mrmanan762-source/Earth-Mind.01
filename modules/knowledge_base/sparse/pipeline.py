"""R6 Sparse Pipeline Orchestrator for EarthMind.

Coordinates end-to-end processing:
R3 Knowledge (Chunks / KnowledgeUnits)
  ↓
R6 Sparse Preparation
  ↓
R6 Sparse Representation (SparseRepresentationRecord)
  ↓
Validation
  ↓
R6 Sparse Indexing (IndexRecord -> Sparse Index Adapter)
  ↓
READY_FOR_HYBRID_RETRIEVAL

Enforces strict R4 dense embedding independence, R5 Qdrant compatibility,
idempotent synchronization, canonical lineage preservation, and zero memory writes.
"""

import time
import uuid
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from core.errors.exceptions import (
    InvalidIndexRecordError,
    InvalidSparseInputError,
    SparseExecutionError,
)
from modules.knowledge_base.canonical_models import Chunk, KnowledgeUnit
from modules.knowledge_base.enums import IndexStatus, KnowledgeLifecycleState, ProcessingStatus
from modules.knowledge_base.index.engine import KnowledgeIndexEngine
from modules.knowledge_base.index.record import IndexBatchResult, IndexRecord
from modules.knowledge_base.index.sparse_index import ISparseIndexAdapter, InvertedSparseIndexAdapter
from modules.knowledge_base.sparse.bm25_provider import BM25SparseProvider
from modules.knowledge_base.sparse.engine import KnowledgeSparseEngine, SparseBatchResult
from modules.knowledge_base.sparse.record import SparseRepresentationRecord


class R6PipelineSummary(BaseModel):
    """Pipeline execution summary for R6 Sparse Representation & Sparse Indexing."""

    pipeline_id: str = Field(..., description="Unique run identifier for sparse pipeline execution")
    lifecycle_state: KnowledgeLifecycleState = Field(
        KnowledgeLifecycleState.READY_FOR_HYBRID_RETRIEVAL, description="Final output lifecycle state"
    )
    status: ProcessingStatus = Field(ProcessingStatus.COMPLETED, description="Operational status code")
    total_submitted: int = Field(0, description="Total number of canonical entities submitted")
    represented_count: int = Field(0, description="Successfully generated sparse representations count")
    indexed_count: int = Field(0, description="Successfully indexed sparse records count")
    failed_count: int = Field(0, description="Number of items that failed processing")
    sparse_records: List[SparseRepresentationRecord] = Field(
        default_factory=list, description="Generated sparse representation records"
    )
    index_records: List[IndexRecord] = Field(
        default_factory=list, description="Generated and indexed sparse IndexRecords"
    )
    failed_details: List[Dict[str, Any]] = Field(
        default_factory=list, description="Structured failure details per item"
    )
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Pipeline latency and vocabulary stats")
    error_message: Optional[str] = Field(None, description="Global pipeline error summary if applicable")


class R6SparsePipeline:
    """Orchestrator coordinating R6 Sparse Representation & Sparse Indexing pipeline."""

    def __init__(
        self,
        sparse_engine: Optional[KnowledgeSparseEngine] = None,
        sparse_index_adapter: Optional[ISparseIndexAdapter] = None,
        index_engine: Optional[KnowledgeIndexEngine] = None,
    ):
        self.sparse_engine = sparse_engine or KnowledgeSparseEngine()
        self.sparse_index_adapter = sparse_index_adapter or InvertedSparseIndexAdapter()
        self.index_engine = index_engine or KnowledgeIndexEngine(adapter=self.sparse_index_adapter)

    def process_chunks(
        self,
        chunks: List[Chunk],
        collection_name: str = "agri_knowledge_sparse",
        pipeline_id: Optional[str] = None,
        allow_partial: bool = True,
    ) -> R6PipelineSummary:
        """Process canonical Chunks through sparse representation and sparse index layers."""
        run_id = pipeline_id or f"pipe_r6_sp_chk_{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        if not chunks:
            return R6PipelineSummary(
                pipeline_id=run_id,
                lifecycle_state=KnowledgeLifecycleState.INVALID,
                status=ProcessingStatus.FAILED,
                total_submitted=0,
                error_message="No chunks submitted for R6 sparse processing.",
            )

        # Step 1: Sparse Representation Generation
        sparse_batch_res = self.sparse_engine.generate_sparse_chunks_batch(
            chunks=chunks, batch_id=f"batch_{run_id}", allow_partial=allow_partial
        )

        if sparse_batch_res.status == ProcessingStatus.FAILED and not sparse_batch_res.records:
            return R6PipelineSummary(
                pipeline_id=run_id,
                lifecycle_state=KnowledgeLifecycleState.FAILED,
                status=ProcessingStatus.FAILED,
                total_submitted=len(chunks),
                failed_count=len(chunks),
                failed_details=sparse_batch_res.failed_items,
                error_message=sparse_batch_res.error_message or "Sparse representation generation failed.",
            )

        # Ensure target sparse collection exists
        self.sparse_index_adapter.create_collection(collection_name)

        # Step 2: Build IndexRecords from SparseRepresentationRecords
        index_records: List[IndexRecord] = []
        pipeline_failed: List[Dict[str, Any]] = list(sparse_batch_res.failed_items)

        for sp_rec in sparse_batch_res.records:
            try:
                idx_rec = self.index_engine.build_index_record(
                    sparse_record=sp_rec,
                    knowledge_collection=collection_name,
                    lifecycle_state=KnowledgeLifecycleState.READY_FOR_HYBRID_RETRIEVAL,
                )
                index_records.append(idx_rec)
            except Exception as e:
                pipeline_failed.append({
                    "chunk_id": sp_rec.chunk_id,
                    "representation_id": sp_rec.representation_id,
                    "error": f"Failed to build IndexRecord: {str(e)}",
                })

        # Step 3: Index records via Sparse Index Adapter
        indexed_records: List[IndexRecord] = []
        if index_records:
            batch_index_res = self.sparse_index_adapter.index_batch(collection_name, index_records)
            indexed_records = batch_index_res.successful_records
            for f_item in batch_index_res.failed_records:
                pipeline_failed.append({
                    "index_record_id": f_item.get("index_record_id"),
                    "error": f"Sparse indexing failed: {f_item.get('error')}",
                })

        duration = round((time.time() - start_time) * 1000, 2)
        final_lifecycle = (
            KnowledgeLifecycleState.READY_FOR_HYBRID_RETRIEVAL
            if len(indexed_records) > 0
            else KnowledgeLifecycleState.FAILED
        )

        return R6PipelineSummary(
            pipeline_id=run_id,
            lifecycle_state=final_lifecycle,
            status=ProcessingStatus.COMPLETED if indexed_records else ProcessingStatus.FAILED,
            total_submitted=len(chunks),
            represented_count=len(sparse_batch_res.records),
            indexed_count=len(indexed_records),
            failed_count=len(pipeline_failed),
            sparse_records=sparse_batch_res.records,
            index_records=indexed_records,
            failed_details=pipeline_failed,
            metrics={
                "processing_time_ms": duration,
                "provider": self.sparse_engine.adapter.get_provider_metadata().provider_name,
                "vocabulary_size": self.sparse_engine.adapter.get_vocabulary_size(),
            },
        )

    def process_knowledge_units(
        self,
        units: List[KnowledgeUnit],
        collection_name: str = "agri_knowledge_sparse",
        pipeline_id: Optional[str] = None,
        allow_partial: bool = True,
    ) -> R6PipelineSummary:
        """Process canonical KnowledgeUnits through sparse representation and sparse index layers."""
        run_id = pipeline_id or f"pipe_r6_sp_ku_{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        if not units:
            return R6PipelineSummary(
                pipeline_id=run_id,
                lifecycle_state=KnowledgeLifecycleState.INVALID,
                status=ProcessingStatus.FAILED,
                total_submitted=0,
                error_message="No knowledge units submitted for R6 sparse processing.",
            )

        # Step 1: Sparse Representation Generation
        sparse_batch_res = self.sparse_engine.generate_sparse_units_batch(
            units=units, batch_id=f"batch_{run_id}", allow_partial=allow_partial
        )

        if sparse_batch_res.status == ProcessingStatus.FAILED and not sparse_batch_res.records:
            return R6PipelineSummary(
                pipeline_id=run_id,
                lifecycle_state=KnowledgeLifecycleState.FAILED,
                status=ProcessingStatus.FAILED,
                total_submitted=len(units),
                failed_count=len(units),
                failed_details=sparse_batch_res.failed_items,
                error_message=sparse_batch_res.error_message or "Sparse representation generation failed.",
            )

        self.sparse_index_adapter.create_collection(collection_name)

        # Step 2: Build IndexRecords
        index_records: List[IndexRecord] = []
        pipeline_failed: List[Dict[str, Any]] = list(sparse_batch_res.failed_items)

        for sp_rec in sparse_batch_res.records:
            try:
                idx_rec = self.index_engine.build_index_record(
                    sparse_record=sp_rec,
                    knowledge_collection=collection_name,
                    lifecycle_state=KnowledgeLifecycleState.READY_FOR_HYBRID_RETRIEVAL,
                )
                index_records.append(idx_rec)
            except Exception as e:
                pipeline_failed.append({
                    "knowledge_unit_id": sp_rec.knowledge_unit_id,
                    "representation_id": sp_rec.representation_id,
                    "error": f"Failed to build IndexRecord: {str(e)}",
                })

        # Step 3: Index records via Sparse Index Adapter
        indexed_records: List[IndexRecord] = []
        if index_records:
            batch_index_res = self.sparse_index_adapter.index_batch(collection_name, index_records)
            indexed_records = batch_index_res.successful_records
            for f_item in batch_index_res.failed_records:
                pipeline_failed.append({
                    "index_record_id": f_item.get("index_record_id"),
                    "error": f"Sparse indexing failed: {f_item.get('error')}",
                })

        duration = round((time.time() - start_time) * 1000, 2)
        final_lifecycle = (
            KnowledgeLifecycleState.READY_FOR_HYBRID_RETRIEVAL
            if len(indexed_records) > 0
            else KnowledgeLifecycleState.FAILED
        )

        return R6PipelineSummary(
            pipeline_id=run_id,
            lifecycle_state=final_lifecycle,
            status=ProcessingStatus.COMPLETED if indexed_records else ProcessingStatus.FAILED,
            total_submitted=len(units),
            represented_count=len(sparse_batch_res.records),
            indexed_count=len(indexed_records),
            failed_count=len(pipeline_failed),
            sparse_records=sparse_batch_res.records,
            index_records=indexed_records,
            failed_details=pipeline_failed,
            metrics={
                "processing_time_ms": duration,
                "provider": self.sparse_engine.adapter.get_provider_metadata().provider_name,
                "vocabulary_size": self.sparse_engine.adapter.get_vocabulary_size(),
            },
        )
