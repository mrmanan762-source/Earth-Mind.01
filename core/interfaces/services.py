from typing import Protocol, List, Dict, Any, Optional, runtime_checkable
from core.schemas.application import ApplicationRequest, ApplicationResponse

@runtime_checkable
class AIInterface(Protocol):
    def process_language(self, prompt: str) -> str:
        ...

@runtime_checkable
class MemoryInterface(Protocol):
    def store_memory(self, key: str, value: Any) -> bool:
        ...
    def retrieve_memory(self, key: str) -> Optional[Any]:
        ...

@runtime_checkable
class InspectorInterface(Protocol):
    def validate_action(self, action_name: str, payload: Any) -> Dict[str, Any]:
        ...
