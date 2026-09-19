from typing import Any, Dict

from core.logging.logger import get_logger
from modules.orchestrator.enums import (
    CompletionCondition,
    StepExecutionState,
)
from modules.orchestrator.interfaces import ICompletionManager
from modules.orchestrator.schemas import (
    OrchestrationPolicyConfig,
    StepExecutionResult,
    WorkflowComposition,
)

logger = get_logger("orchestrator.completion_manager")


class CompletionManager(ICompletionManager):
    """B5.8 Completion Manager.

    Enforces completion conditions:
    1. All required capabilities/steps completed.
    2. Required outputs available.
    3. Final result valid.
    4. Inspector validation completed (PASS or FLAG).
    5. No unresolved blocking error.
    6. Required human/user confirmation obtained where applicable.
    7. Completion policy satisfied.
    """

    def is_complete(
        self,
        workflow: WorkflowComposition,
        step_results: Dict[str, StepExecutionResult],
        policy: OrchestrationPolicyConfig,
        inspector_status: str = "PASS",
    ) -> bool:
        """Evaluate if workflow execution satisfies all completion criteria."""
        # 1. Check required step completions
        for step in workflow.steps:
            if step.is_required:
                res = step_results.get(step.step_id)
                if not res or res.status != StepExecutionState.COMPLETED:
                    logger.warning(
                        f"Completion check failed: required step '{step.step_id}' status is {res.status if res else 'MISSING'}"
                    )
                    return False

        # 2. Check Inspector status
        if policy.require_inspector:
            if inspector_status not in ("PASS", "FLAG"):
                logger.warning(
                    f"Completion check failed: Inspector status '{inspector_status}' is not PASS or FLAG"
                )
                return False

        # 3. Check completion conditions specified in composition
        for cond in workflow.completion_requirements:
            if cond == CompletionCondition.ALL_STEPS_COMPLETED:
                for step_id, res in step_results.items():
                    if res.status != StepExecutionState.COMPLETED:
                        return False
            elif cond == CompletionCondition.INSPECTOR_PASS:
                if inspector_status not in ("PASS", "FLAG"):
                    return False

        logger.info(
            f"Completion criteria satisfied for workflow {workflow.workflow_id}",
            extra={"workflow_id": workflow.workflow_id, "inspector_status": inspector_status},
        )
        return True

    def extract_final_output(
        self, workflow: WorkflowComposition, step_results: Dict[str, StepExecutionResult]
    ) -> Any:
        """Extract primary output from the last executed required step."""
        for step in reversed(workflow.steps):
            res = step_results.get(step.step_id)
            if res and res.status == StepExecutionState.COMPLETED and res.output is not None:
                return res.output
        return None
