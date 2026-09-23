"""Knowledge Sparse Representation Engine for C.2 Knowledge Base.

Converts canonical KnowledgeUnits and Chunks into traceable SparseRepresentationRecords.
Enforces:
- Provider-independent and storage-independent sparse vector generation
- Strict preservation of canonical source rule (sparse representations are derived)
- Exact version awareness and lineage traceability
- Provider, model, model-version, and vocabulary traceability
- Input order preservation during batch processing
- Explicit failure handling and partial batch failure reporting without vector fabrication
- Provenance chain integration and KnowledgeLifecycleState transitions
"""

import time
import uuid
from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from core.interfaces.sparse import ISparseRepresentationProvider
from core.schemas.embedding import EmbeddingStatus
from core.schemas.sparse import SparseRepresentationRequest
from core.errors.exceptions import (
    SparseRepresentationError,
    InvalidSparseInputError,
    SparseProviderUnavailableError,
)
from modules.knowledge_base.enums import (
    KnowledgeContentType,
    KnowledgeLifecycleState,
    ProcessingStatus,
)
from modules.knowledge_base.provenance import Provenance
from modules.knowledge_base.canonical_models import Chunk, KnowledgeUnit
from modules.knowledge_base.sparse.adapter import SparseRepresentationAdapter
from modules.knowledge_base.sparse.record import SparseRepresentationRecord


class SparseBatchResult(BaseModel):
    """Execution output for batch sparse representation operations."""

    batch_id: str = Field(..., description="Unique identifier for batch processing run")
    lifecycle_state: KnowledgeLifecycleState = Field(
        KnowledgeLifecycleState.EMBEDDED, description="Resulting lifecycle state"
    )
    records: List[SparseRepresentationRecord] = Field(
        default_factory=list, description="Successfully generated SparseRepresentationRecords"
    )
    failed_items: List[Dict[str, Any]] = Field(
        default_factory=list, description="Details of items that failed processing in the batch"
    )
    status: ProcessingStatus = Field(ProcessingStatus.COMPLETED, description="Operational status code")
    total_count: int = Field(0, description="Total number of items submitted")
    success_count: int = Field(0, description="Number of items successfully represented")
    failed_count: int = Field(0, description="Number of items that failed representation")
    error_message: Optional[str] = Field(None, description="Global failure message if entire batch failed")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Execution metrics (e.g., duration, vocabulary size)")


class KnowledgeSparseEngine:
    """Core domain engine coordinating sparse vector generation for canonical knowledge objects."""

    def __init__(
        self,
        adapter: Optional[SparseRepresentationAdapter] = None,
        provider: Optional[ISparseRepresentationProvider] = None,
    ):
        if adapter is not None:
            self._adapter = adapter
        elif provider is not None:
            self._adapter = SparseRepresentationAdapter(provider)
        else:
            self._adapter = SparseRepresentationAdapter.default_adapter()

    @property
    def adapter(self) -> SparseRepresentationAdapter:
        return self._adapter

    def set_adapter(self, adapter: SparseRepresentationAdapter) -> None:
        """Replace active sparse adapter dynamically."""
        if not isinstance(adapter, SparseRepresentationAdapter):
            raise InvalidSparseInputError("Adapter must be an instance of SparseRepresentationAdapter.")
        self._adapter = adapter

    def set_provider(self, provider: ISparseRepresentationProvider) -> None:
        """Replace active provider dynamically within the active adapter."""
        self._adapter.set_provider(provider)

    def supports_content_type(self, content_type: KnowledgeContentType) -> bool:
        """Returns True if content type can be converted to text for sparse representation."""
        if content_type in (
            KnowledgeContentType.TEXT,
            KnowledgeContentType.TABLE,
            KnowledgeContentType.STRUCTURED_DATA,
        ):
            return True
        provider_meta = self._adapter.get_provider_metadata()
        extra = provider_meta.extra or {}
        return extra.get("supports_multimodal", False)

    def extract_text_content(
        self, content: Any, content_type: KnowledgeContentType
    ) -> str:
        """Safely extracts a textual representation from canonical content payload."""
        if content is None:
            raise InvalidSparseInputError("Content payload is None.")

        if isinstance(content, str):
            trimmed = content.strip()
            if not trimmed:
                raise InvalidSparseInputError("Text content payload is empty or whitespace.")
            return trimmed

        if isinstance(content, dict):
            try:
                return json.dumps(content, ensure_ascii=False)
            except Exception as e:
                raise InvalidSparseInputError(f"Failed to serialize structured dict content to string: {e}")

        if isinstance(content, (list, tuple)):
            try:
                return json.dumps(content, ensure_ascii=False)
            except Exception as e:
                raise InvalidSparseInputError(f"Failed to serialize list content to string: {e}")

        if content_type in (KnowledgeContentType.IMAGE, KnowledgeContentType.FIGURE, KnowledgeContentType.MULTIMODAL):
            raise InvalidSparseInputError(
                f"Unsupported raw non-text content type '{content_type.value}'. Multimodal sparse provider is required."
            )

        return str(content)

    def _create_sparse_provenance(
        self,
        base_provenance: Optional[Provenance],
        entity_type: str,
        entity_id: str,
        source_id: str,
        document_id: str,
        version_id: str,
        representation_id: str,
        knowledge_unit_id: Optional[str] = None,
    ) -> Provenance:
        """Creates or enriches provenance record for sparse representation step."""
        prov = (
            base_provenance.model_copy(deep=True)
            if base_provenance
            else Provenance(
                provenance_id=f"prov_sp_{entity_id}",
                source_id=source_id,
                document_id=document_id,
                version_id=version_id,
                chunk_id=entity_id if entity_type == "chunk" else None,
                knowledge_unit_id=knowledge_unit_id if entity_type == "chunk" else (entity_id if entity_type == "knowledge_unit" else None),
            )
        )

        if entity_type == "chunk":
            prov.chunk_id = entity_id
            if knowledge_unit_id:
                prov.knowledge_unit_id = knowledge_unit_id
        elif entity_type == "knowledge_unit":
            prov.knowledge_unit_id = entity_id

        prov_meta = self._adapter.get_provider_metadata()
        model_meta = self._adapter.get_model_metadata()

        prov.processing_stage = "SPARSE_REPRESENTATION"
        prov.processing_operation = "SPARSE_VECTOR_GENERATION"
        prov.representation_provider = {
            "representation_id": representation_id,
            "provider_name": prov_meta.provider_name,
            "provider_type": prov_meta.provider_type,
            "model_name": model_meta.model_name,
            "model_version": model_meta.model_version,
            "vocabulary_id": self._adapter.get_vocabulary_id(),
            "vocabulary_size": self._adapter.get_vocabulary_size(),
            "is_mock": prov_meta.is_mock,
        }

        step = {
            "step_id": f"step_sparse_{uuid.uuid4().hex[:8]}",
            "operation": "SPARSE_GENERATION",
            "processor_name": self.__class__.__name__,
            "parameters": {
                "provider": prov_meta.provider_name,
                "model": model_meta.model_name,
                "model_version": model_meta.model_version,
                "vocabulary_id": self._adapter.get_vocabulary_id(),
                "vocabulary_size": self._adapter.get_vocabulary_size(),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "COMPLETED",
        }
        prov.processing_steps.append(step)
        return prov

    def generate_sparse_chunk(
        self,
        chunk: Chunk,
        custom_representation_id: Optional[str] = None,
    ) -> SparseRepresentationRecord:
        """Generates derived SparseRepresentationRecord for a single canonical Chunk."""
        if not self.supports_content_type(chunk.content_type):
            raise InvalidSparseInputError(
                f"Unsupported raw non-text content type '{chunk.content_type.value}'. Multimodal sparse provider is required."
            )

        text_content = self.extract_text_content(chunk.content, chunk.content_type)
        sp_id = custom_representation_id or f"sp_chk_{chunk.chunk_id}_{uuid.uuid4().hex[:8]}"

        response = self._adapter.generate_sparse_texts(
            texts=[text_content],
            chunk_ids=[chunk.chunk_id],
            source_id=chunk.document_id,
            vocabulary_id=self._adapter.get_vocabulary_id(),
        )

        prov_meta = self._adapter.get_provider_metadata()
        model_meta = self._adapter.get_model_metadata()

        sp_prov = self._create_sparse_provenance(
            base_provenance=chunk.provenance,
            entity_type="chunk",
            entity_id=chunk.chunk_id,
            source_id=chunk.document_id,
            document_id=chunk.document_id,
            version_id=chunk.version_id,
            representation_id=sp_id,
            knowledge_unit_id=chunk.knowledge_unit_id,
        )

        sparse_vec = response.sparse_vectors[0]

        record = SparseRepresentationRecord(
            representation_id=sp_id,
            source_id=chunk.document_id,
            document_id=chunk.document_id,
            version_id=chunk.version_id,
            chunk_id=chunk.chunk_id,
            knowledge_unit_id=chunk.knowledge_unit_id,
            representation_type="SPARSE",
            provider=prov_meta.provider_name,
            model=model_meta.model_name,
            model_version=model_meta.model_version,
            vocabulary_id=self._adapter.get_vocabulary_id(),
            vocabulary_size=self._adapter.get_vocabulary_size(),
            sparse_vector=sparse_vec,
            content_type=chunk.content_type,
            status="ACTIVE",
            metadata=chunk.metadata if isinstance(chunk.metadata, dict) else {},
            provenance=sp_prov,
        )
        return record

    def generate_sparse_knowledge_unit(
        self,
        unit: KnowledgeUnit,
        custom_representation_id: Optional[str] = None,
    ) -> SparseRepresentationRecord:
        """Generates derived SparseRepresentationRecord for a single canonical KnowledgeUnit."""
        if not self.supports_content_type(unit.content_type):
            raise InvalidSparseInputError(
                f"Unsupported raw non-text content type '{unit.content_type.value}'. Multimodal sparse provider is required."
            )

        text_content = self.extract_text_content(unit.content, unit.content_type)
        sp_id = custom_representation_id or f"sp_ku_{unit.knowledge_unit_id}_{uuid.uuid4().hex[:8]}"

        response = self._adapter.generate_sparse_texts(
            texts=[text_content],
            chunk_ids=[unit.knowledge_unit_id],
            source_id=unit.document_id,
            vocabulary_id=self._adapter.get_vocabulary_id(),
        )

        prov_meta = self._adapter.get_provider_metadata()
        model_meta = self._adapter.get_model_metadata()

        sp_prov = self._create_sparse_provenance(
            base_provenance=unit.provenance,
            entity_type="knowledge_unit",
            entity_id=unit.knowledge_unit_id,
            source_id=unit.document_id,
            document_id=unit.document_id,
            version_id=unit.version_id,
            representation_id=sp_id,
        )

        sparse_vec = response.sparse_vectors[0]

        record = SparseRepresentationRecord(
            representation_id=sp_id,
            source_id=unit.document_id,
            document_id=unit.document_id,
            version_id=unit.version_id,
            chunk_id=None,
            knowledge_unit_id=unit.knowledge_unit_id,
            representation_type="SPARSE",
            provider=prov_meta.provider_name,
            model=model_meta.model_name,
            model_version=model_meta.model_version,
            vocabulary_id=self._adapter.get_vocabulary_id(),
            vocabulary_size=self._adapter.get_vocabulary_size(),
            sparse_vector=sparse_vec,
            content_type=unit.content_type,
            status="ACTIVE",
            metadata=unit.metadata if isinstance(unit.metadata, dict) else {},
            provenance=sp_prov,
        )
        return record

    def generate_sparse_chunks_batch(
        self,
        chunks: List[Chunk],
        batch_id: Optional[str] = None,
        allow_partial: bool = True,
    ) -> SparseBatchResult:
        """Batch sparse representation generation for Chunks preserving input order and handling partial failures."""
        run_batch_id = batch_id or f"batch_sp_chk_{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        if not chunks:
            return SparseBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.INVALID,
                status=ProcessingStatus.FAILED,
                total_count=0,
                error_message="Empty chunks list provided for batch sparse representation.",
            )

        if not self._adapter.is_available():
            prov_name = self._adapter.get_provider_metadata().provider_name
            return SparseBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.FAILED,
                status=ProcessingStatus.FAILED,
                total_count=len(chunks),
                failed_count=len(chunks),
                failed_items=[
                    {
                        "index": idx,
                        "chunk_id": chk.chunk_id,
                        "error": f"Provider '{prov_name}' unavailable.",
                    }
                    for idx, chk in enumerate(chunks)
                ],
                error_message=f"Sparse provider '{prov_name}' is unavailable.",
            )

        valid_indices: List[int] = []
        valid_texts: List[str] = []
        valid_chunk_ids: List[str] = []
        failed_items: List[Dict[str, Any]] = []

        for idx, chk in enumerate(chunks):
            if not isinstance(chk, Chunk):
                failed_items.append({
                    "index": idx,
                    "chunk_id": getattr(chk, "chunk_id", None),
                    "error": "Item is not a valid Chunk instance.",
                })
                continue

            if not self.supports_content_type(chk.content_type):
                failed_items.append({
                    "index": idx,
                    "chunk_id": chk.chunk_id,
                    "content_type": chk.content_type.value,
                    "error": f"Unsupported content type '{chk.content_type.value}'.",
                })
                continue

            try:
                text_content = self.extract_text_content(chk.content, chk.content_type)
                valid_indices.append(idx)
                valid_texts.append(text_content)
                valid_chunk_ids.append(chk.chunk_id)
            except Exception as e:
                failed_items.append({
                    "index": idx,
                    "chunk_id": chk.chunk_id,
                    "error": f"Content extraction failed: {str(e)}",
                })

        if not allow_partial and failed_items:
            return SparseBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.FAILED,
                status=ProcessingStatus.FAILED,
                total_count=len(chunks),
                failed_count=len(failed_items),
                failed_items=failed_items,
                error_message="Batch processing failed due to invalid items and allow_partial=False.",
            )

        if not valid_texts:
            return SparseBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.FAILED,
                status=ProcessingStatus.FAILED,
                total_count=len(chunks),
                failed_count=len(chunks),
                failed_items=failed_items,
                error_message="No valid chunks to generate sparse representations in batch.",
            )

        try:
            req = SparseRepresentationRequest(
                texts=valid_texts,
                chunk_ids=valid_chunk_ids,
                vocabulary_id=self._adapter.get_vocabulary_id(),
            )
            response = self._adapter.generate_sparse(req)
        except Exception as e:
            return SparseBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.FAILED,
                status=ProcessingStatus.FAILED,
                total_count=len(chunks),
                failed_count=len(chunks),
                failed_items=[
                    {
                        "index": idx,
                        "chunk_id": chk.chunk_id,
                        "error": str(e),
                    }
                    for idx, chk in enumerate(chunks)
                ],
                error_message=f"Provider sparse execution failed: {str(e)}",
            )

        prov_meta = self._adapter.get_provider_metadata()
        model_meta = self._adapter.get_model_metadata()

        records: List[SparseRepresentationRecord] = []
        for i, original_idx in enumerate(valid_indices):
            chk = chunks[original_idx]
            sp_id = f"sp_chk_{chk.chunk_id}_{uuid.uuid4().hex[:8]}"

            sp_prov = self._create_sparse_provenance(
                base_provenance=chk.provenance,
                entity_type="chunk",
                entity_id=chk.chunk_id,
                source_id=chk.document_id,
                document_id=chk.document_id,
                version_id=chk.version_id,
                representation_id=sp_id,
                knowledge_unit_id=chk.knowledge_unit_id,
            )

            sparse_vec = response.sparse_vectors[i]

            rec = SparseRepresentationRecord(
                representation_id=sp_id,
                source_id=chk.document_id,
                document_id=chk.document_id,
                version_id=chk.version_id,
                chunk_id=chk.chunk_id,
                knowledge_unit_id=chk.knowledge_unit_id,
                representation_type="SPARSE",
                provider=prov_meta.provider_name,
                model=model_meta.model_name,
                model_version=model_meta.model_version,
                vocabulary_id=self._adapter.get_vocabulary_id(),
                vocabulary_size=self._adapter.get_vocabulary_size(),
                sparse_vector=sparse_vec,
                content_type=chk.content_type,
                status="ACTIVE",
                metadata=chk.metadata if isinstance(chk.metadata, dict) else {},
                provenance=sp_prov,
            )
            records.append(rec)

        duration = round((time.time() - start_time) * 1000, 2)
        lifecycle = (
            KnowledgeLifecycleState.EMBEDDED
            if len(records) > 0
            else KnowledgeLifecycleState.FAILED
        )

        return SparseBatchResult(
            batch_id=run_batch_id,
            lifecycle_state=lifecycle,
            records=records,
            failed_items=failed_items,
            status=ProcessingStatus.COMPLETED,
            total_count=len(chunks),
            success_count=len(records),
            failed_count=len(failed_items),
            metrics={
                "processing_time_ms": duration,
                "vocabulary_size": self._adapter.get_vocabulary_size(),
            },
        )

    def generate_sparse_units_batch(
        self,
        units: List[KnowledgeUnit],
        batch_id: Optional[str] = None,
        allow_partial: bool = True,
    ) -> SparseBatchResult:
        """Batch sparse representation generation for KnowledgeUnits preserving input order and handling partial failures."""
        run_batch_id = batch_id or f"batch_sp_ku_{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        if not units:
            return SparseBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.INVALID,
                status=ProcessingStatus.FAILED,
                total_count=0,
                error_message="Empty units list provided for batch sparse representation.",
            )

        if not self._adapter.is_available():
            prov_name = self._adapter.get_provider_metadata().provider_name
            return SparseBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.FAILED,
                status=ProcessingStatus.FAILED,
                total_count=len(units),
                failed_count=len(units),
                failed_items=[
                    {
                        "index": idx,
                        "unit_id": ku.knowledge_unit_id,
                        "error": f"Provider '{prov_name}' unavailable.",
                    }
                    for idx, ku in enumerate(units)
                ],
                error_message=f"Sparse provider '{prov_name}' is unavailable.",
            )

        valid_indices: List[int] = []
        valid_texts: List[str] = []
        valid_unit_ids: List[str] = []
        failed_items: List[Dict[str, Any]] = []

        for idx, ku in enumerate(units):
            if not isinstance(ku, KnowledgeUnit):
                failed_items.append({
                    "index": idx,
                    "unit_id": getattr(ku, "knowledge_unit_id", None),
                    "error": "Item is not a valid KnowledgeUnit instance.",
                })
                continue

            if not self.supports_content_type(ku.content_type):
                failed_items.append({
                    "index": idx,
                    "unit_id": ku.knowledge_unit_id,
                    "content_type": ku.content_type.value,
                    "error": f"Unsupported content type '{ku.content_type.value}'.",
                })
                continue

            try:
                text_content = self.extract_text_content(ku.content, ku.content_type)
                valid_indices.append(idx)
                valid_texts.append(text_content)
                valid_unit_ids.append(ku.knowledge_unit_id)
            except Exception as e:
                failed_items.append({
                    "index": idx,
                    "unit_id": ku.knowledge_unit_id,
                    "error": f"Content extraction failed: {str(e)}",
                })

        if not allow_partial and failed_items:
            return SparseBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.FAILED,
                status=ProcessingStatus.FAILED,
                total_count=len(units),
                failed_count=len(failed_items),
                failed_items=failed_items,
                error_message="Batch processing failed due to invalid items and allow_partial=False.",
            )

        if not valid_texts:
            return SparseBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.FAILED,
                status=ProcessingStatus.FAILED,
                total_count=len(units),
                failed_count=len(units),
                failed_items=failed_items,
                error_message="No valid knowledge units to generate sparse representations in batch.",
            )

        try:
            req = SparseRepresentationRequest(
                texts=valid_texts,
                chunk_ids=valid_unit_ids,
                vocabulary_id=self._adapter.get_vocabulary_id(),
            )
            response = self._adapter.generate_sparse(req)
        except Exception as e:
            return SparseBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.FAILED,
                status=ProcessingStatus.FAILED,
                total_count=len(units),
                failed_count=len(units),
                failed_items=[
                    {
                        "index": idx,
                        "unit_id": ku.knowledge_unit_id,
                        "error": str(e),
                    }
                    for idx, ku in enumerate(units)
                ],
                error_message=f"Provider sparse execution failed: {str(e)}",
            )

        prov_meta = self._adapter.get_provider_metadata()
        model_meta = self._adapter.get_model_metadata()

        records: List[SparseRepresentationRecord] = []
        for i, original_idx in enumerate(valid_indices):
            ku = units[original_idx]
            sp_id = f"sp_ku_{ku.knowledge_unit_id}_{uuid.uuid4().hex[:8]}"

            sp_prov = self._create_sparse_provenance(
                base_provenance=ku.provenance,
                entity_type="knowledge_unit",
                entity_id=ku.knowledge_unit_id,
                source_id=ku.document_id,
                document_id=ku.document_id,
                version_id=ku.version_id,
                representation_id=sp_id,
            )

            sparse_vec = response.sparse_vectors[i]

            rec = SparseRepresentationRecord(
                representation_id=sp_id,
                source_id=ku.document_id,
                document_id=ku.document_id,
                version_id=ku.version_id,
                chunk_id=None,
                knowledge_unit_id=ku.knowledge_unit_id,
                representation_type="SPARSE",
                provider=prov_meta.provider_name,
                model=model_meta.model_name,
                model_version=model_meta.model_version,
                vocabulary_id=self._adapter.get_vocabulary_id(),
                vocabulary_size=self._adapter.get_vocabulary_size(),
                sparse_vector=sparse_vec,
                content_type=ku.content_type,
                status="ACTIVE",
                metadata=ku.metadata if isinstance(ku.metadata, dict) else {},
                provenance=sp_prov,
            )
            records.append(rec)

        duration = round((time.time() - start_time) * 1000, 2)
        lifecycle = (
            KnowledgeLifecycleState.EMBEDDED
            if len(records) > 0
            else KnowledgeLifecycleState.FAILED
        )

        return SparseBatchResult(
            batch_id=run_batch_id,
            lifecycle_state=lifecycle,
            records=records,
            failed_items=failed_items,
            status=ProcessingStatus.COMPLETED,
            total_count=len(units),
            success_count=len(records),
            failed_count=len(failed_items),
            metrics={
                "processing_time_ms": duration,
                "vocabulary_size": self._adapter.get_vocabulary_size(),
            },
        )

    def regenerate_sparse(
        self,
        target: Union[Chunk, KnowledgeUnit],
        previous_record: Optional[SparseRepresentationRecord] = None,
    ) -> SparseRepresentationRecord:
        """Regenerates a new SparseRepresentationRecord for a canonical object without mutating canonical source.

        Updates historical provenance traceability on canonical target.
        """
        prov_meta = self._adapter.get_provider_metadata()

        if hasattr(target, "provenance") and target.provenance is not None:
            target.provenance.update_representation_provider(
                provider_info={
                    "provider_name": prov_meta.provider_name,
                    "previous_representation_id": previous_record.representation_id if previous_record else None,
                    "action": "REGENERATE_SPARSE_REPRESENTATION",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                updated_by=self.__class__.__name__,
            )

        if previous_record is not None:
            previous_record.status = "SUPERSEDED"

        if isinstance(target, Chunk):
            return self.generate_sparse_chunk(target)
        elif isinstance(target, KnowledgeUnit):
            return self.generate_sparse_knowledge_unit(target)
        else:
            raise InvalidSparseInputError(
                f"Target object must be Chunk or KnowledgeUnit, received {type(target)}."
            )
