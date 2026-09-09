from typing import Protocol, Any, Dict, Optional, List
from core.schemas.application import ApplicationRequest, ApplicationResponse

class ModuleInterface(Protocol):
    """Base interface for all EarthMind modules."""
    module_name: str

    def initialize(self) -> None:
        """Initialize module resources."""
        ...

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        """Handle incoming application requests."""
        ...

    def shutdown(self) -> None:
        """Cleanup module resources."""
        ...

class DatabaseInterface(Protocol):
    """Interface for database implementations."""
    def connect(self) -> None:
        ...

    def disconnect(self) -> None:
        ...

    def execute(self, query: str, params: tuple = ()) -> Any:
        ...

    def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        ...

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        ...
