"""Data Contracts for EarthMind Stage R12 Evidence Validator.

Defines Pydantic models for:
- ValidationSeverity: Severity level enum (INFO, WARNING, ERROR, CRITICAL)
- EvidenceValidationStatus: Validation status enum (VALID, PARTIALLY_VALID, INVALID, MALFORMED, UNTRACEABLE, CONFLICTING, EMPTY)
- EvidenceValidationFinding: Structured validation finding record
- EvidenceItemValidationOutcome: Per-item validation outcome and findings summary
- EvidenceValidationRequest: Input payload for evidence package validation
- EvidenceValidationResult: Internal result containing validated package, item outcomes, and findings
- EvidenceValidationResponse: Execution response wrapper for R12 Evidence Validator
"""

from enum import Enum
import time
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.schemas.evidence import EvidenceItem, EvidencePackage


class ValidationSeverity(str, Enum):
    """Severity classification for validation findings."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class EvidenceValidationStatus(str, Enum):
    """Overall status of validation process or item evaluation."""
    VALID = "VALID"
    PARTIALLY_VALID = "PARTIALLY_VALID"
    INVALID = "INVALID"
    MALFORMED = "MALFORMED"
    UNTRACEABLE = "UNTRACEABLE"
    CONFLICTING = "CONFLICTING"
    EMPTY = "EMPTY"


class EvidenceValidationFinding(BaseModel):
    """
    Structured validation finding record documenting a rule/check result,
    severity, affected evidence item, field path, and rationale.
    """
    finding_id: str = Field(
        default_factory=lambda: f"fnd_{uuid.uuid4().hex[:12]}",
        description="Unique finding identifier"
    )
    rule_code: str = Field(..., description="Validation rule or check code (e.g., R12_STRUCT_01)")
    severity: ValidationSeverity = Field(ValidationSeverity.WARNING, description="Severity level")
    evidence_id: Optional[str] = Field(None, description="Affected evidence item identifier if applicable")
    field_path: Optional[str] = Field(None, description="Field path or field name where finding occurred")
    reason: str = Field(..., description="Detailed explanation of the validation finding")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional contextual metadata")


class EvidenceItemValidationOutcome(BaseModel):
    """
    Validation outcome for an individual EvidenceItem, summarizing
    its validity, assigned status, and item-level findings.
    """
    evidence_id: str = Field(..., description="Evidence item identifier")
    is_valid: bool = Field(True, description="Whether the evidence item passed validation rules")
    status: EvidenceValidationStatus = Field(EvidenceValidationStatus.VALID, description="Assigned item-level status")
    findings: List[EvidenceValidationFinding] = Field(default_factory=list, description="Findings specific to this item")
    item: Optional[EvidenceItem] = Field(None, description="Preserved or sanitized evidence item")


class EvidenceValidationRequest(BaseModel):
    """Incoming request payload for Evidence Package validation."""
    package: Optional[EvidencePackage] = Field(None, description="R11 EvidencePackage to validate")
    request_id: Optional[str] = Field(None, description="Correlation / request tracing ID")
    strict_mode: bool = Field(False, description="If True, any ERROR/CRITICAL finding invalidates the entire package")
    policy_config: Dict[str, Any] = Field(default_factory=dict, description="Optional policy runtime overrides")
    user_context: Optional[Dict[str, Any]] = Field(None, description="Upstream user context")


class EvidenceValidationResult(BaseModel):
    """
    Comprehensive validation result containing the validated EvidencePackage,
    aggregated findings, item outcomes, and status metrics.
    """
    validation_id: str = Field(
        default_factory=lambda: f"val_{uuid.uuid4().hex[:12]}",
        description="Unique validation execution ID"
    )
    request_id: Optional[str] = Field(None, description="Correlation / request tracing ID")
    overall_status: EvidenceValidationStatus = Field(EvidenceValidationStatus.VALID, description="Overall validation status")
    validated_package: Optional[EvidencePackage] = Field(None, description="Sanitized/filtered EvidencePackage ready for B2")
    item_outcomes: List[EvidenceItemValidationOutcome] = Field(default_factory=list, description="Per-item outcomes")
    findings: List[EvidenceValidationFinding] = Field(default_factory=list, description="All validation findings")
    valid_items_count: int = Field(0, description="Count of valid items")
    invalid_items_count: int = Field(0, description="Count of invalid items")
    total_items_count: int = Field(0, description="Total evidence items evaluated")
    has_conflicts: bool = Field(False, description="True if conflict indicators or duplicate conflicts were detected")
    execution_time_ms: float = Field(0.0, description="Validation latency in milliseconds")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Execution metadata and summary")


class EvidenceValidationResponse(BaseModel):
    """Output payload from Stage R12 Evidence Validator Engine."""
    request_id: Optional[str] = Field(None, description="Correlation / request tracing ID")
    status: EvidenceValidationStatus = Field(EvidenceValidationStatus.VALID, description="Overall execution status")
    result: Optional[EvidenceValidationResult] = Field(None, description="Validation result object")
    warnings: List[str] = Field(default_factory=list, description="Warning messages during validation")
    error_message: Optional[str] = Field(None, description="Error message if execution failed")
    execution_time_ms: float = Field(0.0, description="Execution latency in milliseconds")
