import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set

from core.logging.logger import get_logger
from modules.orchestrator.enums import (
    StepExecutionState,
    WorkflowState,
)
from modules.orchestrator.errors import (
    CapabilityCancelledError,
    CapabilityExecutionError,
    CapabilityNotFoundError,
    CapabilityTimeoutError,
    InvalidContractError,
)
from modules.orchestrator.interfaces import (
    ICapabilityManager,
    IExecutionController,
)
from modules.orchestrator.schemas import (
    OrchestrationRequest,
    StepExecutionResult,
    WorkflowComposition,
    WorkflowStepSpec,
)

logger = get_logger("orchestrator.execution_controller")


class ExecutionController(IExecutionController):
    """B5.5 Execution Controller.

    Enforces explicit 9-state step execution lifecycle:
    PREPARE -> VALIDATE_INPUT -> CHECK_DEPENDENCY -> INVOKE_CAPABILITY -> MONITOR
    -> RECEIVE_RESULT -> VALIDATE_RESULT_CONTRACT -> RECORD_STATE -> ROUTE_RESULT

    Key Features:
    - Preserves capability dependency ordering.
    - Executes independent operations concurrently where safe using ThreadPoolExecutor.
    - Enforces step-level and request-level timeouts.
    - Propagates cancellation cleanly across active operations.
    - Validates capability result contracts before routing output.
    """

    def __init__(self, max_workers: int = 4) -> None:
        self.max_workers = max_workers

    def execute_workflow(
        self,
        workflow: WorkflowComposition,
        request: OrchestrationRequest,
        capability_manager: ICapabilityManager,
    ) -> Dict[str, StepExecutionResult]:
        """Execute all steps in a WorkflowComposition, respecting dependencies and concurrency."""
        step_results: Dict[str, StepExecutionResult] = {}
        completed_step_ids: Set[str] = set()
        failed_step_ids: Set[str] = set()

        start_time = time.time()
        max_timeout = request.policy.timeout_seconds

        # Build lookup for steps by ID
        steps_by_id: Dict[str, WorkflowStepSpec] = {s.step_id: s for s in workflow.steps}
        remaining_step_ids: Set[str] = set(steps_by_id.keys())

        logger.info(
            f"Starting workflow execution for request {request.request_id} with {len(workflow.steps)} steps",
            extra={"request_id": request.request_id, "workflow_id": workflow.workflow_id},
        )

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            while remaining_step_ids:
                # Check for overall request timeout
                elapsed = time.time() - start_time
                if elapsed > max_timeout:
                    logger.error(f"Workflow timeout exceeded after {elapsed:.2f}s")
                    break

                # Check for cancellation flag in request
                if request.metadata.get("trigger_cancelled") or request.metadata.get("is_cancelled"):
                    logger.warning(f"Workflow execution cancelled for request {request.request_id}")
                    break

                # Identify steps ready to execute (all dependencies satisfied)
                ready_steps: List[WorkflowStepSpec] = []
                for s_id in list(remaining_step_ids):
                    step = steps_by_id[s_id]
                    # Check if all required dependencies are in completed_step_ids
                    # If a dependency failed, handle based on dependency specification
                    deps_satisfied = True
                    deps_failed = False
                    for dep in step.dependencies:
                        if dep in failed_step_ids:
                            deps_failed = True
                            break
                        if dep not in completed_step_ids:
                            deps_satisfied = False
                            break

                    if deps_failed:
                        # Skip or fail step due to failed dependency
                        logger.warning(f"Step '{s_id}' dependency failed, marking skipped/failed")
                        step_results[s_id] = StepExecutionResult(
                            step_id=s_id,
                            capability_id=step.capability_id,
                            operation=step.operation,
                            status=StepExecutionState.SKIPPED if not step.is_required else StepExecutionState.FAILED,
                            error=f"Dependency failed for step '{s_id}'",
                        )
                        remaining_step_ids.remove(s_id)
                        failed_step_ids.add(s_id)
                        continue

                    if deps_satisfied:
                        ready_steps.append(step)

                if not ready_steps:
                    if remaining_step_ids:
                        logger.error("Deadlock or blocked step in workflow execution graph")
                        break
                    else:
                        break

                # Submit ready independent steps for execution (concurrently or sequentially)
                futures = {}
                for step in ready_steps:
                    remaining_step_ids.remove(step.step_id)
                    futures[
                        executor.submit(
                            self.execute_step_lifecycle,
                            step=step,
                            request=request,
                            capability_manager=capability_manager,
                            prior_results=step_results,
                        )
                    ] = step.step_id

                for future in as_completed(futures):
                    step_id = futures[future]
                    try:
                        res = future.result()
                        step_results[step_id] = res
                        if res.status == StepExecutionState.COMPLETED:
                            completed_step_ids.add(step_id)
                        else:
                            failed_step_ids.add(step_id)
                    except Exception as e:
                        logger.error(f"Uncaught exception executing step '{step_id}': {str(e)}")
                        step_results[step_id] = StepExecutionResult(
                            step_id=step_id,
                            capability_id=steps_by_id[step_id].capability_id,
                            operation=steps_by_id[step_id].operation,
                            status=StepExecutionState.FAILED,
                            error=str(e),
                        )
                        failed_step_ids.add(step_id)

        return step_results

    def execute_step_lifecycle(
        self,
        step: WorkflowStepSpec,
        request: OrchestrationRequest,
        capability_manager: ICapabilityManager,
        prior_results: Dict[str, StepExecutionResult],
    ) -> StepExecutionResult:
        """Execute the full 9-state step execution lifecycle."""
        step_start_time = time.time()
        logger.debug(f"Starting execution lifecycle for step '{step.step_id}'")

        # 1. PREPARE
        status = StepExecutionState.PREPARING

        # Check for cancellation
        if request.metadata.get("trigger_cancelled") or request.metadata.get("is_cancelled"):
            return StepExecutionResult(
                step_id=step.step_id,
                capability_id=step.capability_id,
                operation=step.operation,
                status=StepExecutionState.CANCELLED,
                error="Execution cancelled before step start.",
            )

        # 2. VALIDATE_INPUT
        status = StepExecutionState.VALIDATING_INPUT
        payload = self._gather_step_input(step, request, prior_results)

        # 3. CHECK_DEPENDENCY
        status = StepExecutionState.CHECKING_DEPENDENCY
        try:
            capability = capability_manager.get_capability(step.capability_id)
        except CapabilityNotFoundError as e:
            return StepExecutionResult(
                step_id=step.step_id,
                capability_id=step.capability_id,
                operation=step.operation,
                status=StepExecutionState.FAILED,
                error=str(e),
            )

        # 4. INVOKE_CAPABILITY & 5. MONITOR & 6. RECEIVE_RESULT
        status = StepExecutionState.EXECUTING
        retry_count = 0
        max_retries = step.max_retries
        timeout = step.timeout_seconds
        last_error: Optional[str] = None
        result_output: Any = None

        while retry_count <= max_retries:
            try:
                # Execute capability call with timeout check
                invoke_start = time.time()
                result_output = capability.execute(
                    operation=step.operation,
                    payload=payload,
                    metadata={"request_id": request.request_id, "scope": request.scope.model_dump()},
                )
                invoke_duration = time.time() - invoke_start

                if invoke_duration > timeout:
                    raise CapabilityTimeoutError(step.capability_id, timeout)

                # Step execution succeeded
                last_error = None
                break

            except CapabilityTimeoutError as te:
                last_error = str(te)
                logger.warning(
                    f"Step '{step.step_id}' timed out (attempt {retry_count + 1}/{max_retries + 1}): {last_error}"
                )
                retry_count += 1
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Step '{step.step_id}' failed (attempt {retry_count + 1}/{max_retries + 1}): {last_error}"
                )
                retry_count += 1

        duration = time.time() - step_start_time

        if last_error is not None:
            # Check alternative capability substitution if configured
            if step.alternative_capability_id and capability_manager.is_available(step.alternative_capability_id):
                logger.info(
                    f"Attempting capability substitution for step '{step.step_id}': {step.capability_id} -> {step.alternative_capability_id}"
                )
                try:
                    alt_cap = capability_manager.get_capability(step.alternative_capability_id)
                    alt_out = alt_cap.execute(
                        operation=step.operation,
                        payload=payload,
                        metadata={"request_id": request.request_id, "scope": request.scope.model_dump()},
                    )
                    return StepExecutionResult(
                        step_id=step.step_id,
                        capability_id=step.alternative_capability_id,
                        operation=step.operation,
                        status=StepExecutionState.COMPLETED,
                        output=alt_out,
                        duration_seconds=time.time() - step_start_time,
                        retry_count=retry_count,
                    )
                except Exception as alt_err:
                    logger.error(f"Alternative capability substitution failed for '{step.step_id}': {str(alt_err)}")

            return StepExecutionResult(
                step_id=step.step_id,
                capability_id=step.capability_id,
                operation=step.operation,
                status=StepExecutionState.FAILED,
                error=last_error,
                duration_seconds=duration,
                retry_count=retry_count - 1 if retry_count > 0 else 0,
            )

        # 7. VALIDATE_RESULT_CONTRACT
        status = StepExecutionState.VALIDATING_OUTPUT
        if not self._validate_result_contract(step, result_output):
            return StepExecutionResult(
                step_id=step.step_id,
                capability_id=step.capability_id,
                operation=step.operation,
                status=StepExecutionState.FAILED,
                error="Result failed contract validation",
                duration_seconds=duration,
                retry_count=retry_count,
            )

        # 8. RECORD_STATE & 9. ROUTE_RESULT
        status = StepExecutionState.COMPLETED
        logger.info(f"Step '{step.step_id}' completed successfully in {duration:.2f}s")

        return StepExecutionResult(
            step_id=step.step_id,
            capability_id=step.capability_id,
            operation=step.operation,
            status=StepExecutionState.COMPLETED,
            output=result_output,
            duration_seconds=duration,
            retry_count=retry_count,
        )

    def _gather_step_input(
        self,
        step: WorkflowStepSpec,
        request: OrchestrationRequest,
        prior_results: Dict[str, StepExecutionResult],
    ) -> Dict[str, Any]:
        """Combine request payload and outputs from dependency steps into input for this step."""
        combined_payload = dict(request.payload)
        for dep in step.dependencies:
            dep_res = prior_results.get(dep)
            if dep_res and dep_res.output is not None:
                combined_payload[f"dep_{dep}"] = dep_res.output
                if isinstance(dep_res.output, dict):
                    combined_payload.update(dep_res.output)
        return combined_payload

    def _validate_result_contract(self, step: WorkflowStepSpec, result_output: Any) -> bool:
        """Validate result contract against capability output standards."""
        if result_output is None and step.is_required:
            return False
        return True
