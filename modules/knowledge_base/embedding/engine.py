"""Knowledge Embedding Engine and Pipeline for C.2 Knowledge Base.

Converts canonical KnowledgeUnits and Chunks into traceable EmbeddingRecords.
Enforces:
- Provider-independent and storage-independent vector generation
- Strict preservation of canonical source rule (embeddings are derived)
- Version awareness and exact lineage traceability
- Provider, model, and model-version traceability
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

from core.config.settings import settings
from core.interfaces.embedding import IEmbeddingProvider
from core.schemas.embedding import (
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingStatus,
)
from core.errors.exceptions import (
    EmbeddingError,
    InvalidEmbeddingInputError,
    EmbeddingProviderUnavailableError,
)
from modules.knowledge_base.enums import (
    KnowledgeContentType,
    KnowledgeLifecycleState,
    ProcessingStatus,
)
from modules.knowledge_base.provenance import ProcessingStep, Provenance
from modules.knowledge_base.canonical_models import Chunk, KnowledgeUnit
from modules.knowledge_base.embedding.adapter import EmbeddingAdapter
from modules.knowledge_base.embedding.record import EmbeddingRecord


class EmbeddingBatchResult(BaseModel):
    """Execution output for batch embedding operations."""

    batch_id: str = Field(..., description="Unique identifier for batch processing run")
    lifecycle_state: KnowledgeLifecycleState = Field(
        KnowledgeLifecycleState.EMBEDDED, description="Resulting lifecycle state"
    )
    records: List[EmbeddingRecord] = Field(default_factory=list, description="Successfully generated EmbeddingRecords")
    failed_items: List[Dict[str, Any]] = Field(
        default_factory=list, description="Details of items that failed processing in the batch"
    )
    status: ProcessingStatus = Field(ProcessingStatus.COMPLETED, description="Operational status code")
    total_count: int = Field(0, description="Total number of items submitted")
    success_count: int = Field(0, description="Number of items successfully embedded")
    failed_count: int = Field(0, description="Number of items that failed embedding")
    error_message: Optional[str] = Field(None, description="Global failure message if entire batch failed")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Execution metrics (e.g., duration, token counts)")


class KnowledgeEmbeddingEngine:
    """Core domain engine coordinating vector generation for canonical knowledge objects."""

    def __init__(
        self,
        adapter: Optional[EmbeddingAdapter] = None,
        provider: Optional[IEmbeddingProvider] = None,
    ):
        if adapter is not None:
            self._adapter = adapter
        elif provider is not None:
            self._adapter = EmbeddingAdapter(provider)
        else:
            self._adapter = EmbeddingAdapter.from_config(settings.embedding)

    @property
    def adapter(self) -> EmbeddingAdapter:
        return self._adapter

    def set_adapter(self, adapter: EmbeddingAdapter) -> None:
        """Replace active embedding adapter dynamically."""
        if not isinstance(adapter, EmbeddingAdapter):
            raise InvalidEmbeddingInputError("Adapter must be an instance of EmbeddingAdapter.")
        self._adapter = adapter

    def set_provider(self, provider: IEmbeddingProvider) -> None:
        """Replace active provider dynamically within the active adapter."""
        self._adapter.set_provider(provider)

    def supports_content_type(self, content_type: KnowledgeContentType) -> bool:
        """Returns True if the active provider supports generating embeddings for the content type."""
        # Standard text-compatible content types
        if content_type in (
            KnowledgeContentType.TEXT,
            KnowledgeContentType.TABLE,
            KnowledgeContentType.STRUCTURED_DATA,
        ):
            return True
        # For raw binary IMAGE, FIGURE, or MULTIMODAL without multimodal provider
        provider_meta = self._adapter.get_provider_metadata()
        extra = provider_meta.extra or {}
        return extra.get("supports_multimodal", False)

    def extract_text_content(
        self, content: Any, content_type: KnowledgeContentType
    ) -> str:
        """Safely extracts a textual representation from canonical content payload."""
        if content is None:
            raise InvalidEmbeddingInputError("Content payload is None.")

        if isinstance(content, str):
            trimmed = content.strip()
            if not trimmed:
                raise InvalidEmbeddingInputError("Text content payload is empty or whitespace.")
            return trimmed

        if isinstance(content, dict):
            # Convert dictionary to JSON string
            try:
                return json.dumps(content, ensure_ascii=False)
            except Exception as e:
                raise InvalidEmbeddingInputError(f"Failed to serialize structured dict content to string: {e}")

        if isinstance(content, (list, tuple)):
            try:
                return json.dumps(content, ensure_ascii=False)
            except Exception as e:
                raise InvalidEmbeddingInputError(f"Failed to serialize list content to string: {e}")

        # Non-textual binary content (e.g. bytes, media references)
        if content_type in (KnowledgeContentType.IMAGE, KnowledgeContentType.FIGURE, KnowledgeContentType.MULTIMODAL):
            raise InvalidEmbeddingInputError(
                f"Unsupported raw non-text content type '{content_type.value}'. Multimodal vector provider is required."
            )

        return str(content)

    def _create_embedding_provenance(
        self,
        base_provenance: Optional[Provenance],
        entity_type: str,
        entity_id: str,
        source_id: str,
        document_id: str,
        version_id: str,
        embedding_id: str,
        knowledge_unit_id: Optional[str] = None,
    ) -> Provenance:
        """Creates or enriches provenance record for embedding generation step."""
        prov = (
            base_provenance.model_copy(deep=True)
            if base_provenance
            else Provenance(
                provenance_id=f"prov_emb_{entity_id}",
                source_id=source_id,
                document_id=document_id,
                version_id=version_id,
                chunk_id=entity_id if entity_type == "chunk" else None,
                knowledge_unit_id=knowledge_unit_id if entity_type == "chunk" else (entity_id if entity_type == "knowledge_unit" else None),
            )
        )

        # Ensure lineage references are set if base_provenance was copied
        if entity_type == "chunk":
            prov.chunk_id = entity_id
            if knowledge_unit_id:
                prov.knowledge_unit_id = knowledge_unit_id
        elif entity_type == "knowledge_unit":
            prov.knowledge_unit_id = entity_id

        prov_meta = self._adapter.get_provider_metadata()
        model_meta = self._adapter.get_model_metadata()

        prov.processing_stage = "EMBEDDING"
        prov.processing_operation = "VECTOR_GENERATION"
        prov.representation_provider = {
            "embedding_id": embedding_id,
            "provider_name": prov_meta.provider_name,
            "provider_type": prov_meta.provider_type,
            "model_name": model_meta.model_name,
            "model_version": model_meta.model_version,
            "dimension": self._adapter.get_dimension(),
            "is_mock": prov_meta.is_mock,
        }

        step = {
            "step_id": f"step_embed_{uuid.uuid4().hex[:8]}",
            "operation": "EMBEDDING_GENERATION",
            "processor_name": self.__class__.__name__,
            "parameters": {
                "provider": prov_meta.provider_name,
                "model": model_meta.model_name,
                "model_version": model_meta.model_version,
                "dimension": self._adapter.get_dimension(),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "COMPLETED",
        }
        prov.processing_steps.append(step)
        return prov

    def embed_chunk(
        self,
        chunk: Chunk,
        include_sparse: bool = False,
        custom_embedding_id: Optional[str] = None,
    ) -> EmbeddingRecord:
        """Generates derived EmbeddingRecord for a single canonical Chunk."""
        if not self.supports_content_type(chunk.content_type):
            raise InvalidEmbeddingInputError(
                f"Unsupported raw non-text content type '{chunk.content_type.value}'. Multimodal vector provider is required."
            )

        text_content = self.extract_text_content(chunk.content, chunk.content_type)
        emb_id = custom_embedding_id or f"emb_chk_{chunk.chunk_id}_{uuid.uuid4().hex[:8]}"

        response = self._adapter.embed_texts(
            texts=[text_content],
            chunk_ids=[chunk.chunk_id],
            source_id=chunk.document_id,
            include_sparse=include_sparse,
        )

        prov_meta = self._adapter.get_provider_metadata()
        model_meta = self._adapter.get_model_metadata()

        emb_prov = self._create_embedding_provenance(
            base_provenance=chunk.provenance,
            entity_type="chunk",
            entity_id=chunk.chunk_id,
            source_id=chunk.document_id,
            document_id=chunk.document_id,
            version_id=chunk.version_id,
            embedding_id=emb_id,
            knowledge_unit_id=chunk.knowledge_unit_id,
        )

        dense_vec = response.embeddings[0] if response.embeddings else None
        sparse_vec = response.sparse_vectors[0] if response.sparse_vectors else None

        record = EmbeddingRecord(
            embedding_id=emb_id,
            source_id=chunk.document_id,
            document_id=chunk.document_id,
            version_id=chunk.version_id,
            chunk_id=chunk.chunk_id,
            knowledge_unit_id=chunk.knowledge_unit_id,
            representation_type="HYBRID" if sparse_vec else "DENSE",
            provider=prov_meta.provider_name,
            model=model_meta.model_name,
            model_version=model_meta.model_version,
            dimension=response.dimension,
            dense_vector=dense_vec,
            sparse_vector=sparse_vec,
            content_type=chunk.content_type,
            status="ACTIVE",
            metadata=chunk.metadata if isinstance(chunk.metadata, dict) else {},
            provenance=emb_prov,
        )
        return record

    def embed_knowledge_unit(
        self,
        unit: KnowledgeUnit,
        include_sparse: bool = False,
        custom_embedding_id: Optional[str] = None,
    ) -> EmbeddingRecord:
        """Generates derived EmbeddingRecord for a single canonical KnowledgeUnit."""
        if not self.supports_content_type(unit.content_type):
            raise InvalidEmbeddingInputError(
                f"Unsupported raw non-text content type '{unit.content_type.value}'. Multimodal vector provider is required."
            )

        text_content = self.extract_text_content(unit.content, unit.content_type)
        emb_id = custom_embedding_id or f"emb_ku_{unit.knowledge_unit_id}_{uuid.uuid4().hex[:8]}"

        response = self._adapter.embed_texts(
            texts=[text_content],
            chunk_ids=[unit.knowledge_unit_id],
            source_id=unit.document_id,
            include_sparse=include_sparse,
        )

        prov_meta = self._adapter.get_provider_metadata()
        model_meta = self._adapter.get_model_metadata()

        emb_prov = self._create_embedding_provenance(
            base_provenance=unit.provenance,
            entity_type="knowledge_unit",
            entity_id=unit.knowledge_unit_id,
            source_id=unit.document_id,
            document_id=unit.document_id,
            version_id=unit.version_id,
            embedding_id=emb_id,
        )

        dense_vec = response.embeddings[0] if response.embeddings else None
        sparse_vec = response.sparse_vectors[0] if response.sparse_vectors else None

        record = EmbeddingRecord(
            embedding_id=emb_id,
            source_id=unit.document_id,
            document_id=unit.document_id,
            version_id=unit.version_id,
            chunk_id=None,
            knowledge_unit_id=unit.knowledge_unit_id,
            representation_type="HYBRID" if sparse_vec else "DENSE",
            provider=prov_meta.provider_name,
            model=model_meta.model_name,
            model_version=model_meta.model_version,
            dimension=response.dimension,
            dense_vector=dense_vec,
            sparse_vector=sparse_vec,
            content_type=unit.content_type,
            status="ACTIVE",
            metadata=unit.metadata if isinstance(unit.metadata, dict) else {},
            provenance=emb_prov,
        )
        return record

    def embed_chunks_batch(
        self,
        chunks: List[Chunk],
        include_sparse: bool = False,
        batch_id: Optional[str] = None,
        allow_partial: bool = True,
    ) -> EmbeddingBatchResult:
        """Batch embedding execution for Chunks preserving input order and handling partial failures."""
        run_batch_id = batch_id or f"batch_chk_{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        if not chunks:
            return EmbeddingBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.INVALID,
                status=ProcessingStatus.FAILED,
                total_count=0,
                error_message="Empty chunks list provided for batch embedding.",
            )

        if not self._adapter.is_available():
            prov_name = self._adapter.get_provider_metadata().provider_name
            return EmbeddingBatchResult(
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
                error_message=f"Embedding provider '{prov_name}' is unavailable.",
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
            return EmbeddingBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.FAILED,
                status=ProcessingStatus.FAILED,
                total_count=len(chunks),
                failed_count=len(failed_items),
                failed_items=failed_items,
                error_message="Batch processing failed due to invalid items and allow_partial=False.",
            )

        if not valid_texts:
            return EmbeddingBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.FAILED,
                status=ProcessingStatus.FAILED,
                total_count=len(chunks),
                failed_count=len(chunks),
                failed_items=failed_items,
                error_message="No valid chunks to embed in batch.",
            )

        try:
            req = EmbeddingRequest(
                texts=valid_texts,
                chunk_ids=valid_chunk_ids,
                include_sparse=include_sparse,
            )
            response = self._adapter.embed(req)
        except EmbeddingError as e:
            return EmbeddingBatchResult(
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
                error_message=f"Provider embedding execution failed: {str(e)}",
            )

        prov_meta = self._adapter.get_provider_metadata()
        model_meta = self._adapter.get_model_metadata()

        records: List[EmbeddingRecord] = []
        for i, original_idx in enumerate(valid_indices):
            chk = chunks[original_idx]
            emb_id = f"emb_chk_{chk.chunk_id}_{uuid.uuid4().hex[:8]}"

            emb_prov = self._create_embedding_provenance(
                base_provenance=chk.provenance,
                entity_type="chunk",
                entity_id=chk.chunk_id,
                source_id=chk.document_id,
                document_id=chk.document_id,
                version_id=chk.version_id,
                embedding_id=emb_id,
                knowledge_unit_id=chk.knowledge_unit_id,
            )

            dense_vec = response.embeddings[i] if i < len(response.embeddings) else None
            sparse_vec = (
                response.sparse_vectors[i]
                if response.sparse_vectors and i < len(response.sparse_vectors)
                else None
            )

            rec = EmbeddingRecord(
                embedding_id=emb_id,
                source_id=chk.document_id,
                document_id=chk.document_id,
                version_id=chk.version_id,
                chunk_id=chk.chunk_id,
                knowledge_unit_id=chk.knowledge_unit_id,
                representation_type="HYBRID" if sparse_vec else "DENSE",
                provider=prov_meta.provider_name,
                model=model_meta.model_name,
                model_version=model_meta.model_version,
                dimension=response.dimension,
                dense_vector=dense_vec,
                sparse_vector=sparse_vec,
                content_type=chk.content_type,
                status="ACTIVE",
                metadata=chk.metadata if isinstance(chk.metadata, dict) else {},
                provenance=emb_prov,
            )
            records.append(rec)

        duration = round((time.time() - start_time) * 1000, 2)
        lifecycle = (
            KnowledgeLifecycleState.EMBEDDED
            if len(records) > 0
            else KnowledgeLifecycleState.FAILED
        )

        return EmbeddingBatchResult(
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
                "dimension": response.dimension,
            },
        )

    def embed_units_batch(
        self,
        units: List[KnowledgeUnit],
        include_sparse: bool = False,
        batch_id: Optional[str] = None,
        allow_partial: bool = True,
    ) -> EmbeddingBatchResult:
        """Batch embedding execution for KnowledgeUnits preserving input order and handling partial failures."""
        run_batch_id = batch_id or f"batch_ku_{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        if not units:
            return EmbeddingBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.INVALID,
                status=ProcessingStatus.FAILED,
                total_count=0,
                error_message="Empty units list provided for batch embedding.",
            )

        if not self._adapter.is_available():
            prov_name = self._adapter.get_provider_metadata().provider_name
            return EmbeddingBatchResult(
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
                error_message=f"Embedding provider '{prov_name}' is unavailable.",
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
            return EmbeddingBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.FAILED,
                status=ProcessingStatus.FAILED,
                total_count=len(units),
                failed_count=len(failed_items),
                failed_items=failed_items,
                error_message="Batch processing failed due to invalid items and allow_partial=False.",
            )

        if not valid_texts:
            return EmbeddingBatchResult(
                batch_id=run_batch_id,
                lifecycle_state=KnowledgeLifecycleState.FAILED,
                status=ProcessingStatus.FAILED,
                total_count=len(units),
                failed_count=len(units),
                failed_items=failed_items,
                error_message="No valid knowledge units to embed in batch.",
            )

        try:
            req = EmbeddingRequest(
                texts=valid_texts,
                chunk_ids=valid_unit_ids,
                include_sparse=include_sparse,
            )
            response = self._adapter.embed(req)
        except EmbeddingError as e:
            return EmbeddingBatchResult(
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
                error_message=f"Provider embedding execution failed: {str(e)}",
            )

        prov_meta = self._adapter.get_provider_metadata()
        model_meta = self._adapter.get_model_metadata()

        records: List[EmbeddingRecord] = []
        for i, original_idx in enumerate(valid_indices):
            ku = units[original_idx]
            emb_id = f"emb_ku_{ku.knowledge_unit_id}_{uuid.uuid4().hex[:8]}"

            emb_prov = self._create_embedding_provenance(
                base_provenance=ku.provenance,
                entity_type="knowledge_unit",
                entity_id=ku.knowledge_unit_id,
                source_id=ku.document_id,
                document_id=ku.document_id,
                version_id=ku.version_id,
                embedding_id=emb_id,
            )

            dense_vec = response.embeddings[i] if i < len(response.embeddings) else None
            sparse_vec = (
                response.sparse_vectors[i]
                if response.sparse_vectors and i < len(response.sparse_vectors)
                else None
            )

            rec = EmbeddingRecord(
                embedding_id=emb_id,
                source_id=ku.document_id,
                document_id=ku.document_id,
                version_id=ku.version_id,
                chunk_id=None,
                knowledge_unit_id=ku.knowledge_unit_id,
                representation_type="HYBRID" if sparse_vec else "DENSE",
                provider=prov_meta.provider_name,
                model=model_meta.model_name,
                model_version=model_meta.model_version,
                dimension=response.dimension,
                dense_vector=dense_vec,
                sparse_vector=sparse_vec,
                content_type=ku.content_type,
                status="ACTIVE",
                metadata=ku.metadata if isinstance(ku.metadata, dict) else {},
                provenance=emb_prov,
            )
            records.append(rec)

        duration = round((time.time() - start_time) * 1000, 2)
        lifecycle = (
            KnowledgeLifecycleState.EMBEDDED
            if len(records) > 0
            else KnowledgeLifecycleState.FAILED
        )

        return EmbeddingBatchResult(
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
                "dimension": response.dimension,
            },
        )

    def regenerate_embedding(
        self,
        target: Union[Chunk, KnowledgeUnit],
        include_sparse: bool = False,
        previous_record: Optional[EmbeddingRecord] = None,
    ) -> EmbeddingRecord:
        """Regenerates a new EmbeddingRecord for a canonical object without mutating canonical source.

        Updates historical provenance traceability on canonical target.
        """
        prov_meta = self._adapter.get_provider_metadata()

        # Update canonical object's provenance chain without destroying origin
        if hasattr(target, "provenance") and target.provenance is not None:
            target.provenance.update_representation_provider(
                provider_info={
                    "provider_name": prov_meta.provider_name,
                    "previous_embedding_id": previous_record.embedding_id if previous_record else None,
                    "action": "REGENERATE_EMBEDDING",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                updated_by=self.__class__.__name__,
            )

        # Mark previous record as SUPERSEDED if passed
        if previous_record is not None:
            previous_record.status = "SUPERSEDED"

        if isinstance(target, Chunk):
            return self.embed_chunk(target, include_sparse=include_sparse)
        elif isinstance(target, KnowledgeUnit):
            return self.embed_knowledge_unit(target, include_sparse=include_sparse)
        else:
            raise InvalidEmbeddingInputError(
                f"Target object must be Chunk or KnowledgeUnit, received {type(target)}."
            )
