from enum import Enum


class ReasoningState(str, Enum):
    """Lifecycle and operational states for B3 Reasoning Engine processing."""
    REQUESTED = "REQUESTED"
    VALIDATING = "VALIDATING"
    PREPARING_CONTEXT = "PREPARING_CONTEXT"
    ANALYZING_EVIDENCE = "ANALYZING_EVIDENCE"
    COMPARING_EVIDENCE = "COMPARING_EVIDENCE"
    ANALYZING_RELATIONSHIPS = "ANALYZING_RELATIONSHIPS"
    ANALYZING_CONFLICTS = "ANALYZING_CONFLICTS"
    ANALYZING_UNCERTAINTY = "ANALYZING_UNCERTAINTY"
    ITERATING = "ITERATING"
    BUILDING_RESULT = "BUILDING_RESULT"
    VALIDATING_RESULT = "VALIDATING_RESULT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class ConflictType(str, Enum):
    """Categorization of evidence conflicts."""
    CONTRADICTION = "CONTRADICTION"
    TEMPORAL_MISMATCH = "TEMPORAL_MISMATCH"
    SOURCE_DISCREPANCY = "SOURCE_DISCREPANCY"
    VALUE_DISCREPANCY = "VALUE_DISCREPANCY"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"


class RelationshipType(str, Enum):
    """Types of detected relationships between evidence items."""
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    TEMPORAL = "TEMPORAL"
    CAUSAL_HYPOTHESIS = "CAUSAL_HYPOTHESIS"
    SOURCE_CORRELATION = "SOURCE_CORRELATION"


class UncertaintyLevel(str, Enum):
    """Quantified or state-based uncertainty levels."""
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ValidationStatus(str, Enum):
    """Inspector validation status outcomes."""
    PASS = "PASS"
    FLAG = "FLAG"
    RECHECK = "RECHECK"
    PENDING = "PENDING"
    FAILED = "FAILED"


class AssumptionType(str, Enum):
    """Categorization of declared reasoning assumptions."""
    DEFAULT_BASELINE = "DEFAULT_BASELINE"
    TEMPORAL_EXTRAPOLATION = "TEMPORAL_EXTRAPOLATION"
    DOMAIN_PRESUMPTION = "DOMAIN_PRESUMPTION"
    MISSING_DATA_FALLBACK = "MISSING_DATA_FALLBACK"


class EvidenceScope(str, Enum):
    """Granularity scope of evidence items."""
    GLOBAL = "GLOBAL"
    FARM = "FARM"
    FIELD = "FIELD"
    CROP_CYCLE = "CROP_CYCLE"
    SENSOR = "SENSOR"
    OBSERVATION = "OBSERVATION"
