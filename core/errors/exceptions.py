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


class EmbeddingError(EarthMindException):
    """Base exception for C.2 Knowledge Base embedding provider errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "EMBEDDING_ERROR",
        operation: str = "embedding_processing",
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            module="knowledge_base",
            operation=operation,
            retryable=retryable,
            metadata=metadata or {}
        )


class InvalidEmbeddingInputError(EmbeddingError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Invalid embedding input: {details}",
            error_code="INVALID_EMBEDDING_INPUT",
            operation="validate_input",
            metadata={"details": details}
        )


class EmbeddingProviderUnavailableError(EmbeddingError):
    def __init__(self, provider_name: str, details: str = "Provider unavailable or offline."):
        super().__init__(
            message=f"Embedding provider '{provider_name}' unavailable: {details}",
            error_code="EMBEDDING_PROVIDER_UNAVAILABLE",
            operation="check_availability",
            retryable=True,
            metadata={"provider_name": provider_name, "details": details}
        )


class EmbeddingConfigurationError(EmbeddingError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Embedding configuration error: {details}",
            error_code="EMBEDDING_CONFIGURATION_ERROR",
            operation="validate_config",
            metadata={"details": details}
        )


class EmbeddingRateLimitError(EmbeddingError):
    def __init__(self, provider_name: str, details: str = "Rate limit exceeded."):
        super().__init__(
            message=f"Embedding provider '{provider_name}' rate limit exceeded: {details}",
            error_code="EMBEDDING_RATE_LIMIT",
            operation="execute_embedding",
            retryable=True,
            metadata={"provider_name": provider_name, "details": details}
        )


class EmbeddingTimeoutError(EmbeddingError):
    def __init__(self, provider_name: str, timeout: float):
        super().__init__(
            message=f"Embedding generation timed out after {timeout} seconds on provider '{provider_name}'.",
            error_code="EMBEDDING_TIMEOUT",
            operation="execute_embedding",
            retryable=True,
            metadata={"provider_name": provider_name, "timeout": timeout}
        )


class EmbeddingExecutionError(EmbeddingError):
    def __init__(self, provider_name: str, details: str):
        super().__init__(
            message=f"Embedding execution error on provider '{provider_name}': {details}",
            error_code="EMBEDDING_EXECUTION_ERROR",
            operation="execute_embedding",
            metadata={"provider_name": provider_name, "details": details}
        )


class InvalidEmbeddingResponseError(EmbeddingError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Invalid embedding response: {details}",
            error_code="INVALID_EMBEDDING_RESPONSE",
            operation="validate_response",
            metadata={"details": details}
        )


class EmbeddingDimensionMismatchError(EmbeddingError):
    def __init__(self, expected_dim: int, actual_dim: int, details: str = ""):
        msg = f"Dimension mismatch: expected {expected_dim}, got {actual_dim}."
        if details:
            msg += f" {details}"
        super().__init__(
            message=msg,
            error_code="EMBEDDING_DIMENSION_MISMATCH",
            operation="validate_dimension",
            metadata={"expected_dim": expected_dim, "actual_dim": actual_dim, "details": details}
        )


class SparseRepresentationError(EmbeddingError):
    """Base exception for C.2 Knowledge Base sparse representation errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "SPARSE_REPRESENTATION_ERROR",
        operation: str = "sparse_processing",
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            operation=operation,
            retryable=retryable,
            metadata=metadata or {}
        )


class InvalidSparseInputError(SparseRepresentationError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Invalid sparse representation input: {details}",
            error_code="INVALID_SPARSE_INPUT",
            operation="validate_input",
            metadata={"details": details}
        )


class SparseProviderUnavailableError(SparseRepresentationError):
    def __init__(self, provider_name: str, details: str = "Sparse provider unavailable or offline."):
        super().__init__(
            message=f"Sparse provider '{provider_name}' unavailable: {details}",
            error_code="SPARSE_PROVIDER_UNAVAILABLE",
            operation="check_availability",
            retryable=True,
            metadata={"provider_name": provider_name, "details": details}
        )


class SparseConfigurationError(SparseRepresentationError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Sparse provider configuration error: {details}",
            error_code="SPARSE_CONFIGURATION_ERROR",
            operation="validate_config",
            metadata={"details": details}
        )


class SparseExecutionError(SparseRepresentationError):
    def __init__(self, provider_name: str, details: str):
        super().__init__(
            message=f"Sparse execution error on provider '{provider_name}': {details}",
            error_code="SPARSE_EXECUTION_ERROR",
            operation="execute_sparse",
            metadata={"provider_name": provider_name, "details": details}
        )


class InvalidSparseResponseError(SparseRepresentationError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Invalid sparse response: {details}",
            error_code="INVALID_SPARSE_RESPONSE",
            operation="validate_response",
            metadata={"details": details}
        )


class SparseVectorValidationError(SparseRepresentationError):
    def __init__(self, details: str):
        super().__init__(
            message=f"SparseVector validation failed: {details}",
            error_code="SPARSE_VECTOR_VALIDATION_ERROR",
            operation="validate_sparse_vector",
            metadata={"details": details}
        )


class IndexError(EarthMindException):
    """Base exception for C.2 Knowledge Base Index Layer errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "INDEX_ERROR",
        operation: str = "index_processing",
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            module="knowledge_base",
            operation=operation,
            retryable=retryable,
            metadata=metadata or {}
        )


class InvalidIndexRecordError(IndexError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Invalid index record: {details}",
            error_code="INVALID_INDEX_RECORD",
            operation="validate_record",
            metadata={"details": details}
        )


class IndexProviderUnavailableError(IndexError):
    def __init__(self, provider_name: str, details: str = "Index provider unavailable or offline."):
        super().__init__(
            message=f"Index provider '{provider_name}' unavailable: {details}",
            error_code="INDEX_PROVIDER_UNAVAILABLE",
            operation="check_availability",
            retryable=True,
            metadata={"provider_name": provider_name, "details": details}
        )


class IndexConfigurationError(IndexError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Index configuration error: {details}",
            error_code="INDEX_CONFIGURATION_ERROR",
            operation="validate_config",
            metadata={"details": details}
        )


class IndexExecutionError(IndexError):
    def __init__(self, provider_name: str, details: str):
        super().__init__(
            message=f"Index execution error on provider '{provider_name}': {details}",
            error_code="INDEX_EXECUTION_ERROR",
            operation="execute_index",
            metadata={"provider_name": provider_name, "details": details}
        )


class CollectionOperationError(IndexError):
    def __init__(self, collection_name: str, operation: str, details: str):
        super().__init__(
            message=f"Collection operation '{operation}' failed on '{collection_name}': {details}",
            error_code="COLLECTION_OPERATION_ERROR",
            operation=operation,
            metadata={"collection_name": collection_name, "details": details}
        )


class IndexDimensionMismatchError(IndexError):
    def __init__(self, expected_dim: int, actual_dim: int, details: str = ""):
        msg = f"Index vector dimension mismatch: expected {expected_dim}, got {actual_dim}."
        if details:
            msg += f" {details}"
        super().__init__(
            message=msg,
            error_code="INDEX_DIMENSION_MISMATCH",
            operation="validate_dimension",
            metadata={"expected_dim": expected_dim, "actual_dim": actual_dim, "details": details}
        )


class QdrantAdapterError(IndexError):
    def __init__(self, details: str, operation: str = "qdrant_operation", retryable: bool = False):
        super().__init__(
            message=f"Qdrant adapter error: {details}",
            error_code="QDRANT_ADAPTER_ERROR",
            operation=operation,
            retryable=retryable,
            metadata={"details": details}
        )


class CollectionError(EarthMindException):
    """Base exception for C.2 Knowledge Base Collection errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "COLLECTION_ERROR",
        operation: str = "collection_processing",
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            module="knowledge_base",
            operation=operation,
            retryable=retryable,
            metadata=metadata or {}
        )


class InvalidCollectionError(CollectionError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Invalid collection definition: {details}",
            error_code="INVALID_COLLECTION",
            operation="validate_collection",
            metadata={"details": details}
        )


class CollectionNotFoundError(CollectionError):
    def __init__(self, collection_identifier: str):
        super().__init__(
            message=f"Knowledge Collection '{collection_identifier}' was not found.",
            error_code="COLLECTION_NOT_FOUND",
            operation="lookup_collection",
            metadata={"collection_identifier": collection_identifier}
        )


class DuplicateCollectionError(CollectionError):
    def __init__(self, collection_identifier: str):
        super().__init__(
            message=f"Knowledge Collection '{collection_identifier}' already exists.",
            error_code="DUPLICATE_COLLECTION",
            operation="create_collection",
            metadata={"collection_identifier": collection_identifier}
        )


class PublicationError(EarthMindException):
    """Base exception for C.2 Knowledge Base Publication errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "PUBLICATION_ERROR",
        operation: str = "publication_processing",
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            module="knowledge_base",
            operation=operation,
            retryable=retryable,
            metadata=metadata or {}
        )


class PublicationEligibilityError(PublicationError):
    def __init__(self, object_id: str, reasons: Any):
        super().__init__(
            message=f"Knowledge object '{object_id}' is not eligible for publication: {reasons}",
            error_code="PUBLICATION_ELIGIBILITY_ERROR",
            operation="evaluate_eligibility",
            metadata={"object_id": object_id, "reasons": str(reasons)}
        )


class PublicationValidationError(PublicationError):
    def __init__(self, object_id: str, details: str):
        super().__init__(
            message=f"Publication validation failed for object '{object_id}': {details}",
            error_code="PUBLICATION_VALIDATION_ERROR",
            operation="validate_publication",
            metadata={"object_id": object_id, "details": details}
        )


class InvalidPublicationStateError(PublicationError):
    def __init__(self, object_id: str, current_state: str, target_state: str, details: str = ""):
        msg = f"Invalid publication state transition for object '{object_id}': {current_state} -> {target_state}."
        if details:
            msg += f" Details: {details}"
        super().__init__(
            message=msg,
            error_code="INVALID_PUBLICATION_STATE",
            operation="transition_state",
            metadata={"object_id": object_id, "current_state": current_state, "target_state": target_state}
        )


class PublicationIndexUnavailableError(PublicationError):
    def __init__(self, object_id: str, details: str = "Index adapter or representation is unavailable."):
        super().__init__(
            message=f"Index unavailable for published object '{object_id}': {details}",
            error_code="PUBLICATION_INDEX_UNAVAILABLE",
            operation="sync_index",
            retryable=True,
            metadata={"object_id": object_id, "details": details}
        )


class BoundaryError(EarthMindException):
    """Base exception for C.3 RAG-Memory boundary errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "BOUNDARY_ERROR",
        operation: str = "boundary_validation",
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


class BoundaryValidationError(BoundaryError):
    def __init__(self, details: str, metadata: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Boundary validation failed: {details}",
            error_code="BOUNDARY_VALIDATION_ERROR",
            operation="validate_boundary",
            metadata=metadata or {}
        )


class PromotionNotAllowedError(BoundaryError):
    def __init__(self, source_ownership: str, target_ownership: str, reason: str = ""):
        msg = f"Cross-domain promotion not allowed from '{source_ownership}' to '{target_ownership}'."
        if reason:
            msg += f" {reason}"
        super().__init__(
            message=msg,
            error_code="PROMOTION_NOT_ALLOWED",
            operation="promote_domain",
            metadata={"source_ownership": source_ownership, "target_ownership": target_ownership}
        )


class ScopeViolationBoundaryError(BoundaryValidationError):
    def __init__(self, scope: str, details: str):
        super().__init__(
            details=f"Scope '{scope}' violation: {details}",
            metadata={"scope": scope, "details": details}
        )


class PrivacyBoundaryError(BoundaryValidationError):
    def __init__(self, details: str):
        super().__init__(
            details=f"Privacy boundary violation: {details}",
            metadata={"details": details}
        )


class ULPUError(EarthMindException):
    """Base exception for all ULPU (Universal Language Processing Unit) errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "ULPU_ERROR",
        operation: str = "language_processing",
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            module="ulpu",
            operation=operation,
            retryable=retryable,
            metadata=metadata or {}
        )


class InvalidInputError(ULPUError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Invalid ULPU input: {details}",
            error_code="INVALID_INPUT",
            operation="validate_input",
            metadata={"details": details}
        )


class UnsupportedLanguageError(ULPUError):
    def __init__(self, language_code: str, capability: str = "general"):
        super().__init__(
            message=f"Unsupported language code '{language_code}' for capability '{capability}'.",
            error_code="UNSUPPORTED_LANGUAGE",
            operation="check_language_support",
            metadata={"language_code": language_code, "capability": capability}
        )


class AudioProcessingError(ULPUError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Audio processing error: {details}",
            error_code="AUDIO_PROCESSING_ERROR",
            operation="process_audio",
            metadata={"details": details}
        )


class STTError(ULPUError):
    def __init__(self, provider_name: str, details: str, retryable: bool = False):
        super().__init__(
            message=f"Speech-to-Text error from provider '{provider_name}': {details}",
            error_code="STT_ERROR",
            operation="transcribe_speech",
            retryable=retryable,
            metadata={"provider_name": provider_name, "details": details}
        )


class TranslationError(ULPUError):
    def __init__(self, provider_name: str, source_lang: str, target_lang: str, details: str, retryable: bool = False):
        super().__init__(
            message=f"Translation error ({source_lang} -> {target_lang}) from provider '{provider_name}': {details}",
            error_code="TRANSLATION_ERROR",
            operation="translate_text",
            retryable=retryable,
            metadata={"provider_name": provider_name, "source_lang": source_lang, "target_lang": target_lang, "details": details}
        )


class TTSError(ULPUError):
    def __init__(self, provider_name: str, details: str, retryable: bool = False):
        super().__init__(
            message=f"Text-to-Speech synthesis error from provider '{provider_name}': {details}",
            error_code="TTS_ERROR",
            operation="synthesize_speech",
            retryable=retryable,
            metadata={"provider_name": provider_name, "details": details}
        )


class ProviderError(ULPUError):
    def __init__(self, provider_name: str, details: str, retryable: bool = False):
        super().__init__(
            message=f"ULPU provider error for '{provider_name}': {details}",
            error_code="PROVIDER_ERROR",
            operation="invoke_provider",
            retryable=retryable,
            metadata={"provider_name": provider_name, "details": details}
        )


class ULPUTimeoutError(ULPUError):
    def __init__(self, operation: str, timeout: float):
        super().__init__(
            message=f"ULPU operation '{operation}' timed out after {timeout} seconds.",
            error_code="ULPU_TIMEOUT",
            operation=operation,
            retryable=True,
            metadata={"timeout": timeout}
        )


class LowConfidenceError(ULPUError):
    def __init__(self, operation: str, confidence: float, threshold: float):
        super().__init__(
            message=f"ULPU confidence {confidence:.2f} below threshold {threshold:.2f} for operation '{operation}'.",
            error_code="LOW_CONFIDENCE",
            operation=operation,
            metadata={"confidence": confidence, "threshold": threshold}
        )


class ULPUConfigurationError(ULPUError):
    def __init__(self, details: str):
        super().__init__(
            message=f"ULPU configuration error: {details}",
            error_code="ULPU_CONFIGURATION_ERROR",
            operation="validate_config",
            metadata={"details": details}
        )


class InternalULPUError(ULPUError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Internal ULPU failure: {details}",
            error_code="INTERNAL_ULPU_ERROR",
            operation="execute_ulpu",
            metadata={"details": details}
        )


class RerankError(EarthMindException):
    """Base exception for Stage R8 Reranking errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "RERANK_ERROR",
        operation: str = "rerank_processing",
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            module="knowledge_base",
            operation=operation,
            retryable=retryable,
            metadata=metadata or {}
        )


class InvalidRerankRequestError(RerankError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Invalid rerank request: {details}",
            error_code="INVALID_RERANK_REQUEST",
            operation="validate_request",
            metadata={"details": details}
        )


class RerankerProviderUnavailableError(RerankError):
    def __init__(self, provider_name: str, details: str = "Reranker provider unavailable or offline."):
        super().__init__(
            message=f"Reranker provider '{provider_name}' unavailable: {details}",
            error_code="RERANKER_PROVIDER_UNAVAILABLE",
            operation="check_availability",
            retryable=True,
            metadata={"provider_name": provider_name, "details": details}
        )


class RerankerConfigurationError(RerankError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Reranker configuration error: {details}",
            error_code="RERANKER_CONFIGURATION_ERROR",
            operation="validate_config",
            metadata={"details": details}
        )


class RerankerExecutionError(RerankError):
    def __init__(self, provider_name: str, details: str):
        super().__init__(
            message=f"Reranker execution error on provider '{provider_name}': {details}",
            error_code="RERANKER_EXECUTION_ERROR",
            operation="execute_rerank",
            metadata={"provider_name": provider_name, "details": details}
        )


class InvalidRerankerResponseError(RerankError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Invalid reranker response: {details}",
            error_code="INVALID_RERANKER_RESPONSE",
            operation="validate_response",
            metadata={"details": details}
        )


class RerankerTimeoutError(RerankError):
    def __init__(self, provider_name: str, timeout: float):
        super().__init__(
            message=f"Reranking timed out after {timeout} seconds on provider '{provider_name}'.",
            error_code="RERANKER_TIMEOUT",
            operation="execute_rerank",
            retryable=True,
            metadata={"provider_name": provider_name, "timeout": timeout}
        )


class RerankFallbackError(RerankError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Rerank fallback failed: {details}",
            error_code="RERANK_FALLBACK_ERROR",
            operation="execute_fallback",
            metadata={"details": details}
        )


class QueryProcessingError(EarthMindException):
    """Base exception for Stage R9 Query Processing errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "QUERY_PROCESSING_ERROR",
        operation: str = "query_processing",
        retryable: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=error_code,
            module="knowledge_base",
            operation=operation,
            retryable=retryable,
            metadata=metadata or {}
        )


class InvalidQueryError(QueryProcessingError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Invalid query: {details}",
            error_code="INVALID_QUERY",
            operation="validate_request",
            metadata={"details": details}
        )


class QueryValidationError(QueryProcessingError):
    def __init__(self, details: str, errors: Optional[list] = None):
        super().__init__(
            message=f"Query validation error: {details}",
            error_code="QUERY_VALIDATION_ERROR",
            operation="validate_query",
            metadata={"details": details, "errors": errors or []}
        )


class QueryNormalizationError(QueryProcessingError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Query normalization error: {details}",
            error_code="QUERY_NORMALIZATION_ERROR",
            operation="normalize_query",
            metadata={"details": details}
        )


class QueryExpansionError(QueryProcessingError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Query expansion error: {details}",
            error_code="QUERY_EXPANSION_ERROR",
            operation="expand_query",
            metadata={"details": details}
        )


class QueryProcessingTimeoutError(QueryProcessingError):
    def __init__(self, request_id: str, timeout: float):
        super().__init__(
            message=f"Query processing timed out after {timeout} seconds for request '{request_id}'.",
            error_code="QUERY_PROCESSING_TIMEOUT",
            operation="process_query",
            retryable=True,
            metadata={"request_id": request_id, "timeout": timeout}
        )


class QueryConfigurationError(QueryProcessingError):
    def __init__(self, details: str):
        super().__init__(
            message=f"Query processing configuration error: {details}",
            error_code="QUERY_CONFIGURATION_ERROR",
            operation="validate_config",
            metadata={"details": details}
        )
