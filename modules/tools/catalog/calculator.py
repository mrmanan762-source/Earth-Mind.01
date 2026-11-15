"""Calculator tool for EarthMind Phase 3.

Provides deterministic arithmetic. Expressions are parsed with Python's `ast`
module and evaluated over a strict whitelist of node types and functions.
Unrestricted `eval` is never used, and arbitrary code execution is impossible
by construction (no attribute access, no names other than approved constants,
no calls other than approved math functions).

Supported operations:
- Addition, subtraction, multiplication, division, floor division, modulo, power.
- Percentage helpers (percentage_of, percent_change).
- Unit conversions for deterministic, well-defined units.

Explicitly out of scope: pesticide / fertilizer dosage recommendations.
"""

import ast
import math
import operator
from typing import Any, Dict, List, Optional

from core.errors.exceptions import (
    InvalidToolRequestError,
    ToolExecutionError,
    ToolValidationError,
    UnsafeToolExpressionError,
)
from core.schemas.tools import (
    ToolDefinition,
    ToolExecutionConfig,
    ToolPermission,
)

MAX_EXPRESSION_LENGTH = 512
MAX_POWER_EXPONENT = 64
MAX_ABS_RESULT = 1e18

_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_ALLOWED_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

_ALLOWED_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "floor": math.floor,
    "ceil": math.ceil,
    "fabs": math.fabs,
    "degrees": math.degrees,
    "radians": math.radians,
}

# Deterministic unit conversions: category -> unit -> factor to the base unit.
_UNIT_CONVERSIONS: Dict[str, Dict[str, float]] = {
    "length": {  # base: metre
        "m": 1.0, "meter": 1.0, "metre": 1.0, "meters": 1.0, "metres": 1.0,
        "km": 1000.0, "kilometer": 1000.0, "kilometre": 1000.0, "kilometers": 1000.0,
        "cm": 0.01, "centimeter": 0.01, "millimeter": 0.001, "mm": 0.001,
        "inch": 0.0254, "in": 0.0254, "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
        "mile": 1609.344, "miles": 1609.344, "acre_foot_depth": 0.3048,
    },
    "area": {  # base: square metre
        "m2": 1.0, "sqm": 1.0, "square_meter": 1.0,
        "hectare": 10000.0, "ha": 10000.0,
        "acre": 4046.8564224, "acres": 4046.8564224,
        "km2": 1_000_000.0, "sqkm": 1_000_000.0,
        "bigha": 2529.285264,  # conventional Indian bigha approximation
    },
    "mass": {  # base: kilogram
        "kg": 1.0, "kilogram": 1.0, "kilograms": 1.0,
        "g": 0.001, "gram": 0.001, "grams": 0.001,
        "mg": 1e-6, "milligram": 1e-6,
        "tonne": 1000.0, "ton": 1000.0, "metric_ton": 1000.0,
        "quintal": 100.0,
        "lb": 0.45359237, "pound": 0.45359237, "pounds": 0.45359237,
    },
    "volume": {  # base: litre
        "l": 1.0, "liter": 1.0, "litre": 1.0, "liters": 1.0, "litres": 1.0,
        "ml": 0.001, "milliliter": 0.001, "millilitre": 0.001,
        "m3": 1000.0, "cubic_meter": 1000.0,
        "gallon": 3.785411784, "gallons": 3.785411784,
        "gallon_us": 3.785411784, "gallon_uk": 4.54609,
    },
    "temperature": {"c": 1.0, "celsius": 1.0, "k": 1.0, "kelvin": 1.0, "f": 1.0, "fahrenheit": 1.0},
    "time": {  # base: second
        "s": 1.0, "second": 1.0, "seconds": 1.0,
        "min": 60.0, "minute": 60.0, "minutes": 60.0,
        "h": 3600.0, "hr": 3600.0, "hour": 3600.0, "hours": 3600.0,
        "day": 86400.0, "days": 86400.0,
    },
}


class CalculatorTool:
    """Deterministic, sandboxed calculator tool."""

    tool_id = "calculator"

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_id=self.tool_id,
            name="Calculator",
            description=(
                "Perform deterministic mathematical calculations: arithmetic, "
                "percentage computations, and deterministic unit conversions. "
                "Does not provide pesticide or fertilizer dosage recommendations."
            ),
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["evaluate", "percentage_of", "percent_change", "convert_units"],
                        "default": "evaluate",
                    },
                    "expression": {"type": "string", "description": "Arithmetic expression for 'evaluate'"},
                    "value": {"type": "number", "description": "Base value for percentage operations"},
                    "percent": {"type": "number", "description": "Percentage for 'percentage_of'"},
                    "from_value": {"type": "number", "description": "Original value for 'percent_change'"},
                    "to_value": {"type": "number", "description": "New value for 'percent_change'"},
                    "quantity": {"type": "number", "description": "Quantity for 'convert_units'"},
                    "from_unit": {"type": "string", "description": "Source unit for 'convert_units'"},
                    "to_unit": {"type": "string", "description": "Target unit for 'convert_units'"},
                },
                "required": ["operation"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "operation": {"type": "string"},
                    "result": {"type": "number"},
                    "expression": {"type": "string"},
                    "unit": {"type": "string"},
                    "details": {"type": "object"},
                },
                "required": ["operation", "result"],
            },
            required_permissions=[ToolPermission.COMPUTE],
            execution=ToolExecutionConfig(
                timeout_seconds=2.0,
                max_retries=0,
                idempotent=True,
                max_concurrency=16,
                max_request_bytes=4096,
                max_result_bytes=16384,
            ),
            error_contract=[
                "INVALID_TOOL_REQUEST",
                "TOOL_VALIDATION_ERROR",
                "UNSAFE_TOOL_EXPRESSION",
                "TOOL_EXECUTION_ERROR",
            ],
            tags=["math", "deterministic", "offline"],
        )

    def is_available(self) -> bool:
        return True

    def validate_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        operation = str(arguments.get("operation", "evaluate")).strip().lower()
        if operation not in ("evaluate", "percentage_of", "percent_change", "convert_units"):
            raise ToolValidationError(
                f"Unsupported operation '{operation}'.", tool_id=self.tool_id
            )

        cleaned: Dict[str, Any] = {"operation": operation}

        if operation == "evaluate":
            expression = arguments.get("expression")
            if not isinstance(expression, str) or not expression.strip():
                raise InvalidToolRequestError(
                    "'expression' is required for the evaluate operation.",
                    tool_id=self.tool_id,
                )
            if len(expression) > MAX_EXPRESSION_LENGTH:
                raise ToolValidationError(
                    f"Expression exceeds {MAX_EXPRESSION_LENGTH} characters.", tool_id=self.tool_id
                )
            cleaned["expression"] = expression

        elif operation == "percentage_of":
            cleaned["value"] = self._require_number(arguments, "value")
            cleaned["percent"] = self._require_number(arguments, "percent")

        elif operation == "percent_change":
            cleaned["from_value"] = self._require_number(arguments, "from_value")
            cleaned["to_value"] = self._require_number(arguments, "to_value")

        elif operation == "convert_units":
            cleaned["quantity"] = self._require_number(arguments, "quantity")
            cleaned["from_unit"] = self._require_unit(arguments, "from_unit")
            cleaned["to_unit"] = self._require_unit(arguments, "to_unit")

        return cleaned

    def execute(self, arguments: Dict[str, Any], request) -> Dict[str, Any]:
        operation = arguments["operation"]
        try:
            if operation == "evaluate":
                value = self._evaluate_expression(arguments["expression"])
                return {
                    "operation": operation,
                    "expression": arguments["expression"],
                    "result": value,
                    "details": {"status": "CALCULATED"},
                }
            if operation == "percentage_of":
                value = arguments["value"] * (arguments["percent"] / 100.0)
                return {
                    "operation": operation,
                    "result": self._finite(value),
                    "details": {
                        "value": arguments["value"],
                        "percent": arguments["percent"],
                        "status": "CALCULATED",
                    },
                }
            if operation == "percent_change":
                base = arguments["from_value"]
                if base == 0:
                    raise ToolExecutionError(
                        self.tool_id,
                        "Cannot compute percentage change from a base value of zero.",
                    )
                change = ((arguments["to_value"] - base) / base) * 100.0
                return {
                    "operation": operation,
                    "result": self._finite(change),
                    "details": {
                        "from_value": base,
                        "to_value": arguments["to_value"],
                        "direction": "increase" if change >= 0 else "decrease",
                        "status": "CALCULATED",
                    },
                }
            if operation == "convert_units":
                converted = self._convert_units(
                    arguments["quantity"], arguments["from_unit"], arguments["to_unit"]
                )
                return {
                    "operation": operation,
                    "result": converted,
                    "unit": arguments["to_unit"],
                    "details": {
                        "quantity": arguments["quantity"],
                        "from_unit": arguments["from_unit"],
                        "to_unit": arguments["to_unit"],
                        "status": "CONVERTED",
                    },
                }
        except (UnsafeToolExpressionError, InvalidToolRequestError, ToolValidationError):
            raise
        except ZeroDivisionError as exc:
            raise ToolExecutionError(self.tool_id, "Division by zero is undefined.") from exc
        except ValueError as exc:
            raise ToolExecutionError(self.tool_id, str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise ToolExecutionError(self.tool_id, str(exc)) from exc

        raise ToolExecutionError(self.tool_id, f"Unhandled operation '{operation}'.")

    # -- expression evaluation --------------------------------------------

    def _evaluate_expression(self, expression: str) -> float:
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ToolValidationError(
                f"Invalid arithmetic expression: {exc.msg}", tool_id=self.tool_id
            ) from exc

        result = self._eval_node(tree.body)
        return self._finite(result)

    def _eval_node(self, node: ast.AST) -> float:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise UnsafeToolExpressionError(
                    f"Only numeric literals are permitted, got {type(node.value).__name__}.",
                    tool_id=self.tool_id,
                )
            return node.value

        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _BINARY_OPERATORS:
                raise UnsafeToolExpressionError(
                    f"Operator '{op_type.__name__}' is not permitted.", tool_id=self.tool_id
                )
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            if op_type is ast.Pow:
                if abs(right) > MAX_POWER_EXPONENT:
                    raise UnsafeToolExpressionError(
                        f"Exponent magnitude exceeds {MAX_POWER_EXPONENT}.", tool_id=self.tool_id
                    )
            return _BINARY_OPERATORS[op_type](left, right)

        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in _UNARY_OPERATORS:
                raise UnsafeToolExpressionError(
                    f"Unary operator '{op_type.__name__}' is not permitted.", tool_id=self.tool_id
                )
            return _UNARY_OPERATORS[op_type](self._eval_node(node.operand))

        if isinstance(node, ast.Name):
            if node.id in _ALLOWED_CONSTANTS:
                return _ALLOWED_CONSTANTS[node.id]
            raise UnsafeToolExpressionError(
                f"Name '{node.id}' is not permitted.", tool_id=self.tool_id
            )

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCTIONS:
                raise UnsafeToolExpressionError(
                    "Only approved math functions may be called.", tool_id=self.tool_id
                )
            if node.keywords:
                raise UnsafeToolExpressionError(
                    "Keyword arguments are not permitted.", tool_id=self.tool_id
                )
            func = _ALLOWED_FUNCTIONS[node.func.id]
            args = [self._eval_node(arg) for arg in node.args]
            try:
                return func(*args)
            except (ValueError, TypeError, ZeroDivisionError) as exc:
                raise ToolExecutionError(
                    self.tool_id, f"Function '{node.func.id}' failed: {exc}"
                ) from exc

        raise UnsafeToolExpressionError(
            f"Expression element '{type(node).__name__}' is not permitted.", tool_id=self.tool_id
        )

    # -- unit conversion ---------------------------------------------------

    def _convert_units(self, quantity: float, from_unit: str, to_unit: str) -> float:
        from_lower = from_unit.lower().strip()
        to_lower = to_unit.lower().strip()

        category = self._unit_category(from_lower)
        if category is None:
            raise ToolValidationError(f"Unknown unit '{from_unit}'.", tool_id=self.tool_id)
        if self._unit_category(to_lower) != category:
            raise ToolValidationError(
                f"Cannot convert between incompatible units '{from_unit}' and '{to_unit}'.",
                tool_id=self.tool_id,
            )

        if category == "temperature":
            return self._convert_temperature(quantity, from_lower, to_lower)

        factor_from = _UNIT_CONVERSIONS[category][from_lower]
        factor_to = _UNIT_CONVERSIONS[category][to_lower]
        return self._finite(quantity * factor_from / factor_to)

    @staticmethod
    def _unit_category(unit: str) -> Optional[str]:
        for category, units in _UNIT_CONVERSIONS.items():
            if unit in units:
                return category
        return None

    def _convert_temperature(self, quantity: float, from_unit: str, to_unit: str) -> float:
        aliases = {"celsius": "c", "kelvin": "k", "fahrenheit": "f"}
        src = aliases.get(from_unit, from_unit)
        dst = aliases.get(to_unit, to_unit)

        # Convert to Celsius first.
        if src == "c":
            celsius = quantity
        elif src == "k":
            celsius = quantity - 273.15
        elif src == "f":
            celsius = (quantity - 32.0) * 5.0 / 9.0
        else:
            raise ToolValidationError(f"Unknown temperature unit '{from_unit}'.", tool_id=self.tool_id)

        if dst == "c":
            return self._finite(celsius)
        if dst == "k":
            return self._finite(celsius + 273.15)
        if dst == "f":
            return self._finite(celsius * 9.0 / 5.0 + 32.0)
        raise ToolValidationError(f"Unknown temperature unit '{to_unit}'.", tool_id=self.tool_id)

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _require_number(arguments: Dict[str, Any], key: str) -> float:
        if key not in arguments:
            raise InvalidToolRequestError(f"'{key}' is required.", tool_id=CalculatorTool.tool_id)
        value = arguments[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ToolValidationError(
                f"'{key}' must be a number.", tool_id=CalculatorTool.tool_id
            )
        return float(value)

    @staticmethod
    def _require_unit(arguments: Dict[str, Any], key: str) -> str:
        value = arguments.get(key)
        if not isinstance(value, str) or not value.strip():
            raise InvalidToolRequestError(
                f"'{key}' must be a non-empty unit string.", tool_id=CalculatorTool.tool_id
            )
        return value.strip()

    @staticmethod
    def _finite(value: float) -> float:
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise ToolExecutionError(
                CalculatorTool.tool_id, "Calculation produced a non-finite result."
            )
        if abs(value) > MAX_ABS_RESULT:
            raise ToolExecutionError(
                CalculatorTool.tool_id, "Calculation result magnitude is out of range."
            )
        return value
