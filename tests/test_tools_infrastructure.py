"""Unit, security and integration tests for the EarthMind Phase 3 tool infrastructure.

Coverage:
- Tool registration & schema validation.
- Dispatcher routing.
- Calculator operations (safe parsing, division by zero, unsafe rejection).
- Result normalization.
- Error handling.
- Execution manager: timeout, retry policy, concurrency, cancellation, rate limit.
- Model-independent request parsing (future Sarvam integration boundary).

All provider interactions here are MOCKED / deterministic. No live external
network calls are performed by this module.
"""

import time
from typing import Any, Dict

import pytest

from core.errors.exceptions import (
    InvalidToolSchemaError,
    ToolAlreadyRegisteredError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolPermissionError,
    ToolTimeoutError,
    UnsafeToolExpressionError,
)
from core.schemas.tools import (
    ToolCallRequest,
    ToolCallResult,
    ToolCallStatus,
    ToolDefinition,
    ToolExecutionConfig,
    ToolPermission,
)
from modules.tools.catalog.calculator import CalculatorTool
from modules.tools.dispatcher import ToolDispatcher
from modules.tools.execution_manager import ToolExecutionManager
from modules.tools.normalizer import ToolResultNormalizer
from modules.tools.registry import ToolRegistry
from modules.tools.request_parser import parse_model_tool_call


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class EchoTool:
    """Minimal valid tool that echoes its input."""

    tool_id = "echo"

    def __init__(self, available: bool = True):
        self._available = available

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_id="echo",
            name="Echo",
            description="Echo the provided value back.",
            input_schema={"type": "object", "properties": {"value": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"value": {"type": "string"}}},
            required_permissions=[ToolPermission.READ_ONLY],
            execution=ToolExecutionConfig(timeout_seconds=2.0, max_retries=0, max_concurrency=2),
            error_contract=["TOOL_EXECUTION_ERROR"],
        )

    def validate_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if "value" not in arguments:
            raise ToolExecutionError(self.tool_id, "value is required")
        return {"value": arguments["value"]}

    def is_available(self) -> bool:
        return self._available

    def execute(self, arguments: Dict[str, Any], request: ToolCallRequest) -> Any:
        return {"value": arguments["value"]}


class BrokenDefinitionTool:
    def get_definition(self):
        # Missing required fields -> invalid schema.
        return {"tool_id": "broken"}

    def validate_arguments(self, arguments):
        return arguments

    def is_available(self):
        return True

    def execute(self, arguments, request):
        return {}


class SlowTool:
    tool_id = "slow"

    def __init__(self, delay: float):
        self._delay = delay

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_id="slow",
            name="Slow",
            description="Sleeps for a configurable duration.",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            required_permissions=[],
            execution=ToolExecutionConfig(timeout_seconds=0.2, max_retries=0, idempotent=True),
            error_contract=["TOOL_TIMEOUT"],
        )

    def validate_arguments(self, arguments):
        return dict(arguments)

    def is_available(self):
        return True

    def execute(self, arguments, request):
        time.sleep(self._delay)
        return {"slept": self._delay}


class FlakyTool:
    """Fails with a retryable error a fixed number of times before succeeding."""

    tool_id = "flaky"

    def __init__(self, failures: int, retryable: bool = True):
        self._remaining = failures
        self._retryable = retryable
        self.attempts = 0

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_id="flaky",
            name="Flaky",
            description="Fails transiently then succeeds.",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            required_permissions=[],
            execution=ToolExecutionConfig(
                timeout_seconds=2.0, max_retries=3, retry_backoff_seconds=0.0, idempotent=True
            ),
            error_contract=["TOOL_EXECUTION_ERROR"],
        )

    def validate_arguments(self, arguments):
        return dict(arguments)

    def is_available(self):
        return True

    def execute(self, arguments, request):
        self.attempts += 1
        if self._remaining > 0:
            self._remaining -= 1
            exc = ToolExecutionError(self.tool_id, "transient failure", retryable=self._retryable)
            raise exc
        return {"attempts": self.attempts}


class NonIdempotentFlakyTool(FlakyTool):
    tool_id = "non_idempotent_flaky"

    def get_definition(self) -> ToolDefinition:
        definition = super().get_definition()
        definition.tool_id = self.tool_id
        definition.execution.idempotent = False
        return definition


class LargeResultTool:
    tool_id = "large"

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_id="large",
            name="Large",
            description="Returns a result larger than the configured limit.",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            required_permissions=[],
            execution=ToolExecutionConfig(timeout_seconds=2.0, max_result_bytes=64),
            error_contract=["TOOL_PAYLOAD_LIMIT_EXCEEDED"],
        )

    def validate_arguments(self, arguments):
        return dict(arguments)

    def is_available(self):
        return True

    def execute(self, arguments, request):
        return {"data": "x" * 1000}


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

def test_registry_register_and_list():
    registry = ToolRegistry()
    definition = registry.register(EchoTool())
    assert definition.tool_id == "echo"
    assert registry.has("echo")
    assert registry.count() == 1
    descriptors = registry.list_tools()
    assert [d.tool_id for d in descriptors] == ["echo"]
    assert descriptors[0].required_permissions == [ToolPermission.READ_ONLY]


def test_registry_duplicate_rejected():
    registry = ToolRegistry()
    registry.register(EchoTool())
    with pytest.raises(ToolAlreadyRegisteredError):
        registry.register(EchoTool())
    # Replace is allowed explicitly.
    registry.register(EchoTool(), replace=True)
    assert registry.count() == 1


def test_registry_invalid_schema_rejected():
    registry = ToolRegistry()
    with pytest.raises(InvalidToolSchemaError):
        registry.register(BrokenDefinitionTool())


def test_registry_unknown_tool_raises():
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        registry.get("missing")


def test_registry_availability_probe():
    registry = ToolRegistry()
    registry.register(EchoTool(available=False))
    descriptor = registry.list_tools()[0]
    assert descriptor.available is False
    assert registry.list_tools(only_available=True) == []


def test_tool_definition_schema_validation_rules():
    with pytest.raises(ValueError):
        ToolDefinition(
            tool_id="Bad Id!",
            name="x",
            description="y",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            error_contract=["E"],
        ).validate_schema()


# ---------------------------------------------------------------------------
# Dispatcher routing
# ---------------------------------------------------------------------------

def test_dispatcher_routes_to_tool():
    registry = ToolRegistry()
    registry.register(EchoTool())
    dispatcher = ToolDispatcher(registry)
    result = dispatcher.dispatch(
        ToolCallRequest(tool_id="echo", arguments={"value": "hello"}, permissions=[ToolPermission.READ_ONLY])
    )
    assert result.status == ToolCallStatus.SUCCESS
    assert result.payload == {"value": "hello"}
    assert result.ok is True


def test_dispatcher_unknown_tool_not_found():
    dispatcher = ToolDispatcher(ToolRegistry())
    result = dispatcher.dispatch(ToolCallRequest(tool_id="ghost", arguments={}))
    assert result.status == ToolCallStatus.NOT_FOUND
    assert result.error["error_code"] == "TOOL_NOT_FOUND"


def test_dispatcher_permission_denied():
    registry = ToolRegistry()
    registry.register(EchoTool())
    dispatcher = ToolDispatcher(registry)
    result = dispatcher.dispatch(ToolCallRequest(tool_id="echo", arguments={"value": "x"}))
    assert result.status == ToolCallStatus.PERMISSION_DENIED


def test_dispatcher_admin_permission_grants_all():
    registry = ToolRegistry()
    registry.register(EchoTool())
    dispatcher = ToolDispatcher(registry)
    result = dispatcher.dispatch(
        ToolCallRequest(tool_id="echo", arguments={"value": "x"}, permissions=[ToolPermission.ADMIN])
    )
    assert result.status == ToolCallStatus.SUCCESS


def test_dispatcher_unavailable_tool():
    registry = ToolRegistry()
    registry.register(EchoTool(available=False))
    dispatcher = ToolDispatcher(registry)
    result = dispatcher.dispatch(
        ToolCallRequest(tool_id="echo", arguments={"value": "x"}, permissions=[ToolPermission.READ_ONLY])
    )
    assert result.status == ToolCallStatus.UNAVAILABLE


def test_dispatcher_dry_run_does_not_execute():
    registry = ToolRegistry()
    registry.register(EchoTool())
    dispatcher = ToolDispatcher(registry)
    result = dispatcher.dispatch(
        ToolCallRequest(
            tool_id="echo",
            arguments={"value": "x"},
            permissions=[ToolPermission.READ_ONLY],
            dry_run=True,
        )
    )
    assert result.status == ToolCallStatus.SUCCESS
    assert result.payload["dry_run"] is True


def test_dispatcher_request_size_limit():
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    dispatcher = ToolDispatcher(registry)
    huge_expression = "1+" * 5000 + "1"
    result = dispatcher.dispatch(
        ToolCallRequest(
            tool_id="calculator",
            arguments={"operation": "evaluate", "expression": huge_expression},
            permissions=[ToolPermission.COMPUTE],
        )
    )
    assert result.status == ToolCallStatus.PAYLOAD_LIMIT_EXCEEDED


def test_dispatcher_result_size_limit():
    registry = ToolRegistry()
    registry.register(LargeResultTool())
    dispatcher = ToolDispatcher(registry)
    result = dispatcher.dispatch(ToolCallRequest(tool_id="large", arguments={}))
    assert result.status == ToolCallStatus.PAYLOAD_LIMIT_EXCEEDED


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

@pytest.fixture()
def calculator_dispatcher():
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    return ToolDispatcher(registry)


def _calc(dispatcher, **arguments):
    return dispatcher.dispatch(
        ToolCallRequest(
            tool_id="calculator",
            arguments=arguments,
            permissions=[ToolPermission.COMPUTE],
        )
    )


def test_calculator_addition_subtraction(calculator_dispatcher):
    assert _calc(calculator_dispatcher, operation="evaluate", expression="7+3-2").payload["result"] == 8


def test_calculator_multiplication_division(calculator_dispatcher):
    assert _calc(calculator_dispatcher, operation="evaluate", expression="6*7").payload["result"] == 42
    assert _calc(calculator_dispatcher, operation="evaluate", expression="9/3").payload["result"] == 3


def test_calculator_precedence_and_parentheses(calculator_dispatcher):
    assert _calc(calculator_dispatcher, operation="evaluate", expression="2+3*4").payload["result"] == 14
    assert _calc(calculator_dispatcher, operation="evaluate", expression="(2+3)*4").payload["result"] == 20


def test_calculator_percentage_of(calculator_dispatcher):
    result = _calc(calculator_dispatcher, operation="percentage_of", value=250, percent=12)
    assert result.payload["result"] == 30.0


def test_calculator_percent_change(calculator_dispatcher):
    result = _calc(calculator_dispatcher, operation="percent_change", from_value=100, to_value=150)
    assert result.payload["result"] == 50.0
    assert result.payload["details"]["direction"] == "increase"


def test_calculator_percent_change_zero_base(calculator_dispatcher):
    result = _calc(calculator_dispatcher, operation="percent_change", from_value=0, to_value=50)
    assert result.status == ToolCallStatus.EXECUTION_ERROR


def test_calculator_unit_conversion_area(calculator_dispatcher):
    result = _calc(calculator_dispatcher, operation="convert_units", quantity=1, from_unit="hectare", to_unit="acre")
    assert round(result.payload["result"], 4) == 2.4711


def test_calculator_unit_conversion_temperature(calculator_dispatcher):
    result = _calc(calculator_dispatcher, operation="convert_units", quantity=100, from_unit="celsius", to_unit="fahrenheit")
    assert result.payload["result"] == 212.0


def test_calculator_incompatible_units(calculator_dispatcher):
    result = _calc(calculator_dispatcher, operation="convert_units", quantity=1, from_unit="kg", to_unit="km")
    assert result.status == ToolCallStatus.VALIDATION_ERROR


def test_calculator_division_by_zero(calculator_dispatcher):
    result = _calc(calculator_dispatcher, operation="evaluate", expression="1/0")
    assert result.status == ToolCallStatus.EXECUTION_ERROR
    assert "zero" in result.error["message"].lower()


def test_calculator_invalid_expression(calculator_dispatcher):
    result = _calc(calculator_dispatcher, operation="evaluate", expression="2 +* 3")
    assert result.status == ToolCallStatus.VALIDATION_ERROR


def test_calculator_math_functions(calculator_dispatcher):
    assert _calc(calculator_dispatcher, operation="evaluate", expression="sqrt(16)").payload["result"] == 4
    assert round(_calc(calculator_dispatcher, operation="evaluate", expression="cos(0)").payload["result"], 6) == 1.0


def test_calculator_missing_expression(calculator_dispatcher):
    result = _calc(calculator_dispatcher, operation="evaluate")
    assert result.status == ToolCallStatus.INVALID_REQUEST


# ---------------------------------------------------------------------------
# Security: unsafe expressions / arbitrary execution prevention
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo hacked')",
        "open('/etc/passwd').read()",
        "().__class__.__bases__[0].__subclasses__()",
        "eval('1+1')",
        "exec('x=1')",
        "globals()",
        "os.getcwd()",
        "[x for x in range(3)]",
        "lambda: 1",
        "1 if True else 2",
        "'a' * 3",
    ],
)
def test_calculator_rejects_unsafe_expressions(calculator_dispatcher, expression):
    result = _calc(calculator_dispatcher, operation="evaluate", expression=expression)
    assert result.status == ToolCallStatus.VALIDATION_ERROR
    assert result.error["error_code"] == "UNSAFE_TOOL_EXPRESSION"


def test_calculator_rejects_huge_exponent(calculator_dispatcher):
    result = _calc(calculator_dispatcher, operation="evaluate", expression="9**999999")
    assert result.status == ToolCallStatus.VALIDATION_ERROR


def test_calculator_rejects_unknown_name(calculator_dispatcher):
    result = _calc(calculator_dispatcher, operation="evaluate", expression="secret_variable + 1")
    assert result.status == ToolCallStatus.VALIDATION_ERROR


# ---------------------------------------------------------------------------
# Result normalizer
# ---------------------------------------------------------------------------

def test_normalizer_success_contract():
    normalizer = ToolResultNormalizer()
    result = normalizer.success("echo", "req-1", {"value": 1})
    assert isinstance(result, ToolCallResult)
    assert result.tool_id == "echo"
    assert result.request_id == "req-1"
    assert result.status == ToolCallStatus.SUCCESS
    assert result.payload == {"value": 1}
    assert result.execution is not None


def test_normalizer_from_exception_preserves_contract():
    normalizer = ToolResultNormalizer()
    result = normalizer.from_exception("echo", "req-2", ToolNotFoundError("echo"))
    assert result.status == ToolCallStatus.NOT_FOUND
    assert result.error["error_code"] == "TOOL_NOT_FOUND"
    assert result.request_id == "req-2"


def test_normalizer_public_dict_is_json_safe():
    normalizer = ToolResultNormalizer()
    result = normalizer.success("echo", "req-3", {"value": 1})
    import json

    json.dumps(result.to_public_dict())  # must not raise


# ---------------------------------------------------------------------------
# Execution manager: timeout, retries, concurrency, cancellation, rate limits
# ---------------------------------------------------------------------------

def test_execution_manager_timeout():
    registry = ToolRegistry()
    registry.register(SlowTool(delay=1.0))
    dispatcher = ToolDispatcher(registry)
    result = dispatcher.dispatch(ToolCallRequest(tool_id="slow", arguments={}))
    assert result.status == ToolCallStatus.TIMEOUT
    assert result.error["error_code"] == "TOOL_TIMEOUT"


def test_execution_manager_retries_retryable_failure():
    registry = ToolRegistry()
    tool = FlakyTool(failures=2)
    registry.register(tool)
    dispatcher = ToolDispatcher(registry)
    result = dispatcher.dispatch(ToolCallRequest(tool_id="flaky", arguments={}))
    assert result.status == ToolCallStatus.SUCCESS
    assert result.payload == {"attempts": 3}
    assert result.execution.attempts == 3


def test_execution_manager_does_not_retry_non_idempotent():
    registry = ToolRegistry()
    tool = NonIdempotentFlakyTool(failures=1)
    registry.register(tool)
    dispatcher = ToolDispatcher(registry)
    result = dispatcher.dispatch(ToolCallRequest(tool_id="non_idempotent_flaky", arguments={}))
    assert result.status == ToolCallStatus.EXECUTION_ERROR
    assert tool.attempts == 1


def test_execution_manager_concurrency_limit():
    manager = ToolExecutionManager()
    registry = ToolRegistry()
    definition = ToolDefinition(
        tool_id="concurrency_probe",
        name="Concurrency Probe",
        description="Holds a semaphore slot.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        error_contract=["TOOL_EXECUTION_ERROR"],
        execution=ToolExecutionConfig(timeout_seconds=2.0, max_concurrency=1),
    )

    # Manually acquire the single slot to force the limit.
    sem = manager._get_semaphore("concurrency_probe", 1)
    sem.acquire()
    try:
        request = ToolCallRequest(tool_id="concurrency_probe", arguments={})
        with pytest.raises(Exception) as exc_info:
            manager.execute(definition, request, lambda: {"ok": True})
        assert "concurrency" in str(exc_info.value).lower()
    finally:
        sem.release()


def test_execution_manager_cancellation():
    manager = ToolExecutionManager()
    definition = ToolDefinition(
        tool_id="cancellable",
        name="Cancellable",
        description="Cancellation probe.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        error_contract=["TOOL_CANCELLED"],
        execution=ToolExecutionConfig(timeout_seconds=2.0),
    )
    request = ToolCallRequest(tool_id="cancellable", arguments={}, request_id="cancel-me")
    assert manager.request_cancel("cancel-me") is True
    from core.errors.exceptions import ToolCancelledError

    with pytest.raises(ToolCancelledError):
        manager.execute(definition, request, lambda: {"ok": True})


def test_execution_manager_rate_limit():
    manager = ToolExecutionManager()
    definition = ToolDefinition(
        tool_id="rate_limited",
        name="Rate Limited",
        description="Rate limit probe.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        error_contract=["TOOL_RATE_LIMITED"],
        execution=ToolExecutionConfig(timeout_seconds=2.0, rate_limit_per_minute=1),
    )
    manager.execute(definition, ToolCallRequest(tool_id="rate_limited", arguments={}), lambda: {"ok": 1})
    from core.errors.exceptions import ToolRateLimitError

    with pytest.raises(ToolRateLimitError):
        manager.execute(definition, ToolCallRequest(tool_id="rate_limited", arguments={}), lambda: {"ok": 1})


def test_execution_manager_status_tracking():
    manager = ToolExecutionManager()
    definition = ToolDefinition(
        tool_id="tracked",
        name="Tracked",
        description="Status probe.",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        error_contract=["TOOL_EXECUTION_ERROR"],
        execution=ToolExecutionConfig(timeout_seconds=2.0),
    )
    request = ToolCallRequest(tool_id="tracked", arguments={}, request_id="tracked-1")
    manager.execute(definition, request, lambda: {"ok": True})
    record = manager.get_record("tracked-1")
    assert record is not None
    assert record.status == ToolCallStatus.SUCCESS
    assert manager.status_snapshot().get("SUCCESS", 0) >= 1


# ---------------------------------------------------------------------------
# Model-independent request parsing (future Sarvam integration boundary)
# ---------------------------------------------------------------------------

def test_parse_model_tool_call_from_json_string():
    request = parse_model_tool_call(
        '{"tool_id": "calculator", "arguments": {"operation": "evaluate", "expression": "1+1"}}',
        granted_permissions=[ToolPermission.COMPUTE],
    )
    assert request.tool_id == "calculator"
    assert request.arguments["expression"] == "1+1"
    assert ToolPermission.COMPUTE in request.permissions


def test_parse_model_tool_call_from_dict_with_string_args():
    request = parse_model_tool_call(
        {"tool": "weather", "args": '{"latitude": 19.0, "longitude": 73.0}'},
        granted_permissions=[ToolPermission.WEATHER_DATA],
    )
    assert request.tool_id == "weather"
    assert request.arguments["latitude"] == 19.0


def test_parse_model_tool_call_rejects_self_asserted_permissions():
    from core.errors.exceptions import InvalidToolRequestError

    with pytest.raises(InvalidToolRequestError):
        parse_model_tool_call({"tool_id": "calculator", "permissions": ["ADMIN"], "arguments": {}})


def test_parse_model_tool_call_rejects_invalid_json():
    from core.errors.exceptions import InvalidToolRequestError

    with pytest.raises(InvalidToolRequestError):
        parse_model_tool_call("not json at all")


def test_parse_model_tool_call_ignores_model_permission_claims():
    """Permissions come only from the trusted caller, never the model output."""
    request = parse_model_tool_call(
        {"tool_id": "calculator", "arguments": {}},
        granted_permissions=[],
    )
    assert request.permissions == []
