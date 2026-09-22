"""Provenance Model for EarthMind Knowledge Base.

Defines structure for tracking complete origin and processing chain:
Source -> Artifact -> Document -> DocumentVersion -> Processing Pipeline -> Chunking Operation -> Representation/Embedding Provider -> Timestamp

Supports auditability and replacement of future representation/index layers without losing canonical origin traceability.
Handles incomplete provenance explicitly without silent fabrication of missing values.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


def _clean_str(field_name: str, value: Optional[str]) -> Optional[str]:
    if value is not None:
        val = value.strip()
        if not val:
            raise ValueError(f"Field '{field_name}' cannot be an empty or whitespace string.")
        return val
    return None


class ProcessingStep(BaseModel):
    """Represents an individual step in a processing pipeline audit trail."""

    step_id: str = Field(..., description="Unique step identifier")
    operation: str = Field(..., description="Operation name or action performed")
    processor_name: str = Field(..., description="Service, module, or algorithm executing step")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters used during execution")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Step execution timestamp")
    status: str = Field("COMPLETED", description="Status of step execution")


class Provenance(BaseModel):
    """Explicit provenance structure representing origin and processing chain.

    Traces lineage across Source, Artifact, Document, DocumentVersion, Section,
    KnowledgeUnit, Chunk, Processing Pipelines, Chunking Operations, and
    Representation Providers.
    """

    provenance_id: str = Field(..., description="Unique identifier for provenance record")

    # Upstream Canonical Lineage References
    source_id: Optional[str] = Field(None, description="Origin source reference ID")
    artifact_id: Optional[str] = Field(None, description="Source artifact reference ID")
    document_id: Optional[str] = Field(None, description="Logical document reference ID")
    version_id: Optional[str] = Field(None, description="Document version reference ID")
    section_id: Optional[str] = Field(None, description="Section reference ID")
    knowledge_unit_id: Optional[str] = Field(None, description="Knowledge unit reference ID")
    chunk_id: Optional[str] = Field(None, description="Chunk reference ID")

    # Processing Chain Details
    processing_stage: Optional[str] = Field(None, description="Current processing stage (e.g., 'INGESTION', 'CHUNKING', 'EMBEDDING')")
    processing_operation: Optional[str] = Field(None, description="Name of processing operation executed")
    chunking_operation: Optional[Dict[str, Any]] = Field(None, description="Chunking strategy configuration details")
    representation_provider: Optional[Dict[str, Any]] = Field(None, description="Future embedding/representation provider configuration")

    # Operational Identifiers & Audit Trail
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of provenance record")
    operation_id: Optional[str] = Field(None, description="Execution run or job identifier")
    version_identifiers: Dict[str, str] = Field(default_factory=dict, description="Tooling and pipeline component versions")
    processing_steps: List[Dict[str, Any]] = Field(default_factory=list, description="Ordered execution step records")

    # Explicit Traceability State
    is_complete: bool = Field(True, description="Explicit flag indicating whether required lineage references exist")
    missing_fields: List[str] = Field(default_factory=list, description="Explicit list of missing expected lineage fields")

    @field_validator("provenance_id")
    @classmethod
    def validate_provenance_id(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Field 'provenance_id' must be a non-empty string.")
        return v.strip()

    @field_validator(
        "source_id", "artifact_id", "document_id", "version_id",
        "section_id", "knowledge_unit_id", "chunk_id",
        "processing_stage", "processing_operation", "operation_id"
    )
    @classmethod
    def validate_optional_strings(cls, v: Optional[str], info) -> Optional[str]:
        return _clean_str(info.field_name, v)

    @model_validator(mode="after")
    def evaluate_lineage_completeness(self) -> "Provenance":
        """Evaluates completeness of upstream references without fabricating missing values.

        If a downstream entity is referenced (e.g. chunk_id or knowledge_unit_id or document_id),
        the corresponding ancestor references (e.g. source_id, document_id, version_id) should be present.
        If missing, mark `is_complete = False` and populate `missing_fields`.
        """
        missing = []

        # If document_id is present, source_id should be present
        if self.document_id is not None and self.source_id is None:
            missing.append("source_id")

        # If version_id is present, document_id and source_id should be present
        if self.version_id is not None:
            if self.document_id is None and "document_id" not in missing:
                missing.append("document_id")
            if self.source_id is None and "source_id" not in missing:
                missing.append("source_id")

        # If knowledge_unit_id is present, version_id, document_id, and source_id should be present
        if self.knowledge_unit_id is not None:
            if self.version_id is None and "version_id" not in missing:
                missing.append("version_id")
            if self.document_id is None and "document_id" not in missing:
                missing.append("document_id")
            if self.source_id is None and "source_id" not in missing:
                missing.append("source_id")

        # If chunk_id is present, knowledge_unit_id, version_id, document_id, source_id should be present
        if self.chunk_id is not None:
            if self.knowledge_unit_id is None and "knowledge_unit_id" not in missing:
                missing.append("knowledge_unit_id")
            if self.version_id is None and "version_id" not in missing:
                missing.append("version_id")
            if self.document_id is None and "document_id" not in missing:
                missing.append("document_id")
            if self.source_id is None and "source_id" not in missing:
                missing.append("source_id")

        if missing:
            self.is_complete = False
            # Preserve existing missing_fields entries if any, deduplicating while retaining order
            combined_missing = list(self.missing_fields)
            for m in missing:
                if m not in combined_missing:
                    combined_missing.append(m)
            self.missing_fields = combined_missing

        return self

    def update_representation_provider(
        self,
        provider_info: Dict[str, Any],
        operation_id: Optional[str] = None,
        updated_by: Optional[str] = None
    ) -> None:
        """Updates representation/embedding provider info while preserving canonical lineage.

        Enables representation replacement without losing original source provenance.
        """
        old_provider = self.representation_provider
        self.representation_provider = provider_info
        self.timestamp = datetime.now(timezone.utc)
        if operation_id is not None:
            self.operation_id = operation_id

        step_record = {
            "step_id": f"step_rep_replace_{int(self.timestamp.timestamp())}",
            "operation": "REPLACEMENT_REPRESENTATION_PROVIDER",
            "processor_name": updated_by or "system_representation_updater",
            "parameters": {
                "previous_provider": old_provider,
                "new_provider": provider_info,
            },
            "timestamp": self.timestamp.isoformat(),
            "status": "COMPLETED",
        }
        self.processing_steps.append(step_record)
