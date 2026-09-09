from typing import Protocol, List, Dict, Any, Optional
from core.schemas.application import ApplicationRequest, ApplicationResponse

class AIInterface(Protocol):
    def process_language(self, prompt: str) -> str:
        ...

class MemoryInterface(Protocol):
    def store_memory(self, key: str, value: Any) -> bool:
        ...
    def retrieve_memory(self, key: str) -> Optional[Any]:
        ...

class InspectorInterface(Protocol):
    def validate_action(self, action_name: str, payload: Any) -> Dict[str, Any]:
        ...
