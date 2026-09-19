from enum import Enum


class WorkflowState(str, Enum):
    """Explicit workflow execution states supported by B5 AI Orchestrator."""
    REQUESTED = "REQUESTED"
    VALIDATING = "VALIDATING"
    SELECTING_WORKFLOW = "SELECTING_WORKFLOW"
    PREPARING_CAPABILITIES = "PREPARING_CAPABILITIES"
    EXECUTING = "EXECUTING"
    WAITING_FOR_RESULT = "WAITING_FOR_RESULT"
    EVALUATING_RESULT = "EVALUATING_RESULT"
    ROUTING = "ROUTING"
    NEXT_CAPABILITY = "NEXT_CAPABILITY"
    VALIDATING_FINAL_RESULT = "VALIDATING_FINAL_RESULT"
    COMPLETED = "COMPLETED"

    # Recovery / Failure States
    RETRYING = "RETRYING"
    REPLANNING = "REPLANNING"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    REQUIRES_CONFIRMATION = "REQUIRES_CONFIRMATION"
    REJECTED = "REJECTED"


class WorkflowStrategyType(str, Enum):
    """Configurable workflow execution strategies for B5 AI Orchestrator."""
    STANDARD_DECISION = "STANDARD_DECISION"
    VISUAL_DIAGNOSIS = "VISUAL_DIAGNOSIS"
    MISSING_INFORMATION = "MISSING_INFORMATION"
    MEMORY_ASSISTED = "MEMORY_ASSISTED"
    MULTIMODAL = "MULTIMODAL"
    CUSTOM = "CUSTOM"


class CapabilityStatus(str, Enum):
    """Health and lifecycle availability state of registered capabilities."""
    REGISTERED = "REGISTERED"
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    DISABLED = "DISABLED"


class StepExecutionState(str, Enum):
    """Granular execution state of an individual workflow capability step."""
    PENDING = "PENDING"
    PREPARING = "PREPARING"
    VALIDATING_INPUT = "VALIDATING_INPUT"
    CHECKING_DEPENDENCY = "CHECKING_DEPENDENCY"
    EXECUTING = "EXECUTING"
    WAITING_FOR_RESULT = "WAITING_FOR_RESULT"
    VALIDATING_OUTPUT = "VALIDATING_OUTPUT"
    COMPLETED = "COMPLETED"
    RETRYING = "RETRYING"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class FailureHandlingPolicy(str, Enum):
    """Execution policy for handling capability step failure."""
    STOP_ON_FAILURE = "STOP_ON_FAILURE"
    RETRY_THEN_ALT = "RETRY_THEN_ALT"
    CONTINUE_ON_PARTIAL = "CONTINUE_ON_PARTIAL"
    REPLAN = "REPLAN"


class CompletionCondition(str, Enum):
    """Policy conditions required to deem workflow execution complete."""
    ALL_STEPS_COMPLETED = "ALL_STEPS_COMPLETED"
    REQUIRED_STEPS_COMPLETED = "REQUIRED_STEPS_COMPLETED"
    INSPECTOR_PASS = "INSPECTOR_PASS"
    CONFIRMATION_GRANTED = "CONFIRMATION_GRANTED"
