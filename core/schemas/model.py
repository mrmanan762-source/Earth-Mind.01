from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

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
