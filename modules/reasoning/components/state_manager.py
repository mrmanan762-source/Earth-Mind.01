import datetime
from typing import Any, Dict, List, Optional
from core.errors.exceptions import InvalidLifecycleTransitionError
from modules.reasoning.enums import ReasoningState


class ReasoningStateManager:
    """Manages B3 reasoning lifecycle states and validates transition rules."""

    # Valid transition graph
    _ALLOWED_TRANSITIONS: Dict[ReasoningState, List[ReasoningState]] = {
        ReasoningState.REQUESTED: [
            ReasoningState.VALIDATING,
            ReasoningState.FAILED,
            ReasoningState.TIMEOUT,
            ReasoningState.CANCELLED,
            ReasoningState.REJECTED,
        ],
        ReasoningState.VALIDATING: [
            ReasoningState.PREPARING_CONTEXT,
            ReasoningState.FAILED,
            ReasoningState.INSUFFICIENT_EVIDENCE,
            ReasoningState.REJECTED,
            ReasoningState.TIMEOUT,
            ReasoningState.CANCELLED,
        ],
        ReasoningState.PREPARING_CONTEXT: [
            ReasoningState.ANALYZING_EVIDENCE,
            ReasoningState.FAILED,
            ReasoningState.INSUFFICIENT_EVIDENCE,
            ReasoningState.TIMEOUT,
            ReasoningState.CANCELLED,
        ],
        ReasoningState.ANALYZING_EVIDENCE: [
            ReasoningState.COMPARING_EVIDENCE,
            ReasoningState.FAILED,
            ReasoningState.INSUFFICIENT_EVIDENCE,
            ReasoningState.TIMEOUT,
            ReasoningState.CANCELLED,
        ],
        ReasoningState.COMPARING_EVIDENCE: [
            ReasoningState.ANALYZING_RELATIONSHIPS,
            ReasoningState.FAILED,
            ReasoningState.TIMEOUT,
            ReasoningState.CANCELLED,
        ],
        ReasoningState.ANALYZING_RELATIONSHIPS: [
            ReasoningState.ANALYZING_CONFLICTS,
            ReasoningState.FAILED,
            ReasoningState.TIMEOUT,
            ReasoningState.CANCELLED,
        ],
        ReasoningState.ANALYZING_CONFLICTS: [
            ReasoningState.ANALYZING_UNCERTAINTY,
            ReasoningState.FAILED,
            ReasoningState.TIMEOUT,
            ReasoningState.CANCELLED,
        ],
        ReasoningState.ANALYZING_UNCERTAINTY: [
            ReasoningState.ITERATING,
            ReasoningState.BUILDING_RESULT,
            ReasoningState.FAILED,
            ReasoningState.INSUFFICIENT_EVIDENCE,
            ReasoningState.TIMEOUT,
            ReasoningState.CANCELLED,
        ],
        ReasoningState.ITERATING: [
            ReasoningState.ANALYZING_EVIDENCE,
            ReasoningState.BUILDING_RESULT,
            ReasoningState.FAILED,
            ReasoningState.INSUFFICIENT_EVIDENCE,
            ReasoningState.TIMEOUT,
            ReasoningState.CANCELLED,
        ],
        ReasoningState.BUILDING_RESULT: [
            ReasoningState.VALIDATING_RESULT,
            ReasoningState.FAILED,
            ReasoningState.TIMEOUT,
            ReasoningState.CANCELLED,
        ],
        ReasoningState.VALIDATING_RESULT: [
            ReasoningState.COMPLETED,
            ReasoningState.FAILED,
            ReasoningState.REJECTED,
            ReasoningState.TIMEOUT,
            ReasoningState.CANCELLED,
        ],
        ReasoningState.COMPLETED: [],
        ReasoningState.FAILED: [],
        ReasoningState.INSUFFICIENT_EVIDENCE: [],
        ReasoningState.TIMEOUT: [],
        ReasoningState.CANCELLED: [],
        ReasoningState.REJECTED: [],
    }

    def __init__(self, request_id: str, initial_state: ReasoningState = ReasoningState.REQUESTED):
        self.request_id = request_id
        self._current_state: ReasoningState = initial_state
        self._history: List[Dict[str, Any]] = [
            {
                "state": initial_state.value,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "reason": "initialization",
            }
        ]

    @property
    def current_state(self) -> ReasoningState:
        return self._current_state

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    def transition_to(self, target_state: ReasoningState, reason: str = "") -> None:
        """Transition to target state if transition is valid according to transition graph."""
        if target_state == self._current_state:
            return

        allowed = self._ALLOWED_TRANSITIONS.get(self._current_state, [])
        if target_state not in allowed:
            raise InvalidLifecycleTransitionError(
                identifier=f"reasoning:{self.request_id}",
                version="1.0.0",
                current_state=self._current_state.value,
                target_state=target_state.value,
                reason=reason or f"Transition from {self._current_state.value} to {target_state.value} is not allowed."
            )

        self._current_state = target_state
        self._history.append(
            {
                "state": target_state.value,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "reason": reason,
            }
        )
