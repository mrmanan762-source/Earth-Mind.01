"""Satellite Request State and Lifecycle Manager for EarthMind Satellite Module (Stage D3).

Coordinates discovery, acquisition, and ingestion request lifecycles.
Manages:
- Request identity preservation
- Request lifecycle states:
  PENDING -> DISCOVERING -> DISCOVERED -> ACQUIRING -> ACQUIRED -> INGESTING -> COMPLETED
  (with FAILED and CANCELLED terminal states)
- Valid state transition verification
- Concurrency tracking and throttles
- Idempotency & duplicate request detection
"""

from enum import Enum
import threading
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.logging.logger import get_logger
from modules.satellite.errors import (
    SatelliteInvalidArgumentError,
    SatelliteProcessingError,
)

logger = get_logger("modules.satellite.request_manager")


class SatelliteRequestState(str, Enum):
    """Lifecycle states of a satellite data processing request."""
    PENDING = "PENDING"
    DISCOVERING = "DISCOVERING"
    DISCOVERED = "DISCOVERED"
    ACQUIRING = "ACQUIRING"
    ACQUIRED = "ACQUIRED"
    INGESTING = "INGESTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Valid state transitions graph
_VALID_TRANSITIONS = {
    SatelliteRequestState.PENDING: {
        SatelliteRequestState.DISCOVERING,
        SatelliteRequestState.ACQUIRING,
        SatelliteRequestState.COMPLETED,
        SatelliteRequestState.CANCELLED,
        SatelliteRequestState.FAILED,
    },
    SatelliteRequestState.DISCOVERING: {
        SatelliteRequestState.DISCOVERED,
        SatelliteRequestState.CANCELLED,
        SatelliteRequestState.FAILED,
    },
    SatelliteRequestState.DISCOVERED: {
        SatelliteRequestState.ACQUIRING,
        SatelliteRequestState.COMPLETED,  # If discovery-only request
        SatelliteRequestState.CANCELLED,
        SatelliteRequestState.FAILED,
    },
    SatelliteRequestState.ACQUIRING: {
        SatelliteRequestState.ACQUIRED,
        SatelliteRequestState.CANCELLED,
        SatelliteRequestState.FAILED,
    },
    SatelliteRequestState.ACQUIRED: {
        SatelliteRequestState.INGESTING,
        SatelliteRequestState.COMPLETED,
        SatelliteRequestState.CANCELLED,
        SatelliteRequestState.FAILED,
    },
    SatelliteRequestState.INGESTING: {
        SatelliteRequestState.COMPLETED,
        SatelliteRequestState.CANCELLED,
        SatelliteRequestState.FAILED,
    },
    SatelliteRequestState.COMPLETED: set(),
    SatelliteRequestState.FAILED: set(),
    SatelliteRequestState.CANCELLED: set(),
}


class RequestTrackRecord(BaseModel):
    """Tracking record for active and historical satellite requests."""
    request_id: str
    tenant_id: str = "default"
    state: SatelliteRequestState = SatelliteRequestState.PENDING
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    selected_dataset_id: Optional[str] = None
    provider_id: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SatelliteRequestManager:
    """Manages request state machine, concurrency boundaries, and idempotency."""

    def __init__(self, max_concurrent_requests: int = 10):
        self._max_concurrency = max_concurrent_requests
        self._lock = threading.RLock()
        self._requests: Dict[str, RequestTrackRecord] = {}

    def create_request(
        self,
        request_id: str,
        tenant_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RequestTrackRecord:
        """Register a new request in PENDING state."""
        if not request_id or not request_id.strip():
            raise SatelliteInvalidArgumentError(
                details="Cannot track satellite request with empty request_id.",
                operation="create_request",
            )

        with self._lock:
            rid = request_id.strip()
            if rid in self._requests:
                # Return existing record for idempotency
                return self._requests[rid]

            # Check concurrency limit
            active_count = sum(
                1 for r in self._requests.values()
                if r.state not in (SatelliteRequestState.COMPLETED, SatelliteRequestState.FAILED, SatelliteRequestState.CANCELLED)
            )
            if active_count >= self._max_concurrency:
                raise SatelliteProcessingError(
                    details=f"Maximum concurrent satellite requests limit ({self._max_concurrency}) reached.",
                    operation="create_request",
                )

            rec = RequestTrackRecord(
                request_id=rid,
                tenant_id=tenant_id,
                state=SatelliteRequestState.PENDING,
                metadata=metadata or {},
            )
            self._requests[rid] = rec
            logger.debug(f"Created request record '{rid}' in state PENDING.")
            return rec

    def transition_state(
        self,
        request_id: str,
        new_state: SatelliteRequestState,
        error_message: Optional[str] = None,
        selected_dataset_id: Optional[str] = None,
        provider_id: Optional[str] = None,
    ) -> RequestTrackRecord:
        """Transition request to a new state validating against state machine graph."""
        with self._lock:
            rec = self._requests.get(request_id)
            if not rec:
                raise SatelliteInvalidArgumentError(
                    details=f"Request '{request_id}' not found in request tracker.",
                    operation="transition_state",
                )

            curr = rec.state
            allowed = _VALID_TRANSITIONS.get(curr, set())
            if new_state not in allowed:
                raise SatelliteProcessingError(
                    details=f"Invalid state transition for request '{request_id}': cannot move from {curr.value} to {new_state.value}.",
                    operation="transition_state",
                )

            rec.state = new_state
            rec.updated_at = time.time()
            if error_message:
                rec.error_message = error_message
            if selected_dataset_id:
                rec.selected_dataset_id = selected_dataset_id
            if provider_id:
                rec.provider_id = provider_id

            logger.info(f"Transitioned satellite request '{request_id}': {curr.value} -> {new_state.value}.")
            return rec

    def get_request(self, request_id: str) -> Optional[RequestTrackRecord]:
        """Retrieve tracking record for a request."""
        with self._lock:
            return self._requests.get(request_id)

    def cancel_request(self, request_id: str) -> bool:
        """Cancel an in-flight request if not already in terminal state."""
        with self._lock:
            rec = self._requests.get(request_id)
            if not rec:
                return False
            if rec.state in (SatelliteRequestState.COMPLETED, SatelliteRequestState.FAILED, SatelliteRequestState.CANCELLED):
                return False
            rec.state = SatelliteRequestState.CANCELLED
            rec.updated_at = time.time()
            logger.info(f"Cancelled satellite request '{request_id}'.")
            return True

    def clear(self) -> None:
        """Clear requests (for testing)."""
        with self._lock:
            self._requests.clear()
