import uuid
from typing import Any, Dict, List, Optional

from core.logging.logger import get_logger
from modules.orchestrator.enums import (
    CompletionCondition,
    FailureHandlingPolicy,
    WorkflowStrategyType,
)
from modules.orchestrator.errors import WorkflowCompositionError
from modules.orchestrator.schemas import WorkflowComposition, WorkflowStepSpec

logger = get_logger("orchestrator.workflow_composer")


class WorkflowComposer:
    """B5.2 Workflow Selector / Composer.

    Responsibility:
    - Select required capability components for a requested strategy.
    - Compose execution workflow with explicit step specifications.
    - Preserve capability dependencies and execution order.
    - Identify sequential operations, parallelizable operations, and conditional branches.
    - Define workflow completion requirements.

    CRITICAL ARCHITECTURAL BOUNDARY:
    - Does NOT create agricultural plans or decisions (B4 responsibility).
    - Does NOT perform agricultural domain reasoning (B3 responsibility).
    - Does NOT prepare or collect context (B2 responsibility).
    - ONLY manages orchestration-level workflow execution graph.
    """

    def compose_workflow(
        self,
        strategy_type: WorkflowStrategyType,
        request_payload: Dict[str, Any],
        available_capability_ids: Optional[List[str]] = None,
        custom_steps: Optional[List[Dict[str, Any]]] = None,
    ) -> WorkflowComposition:
        """Compose a WorkflowComposition graph based on requested strategy_type."""
        workflow_id = f"wf_comp_{uuid.uuid4().hex[:12]}"

        if strategy_type == WorkflowStrategyType.STANDARD_DECISION:
            composition = self._compose_standard_decision(workflow_id, request_payload)
        elif strategy_type == WorkflowStrategyType.VISUAL_DIAGNOSIS:
            composition = self._compose_visual_diagnosis(workflow_id, request_payload)
        elif strategy_type == WorkflowStrategyType.MISSING_INFORMATION:
            composition = self._compose_missing_information(workflow_id, request_payload)
        elif strategy_type == WorkflowStrategyType.MEMORY_ASSISTED:
            composition = self._compose_memory_assisted(workflow_id, request_payload)
        elif strategy_type == WorkflowStrategyType.MULTIMODAL:
            composition = self._compose_multimodal(workflow_id, request_payload)
        elif strategy_type == WorkflowStrategyType.CUSTOM:
            composition = self._compose_custom(workflow_id, request_payload, custom_steps)
        else:
            raise WorkflowCompositionError(workflow_id, f"Unsupported strategy type '{strategy_type}'")

        # Verify dependency integrity of composed workflow
        self.validate_workflow_composition(composition)

        logger.info(
            f"Composed workflow {composition.workflow_id} with strategy {strategy_type.value} containing {len(composition.steps)} steps",
            extra={"workflow_id": composition.workflow_id, "step_count": len(composition.steps)},
        )
        return composition

    def _compose_standard_decision(
        self, workflow_id: str, payload: Dict[str, Any]
    ) -> WorkflowComposition:
        """Standard decision pipeline: Context (B2) -> Reasoning (B3) -> Planning (B4) -> Inspector."""
        steps = [
            WorkflowStepSpec(
                step_id="step_context",
                capability_id="context",
                operation="prepare_context",
                dependencies=[],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_reasoning",
                capability_id="reasoning",
                operation="reason",
                dependencies=["step_context"],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_planning",
                capability_id="planning",
                operation="execute_planning",
                dependencies=["step_reasoning"],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_inspector",
                capability_id="inspector",
                operation="validate_action",
                dependencies=["step_planning"],
                is_required=True,
            ),
        ]
        return WorkflowComposition(
            workflow_id=workflow_id,
            strategy_type=WorkflowStrategyType.STANDARD_DECISION,
            steps=steps,
            completion_requirements=[
                CompletionCondition.REQUIRED_STEPS_COMPLETED,
                CompletionCondition.INSPECTOR_PASS,
            ],
            parallel_groups=[],
        )

    def _compose_visual_diagnosis(
        self, workflow_id: str, payload: Dict[str, Any]
    ) -> WorkflowComposition:
        """Visual diagnosis pipeline: Vision -> Context -> Reasoning -> Planning -> Inspector."""
        steps = [
            WorkflowStepSpec(
                step_id="step_vision",
                capability_id="vision",
                operation="analyze_image",
                dependencies=[],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_context",
                capability_id="context",
                operation="prepare_context",
                dependencies=["step_vision"],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_reasoning",
                capability_id="reasoning",
                operation="reason",
                dependencies=["step_context"],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_planning",
                capability_id="planning",
                operation="execute_planning",
                dependencies=["step_reasoning"],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_inspector",
                capability_id="inspector",
                operation="validate_action",
                dependencies=["step_planning"],
                is_required=True,
            ),
        ]
        return WorkflowComposition(
            workflow_id=workflow_id,
            strategy_type=WorkflowStrategyType.VISUAL_DIAGNOSIS,
            steps=steps,
            completion_requirements=[
                CompletionCondition.REQUIRED_STEPS_COMPLETED,
                CompletionCondition.INSPECTOR_PASS,
            ],
            parallel_groups=[],
        )

    def _compose_missing_information(
        self, workflow_id: str, payload: Dict[str, Any]
    ) -> WorkflowComposition:
        """Missing information pipeline: Target missing info capability -> Context -> Reasoning -> Planning -> Inspector."""
        target_capability = payload.get("missing_info_capability") or "context"
        steps = [
            WorkflowStepSpec(
                step_id="step_fetch_missing_info",
                capability_id=target_capability,
                operation="collect_info",
                dependencies=[],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_context",
                capability_id="context",
                operation="prepare_context",
                dependencies=["step_fetch_missing_info"],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_reasoning",
                capability_id="reasoning",
                operation="reason",
                dependencies=["step_context"],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_planning",
                capability_id="planning",
                operation="execute_planning",
                dependencies=["step_reasoning"],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_inspector",
                capability_id="inspector",
                operation="validate_action",
                dependencies=["step_planning"],
                is_required=True,
            ),
        ]
        return WorkflowComposition(
            workflow_id=workflow_id,
            strategy_type=WorkflowStrategyType.MISSING_INFORMATION,
            steps=steps,
            completion_requirements=[
                CompletionCondition.REQUIRED_STEPS_COMPLETED,
                CompletionCondition.INSPECTOR_PASS,
            ],
            parallel_groups=[],
        )

    def _compose_memory_assisted(
        self, workflow_id: str, payload: Dict[str, Any]
    ) -> WorkflowComposition:
        """Memory-assisted pipeline: Memory -> Context -> Reasoning -> Planning -> Inspector."""
        steps = [
            WorkflowStepSpec(
                step_id="step_memory",
                capability_id="memory",
                operation="retrieve_memory",
                dependencies=[],
                is_required=False,
                failure_policy=FailureHandlingPolicy.CONTINUE_ON_PARTIAL,
            ),
            WorkflowStepSpec(
                step_id="step_context",
                capability_id="context",
                operation="prepare_context",
                dependencies=["step_memory"],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_reasoning",
                capability_id="reasoning",
                operation="reason",
                dependencies=["step_context"],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_planning",
                capability_id="planning",
                operation="execute_planning",
                dependencies=["step_reasoning"],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_inspector",
                capability_id="inspector",
                operation="validate_action",
                dependencies=["step_planning"],
                is_required=True,
            ),
        ]
        return WorkflowComposition(
            workflow_id=workflow_id,
            strategy_type=WorkflowStrategyType.MEMORY_ASSISTED,
            steps=steps,
            completion_requirements=[
                CompletionCondition.REQUIRED_STEPS_COMPLETED,
                CompletionCondition.INSPECTOR_PASS,
            ],
            parallel_groups=[],
        )

    def _compose_multimodal(
        self, workflow_id: str, payload: Dict[str, Any]
    ) -> WorkflowComposition:
        """Multimodal pipeline: Parallel (Vision & ULPU/Language) -> Context -> Reasoning -> Planning -> Inspector."""
        steps = [
            WorkflowStepSpec(
                step_id="step_vision",
                capability_id="vision",
                operation="analyze_image",
                dependencies=[],
                is_required=False,
                failure_policy=FailureHandlingPolicy.CONTINUE_ON_PARTIAL,
            ),
            WorkflowStepSpec(
                step_id="step_ulpu",
                capability_id="ulpu",
                operation="process_language",
                dependencies=[],
                is_required=False,
                failure_policy=FailureHandlingPolicy.CONTINUE_ON_PARTIAL,
            ),
            WorkflowStepSpec(
                step_id="step_context",
                capability_id="context",
                operation="prepare_context",
                dependencies=["step_vision", "step_ulpu"],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_reasoning",
                capability_id="reasoning",
                operation="reason",
                dependencies=["step_context"],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_planning",
                capability_id="planning",
                operation="execute_planning",
                dependencies=["step_reasoning"],
                is_required=True,
            ),
            WorkflowStepSpec(
                step_id="step_inspector",
                capability_id="inspector",
                operation="validate_action",
                dependencies=["step_planning"],
                is_required=True,
            ),
        ]
        return WorkflowComposition(
            workflow_id=workflow_id,
            strategy_type=WorkflowStrategyType.MULTIMODAL,
            steps=steps,
            completion_requirements=[
                CompletionCondition.REQUIRED_STEPS_COMPLETED,
                CompletionCondition.INSPECTOR_PASS,
            ],
            parallel_groups=[["step_vision", "step_ulpu"]],
        )

    def _compose_custom(
        self,
        workflow_id: str,
        payload: Dict[str, Any],
        custom_steps: Optional[List[Dict[str, Any]]] = None,
    ) -> WorkflowComposition:
        """Custom strategy composition built from provided step definitions or payload."""
        step_dicts = custom_steps or payload.get("custom_steps") or []
        if not step_dicts:
            raise WorkflowCompositionError(workflow_id, "Custom strategy requires 'custom_steps' list.")

        steps: List[WorkflowStepSpec] = []
        for sdict in step_dicts:
            spec = WorkflowStepSpec(**sdict) if isinstance(sdict, dict) else sdict
            steps.append(spec)

        return WorkflowComposition(
            workflow_id=workflow_id,
            strategy_type=WorkflowStrategyType.CUSTOM,
            steps=steps,
            completion_requirements=[
                CompletionCondition.REQUIRED_STEPS_COMPLETED,
            ],
        )

    def validate_workflow_composition(self, composition: WorkflowComposition) -> None:
        """Validate workflow steps, checking for missing dependencies and cyclic references."""
        step_ids = {s.step_id for s in composition.steps}
        for step in composition.steps:
            for dep in step.dependencies:
                if dep not in step_ids:
                    raise WorkflowCompositionError(
                        composition.workflow_id,
                        f"Step '{step.step_id}' depends on missing step '{dep}'",
                    )

        # Check for cyclic dependencies using DFS
        visited = set()
        rec_stack = set()

        adj = {s.step_id: s.dependencies for s in composition.steps}

        def is_cyclic(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for dep in adj.get(node, []):
                if dep not in visited:
                    if is_cyclic(dep):
                        return True
                elif dep in rec_stack:
                    return True
            rec_stack.remove(node)
            return False

        for step_id in step_ids:
            if step_id not in visited:
                if is_cyclic(step_id):
                    raise WorkflowCompositionError(
                        composition.workflow_id,
                        f"Cyclic dependency detected involving step '{step_id}'",
                    )
