from enum import Enum


class PlanningState(str, Enum):
    """Lifecycle and operational states for B4 Planning & Decision Engine processing."""
    # Active execution states
    REQUESTED = "REQUESTED"
    VALIDATING = "VALIDATING"
    PREPARING = "PREPARING"
    INTERPRETING_REASONING = "INTERPRETING_REASONING"
    ANALYZING_GOAL = "ANALYZING_GOAL"
    ANALYZING_CONSTRAINTS = "ANALYZING_CONSTRAINTS"
    GENERATING_OPTIONS = "GENERATING_OPTIONS"
    ANALYZING_FEASIBILITY = "ANALYZING_FEASIBILITY"
    ANALYZING_RISK = "ANALYZING_RISK"
    BUILDING_PLANS = "BUILDING_PLANS"
    COMPARING_OPTIONS = "COMPARING_OPTIONS"
    FORMING_DECISION = "FORMING_DECISION"
    BUILDING_RESULT = "BUILDING_RESULT"
    VALIDATING_RESULT = "VALIDATING_RESULT"
    INSPECTOR_HANDOFF = "INSPECTOR_HANDOFF"

    # Complete & Terminal / Failure states
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    NO_FEASIBLE_OPTION = "NO_FEASIBLE_OPTION"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    REQUIRES_CONFIRMATION = "REQUIRES_CONFIRMATION"
    REJECTED = "REJECTED"


class FeasibilityState(str, Enum):
    """Explicit feasibility evaluation outcomes for candidate actions or plans."""
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    CONDITIONAL = "CONDITIONAL"
    UNKNOWN = "UNKNOWN"


class HardSoftType(str, Enum):
    """Distinction between hard (unviolable) and soft (preferential) constraints."""
    HARD = "HARD"
    SOFT = "SOFT"


class ConstraintType(str, Enum):
    """Generic constraint classifications."""
    RESOURCE = "RESOURCE"
    TEMPORAL = "TEMPORAL"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    REGULATORY = "REGULATORY"
    OPERATIONAL = "OPERATIONAL"
    POLICY = "POLICY"
    SAFETY = "SAFETY"
    PHYSICAL = "PHYSICAL"
    BUDGETARY = "BUDGETARY"


class ConstraintSeverity(str, Enum):
    """Severity ratings for constraints or constraint violations."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskLevel(str, Enum):
    """Risk severity classification for planning options."""
    NEGLIGIBLE = "NEGLIGIBLE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DecisionState(str, Enum):
    """State classification of decision output."""
    PROPOSED = "PROPOSED"
    DECIDED = "DECIDED"
    CONDITIONAL = "CONDITIONAL"
    REQUIRES_CONFIRMATION = "REQUIRES_CONFIRMATION"
    REJECTED = "REJECTED"
