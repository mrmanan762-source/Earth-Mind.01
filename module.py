from typing import Protocol, Any
from core.schemas.application import ApplicationRequest, ApplicationResponse

class ModuleInterface(Protocol):
    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        ...
