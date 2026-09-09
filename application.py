from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

@dataclass
class ApplicationRequest:
    request_id: str
    source: str
    actor: str | None
    operation: str
    payload: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime | None = None

@dataclass
class ApplicationResponse:
    request_id: str
    status: str
    response: Any = None
    attachments: list[Any] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
