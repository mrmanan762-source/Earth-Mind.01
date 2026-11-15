"""Tool Registry for the EarthMind Phase 3 Backend Tool Infrastructure.

The registry is the single source of truth for available tools. It stores tool
implementations, their validated definitions (id, name, description, input and
output schemas, permissions, execution config and error contract), and their
availability status. New tools can be registered without modifying the core
infrastructure.
"""

import threading
from typing import Dict, List, Optional

from core.errors.exceptions import (
    InvalidToolSchemaError,
    ToolAlreadyRegisteredError,
    ToolNotFoundError,
)
from core.logging.logger import get_logger
from core.schemas.tools import ToolDefinition, ToolDescriptor
from modules.tools.interfaces import ITool

logger = get_logger("modules.tools.registry")


class ToolRegistry:
    """Thread-safe registry of backend tools."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tools: Dict[str, ITool] = {}
        self._definitions: Dict[str, ToolDefinition] = {}

    def register(self, tool: ITool, *, replace: bool = False) -> ToolDefinition:
        """Register a tool implementation after validating its definition.

        Raises InvalidToolSchemaError when the definition is malformed and
        ToolAlreadyRegisteredError when the tool id already exists.
        """
        definition = self._extract_definition(tool)

        with self._lock:
            if definition.tool_id in self._tools and not replace:
                raise ToolAlreadyRegisteredError(definition.tool_id)

            # Refresh runtime availability from the tool implementation.
            available, reason = self._probe_availability(tool, definition)
            definition.available = available
            definition.unavailable_reason = reason

            self._tools[definition.tool_id] = tool
            self._definitions[definition.tool_id] = definition

        logger.info(
            "Registered tool '%s' v%s (available=%s)",
            definition.tool_id,
            definition.version,
            definition.available,
        )
        return definition

    def unregister(self, tool_id: str) -> bool:
        with self._lock:
            existed = tool_id in self._tools
            self._tools.pop(tool_id, None)
            self._definitions.pop(tool_id, None)
        if existed:
            logger.info("Unregistered tool '%s'", tool_id)
        return existed

    def has(self, tool_id: str) -> bool:
        with self._lock:
            return tool_id in self._tools

    def get(self, tool_id: str) -> ITool:
        with self._lock:
            tool = self._tools.get(tool_id)
        if tool is None:
            raise ToolNotFoundError(tool_id)
        return tool

    def get_definition(self, tool_id: str) -> ToolDefinition:
        with self._lock:
            definition = self._definitions.get(tool_id)
        if definition is None:
            raise ToolNotFoundError(tool_id)
        return definition

    def list_tools(self, *, only_available: bool = False) -> List[ToolDescriptor]:
        with self._lock:
            definitions = list(self._definitions.values())
        descriptors = [ToolDescriptor.from_definition(d) for d in definitions]
        if only_available:
            descriptors = [d for d in descriptors if d.available]
        return sorted(descriptors, key=lambda d: d.tool_id)

    def set_availability(self, tool_id: str, available: bool, reason: Optional[str] = None) -> None:
        with self._lock:
            definition = self._definitions.get(tool_id)
            if definition is None:
                raise ToolNotFoundError(tool_id)
            definition.available = available
            definition.unavailable_reason = None if available else reason
            logger.info("Tool '%s' availability set to %s (%s)", tool_id, available, reason or "")

    def refresh_availability(self) -> None:
        """Re-probe availability of all registered tools."""
        with self._lock:
            items = list(self._tools.items())
        for tool_id, tool in items:
            definition = self._definitions.get(tool_id)
            if definition is None:
                continue
            available, reason = self._probe_availability(tool, definition)
            definition.available = available
            definition.unavailable_reason = reason

    def count(self) -> int:
        with self._lock:
            return len(self._tools)

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _extract_definition(tool: ITool) -> ToolDefinition:
        if not hasattr(tool, "get_definition") or not callable(tool.get_definition):
            raise InvalidToolSchemaError("Tool implementation does not implement get_definition().")

        definition = tool.get_definition()
        if not isinstance(definition, ToolDefinition):
            raise InvalidToolSchemaError(
                f"get_definition() must return a ToolDefinition, got {type(definition).__name__}."
            )

        try:
            definition.validate_schema()
        except ValueError as exc:
            raise InvalidToolSchemaError(str(exc), tool_id=definition.tool_id) from exc
        return definition

    @staticmethod
    def _probe_availability(tool: ITool, definition: ToolDefinition):
        try:
            if hasattr(tool, "is_available") and callable(tool.is_available):
                available = bool(tool.is_available())
            else:
                available = True
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Availability probe failed for '%s': %s", definition.tool_id, exc)
            return False, f"Availability probe failed: {exc}"

        if available:
            return True, None
        return False, definition.unavailable_reason or "Tool reported itself unavailable."
