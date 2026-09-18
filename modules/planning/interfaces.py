from typing import Protocol, List, Optional, Dict, Any
from modules.planning.schemas import (
    PlanningInput,
    PlanningResult,
    CandidateAction,
    PlanReference,
    FeasibilityAnalysisResult,
    Goal,
    Constraint,
)


class IPlanningStrategy(Protocol):
    """Replaceable strategy contract for plan generation and structuring."""
    strategy_name: str

    def generate_candidate_actions(
        self,
        goal: Goal,
        reasoning_result: Optional[Any],
        constraints: List[Constraint],
        policy: Any,
    ) -> List[CandidateAction]:
        """Generate candidate actions from goal, reasoning findings, and constraints."""
        ...

    def build_plans(
        self,
        goal: Goal,
        actions: List[CandidateAction],
        constraints: List[Constraint],
        policy: Any,
    ) -> List[PlanReference]:
        """Build structured candidate plan options from candidate actions."""
        ...


class IDecisionStrategy(Protocol):
    """Replaceable strategy contract for option comparison and decision formation."""
    strategy_name: str

    def evaluate_feasibility(
        self,
        candidate_plans: List[PlanReference],
        constraints: List[Constraint],
        available_resources: List[Any],
    ) -> List[FeasibilityAnalysisResult]:
        """Evaluate explicit feasibility state for candidate plans."""
        ...

    def select_best_option(
        self,
        candidate_plans: List[PlanReference],
        feasibility_results: List[FeasibilityAnalysisResult],
        decision_policy: Any,
    ) -> Optional[PlanReference]:
        """Compare options based on policy criteria and select recommended decision."""
        ...


class IPlanningCapability(Protocol):
    """Generic interface for domain-specific planning capabilities."""
    capability_name: str

    def is_available(self) -> bool:
        """Check if capability is available for planning execution."""
        ...

    def execute_planning_step(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute capability-specific planning operation."""
        ...
