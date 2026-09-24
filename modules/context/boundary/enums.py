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
