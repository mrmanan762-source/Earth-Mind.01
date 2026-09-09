from datetime import datetime, timezone
from typing import Any, Optional, List, Dict
from pydantic import BaseModel, Field

class ApplicationRequest(BaseModel):
    request_id: str
    source: str
    actor: Optional[str] = None
    operation: str
    payload: Any = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ApplicationResponse(BaseModel):
    request_id: str
    status: str
    response: Any = None
    attachments: List[Any] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
