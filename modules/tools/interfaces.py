"""Protocol interfaces for the EarthMind Phase 3 Backend Tool Infrastructure.

These interfaces define the replaceable boundaries between the Tool Registry,
Tool Dispatcher and individual tool implementations. Individual tools implement
`ITool`; the registry implements `IToolRegistry`; the dispatcher implements
`IToolDispatcher`.
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from core.schemas.tools import (
    ToolCallRequest,
    ToolCallResult,
    ToolDefinition,
    ToolDescriptor,
)


@runtime_checkable
class ITool(Protocol):
    """Contract implemented by every backend tool.

    Implementations must be self-contained, must never execute arbitrary
    model-generated code, and must never return secrets.
    """

    def get_definition(self) -> ToolDefinition:
        """Return the static tool descriptor (id, schemas, permissions, config)."""
        ...

    def validate_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalise raw arguments, raising on invalid input.

        Returns a cleaned argument mapping suitable for execution.
        """
        ...

    def is_available(self) -> bool:
        """Return whether the tool can currently execute (e.g. credentials present)."""
        ...

    def execute(self, arguments: Dict[str, Any], request: ToolCallRequest) -> Any:
        """Execute the tool and return a raw (pre-normalisation) result payload."""
        ...


@runtime_checkable
class IToolRegistry(Protocol):
    """Registry of available tools and their schemas/availability."""

    def register(self, tool: ITool, *, replace: bool = False) -> ToolDefinition:
        ...

    def unregister(self, tool_id: str) -> bool:
        ...

    def get(self, tool_id: str) -> ITool:
        ...

    def get_definition(self, tool_id: str) -> ToolDefinition:
        ...

    def has(self, tool_id: str) -> bool:
        ...

    def list_tools(self, *, only_available: bool = False) -> List[ToolDescriptor]:
        ...

    def set_availability(self, tool_id: str, available: bool, reason: Optional[str] = None) -> None:
        ...


@runtime_checkable
class IToolDispatcher(Protocol):
    """Validates and routes tool requests to the correct tool implementation."""

    def dispatch(self, request: ToolCallRequest) -> ToolCallResult:
        ...
