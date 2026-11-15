"""Model-independent tool-call parsing for EarthMind Phase 3.

This module translates a model-generated tool call (a loosely structured JSON
object emitted by an LLM) into a validated `ToolCallRequest`. It deliberately
makes no assumption about any specific model's native function-calling support:
future model adapters (e.g. Sarvam-105B in Phase 5) can call `parse_model_tool_call`
to convert their output into the same backend contract.

Security rules enforced here:
- Model-generated requests are separated from actual execution (this module only
  produces a request; the Dispatcher decides whether to run it).
- Arbitrary model-generated code is never executed.
- A model cannot self-grant permissions: permission grants are supplied by the
  trusted caller (model adapter / orchestrator), never read from the model output.
"""

import json
from typing import Any, Dict, Iterable, Optional, Union

from core.errors.exceptions import InvalidToolRequestError
from core.schemas.tools import ToolCallRequest, ToolPermission

# Permissions the model output is explicitly forbidden from self-asserting.
_FORBIDDEN_MODEL_FIELDS = ("permissions", "granted_permissions", "admin", "is_admin")


def parse_model_tool_call(
    model_output: Union[str, Dict[str, Any]],
    *,
    caller: str = "model_adapter",
    source: str = "model",
    granted_permissions: Optional[Iterable[ToolPermission]] = None,
    request_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ToolCallRequest:
    """Parse a model-generated tool call into a validated `ToolCallRequest`.

    Accepts either a JSON string or a dict of the shape:
        {"tool_id": "calculator", "arguments": {...}}

    Permissions are taken exclusively from `granted_permissions` (trusted caller
    input). Any permission field present in the model output is ignored and the
    call is rejected to make the attempt visible.
    """
    payload = _coerce_to_dict(model_output)

    for forbidden in _FORBIDDEN_MODEL_FIELDS:
        if forbidden in payload:
            raise InvalidToolRequestError(
                f"Model output must not self-assert permission field '{forbidden}'.",
                request_id=request_id,
            )

    tool_id = payload.get("tool_id") or payload.get("tool") or payload.get("name")
    if not tool_id or not isinstance(tool_id, str):
        raise InvalidToolRequestError("Model tool call is missing a valid 'tool_id'.")

    arguments = payload.get("arguments", payload.get("args", payload.get("parameters", {})))
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        # Some models emit arguments as a JSON string.
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise InvalidToolRequestError(
                    f"Model tool call arguments are not valid JSON: {exc}"
                ) from exc
        if not isinstance(arguments, dict):
            raise InvalidToolRequestError("Model tool call 'arguments' must be a JSON object.")

    return ToolCallRequest(
        tool_id=tool_id.strip(),
        request_id=request_id or _generate_request_id(),
        arguments=arguments,
        caller=caller,
        source=source,
        permissions=list(granted_permissions or []),
        metadata=metadata or {},
    )


def _coerce_to_dict(model_output: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(model_output, dict):
        return dict(model_output)
    if isinstance(model_output, str):
        text = model_output.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InvalidToolRequestError(f"Model tool call is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise InvalidToolRequestError("Model tool call must decode to a JSON object.")
        return parsed
    raise InvalidToolRequestError(
        f"Unsupported model tool call type: {type(model_output).__name__}"
    )


def _generate_request_id() -> str:
    import uuid

    return f"tool_req_{uuid.uuid4().hex[:12]}"
