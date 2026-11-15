"""Data contracts for the EarthMind Phase 3 Backend Tool Infrastructure.

These models define the model-independent tool request/response contract used by
the Tool Registry, Tool Dispatcher, Tool Execution Manager and Tool Result
Normalizer. They are intentionally decoupled from any specific model's native
function-calling format (e.g. Sarvam-105B), so that future model adapters can
translate model-generated requests into these validated backend tool requests.

Contracts:
- ToolPermission: A single permission grant required to invoke a tool.
- ToolExecutionConfig: Per-tool execution policy (timeout, retries, concurrency).
- ToolDefinition: Static tool descriptor (id, name, description, schemas, ...).
- ToolCallRequest: A validated request to execute a registered tool.
- ToolCallStatus: Execution status enum used by the normalizer.
- ToolCallResult: Normalized, structured tool execution result.
- ToolDescriptor (registry view): Serialisable registry metadata for discovery.
"""

from datetime import datetime, timezone
from enum import Enum
import time
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolPermission(str, Enum):
    """Discrete permission scopes a caller may hold for tool invocation."""

    READ_ONLY = "READ_ONLY"
    EXTERNAL_NETWORK = "EXTERNAL_NETWORK"
    SATELLITE_DATA = "SATELLITE_DATA"
    WEATHER_DATA = "WEATHER_DATA"
    WEB_SEARCH = "WEB_SEARCH"
    COMPUTE = "COMPUTE"
    ADMIN = "ADMIN"


class ToolExecutionConfig(BaseModel):
    """Execution policy applied by the Tool Execution Manager for a single tool."""

    timeout_seconds: float = Field(15.0, gt=0.0, description="Maximum wall-clock execution time in seconds")
    max_retries: int = Field(0, ge=0, description="Maximum retry attempts for transient failures")
    retry_backoff_seconds: float = Field(0.2, ge=0.0, description="Base backoff between retries in seconds")
    idempotent: bool = Field(True, description="Whether the tool is safe to retry (non-idempotent tools are never retried)")
    max_concurrency: int = Field(4, ge=1, description="Maximum concurrent in-flight executions for this tool")
    rate_limit_per_minute: Optional[int] = Field(None, ge=1, description="Optional per-tool request rate limit")
    cancellable: bool = Field(True, description="Whether the tool supports cooperative cancellation")
    max_request_bytes: int = Field(65536, gt=0, description="Maximum serialized request payload size in bytes")
    max_result_bytes: int = Field(262144, gt=0, description="Maximum serialized result payload size in bytes")


class ToolDefinition(BaseModel):
    """Static, validated descriptor for a registered tool."""

    tool_id: str = Field(..., min_length=1, description="Unique tool identifier (e.g. 'calculator')")
    name: str = Field(..., min_length=1, description="Human readable tool name")
    description: str = Field(..., min_length=1, description="What the tool does and when to use it")
    version: str = Field("1.0.0", description="Tool implementation version")
    input_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON-schema style input contract")
    output_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON-schema style output contract")
    required_permissions: List[ToolPermission] = Field(
        default_factory=list, description="Permissions required to invoke this tool"
    )
    execution: ToolExecutionConfig = Field(default_factory=ToolExecutionConfig)
    error_contract: List[str] = Field(
        default_factory=list, description="Documented error codes this tool may return"
    )
    tags: List[str] = Field(default_factory=list, description="Categorisation tags for discovery")
    available: bool = Field(True, description="Whether the tool is currently available for execution")
    unavailable_reason: Optional[str] = Field(None, description="Reason when available is False")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional static tool metadata")

    @field_validator("tool_id")
    @classmethod
    def _validate_tool_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("tool_id cannot be empty or whitespace")
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
        if not set(cleaned.lower()).issubset(allowed):
            raise ValueError("tool_id may only contain lowercase letters, digits, '_' and '-'")
        return cleaned

    def validate_schema(self) -> bool:
        """Validate the tool definition is structurally complete."""
        if not self.name.strip():
            raise ValueError("Tool name cannot be empty")
        if not self.description.strip():
            raise ValueError("Tool description cannot be empty")
        if not isinstance(self.input_schema, dict) or not self.input_schema:
            raise ValueError("Tool input_schema must be a non-empty object")
        if not isinstance(self.output_schema, dict) or not self.output_schema:
            raise ValueError("Tool output_schema must be a non-empty object")
        if not self.error_contract:
            raise ValueError("Tool error_contract must declare at least one error code")
        return True


class ToolCallRequest(BaseModel):
    """A validated, model-independent request to execute a registered tool."""

    tool_id: str = Field(..., min_length=1, description="Target tool identifier")
    request_id: str = Field(default_factory=lambda: f"tool_req_{uuid.uuid4().hex[:12]}", description="Correlation id")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Validated tool input arguments")
    caller: Optional[str] = Field(None, description="Caller identity (model adapter, module, user)")
    permissions: List[ToolPermission] = Field(
        default_factory=list, description="Permissions granted to this request by the caller"
    )
    source: str = Field("internal", description="Request origin (e.g. 'model_adapter', 'orchestrator', 'api')")
    timeout_override: Optional[float] = Field(None, gt=0.0, description="Optional per-call timeout override (bounded)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Opaque correlation metadata")
    dry_run: bool = Field(False, description="Validate and route without executing the tool")
    requested_at: datetime = Field(default_factory=_utc_now, description="UTC timestamp the request was created")

    @field_validator("arguments")
    @classmethod
    def _validate_arguments_type(cls, value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("arguments must be a JSON object")
        return value


class ToolCallStatus(str, Enum):
    """Normalized execution status for a tool call."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    UNAVAILABLE = "UNAVAILABLE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    RATE_LIMITED = "RATE_LIMITED"
    CONCURRENCY_LIMIT = "CONCURRENCY_LIMIT"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    PAYLOAD_LIMIT_EXCEEDED = "PAYLOAD_LIMIT_EXCEEDED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ToolSourceReference(BaseModel):
    """Provenance / source reference attached to a tool result."""

    source_type: str = Field(..., description="Source category (e.g. 'web', 'weather', 'satellite', 'internal')")
    title: Optional[str] = Field(None, description="Source title")
    url: Optional[str] = Field(None, description="Source URL where applicable")
    provider: Optional[str] = Field(None, description="Provider identifier")
    publication_date: Optional[str] = Field(None, description="Publication / observation date when available")
    observed_at: Optional[str] = Field(None, description="Observation timestamp when available")
    is_forecast: bool = Field(False, description="True if the reference describes forecast rather than observed data")
    attribution: Optional[str] = Field(None, description="Attribution text required by a provider")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional source metadata")


class ToolExecutionMetadata(BaseModel):
    """Execution telemetry captured by the Execution Manager."""

    started_at: datetime = Field(default_factory=_utc_now)
    finished_at: Optional[datetime] = None
    duration_ms: float = Field(0.0, ge=0.0)
    attempts: int = Field(1, ge=1)
    retries: int = Field(0, ge=0)
    timed_out: bool = Field(False)
    cancelled: bool = Field(False)
    rate_limited: bool = Field(False)
    provider: Optional[str] = Field(None)
    cached: bool = Field(False)
    extra: Dict[str, Any] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    """Normalized, structured result of a tool call.

    Preserves tool id, request id, execution status, result payload, source
    references, execution metadata and error information in one consistent shape.
    """

    tool_id: str = Field(..., description="Executed tool identifier")
    request_id: str = Field(..., description="Correlation id from the originating request")
    status: ToolCallStatus = Field(..., description="Normalized execution status")
    payload: Optional[Any] = Field(None, description="Structured tool result payload on success")
    sources: List[ToolSourceReference] = Field(default_factory=list, description="Source provenance references")
    execution: ToolExecutionMetadata = Field(default_factory=ToolExecutionMetadata)
    error: Optional[Dict[str, Any]] = Field(None, description="Error contract when status is not SUCCESS")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings")
    produced_at: datetime = Field(default_factory=_utc_now)

    @property
    def ok(self) -> bool:
        return self.status in (ToolCallStatus.SUCCESS, ToolCallStatus.PARTIAL)

    def to_public_dict(self) -> Dict[str, Any]:
        """Return a frontend-safe dictionary (no secrets, JSON-serialisable)."""
        return self.model_dump(mode="json")


class ToolDescriptor(BaseModel):
    """Registry view of a tool for discovery and model-facing schema exposure."""

    tool_id: str
    name: str
    description: str
    version: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    required_permissions: List[ToolPermission]
    available: bool
    unavailable_reason: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    execution: ToolExecutionConfig = Field(default_factory=ToolExecutionConfig)

    @classmethod
    def from_definition(cls, definition: ToolDefinition) -> "ToolDescriptor":
        return cls(
            tool_id=definition.tool_id,
            name=definition.name,
            description=definition.description,
            version=definition.version,
            input_schema=definition.input_schema,
            output_schema=definition.output_schema,
            required_permissions=list(definition.required_permissions),
            available=definition.available,
            unavailable_reason=definition.unavailable_reason,
            tags=list(definition.tags),
            execution=definition.execution,
        )


class ToolCallRecord(BaseModel):
    """Mutable execution status record tracked by the Execution Manager."""

    request_id: str
    tool_id: str
    status: ToolCallStatus = ToolCallStatus.INVALID_REQUEST
    started_at: float = Field(default_factory=time.time)
    finished_at: Optional[float] = None
    attempts: int = 0
    cancel_requested: bool = False
    error_code: Optional[str] = None

    def mark_finished(self, status: ToolCallStatus, error_code: Optional[str] = None) -> None:
        self.status = status
        self.finished_at = time.time()
        self.error_code = error_code
