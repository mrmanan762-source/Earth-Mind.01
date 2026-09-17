from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class InferenceExecutionState(str, Enum):
    REQUESTED = "REQUESTED"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    UNAVAILABLE = "UNAVAILABLE"


class ModelLifecycleState(str, Enum):
    REGISTERED = "REGISTERED"
    VALIDATING = "VALIDATING"
    STAGED = "STAGED"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class ValidationResult(BaseModel):
    is_valid: bool = Field(..., description="Whether validation checks passed")
    checks: List[Dict[str, Any]] = Field(default_factory=list, description="List of performed validation check details")
    errors: List[str] = Field(default_factory=list, description="Validation failure messages if any")
    timestamp: str = Field(..., description="ISO string timestamp of validation execution")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary validation metadata")


class ModelVersionRecord(BaseModel):
    identifier: str = Field(..., description="Unique model identifier within EarthMind (e.g. 'sarvam-105b')")
    version: str = Field(..., description="Model version or release tag (e.g. '1.0.0')")
    family: str = Field("sarvam", description="Model family name")
    provider: str = Field("huggingface", description="Model provider or platform")
    repo_id: str = Field(..., description="Hugging Face repository ID")
    revision: str = Field(..., description="Exact pinned commit SHA or revision")
    model_type: str = Field("causal_lm", description="Architecture/type metadata")
    license: str = Field("Apache-2.0", description="Model license terms")
    provenance: str = Field("upstream: sarvamai/sarvam-105b", description="Model provenance information")
    state: ModelLifecycleState = Field(ModelLifecycleState.REGISTERED, description="Current lifecycle state")
    capabilities: List[str] = Field(default_factory=lambda: ["text-generation", "chat"], description="Capabilities supported")
    execution_strategy: str = Field("causal_lm_adapter", description="Execution strategy identifier")
    registration_timestamp: str = Field(..., description="Registration ISO timestamp string")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary version metadata")
    is_main_model: bool = Field(False, description="Whether marked as main system model")


class ModelGenerationRequest(BaseModel):
    request_id: str = Field(..., description="Unique identifier for the generation request")
    task: str = Field(..., description="High-level task or prompt description")
    instructions: Optional[str] = Field(None, description="Specific instructions for model behavior")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Contextual background data")
    conversation: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Prior conversation history")
    multimodal_data: Optional[Any] = Field(None, description="Multimodal payloads or references")
    tools_available: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Available tools specification")
    constraints: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Execution or output constraints")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")


class ModelGenerationResponse(BaseModel):
    request_id: str = Field(..., description="Identifier matching the generation request")
    status: str = Field(..., description="Response status (e.g., 'success', 'failed')")
    response: Any = Field(None, description="Generated response content or payload")
    reasoning_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Internal reasoning or thought process data")
    tool_information: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Tool execution or invocation details")
    confidence_level: Optional[float] = Field(None, description="Model output confidence score (0.0 to 1.0)")
    uncertainty: Optional[float] = Field(None, description="Model output uncertainty estimate")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal execution warnings")
    model_version: str = Field(..., description="Identifier or version SHA of the generating model")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata")
