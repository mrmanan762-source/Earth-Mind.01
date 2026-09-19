from typing import Any, Dict, Optional
from core.schemas.contracts import ErrorContract

class EarthMindException(Exception):
    """Base exception for all EarthMind framework errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "EARTHMIND_ERROR",
        module: str = "core",
        operation: str = "unknown",
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.error_contract = ErrorContract(
            error_code=error_code,
            message=message,
            module=module,
            operation=operation,
            retryable=retryable,
            metadata=metadata or {}
        )

class ModuleNotFoundError(EarthMindException):
    def __init__(self, module_name: str):
        super().__init__(
            message=f"Module '{module_name}' is not registered.",
            error_code="MODULE_NOT_FOUND",
            module="core",
            operation="registry_lookup"
        )

class ModuleExecutionError(EarthMindException):
    def __init__(self, module_name: str, details: str):
        super().__init__(
            message=f"Execution error in module '{module_name}': {details}",
            error_code="MODULE_EXECUTION_ERROR",
            module=module_name,
            operation="handle"
        )

class ModelNotLoadedError(EarthMindException):
    def __init__(self, model_identifier: str):
        super().__init__(
            message=f"Model '{model_identifier}' is not loaded.",
            error_code="MODEL_NOT_LOADED",
            module="ai",
            operation="generate"
        )

class ModelExecutionError(EarthMindException):
    def __init__(self, model_identifier: str, details: str):
        super().__init__(
            message=f"Error executing model '{model_identifier}': {details}",
            error_code="MODEL_EXECUTION_ERROR",
            module="ai",
            operation="generate"
        )

class InferenceValidationError(EarthMindException):
    def __init__(self, details: str):
        super().__init__(
            message=f"Inference request validation failed: {details}",
            error_code="INFERENCE_VALIDATION_ERROR",
            module="ai",
            operation="validate_request"
        )

class RuntimeUnavailableError(EarthMindException):
    def __init__(self, details: str = "Runtime or model backend is unavailable."):
        super().__init__(
            message=details,
            error_code="RUNTIME_UNAVAILABLE",
            module="ai",
            operation="execute"
        )

class InferenceTimeoutError(EarthMindException):
    def __init__(self, request_id: str, timeout: float):
        super().__init__(
            message=f"Inference request '{request_id}' timed out after {timeout} seconds.",
            error_code="INFERENCE_TIMEOUT",
            module="ai",
            operation="execute",
            retryable=True,
            metadata={"request_id": request_id, "timeout": timeout}
        )

class InferenceCancelledError(EarthMindException):
    def __init__(self, request_id: str):
        super().__init__(
            message=f"Inference request '{request_id}' was cancelled.",
            error_code="INFERENCE_CANCELLED",
            module="ai",
            operation="execute",
            metadata={"request_id": request_id}
        )


class OrchestratorError(EarthMindException):
    """Base exception for B5 AI Orchestrator errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "ORCHESTRATOR_ERROR",
        operation: str = "orchestration",
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            module="orchestrator",
            operation=operation,
            retryable=retryable,
            metadata=metadata or {}
        )


class InvalidOrchestrationRequestError(OrchestratorError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Invalid orchestration request: {details}",
            error_code="INVALID_ORCHESTRATION_REQUEST",
            operation="validate_request"
        )


class WorkflowCompositionError(OrchestratorError):
    def __init__(self, workflow_id: str, details: str):
        super().__init__(
            message=f"Workflow composition error for '{workflow_id}': {details}",
            error_code="WORKFLOW_COMPOSITION_ERROR",
            operation="compose_workflow",
            metadata={"workflow_id": workflow_id}
        )


class CapabilityNotFoundError(OrchestratorError):
    def __init__(self, capability_id: str):
        super().__init__(
            message=f"Capability '{capability_id}' was not found in registry.",
            error_code="CAPABILITY_NOT_FOUND",
            operation="lookup_capability",
            metadata={"capability_id": capability_id}
        )


class CapabilityExecutionError(OrchestratorError):
    def __init__(self, capability_id: str, details: str, retryable: bool = False):
        super().__init__(
            message=f"Capability '{capability_id}' execution failed: {details}",
            error_code="CAPABILITY_EXECUTION_ERROR",
            operation="execute_capability",
            retryable=retryable,
            metadata={"capability_id": capability_id}
        )


class CapabilityTimeoutError(OrchestratorError):
    def __init__(self, capability_id: str, timeout: float):
        super().__init__(
            message=f"Capability '{capability_id}' timed out after {timeout} seconds.",
            error_code="CAPABILITY_TIMEOUT",
            operation="execute_capability",
            retryable=True,
            metadata={"capability_id": capability_id, "timeout": timeout}
        )


class CapabilityCancelledError(OrchestratorError):
    def __init__(self, capability_id: str):
        super().__init__(
            message=f"Capability '{capability_id}' execution was cancelled.",
            error_code="CAPABILITY_CANCELLED",
            operation="execute_capability",
            metadata={"capability_id": capability_id}
        )


class InvalidContractError(OrchestratorError):
    def __init__(self, capability_id: str, details: str):
        super().__init__(
            message=f"Contract validation failed for capability '{capability_id}': {details}",
            error_code="INVALID_CONTRACT",
            operation="validate_contract",
            metadata={"capability_id": capability_id}
        )


class OrchestrationScopeViolationError(OrchestratorError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Scope violation in orchestration: {details}",
            error_code="ORCHESTRATION_SCOPE_VIOLATION",
            operation="validate_scope"
        )


class RecheckLimitExceededError(OrchestratorError):
    def __init__(self, request_id: str, max_rechecks: int):
        super().__init__(
            message=f"Orchestration request '{request_id}' exceeded max recheck limit of {max_rechecks}.",
            error_code="RECHECK_LIMIT_EXCEEDED",
            operation="inspector_recheck",
            metadata={"request_id": request_id, "max_rechecks": max_rechecks}
        )


class InvalidWorkflowStateTransitionError(OrchestratorError):
    def __init__(self, current_state: str, target_state: str, reason: str = ""):
        msg = f"Invalid workflow state transition: {current_state} -> {target_state}."
        if reason:
            msg += f" {reason}"
        super().__init__(
            message=msg,
            error_code="INVALID_WORKFLOW_STATE_TRANSITION",
            operation="transition_state",
            metadata={"current_state": current_state, "target_state": target_state}
        )


class PlanningError(EarthMindException):
    """Base exception for B4 Planning & Decision Engine errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "PLANNING_ERROR",
        operation: str = "planning_processing",
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            module="planning",
            operation=operation,
            retryable=retryable,
            metadata=metadata or {}
        )


class InvalidPlanningInputError(PlanningError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Invalid planning input: {details}",
            error_code="INVALID_PLANNING_INPUT",
            operation="validate_input"
        )


class InvalidPlanningReasoningInputError(PlanningError):
    def __init__(self, request_id: str, details: str):
        super().__init__(
            message=f"Invalid reasoning input for planning request '{request_id}': {details}",
            error_code="INVALID_REASONING_INPUT",
            operation="interpret_reasoning",
            metadata={"request_id": request_id}
        )


class MissingGoalError(PlanningError):
    def __init__(self, request_id: str, details: str = "Planning objective/goal is missing or unspecified."):
        super().__init__(
            message=f"Missing goal for planning request '{request_id}': {details}",
            error_code="MISSING_GOAL",
            operation="analyze_goal",
            metadata={"request_id": request_id}
        )


class InvalidConstraintError(PlanningError):
    def __init__(self, constraint_id: str, details: str):
        super().__init__(
            message=f"Invalid constraint '{constraint_id}': {details}",
            error_code="INVALID_CONSTRAINT",
            operation="validate_constraint",
            metadata={"constraint_id": constraint_id}
        )


class ImpossibleConstraintError(PlanningError):
    def __init__(self, constraint_id: str, details: str):
        super().__init__(
            message=f"Impossible or contradictory constraint '{constraint_id}': {details}",
            error_code="IMPOSSIBLE_CONSTRAINT",
            operation="analyze_constraints",
            metadata={"constraint_id": constraint_id}
        )


class UnavailableCapabilityError(PlanningError):
    def __init__(self, capability_name: str, details: str):
        super().__init__(
            message=f"Required capability '{capability_name}' is unavailable: {details}",
            error_code="UNAVAILABLE_CAPABILITY",
            operation="check_capabilities",
            retryable=True,
            metadata={"capability_name": capability_name}
        )


class PlanningTimeoutError(PlanningError):
    def __init__(self, request_id: str, timeout: float):
        super().__init__(
            message=f"Planning request '{request_id}' timed out after {timeout} seconds.",
            error_code="PLANNING_TIMEOUT",
            operation="execute_planning",
            retryable=True,
            metadata={"request_id": request_id, "timeout": timeout}
        )


class PlanningIterationLimitError(PlanningError):
    def __init__(self, request_id: str, max_iterations: int):
        super().__init__(
            message=f"Planning request '{request_id}' reached iteration limit of {max_iterations}.",
            error_code="ITERATION_LIMIT_REACHED",
            operation="iterate_planning",
            metadata={"request_id": request_id, "max_iterations": max_iterations}
        )


class NoFeasibleOptionError(PlanningError):
    def __init__(self, request_id: str, details: str):
        super().__init__(
            message=f"No feasible option found for planning request '{request_id}': {details}",
            error_code="NO_FEASIBLE_OPTION",
            operation="analyze_feasibility",
            metadata={"request_id": request_id}
        )


class InvalidDecisionError(PlanningError):
    def __init__(self, request_id: str, details: str):
        super().__init__(
            message=f"Invalid decision for request '{request_id}': {details}",
            error_code="INVALID_DECISION",
            operation="form_decision",
            metadata={"request_id": request_id}
        )


class InternalPlanningFailureError(PlanningError):
    def __init__(self, request_id: str, details: str):
        super().__init__(
            message=f"Internal planning failure for request '{request_id}': {details}",
            error_code="INTERNAL_PLANNING_FAILURE",
            operation="execute_planning",
            metadata={"request_id": request_id}
        )


class ReasoningError(EarthMindException):
    """Base exception for B3 Reasoning Engine errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "REASONING_ERROR",
        operation: str = "reasoning_processing",
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            module="reasoning",
            operation=operation,
            retryable=retryable,
            metadata=metadata or {}
        )


class InvalidReasoningInputError(ReasoningError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Invalid reasoning input: {details}",
            error_code="INVALID_REASONING_INPUT",
            operation="validate_input"
        )


class InvalidEvidenceError(ReasoningError):
    def __init__(self, evidence_id: str, details: str):
        super().__init__(
            message=f"Invalid evidence item '{evidence_id}': {details}",
            error_code="INVALID_EVIDENCE",
            operation="validate_evidence",
            metadata={"evidence_id": evidence_id}
        )


class InsufficientEvidenceError(ReasoningError):
    def __init__(self, request_id: str, details: str):
        super().__init__(
            message=f"Insufficient evidence for reasoning request '{request_id}': {details}",
            error_code="INSUFFICIENT_EVIDENCE",
            operation="analyze_evidence",
            metadata={"request_id": request_id}
        )


class ReasoningCapabilityUnavailableError(ReasoningError):
    def __init__(self, capability_name: str, details: str):
        super().__init__(
            message=f"Reasoning capability '{capability_name}' unavailable: {details}",
            error_code="REASONING_CAPABILITY_UNAVAILABLE",
            operation="invoke_capability",
            retryable=True,
            metadata={"capability_name": capability_name}
        )


class ReasoningTimeoutError(ReasoningError):
    def __init__(self, request_id: str, timeout: float):
        super().__init__(
            message=f"Reasoning request '{request_id}' timed out after {timeout} seconds.",
            error_code="REASONING_TIMEOUT",
            operation="execute_strategy",
            retryable=True,
            metadata={"request_id": request_id, "timeout": timeout}
        )


class IterationLimitReachedError(ReasoningError):
    def __init__(self, request_id: str, max_iterations: int):
        super().__init__(
            message=f"Reasoning request '{request_id}' reached iteration limit of {max_iterations}.",
            error_code="ITERATION_LIMIT_REACHED",
            operation="iterate_strategy",
            metadata={"request_id": request_id, "max_iterations": max_iterations}
        )


class InvalidReasoningResultError(ReasoningError):
    def __init__(self, request_id: str, details: str):
        super().__init__(
            message=f"Invalid reasoning result for request '{request_id}': {details}",
            error_code="INVALID_REASONING_RESULT",
            operation="validate_result",
            metadata={"request_id": request_id}
        )


class ReasoningValidationHandoffError(ReasoningError):
    def __init__(self, request_id: str, details: str):
        super().__init__(
            message=f"Validation handoff failed for reasoning request '{request_id}': {details}",
            error_code="REASONING_VALIDATION_HANDOFF_ERROR",
            operation="handoff_validation",
            metadata={"request_id": request_id}
        )


class InternalReasoningFailureError(ReasoningError):
    def __init__(self, request_id: str, details: str):
        super().__init__(
            message=f"Internal reasoning failure for request '{request_id}': {details}",
            error_code="INTERNAL_REASONING_FAILURE",
            operation="execute_reasoning",
            metadata={"request_id": request_id}
        )


class ContextError(EarthMindException):
    """Base exception for B2 Context Manager errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "CONTEXT_ERROR",
        operation: str = "context_processing",
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            module="context",
            operation=operation,
            retryable=retryable,
            metadata=metadata or {}
        )


class InvalidContextRequestError(ContextError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Invalid context request: {details}",
            error_code="INVALID_CONTEXT_REQUEST",
            operation="validate_request"
        )


class InvalidContextItemError(ContextError):
    def __init__(self, item_id: str, details: str):
        super().__init__(
            message=f"Invalid context item '{item_id}': {details}",
            error_code="INVALID_CONTEXT_ITEM",
            operation="validate_item",
            metadata={"item_id": item_id}
        )


class ContextScopeViolationError(ContextError):
    def __init__(self, item_id: str, details: str):
        super().__init__(
            message=f"Scope violation in context item '{item_id}': {details}",
            error_code="CONTEXT_SCOPE_VIOLATION",
            operation="filter_scope",
            metadata={"item_id": item_id}
        )


class ContextPrivacyViolationError(ContextError):
    def __init__(self, item_id: str, details: str):
        super().__init__(
            message=f"Privacy violation in context item '{item_id}': {details}",
            error_code="CONTEXT_PRIVACY_VIOLATION",
            operation="filter_privacy",
            metadata={"item_id": item_id}
        )


class InsufficientContextError(ContextError):
    def __init__(self, request_id: str, details: str):
        super().__init__(
            message=f"Insufficient context for request '{request_id}': {details}",
            error_code="INSUFFICIENT_CONTEXT",
            operation="prepare_context",
            metadata={"request_id": request_id}
        )


class ContextOutputValidationError(ContextError):
    def __init__(self, request_id: str, details: str):
        super().__init__(
            message=f"Output validation failed for context request '{request_id}': {details}",
            error_code="CONTEXT_OUTPUT_VALIDATION_ERROR",
            operation="validate_output",
            metadata={"request_id": request_id}
        )


class ContextProviderError(ContextError):
    def __init__(self, provider_name: str, details: str):
        super().__init__(
            message=f"Context provider '{provider_name}' error: {details}",
            error_code="CONTEXT_PROVIDER_ERROR",
            operation="collect_context",
            metadata={"provider_name": provider_name}
        )


class UnknownModelVersionError(EarthMindException):
    def __init__(self, identifier: str, version: str):
        super().__init__(
            message=f"Model '{identifier}' version '{version}' is not registered.",
            error_code="UNKNOWN_MODEL_VERSION",
            module="ai",
            operation="version_lookup"
        )


class InvalidLifecycleTransitionError(EarthMindException):
    def __init__(self, identifier: str, version: str, current_state: str, target_state: str, reason: str = ""):
        msg = f"Invalid lifecycle transition for model '{identifier}' (v{version}): {current_state} -> {target_state}."
        if reason:
            msg += f" Reason: {reason}"
        super().__init__(
            message=msg,
            error_code="INVALID_LIFECYCLE_TRANSITION",
            module="ai",
            operation="transition_lifecycle"
        )


class ModelCompatibilityError(EarthMindException):
    def __init__(self, identifier: str, version: str, details: str):
        super().__init__(
            message=f"Model '{identifier}' (v{version}) failed compatibility check: {details}",
            error_code="MODEL_COMPATIBILITY_ERROR",
            module="ai",
            operation="check_compatibility"
        )


class ValidationGateError(EarthMindException):
    def __init__(self, identifier: str, version: str, details: str):
        super().__init__(
            message=f"Validation gate failed for model '{identifier}' (v{version}): {details}",
            error_code="VALIDATION_GATE_ERROR",
            module="ai",
            operation="validate_gate"
        )


class ModelActivationError(EarthMindException):
    def __init__(self, identifier: str, version: str, details: str):
        super().__init__(
            message=f"Failed to activate model '{identifier}' (v{version}): {details}",
            error_code="MODEL_ACTIVATION_ERROR",
            module="ai",
            operation="activate_version"
        )


class ModelRollbackError(EarthMindException):
    def __init__(self, identifier: str, details: str):
        super().__init__(
            message=f"Rollback failed for model '{identifier}': {details}",
            error_code="MODEL_ROLLBACK_ERROR",
            module="ai",
            operation="rollback_version"
        )


class RetiredModelSelectedError(EarthMindException):
    def __init__(self, identifier: str, version: str):
        super().__init__(
            message=f"Cannot select or activate retired model '{identifier}' (v{version}).",
            error_code="RETIRED_MODEL_SELECTED",
            module="ai",
            operation="select_version"
        )


class ConflictingActiveVersionError(EarthMindException):
    def __init__(self, identifier: str, existing_version: str, new_version: str):
        super().__init__(
            message=f"Cannot set active version to '{new_version}' because '{existing_version}' is already active for model '{identifier}'.",
            error_code="CONFLICTING_ACTIVE_VERSION",
            module="ai",
            operation="activate_version"
        )


class InvalidRevisionError(EarthMindException):
    def __init__(self, identifier: str, revision: str, details: str):
        super().__init__(
            message=f"Invalid revision '{revision}' for model '{identifier}': {details}",
            error_code="INVALID_REVISION",
            module="ai",
            operation="validate_revision"
        )

class DuplicateRequestError(EarthMindException):
    def __init__(self, request_id: str):
        super().__init__(
            message=f"Duplicate inference request with ID '{request_id}'.",
            error_code="DUPLICATE_REQUEST",
            module="ai",
            operation="execute",
            metadata={"request_id": request_id}
        )
