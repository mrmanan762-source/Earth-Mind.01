import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest
from modules.orchestrator.enums import WorkflowState, WorkflowStrategyType
from modules.orchestrator.errors import (
    InvalidOrchestrationRequestError,
    OrchestrationScopeViolationError,
)
from modules.orchestrator.schemas import (
    OrchestrationPolicyConfig,
    OrchestrationRequest,
    OrchestrationTrace,
    ScopeContext,
    TraceRecord,
)

logger = get_logger("orchestrator.request_manager")


class RequestManager:
    """B5.1 Request Manager.

    Responsibilities:
    - Receive standardized request from System Skeleton or Application Entry Points.
    - Validate orchestration-level request fields and parameters.
    - Ensure strict scope boundary isolation (farmer, farm, field, crop_cycle, session).
    - Generate unique workflow_id and execution_id if absent.
    - Initialize execution trace and attach policy/session metadata safely.
    """

    def process_incoming_request(
        self, request: Union[ApplicationRequest, OrchestrationRequest, Dict[str, Any]]
    ) -> OrchestrationRequest:
        """Process and validate an incoming request into a standardized OrchestrationRequest."""
        if isinstance(request, OrchestrationRequest):
            orch_req = request
        elif isinstance(request, ApplicationRequest):
            orch_req = self._from_application_request(request)
        elif isinstance(request, dict):
            orch_req = self._from_dict(request)
        else:
            raise InvalidOrchestrationRequestError(f"Unsupported request type: {type(request)}")

        self.validate_request(orch_req)
        return orch_req

    def _from_application_request(self, app_req: ApplicationRequest) -> OrchestrationRequest:
        payload = app_req.payload if isinstance(app_req.payload, dict) else {"data": app_req.payload}
        meta = app_req.metadata or {}

        # Extract strategy from metadata or payload
        strat_str = meta.get("strategy") or payload.get("strategy") or "STANDARD_DECISION"
        try:
            strategy = WorkflowStrategyType(strat_str.upper())
        except ValueError:
            strategy = WorkflowStrategyType.STANDARD_DECISION

        # Extract scope context
        scope_data = meta.get("scope") or payload.get("scope") or {}
        scope = ScopeContext(
            farmer_id=scope_data.get("farmer_id") or meta.get("farmer_id"),
            farm_id=scope_data.get("farm_id") or meta.get("farm_id"),
            field_id=scope_data.get("field_id") or meta.get("field_id"),
            crop_cycle_id=scope_data.get("crop_cycle_id") or meta.get("crop_cycle_id"),
            session_id=scope_data.get("session_id") or meta.get("session_id"),
        )

        policy_dict = meta.get("policy") or payload.get("policy") or {}
        policy = OrchestrationPolicyConfig(**policy_dict) if policy_dict else OrchestrationPolicyConfig()

        req_id = app_req.request_id or f"req_{uuid.uuid4().hex[:12]}"
        wf_id = meta.get("workflow_id") or f"wf_{uuid.uuid4().hex[:12]}"
        exec_id = meta.get("execution_id") or f"exec_{uuid.uuid4().hex[:12]}"

        return OrchestrationRequest(
            request_id=req_id,
            workflow_id=wf_id,
            execution_id=exec_id,
            strategy=strategy,
            payload=payload,
            scope=scope,
            policy=policy,
            metadata=meta,
        )

    def _from_dict(self, data: Dict[str, Any]) -> OrchestrationRequest:
        req_id = data.get("request_id") or f"req_{uuid.uuid4().hex[:12]}"
        wf_id = data.get("workflow_id") or f"wf_{uuid.uuid4().hex[:12]}"
        exec_id = data.get("execution_id") or f"exec_{uuid.uuid4().hex[:12]}"

        strat_str = data.get("strategy", "STANDARD_DECISION")
        try:
            strategy = WorkflowStrategyType(strat_str.upper())
        except ValueError:
            strategy = WorkflowStrategyType.STANDARD_DECISION

        scope_dict = data.get("scope", {})
        scope = ScopeContext(**scope_dict) if isinstance(scope_dict, dict) else ScopeContext()

        policy_dict = data.get("policy", {})
        policy = OrchestrationPolicyConfig(**policy_dict) if isinstance(policy_dict, dict) else OrchestrationPolicyConfig()

        payload = data.get("payload", {})
        meta = data.get("metadata", {})

        return OrchestrationRequest(
            request_id=req_id,
            workflow_id=wf_id,
            execution_id=exec_id,
            strategy=strategy,
            payload=payload,
            scope=scope,
            policy=policy,
            metadata=meta,
        )

    def validate_request(self, request: OrchestrationRequest) -> None:
        """Validate request completeness, parameters, and scope boundary consistency."""
        if not request.request_id or not str(request.request_id).strip():
            raise InvalidOrchestrationRequestError("request_id cannot be empty.")

        if not request.workflow_id:
            request.workflow_id = f"wf_{uuid.uuid4().hex[:12]}"

        if not request.execution_id:
            request.execution_id = f"exec_{uuid.uuid4().hex[:12]}"

        # Validate scope boundary parameters to prevent cross-tenant leakage
        self.verify_scope_isolation(request)

        logger.info(
            f"Validated orchestration request {request.request_id} for strategy {request.strategy.value}",
            extra={"request_id": request.request_id, "workflow_id": request.workflow_id},
        )

    def verify_scope_isolation(self, request: OrchestrationRequest) -> None:
        """Verify scope parameters in metadata and scope context are consistent."""
        scope = request.scope
        meta = request.metadata or {}

        scope_fields = ["farmer_id", "farm_id", "field_id", "crop_cycle_id", "session_id"]
        for field in scope_fields:
            scope_val = getattr(scope, field)
            meta_val = meta.get(field)
            if scope_val and meta_val and str(scope_val) != str(meta_val):
                raise OrchestrationScopeViolationError(
                    f"Scope mismatch for '{field}': scope context value '{scope_val}' != metadata value '{meta_val}'"
                )

    def create_initial_trace(self, request: OrchestrationRequest) -> OrchestrationTrace:
        """Initialize trace object for auditing workflow execution."""
        if not request.workflow_id:
            request.workflow_id = f"wf_{uuid.uuid4().hex[:12]}"
        if not request.execution_id:
            request.execution_id = f"exec_{uuid.uuid4().hex[:12]}"

        initial_record = TraceRecord(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            request_id=request.request_id,
            workflow_id=request.workflow_id,
            execution_id=request.execution_id,
            workflow_state=WorkflowState.REQUESTED,
            start_time=datetime.now(timezone.utc),
            details={"strategy": request.strategy.value},
        )
        trace = OrchestrationTrace(
            request_id=request.request_id,
            workflow_id=request.workflow_id,
            execution_id=request.execution_id,
            records=[initial_record],
            state_history=[
                {
                    "state": WorkflowState.REQUESTED.value,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason": "Request accepted",
                }
            ],
            metadata={"strategy": request.strategy.value},
        )
        return trace
