"""Lifecycle and Status Management for EarthMind Satellite Intelligence Module (Stage D2).

Manages state machine transitions, startup, running, stopping, and shutdown
coordination for the Satellite Module.
"""

from enum import Enum
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from core.logging.logger import get_logger
from modules.satellite.errors import (
    SatelliteInternalError,
    SatelliteInvalidArgumentError,
)

logger = get_logger("modules.satellite.lifecycle")


class SatelliteLifecycleState(str, Enum):
    """Controlled lifecycle states for Satellite Module."""
    INITIALIZED = "INITIALIZED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


# Valid lifecycle state transitions matrix
VALID_LIFECYCLE_TRANSITIONS: Dict[SatelliteLifecycleState, List[SatelliteLifecycleState]] = {
    SatelliteLifecycleState.INITIALIZED: [
        SatelliteLifecycleState.STARTING,
        SatelliteLifecycleState.FAILED,
    ],
    SatelliteLifecycleState.STARTING: [
        SatelliteLifecycleState.RUNNING,
        SatelliteLifecycleState.FAILED,
    ],
    SatelliteLifecycleState.RUNNING: [
        SatelliteLifecycleState.STOPPING,
        SatelliteLifecycleState.FAILED,
    ],
    SatelliteLifecycleState.STOPPING: [
        SatelliteLifecycleState.STOPPED,
        SatelliteLifecycleState.FAILED,
    ],
    SatelliteLifecycleState.STOPPED: [
        SatelliteLifecycleState.STARTING,  # Re-start support
    ],
    SatelliteLifecycleState.FAILED: [
        SatelliteLifecycleState.STARTING,  # Recovery support
    ],
}


class SatelliteLifecycleTracker:
    """Thread-safe lifecycle tracker managing module state transitions, history, and timestamps."""

    def __init__(self, initial_state: SatelliteLifecycleState = SatelliteLifecycleState.INITIALIZED):
        self._lock = threading.RLock()
        self._current_state = initial_state
        self._state_history: List[Dict[str, Any]] = [
            {
                "state": initial_state.value,
                "timestamp": time.time(),
                "reason": "Lifecycle tracker initialized",
            }
        ]
        self._failure_reason: Optional[str] = None

    @property
    def current_state(self) -> SatelliteLifecycleState:
        with self._lock:
            return self._current_state

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._current_state == SatelliteLifecycleState.RUNNING

    @property
    def is_healthy(self) -> bool:
        with self._lock:
            return self._current_state in (
                SatelliteLifecycleState.INITIALIZED,
                SatelliteLifecycleState.RUNNING,
            )

    @property
    def failure_reason(self) -> Optional[str]:
        with self._lock:
            return self._failure_reason

    def transition_to(
        self,
        target_state: SatelliteLifecycleState,
        reason: Optional[str] = None,
    ) -> SatelliteLifecycleState:
        """Perform a validated lifecycle state transition."""
        with self._lock:
            if self._current_state == target_state:
                logger.debug(f"Lifecycle state already {target_state.value}; no-op.")
                return self._current_state

            allowed = VALID_LIFECYCLE_TRANSITIONS.get(self._current_state, [])
            if target_state not in allowed:
                err_msg = (
                    f"Invalid lifecycle transition from '{self._current_state.value}' "
                    f"to '{target_state.value}'. Allowed transitions: {[s.value for s in allowed]}."
                )
                logger.error(err_msg)
                raise SatelliteInvalidArgumentError(
                    details=err_msg,
                    operation="transition_to",
                )

            logger.info(f"Transitioning Satellite Module lifecycle: {self._current_state.value} -> {target_state.value} (reason: {reason})")
            self._current_state = target_state
            if target_state == SatelliteLifecycleState.FAILED:
                self._failure_reason = reason
            elif target_state == SatelliteLifecycleState.RUNNING:
                self._failure_reason = None

            self._state_history.append({
                "state": target_state.value,
                "timestamp": time.time(),
                "reason": reason or "",
            })
            return self._current_state

    def get_history(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._state_history)


class SatelliteLifecycleManager:
    """Orchestrates resource initialization, dependency startup, and graceful shutdown."""

    def __init__(self, tracker: Optional[SatelliteLifecycleTracker] = None):
        self._tracker = tracker or SatelliteLifecycleTracker()
        self._startup_hooks: List[Callable[[], None]] = []
        self._shutdown_hooks: List[Callable[[], None]] = []
        self._lock = threading.RLock()

    @property
    def tracker(self) -> SatelliteLifecycleTracker:
        return self._tracker

    @property
    def state(self) -> SatelliteLifecycleState:
        return self._tracker.current_state

    def add_startup_hook(self, hook: Callable[[], None]) -> None:
        with self._lock:
            self._startup_hooks.append(hook)

    def add_shutdown_hook(self, hook: Callable[[], None]) -> None:
        with self._lock:
            self._shutdown_hooks.append(hook)

    def start(self) -> None:
        """Start the Satellite Module and invoke registered startup hooks."""
        with self._lock:
            if self._tracker.current_state == SatelliteLifecycleState.RUNNING:
                logger.warning("Satellite Module start requested, but already in RUNNING state.")
                return

            self._tracker.transition_to(SatelliteLifecycleState.STARTING, reason="Module startup triggered")

            try:
                for hook in self._startup_hooks:
                    hook()
                self._tracker.transition_to(SatelliteLifecycleState.RUNNING, reason="Startup hooks executed successfully")
                logger.info("Satellite Module is RUNNING.")
            except Exception as exc:
                err_msg = f"Satellite Module startup failed: {exc}"
                logger.error(err_msg)
                self._tracker.transition_to(SatelliteLifecycleState.FAILED, reason=err_msg)
                raise SatelliteInternalError(details=err_msg, operation="lifecycle_start") from exc

    def stop(self) -> None:
        """Stop the Satellite Module and invoke registered shutdown hooks safely."""
        with self._lock:
            current = self._tracker.current_state
            if current in (SatelliteLifecycleState.STOPPED, SatelliteLifecycleState.INITIALIZED):
                logger.info("Satellite Module already stopped or not started.")
                return

            try:
                self._tracker.transition_to(SatelliteLifecycleState.STOPPING, reason="Module shutdown triggered")
            except Exception:
                # If in FAILED state, transition directly or ignore
                pass

            errors = []
            for hook in reversed(self._shutdown_hooks):
                try:
                    hook()
                except Exception as exc:
                    logger.error(f"Error executing shutdown hook: {exc}")
                    errors.append(str(exc))

            if errors:
                self._tracker.transition_to(SatelliteLifecycleState.FAILED, reason=f"Shutdown hook errors: {', '.join(errors)}")
            else:
                self._tracker.transition_to(SatelliteLifecycleState.STOPPED, reason="Clean shutdown complete")
                logger.info("Satellite Module is STOPPED.")
