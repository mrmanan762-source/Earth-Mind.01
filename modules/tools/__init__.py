"""EarthMind Phase 3 Backend Tool Infrastructure.

A secure, modular, reusable backend tool system. Components:
- ToolRegistry: registration, schemas, availability.
- ToolDispatcher: validation, authorization, routing.
- ToolExecutionManager: timeouts, retries, concurrency, rate limits, cancellation.
- ToolResultNormalizer: consistent ToolCallResult contract.
- ToolService / ToolModule: integration container and module entry point.
- catalog/: Calculator, Web Search, Weather, Satellite Intelligence tools.
"""

from core.schemas.tools import (
    ToolCallRequest,
    ToolCallResult,
    ToolCallStatus,
    ToolDefinition,
    ToolDescriptor,
    ToolExecutionConfig,
    ToolExecutionMetadata,
    ToolPermission,
    ToolSourceReference,
)
from modules.tools.dispatcher import ToolDispatcher
from modules.tools.execution_manager import ToolExecutionManager
from modules.tools.interfaces import ITool, IToolDispatcher, IToolRegistry
from modules.tools.normalizer import ToolResultNormalizer
from modules.tools.registry import ToolRegistry
from modules.tools.request_parser import parse_model_tool_call
from modules.tools.tool_module import ToolModule
from modules.tools.tool_service import ToolService, build_default_tool_service

__all__ = [
    "ToolRegistry",
    "ToolDispatcher",
    "ToolExecutionManager",
    "ToolResultNormalizer",
    "ToolService",
    "ToolModule",
    "build_default_tool_service",
    "parse_model_tool_call",
    "ITool",
    "IToolRegistry",
    "IToolDispatcher",
    "ToolCallRequest",
    "ToolCallResult",
    "ToolCallStatus",
    "ToolDefinition",
    "ToolDescriptor",
    "ToolExecutionConfig",
    "ToolExecutionMetadata",
    "ToolPermission",
    "ToolSourceReference",
]
