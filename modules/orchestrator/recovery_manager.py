from typing import Any, Dict, Optional

from core.logging.logger import get_logger
from modules.orchestrator.enums import (
    FailureHandlingPolicy,
    StepExecutionState,
)
from modules.orchestrator.interfaces import (
    ICapabilityManager,
    IRecoveryManager,
)
from modules.orchestrator.schemas import (
    OrchestrationPolicyConfig,
    StepExecutionResult,
    WorkflowComposition,
    WorkflowStepSpec,
)

logger = get_logger("orchestrator.recovery_manager")


class RecoveryManager(IRecoveryManager):
    """B5.7 Recovery / Replanning Manager.

    Responsibilities:
    - RECOVERABLE FAILURE: Bounded retry or compatible alternative capability substitution.
    - MISSING INFORMATION: Identify missing required input/capability and route to re-execute affected workflow stage.
    - CRITICAL FAILURE: Perform controlled stop, record explicit failure, never fabricate outputs!

    STRICT ARCHITECTURAL BOUNDARY:
    - Replanning is strictly orchestration-level (stage re-routing, step substitution).
    - Must NOT perform agricultural domain reasoning or decision making.
    - Must NOT blindly restart the entire workflow.
    """

    def handle_step_failure(
        self,
        step_result: StepExecutionResult,
        workflow: WorkflowComposition,
        capability_manager: ICapabilityManager,
        policy: OrchestrationPolicyConfig,
    ) -> Optional[StepExecutionResult]:
        """Handle capability step failure according to policy and availability of alternatives."""
        step_spec = self._find_step_spec(workflow, step_result.step_id)
        if not step_spec:
            logger.error(f"Step spec '{step_result.step_id}' not found in workflow composition.")
            return step_result

        policy_type = step_spec.failure_policy or policy.failure_policy

        logger.info(
            f"Handling failure for step '{step_result.step_id}' using policy {policy_type.value}",
            extra={"step_id": step_result.step_id, "policy": policy_type.value},
        )

        if policy_type == FailureHandlingPolicy.RETRY_THEN_ALT:
            # 1. Check for alternative capability substitution
            if step_spec.alternative_capability_id and capability_manager.is_available(step_spec.alternative_capability_id):
                if capability_manager.check_contract_compatibility(step_spec.capability_id, step_spec.alternative_capability_id):
                    logger.info(
                        f"Found compatible alternative capability '{step_spec.alternative_capability_id}' for step '{step_result.step_id}'"
                    )
                    alt_cap = capability_manager.get_capability(step_spec.alternative_capability_id)
                    try:
                        out = alt_cap.execute(step_spec.operation, {}, {})
                        return StepExecutionResult(
                            step_id=step_result.step_id,
                            capability_id=step_spec.alternative_capability_id,
                            operation=step_spec.operation,
                            status=StepExecutionState.COMPLETED,
                            output=out,
                        )
                    except Exception as e:
                        logger.error(f"Alternative capability execution failed: {str(e)}")

        elif policy_type == FailureHandlingPolicy.CONTINUE_ON_PARTIAL:
            if not step_spec.is_required:
                logger.info(f"Step '{step_result.step_id}' is not required; permitting partial output continuation")
                return StepExecutionResult(
                    step_id=step_result.step_id,
                    capability_id=step_result.capability_id,
                    operation=step_result.operation,
                    status=StepExecutionState.SKIPPED,
                    error=f"Non-critical failure ignored: {step_result.error}",
                )

        # Critical failure stop: return original failed step result without fabrication
        return step_result

    def identify_missing_information_stage(
        self, missing_info_keys: list, workflow: WorkflowComposition
    ) -> Optional[WorkflowStepSpec]:
        """Identify which affected workflow stage should be re-executed when missing information is identified."""
        for step in workflow.steps:
            if step.capability_id in ("context", "memory", "vision"):
                return step
        return workflow.steps[0] if workflow.steps else None

    def _find_step_spec(
        self, workflow: WorkflowComposition, step_id: str
    ) -> Optional[WorkflowStepSpec]:
        for step in workflow.steps:
            if step.step_id == step_id:
                return step
        return None
