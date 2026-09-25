from enum import Enum


class KnowledgeClassification(str, Enum):
    """Provider-independent classification of knowledge types for C.3 boundary contracts."""
    GENERAL_KNOWLEDGE = "GENERAL_KNOWLEDGE"
    FARMER_KNOWLEDGE = "FARMER_KNOWLEDGE"
    FIELD_KNOWLEDGE = "FIELD_KNOWLEDGE"
    SESSION_CONTEXT = "SESSION_CONTEXT"
    OBSERVATION = "OBSERVATION"
    EXTERNAL_CURRENT_DATA = "EXTERNAL_CURRENT_DATA"


class ContextSourceType(str, Enum):
    """Provider-independent source origin type allowing B2 and downstream components to distinguish context source."""
    RAG = "RAG"
    MEMORY = "MEMORY"
    SESSION = "SESSION"
    OBSERVATION = "OBSERVATION"
    EXTERNAL_SERVICE = "EXTERNAL_SERVICE"


class ContextOwnership(str, Enum):
    """Explicit subsystem ownership semantics governing information lifecycle and meaning."""
    RAG_OWNED = "RAG_OWNED"
    MEMORY_OWNED = "MEMORY_OWNED"
    RUNTIME_OWNED = "RUNTIME_OWNED"
    EXTERNAL_OWNED = "EXTERNAL_OWNED"


class ContextScope(str, Enum):
    """Scope metadata defining spatial, organizational, or operational boundaries of context."""
    GLOBAL = "GLOBAL"
    REGIONAL = "REGIONAL"
    FARMER = "FARMER"
    FARM = "FARM"
    FIELD = "FIELD"
    CROP_CYCLE = "CROP_CYCLE"
    SESSION = "SESSION"
    EVENT = "EVENT"


class PersistenceIntent(str, Enum):
    """Persistence classification signal indicating required retention level."""
    TEMPORARY = "TEMPORARY"
    SESSION_SCOPED = "SESSION_SCOPED"
    PERSISTENT = "PERSISTENT"


class TransitionType(str, Enum):
    """Supported cross-domain promotion transition types for C.3.3 governance."""
    RAG_TO_MEMORY = "RAG_TO_MEMORY"
    MEMORY_TO_RAG = "MEMORY_TO_RAG"


class GovernanceOutcome(str, Enum):
    """Possible outcomes for C.3.3 cross-domain promotion governance evaluation."""
    AUTO_ALLOWED = "AUTO_ALLOWED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    BLOCKED = "BLOCKED"
    INVALID = "INVALID"


class GovernanceState(str, Enum):
    """Lifecycle states for C.3.3 cross-domain governance evaluation and promotion execution."""
    CANDIDATE = "CANDIDATE"
    VALIDATING = "VALIDATING"
    EVALUATING_POLICY = "EVALUATING_POLICY"
    AUTO_ALLOWED = "AUTO_ALLOWED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    EXECUTION_PENDING = "EXECUTION_PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class GovernanceFailureReason(str, Enum):
    """Explicit reasons for governance rejection, blocking, or invalid candidate determination."""
    INVALID_CANDIDATE = "INVALID_CANDIDATE"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"
    INVALID_SCOPE_TRANSITION = "INVALID_SCOPE_TRANSITION"
    PRIVACY_POLICY_VIOLATION = "PRIVACY_POLICY_VIOLATION"
    OWNERSHIP_TRANSITION_BLOCKED = "OWNERSHIP_TRANSITION_BLOCKED"
    PERSISTENCE_TRANSITION_BLOCKED = "PERSISTENCE_TRANSITION_BLOCKED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    TARGET_POLICY_REJECTED = "TARGET_POLICY_REJECTED"
    GOVERNANCE_ERROR = "GOVERNANCE_ERROR"
