from typing import Any, Dict
from pydantic import BaseModel, Field

class ErrorContract(BaseModel):
    error_code: str
    message: str
    module: str
    operation: str
    retryable: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
