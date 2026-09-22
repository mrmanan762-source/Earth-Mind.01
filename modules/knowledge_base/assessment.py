"""Source Assessment Model for EarthMind Knowledge Base.

Defines structured assessment signals for knowledge sources and evidence.

ARCHITECTURAL PRINCIPLE:
SOURCE ASSESSMENT IS NOT TRUTH.
The assessment layer must NOT:
- declare information scientifically true/false
- perform agricultural reasoning
- make recommendations
- replace B3 Reasoning
- automatically decide which evidence wins in conflicts

It only stores structured assessment signals about the source/evidence.
"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, field_validator

from modules.knowledge_base.enums import EvidenceType, ReviewStatus


class SourceAssessment(BaseModel):
    """SourceAssessment stores metadata evaluation signals about knowledge sources or evidence.

    IMPORTANT: Source Assessment is an assessment signal, not a truth judgment.
    """

    assessment_id: str = Field(..., description="Unique assessment identifier")
    source_id: Optional[str] = Field(None, description="Identifier of assessed source")
    document_id: Optional[str] = Field(None, description="Identifier of assessed document if assessment is document-level")

    # Assessment Signal Scores [0.0, 1.0]
    authority: Optional[float] = Field(None, ge=0.0, le=1.0, description="Authority evaluation signal score [0.0, 1.0]")
    reliability: Optional[float] = Field(None, ge=0.0, le=1.0, description="Reliability evaluation signal score [0.0, 1.0]")
    recency: Optional[float] = Field(None, ge=0.0, le=1.0, description="Recency evaluation signal score [0.0, 1.0]")
    domain_relevance: Optional[float] = Field(None, ge=0.0, le=1.0, description="Domain relevance signal score [0.0, 1.0]")
    geographic_relevance: Optional[float] = Field(None, ge=0.0, le=1.0, description="Geographic relevance signal score [0.0, 1.0]")

    # Classification & Context
    review_status: ReviewStatus = Field(ReviewStatus.UNREVIEWED, description="Assessment review status")
    evidence_type: Optional[EvidenceType] = Field(None, description="Classification of evidence type")
    assessment_basis: Optional[str] = Field(None, description="Rationale or metadata basis for assessment signals")
    assessed_by: Optional[str] = Field(None, description="Identity or module responsible for creating assessment")

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Assessment creation timestamp")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Last update timestamp")

    @field_validator("assessment_id")
    @classmethod
    def validate_assessment_id(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Field 'assessment_id' must be a non-empty string.")
        return v.strip()

    @field_validator("source_id", "document_id", "assessment_basis", "assessed_by")
    @classmethod
    def validate_optional_strings(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None:
            v_trimmed = v.strip()
            return v_trimmed if v_trimmed else None
        return None
