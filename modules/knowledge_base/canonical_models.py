"""C.2 Canonical Knowledge Data Model for EarthMind.

This module defines storage-independent canonical knowledge representations:
1. Source
2. Artifact
3. Document
4. DocumentVersion
5. Section
6. KnowledgeUnit
7. Chunk

These domain entities form the authoritative source of truth from which metadata,
provenance, embeddings, indexes, and retrieval representations are derived.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, List, Union
from pydantic import BaseModel, Field, model_validator, field_validator

from modules.knowledge_base.enums import (
    ArtifactStatus,
    ChangeType,
    ChunkStatus,
    DocumentStatus,
    DocumentVersionStatus,
    KnowledgeContentType,
    KnowledgeLifecycleState,
    KnowledgeUnitStatus,
    SourceStatus,
)
from modules.knowledge_base.metadata import CanonicalMetadata
from modules.knowledge_base.provenance import Provenance
from modules.knowledge_base.assessment import SourceAssessment


def _validate_non_empty_str(field_name: str, value: str) -> str:
    """Helper to ensure required string fields are non-empty after trimming."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{field_name}' must be a non-empty string.")
    return value.strip()


class Source(BaseModel):
    """Source represents the logical origin/provider of knowledge."""
    source_id: str = Field(..., description="Unique source identifier")
    source_name: str = Field(..., description="Human-readable name of knowledge source")
    source_type: str = Field(..., description="Type/category of source (e.g. 'ACADEMIC_JOURNAL', 'EXTENSION_SERVICE')")
    organization: Optional[str] = Field(None, description="Publishing or governing organization")
    origin: Optional[str] = Field(None, description="URI, URL, or physical publisher reference")
    language: str = Field("en", description="Primary language code (ISO 639-1)")
    region: Optional[str] = Field(None, description="Geographic applicability region")
    status: SourceStatus = Field(SourceStatus.ACTIVE, description="Source status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Last update timestamp")
    metadata: Union[CanonicalMetadata, Dict[str, Any]] = Field(default_factory=dict, description="Extensible metadata or dict")
    provenance: Optional[Provenance] = Field(None, description="Processing provenance chain")
    assessment: Optional[SourceAssessment] = Field(None, description="Source assessment signals")

    @field_validator("source_id", "source_name", "source_type")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        return _validate_non_empty_str(info.field_name, v)


class Artifact(BaseModel):
    """Artifact represents original/raw source material associated with a Source."""
    artifact_id: str = Field(..., description="Unique artifact identifier")
    source_id: str = Field(..., description="Origin source identifier")
    location_reference: str = Field(..., description="Storage reference path, URI, or key for raw material")
    content_type: str = Field(..., description="MIME content type (e.g. 'application/pdf', 'text/html')")
    checksum: Optional[str] = Field(None, description="Cryptographic checksum (e.g. SHA-256)")
    size_bytes: Optional[int] = Field(None, ge=0, description="Raw size in bytes")
    ingestion_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Ingestion timestamp")
    version_info: Optional[str] = Field(None, description="Version or revision string from origin")
    status: ArtifactStatus = Field(ArtifactStatus.RAW, description="Artifact ingestion/processing status")
    metadata: Union[CanonicalMetadata, Dict[str, Any]] = Field(default_factory=dict, description="Extensible metadata or dict")
    provenance: Optional[Provenance] = Field(None, description="Processing provenance chain")

    @field_validator("artifact_id", "source_id", "location_reference", "content_type")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        return _validate_non_empty_str(info.field_name, v)


class Document(BaseModel):
    """Document represents the logical identity of a knowledge document across versions."""
    document_id: str = Field(..., description="Unique logical document identifier")
    source_id: str = Field(..., description="Origin source identifier")
    title: str = Field(..., description="Document title")
    document_type: str = Field(..., description="Category/type (e.g. 'GUIDELINE', 'MANUAL', 'RESEARCH_PAPER')")
    content_type: Optional[str] = Field(None, description="Optional content classification")
    language: str = Field("en", description="Language code (ISO 639-1)")
    region: Optional[str] = Field(None, description="Geographic applicability region")
    status: DocumentStatus = Field(DocumentStatus.ACTIVE, description="Logical document status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Last update timestamp")
    metadata: Union[CanonicalMetadata, Dict[str, Any]] = Field(default_factory=dict, description="Extensible metadata or dict")
    provenance: Optional[Provenance] = Field(None, description="Processing provenance chain")
    assessment: Optional[SourceAssessment] = Field(None, description="Source assessment signals")

    @field_validator("document_id", "source_id", "title", "document_type")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        return _validate_non_empty_str(info.field_name, v)


class DocumentVersion(BaseModel):
    """DocumentVersion represents a specific version of a Document."""
    version_id: str = Field(..., description="Unique version identifier")
    document_id: str = Field(..., description="Parent document logical identifier")
    parent_version_id: Optional[str] = Field(None, description="Identifier of previous version if applicable")
    version_number: str = Field("1.0.0", description="Semantic version string")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    effective_from: Optional[datetime] = Field(None, description="Effective start timestamp")
    effective_until: Optional[datetime] = Field(None, description="Effective end timestamp")
    change_type: ChangeType = Field(ChangeType.INITIAL_CREATION, description="Type of change")
    change_summary: Optional[str] = Field(None, description="Description of changes introduced")
    status: DocumentVersionStatus = Field(DocumentVersionStatus.ACTIVE, description="Version lifecycle status")
    lifecycle_state: KnowledgeLifecycleState = Field(KnowledgeLifecycleState.RECEIVED, description="Pipeline processing and publication lifecycle state")
    metadata: Union[CanonicalMetadata, Dict[str, Any]] = Field(default_factory=dict, description="Extensible metadata or dict")
    provenance: Optional[Provenance] = Field(None, description="Processing provenance chain")

    @field_validator("version_id", "document_id", "version_number")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        return _validate_non_empty_str(info.field_name, v)

    @model_validator(mode="after")
    def validate_parent_and_dates(self) -> "DocumentVersion":
        if self.parent_version_id is not None:
            if self.parent_version_id.strip() == self.version_id:
                raise ValueError("parent_version_id cannot reference self.")
        if self.effective_from is not None and self.effective_until is not None:
            if self.effective_until < self.effective_from:
                raise ValueError("effective_until cannot be earlier than effective_from.")
        return self


class Section(BaseModel):
    """Section represents hierarchical document structure."""
    section_id: str = Field(..., description="Unique section identifier")
    document_id: str = Field(..., description="Parent document logical identifier")
    version_id: str = Field(..., description="Associated document version identifier")
    parent_section_id: Optional[str] = Field(None, description="Parent section identifier for sub-sections")
    title: str = Field(..., description="Section heading or title")
    sequence: int = Field(0, ge=0, description="Sequential position within section level")
    level: int = Field(1, ge=1, description="Structural depth level (1=top, 2=subsection, ...)")
    content_reference: Optional[str] = Field(None, description="Reference pointer to raw section content")
    metadata: Union[CanonicalMetadata, Dict[str, Any]] = Field(default_factory=dict, description="Extensible metadata or dict")
    provenance: Optional[Provenance] = Field(None, description="Processing provenance chain")

    @field_validator("section_id", "document_id", "version_id", "title")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        return _validate_non_empty_str(info.field_name, v)

    @model_validator(mode="after")
    def validate_parent_reference(self) -> "Section":
        if self.parent_section_id is not None:
            if self.parent_section_id.strip() == self.section_id:
                raise ValueError("parent_section_id cannot reference self.")
        return self


class KnowledgeUnit(BaseModel):
    """KnowledgeUnit represents a semantic unit of knowledge in text, table, figure, or multimodal forms."""
    knowledge_unit_id: str = Field(..., description="Unique knowledge unit identifier")
    document_id: str = Field(..., description="Parent document logical identifier")
    version_id: str = Field(..., description="Associated document version identifier")
    section_id: Optional[str] = Field(None, description="Associated section identifier")
    content_type: KnowledgeContentType = Field(KnowledgeContentType.TEXT, description="Content classification category")
    content: Any = Field(..., description="Knowledge content payload (text string, structured dict, or media reference)")
    sequence: int = Field(0, ge=0, description="Sequential order within document/section")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    status: KnowledgeUnitStatus = Field(KnowledgeUnitStatus.ACTIVE, description="Unit status")
    metadata: Union[CanonicalMetadata, Dict[str, Any]] = Field(default_factory=dict, description="Extensible metadata or dict")
    provenance: Optional[Provenance] = Field(None, description="Processing provenance chain")
    assessment: Optional[SourceAssessment] = Field(None, description="Source assessment signals")

    @field_validator("knowledge_unit_id", "document_id", "version_id")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        return _validate_non_empty_str(info.field_name, v)

    @model_validator(mode="after")
    def validate_content(self) -> "KnowledgeUnit":
        if self.content is None:
            raise ValueError("KnowledgeUnit content must not be None.")
        return self


class Chunk(BaseModel):
    """Chunk represents a granular retrieval/search unit derived from KnowledgeUnits."""
    chunk_id: str = Field(..., description="Unique chunk identifier")
    knowledge_unit_id: str = Field(..., description="Originating knowledge unit identifier")
    document_id: str = Field(..., description="Parent document logical identifier")
    version_id: str = Field(..., description="Associated document version identifier")
    parent_section_id: Optional[str] = Field(None, description="Associated section identifier")
    sequence: int = Field(0, ge=0, description="Sequential order of chunk within KnowledgeUnit/Document")
    content: Any = Field(..., description="Chunk content payload")
    content_type: KnowledgeContentType = Field(KnowledgeContentType.TEXT, description="Chunk content type")
    language: str = Field("en", description="Language code")
    size_bytes: Optional[int] = Field(None, ge=0, description="Size in bytes")
    token_count: Optional[int] = Field(None, ge=0, description="Token count if calculated")
    status: ChunkStatus = Field(ChunkStatus.ACTIVE, description="Chunk status")
    metadata: Union[CanonicalMetadata, Dict[str, Any]] = Field(default_factory=dict, description="Extensible metadata or dict")
    provenance: Optional[Provenance] = Field(None, description="Processing provenance chain")

    @field_validator("chunk_id", "knowledge_unit_id", "document_id", "version_id")
    @classmethod
    def validate_strings(cls, v: str, info) -> str:
        return _validate_non_empty_str(info.field_name, v)

    @model_validator(mode="after")
    def validate_content(self) -> "Chunk":
        if self.content is None:
            raise ValueError("Chunk content must not be None.")
        return self


class LineageValidationError(Exception):
    """Raised when canonical object lineage or cross-entity relationship verification fails."""
    pass


class Step6ValidationError(Exception):
    """Raised when Step 6 metadata, provenance, or source assessment validation fails."""
    pass


def validate_metadata_structure(metadata: Any) -> bool:
    """Validates metadata object structure and non-emptiness.

    Returns True if valid; raises Step6ValidationError if invalid.
    """
    if metadata is None:
        raise Step6ValidationError("Metadata must not be None.")
    if isinstance(metadata, CanonicalMetadata):
        return True
    if isinstance(metadata, dict):
        return True
    raise Step6ValidationError(f"Invalid metadata object type: {type(metadata)}. Expected CanonicalMetadata or dict.")


def validate_provenance_chain(provenance: Optional[Provenance], entity_id: Optional[str] = None) -> bool:
    """Validates explicit provenance structure and optional entity ID reference match.

    Returns True if valid; raises Step6ValidationError if invalid.
    """
    if provenance is None:
        return True
    if not isinstance(provenance, Provenance):
        raise Step6ValidationError(f"Invalid provenance object type: {type(provenance)}. Expected Provenance model.")
    if entity_id is not None:
        matched_id = (
            provenance.chunk_id
            or provenance.knowledge_unit_id
            or provenance.section_id
            or provenance.version_id
            or provenance.document_id
            or provenance.artifact_id
            or provenance.source_id
        )
        if matched_id is not None and matched_id != entity_id:
            raise Step6ValidationError(
                f"Provenance entity reference mismatch: provenance references '{matched_id}' but canonical entity is '{entity_id}'."
            )
    return True


def validate_source_assessment(assessment: Optional[SourceAssessment]) -> bool:
    """Validates SourceAssessment scores and structure.

    Returns True if valid; raises Step6ValidationError if invalid.
    """
    if assessment is None:
        return True
    if not isinstance(assessment, SourceAssessment):
        raise Step6ValidationError(f"Invalid assessment object type: {type(assessment)}. Expected SourceAssessment model.")

    for score_field in ["authority", "reliability", "recency", "domain_relevance", "geographic_relevance"]:
        score_val = getattr(assessment, score_field, None)
        if score_val is not None:
            if not isinstance(score_val, (int, float)) or score_val < 0.0 or score_val > 1.0:
                raise Step6ValidationError(f"SourceAssessment field '{score_field}' score {score_val} must be between 0.0 and 1.0.")

    return True


def validate_canonical_lineage(
    source: Source,
    document: Document,
    version: DocumentVersion,
    sections: Optional[List[Section]] = None,
    units: Optional[List[KnowledgeUnit]] = None,
    chunks: Optional[List[Chunk]] = None,
) -> bool:
    """Verifies complete unbroken lineage across canonical knowledge objects.

    Returns True if valid; raises LineageValidationError if relationships are broken.
    """
    # 1. Document -> Source
    if document.source_id != source.source_id:
        raise LineageValidationError(
            f"Document source_id '{document.source_id}' does not match Source source_id '{source.source_id}'."
        )

    # 2. Version -> Document
    if version.document_id != document.document_id:
        raise LineageValidationError(
            f"Version document_id '{version.document_id}' does not match Document document_id '{document.document_id}'."
        )

    # 3. Sections -> Document & Version
    if sections:
        for section in sections:
            if section.document_id != document.document_id:
                raise LineageValidationError(
                    f"Section '{section.section_id}' document_id '{section.document_id}' mismatch with Document '{document.document_id}'."
                )
            if section.version_id != version.version_id:
                raise LineageValidationError(
                    f"Section '{section.section_id}' version_id '{section.version_id}' mismatch with Version '{version.version_id}'."
                )

    # 4. Units -> Document & Version & Section
    if units:
        section_ids = {s.section_id for s in (sections or [])}
        for unit in units:
            if unit.document_id != document.document_id:
                raise LineageValidationError(
                    f"KnowledgeUnit '{unit.knowledge_unit_id}' document_id '{unit.document_id}' mismatch with Document '{document.document_id}'."
                )
            if unit.version_id != version.version_id:
                raise LineageValidationError(
                    f"KnowledgeUnit '{unit.knowledge_unit_id}' version_id '{unit.version_id}' mismatch with Version '{version.version_id}'."
                )
            if unit.section_id is not None and sections is not None and unit.section_id not in section_ids:
                raise LineageValidationError(
                    f"KnowledgeUnit '{unit.knowledge_unit_id}' references unknown section_id '{unit.section_id}'."
                )

    # 5. Chunks -> KnowledgeUnit & Document & Version
    if chunks:
        unit_map = {u.knowledge_unit_id: u for u in (units or [])}
        for chunk in chunks:
            if chunk.document_id != document.document_id:
                raise LineageValidationError(
                    f"Chunk '{chunk.chunk_id}' document_id '{chunk.document_id}' mismatch with Document '{document.document_id}'."
                )
            if chunk.version_id != version.version_id:
                raise LineageValidationError(
                    f"Chunk '{chunk.chunk_id}' version_id '{chunk.version_id}' mismatch with Version '{version.version_id}'."
                )
            if units is not None:
                if chunk.knowledge_unit_id not in unit_map:
                    raise LineageValidationError(
                        f"Chunk '{chunk.chunk_id}' references unknown knowledge_unit_id '{chunk.knowledge_unit_id}'."
                    )

    # Validate Step 6 attachments if present
    for obj in [source, document, version] + (sections or []) + (units or []) + (chunks or []):
        validate_metadata_structure(obj.metadata)
        if hasattr(obj, "provenance") and obj.provenance is not None:
            validate_provenance_chain(obj.provenance)
        if hasattr(obj, "assessment") and obj.assessment is not None:
            validate_source_assessment(obj.assessment)

    return True
