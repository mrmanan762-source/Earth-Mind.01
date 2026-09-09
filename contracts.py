from dataclasses import dataclass, field
from typing import Any

@dataclass
class ErrorContract:
    error_code: str
    message: str
    module: str
    operation: str
    retryable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
