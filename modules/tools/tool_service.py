"""Tool infrastructure service container for EarthMind Phase 3.

Wires the Tool Registry, Tool Dispatcher, Execution Manager, Result Normalizer
and the default tool catalogue into one reusable, injectable service. This is
the single integration point for B5, B2 and future model adapters.

The service does NOT orchestrate workflows: it executes single tool calls.
"""

from typing import Any, Dict, List, Optional

from core.logging.logger import get_logger
from core.schemas.tools import (
    ToolCallRequest,
    ToolCallResult,
    ToolDescriptor,
    ToolPermission,
)
from modules.tools.catalog.calculator import CalculatorTool
from modules.tools.catalog.satellite import SatelliteTool
from modules.tools.catalog.weather import WeatherTool
from modules.tools.catalog.web_search import WebSearchTool
from modules.tools.dispatcher import ToolDispatcher
from modules.tools.execution_manager import ToolExecutionManager
from modules.tools.normalizer import ToolResultNormalizer
from modules.tools.registry import ToolRegistry

logger = get_logger("modules.tools.service")


class ToolService:
    """Container exposing the complete tool infrastructure."""

    def __init__(
        self,
        *,
        registry: Optional[ToolRegistry] = None,
        execution_manager: Optional[ToolExecutionManager] = None,
        normalizer: Optional[ToolResultNormalizer] = None,
        web_search_engine: Optional[Any] = None,
        weather_provider: Optional[Any] = None,
        satellite_module: Optional[Any] = None,
        register_defaults: bool = True,
    ) -> None:
        self.registry = registry or ToolRegistry()
        self.execution_manager = execution_manager or ToolExecutionManager()
        self.normalizer = normalizer or ToolResultNormalizer()
        self.dispatcher = ToolDispatcher(self.registry, self.execution_manager, self.normalizer)

        self._web_search_engine = web_search_engine
        self._weather_provider = weather_provider
        self._satellite_module = satellite_module

        if register_defaults:
            self.register_default_tools()

    # -- catalogue ---------------------------------------------------------

    def register_default_tools(self) -> None:
        """Register the initial Phase 3 tool catalogue."""
        self.register_tool(WebSearchTool(engine=self._web_search_engine))
        self.register_tool(WeatherTool(provider=self._weather_provider))
        self.register_tool(CalculatorTool())
        self.register_tool(SatelliteTool(satellite_module=self._satellite_module))

    def register_tool(self, tool: Any, *, replace: bool = False) -> None:
        self.registry.register(tool, replace=replace)

    # -- public API --------------------------------------------------------

    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        """Dispatch a validated tool request and return a normalized result."""
        return self.dispatcher.dispatch(request)

    def list_tools(self, *, only_available: bool = False) -> List[ToolDescriptor]:
        return self.registry.list_tools(only_available=only_available)

    def refresh_availability(self) -> None:
        self.registry.refresh_availability()

    def health_report(self) -> Dict[str, Any]:
        """Return a low-cardinality, secret-free tool infrastructure health report."""
        descriptors = self.registry.list_tools()
        return {
            "registered_tools": len(descriptors),
            "available_tools": sum(1 for d in descriptors if d.available),
            "tools": [
                {
                    "tool_id": d.tool_id,
                    "version": d.version,
                    "available": d.available,
                    "unavailable_reason": d.unavailable_reason,
                    "required_permissions": [p.value for p in d.required_permissions],
                }
                for d in descriptors
            ],
        }

    def shutdown(self) -> None:
        self.execution_manager.shutdown()


def build_default_tool_service(**kwargs: Any) -> ToolService:
    """Convenience factory used by the module and application bootstrap."""
    return ToolService(**kwargs)
