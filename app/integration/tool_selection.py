"""Deterministic, request-dependent tool selection for the Phase 4 workflow.

Selection depends only on the (normalised) request text and explicit metadata.
It never invokes every tool for every request, and it never lets the request or
model output self-grant permissions: permission grants always come from trusted
metadata, defaulting to a conservative internal set.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# Keyword hints. Kept intentionally small and explicit so behaviour is testable.
_WEB_SEARCH_HINTS = (
    "latest",
    "news",
    "current",
    "price",
    "market",
    "scheme",
    "subsidy",
    "government",
    "policy",
    "update",
    "search",
    "look up",
    "lookup",
    "trend",
    "forecast price",
)
_WEATHER_HINTS = (
    "weather",
    "rain",
    "rainfall",
    "temperature",
    "humidity",
    "wind",
    "frost",
    "monsoon",
    "heatwave",
    "climate",
    "precipitation",
)
_SATELLITE_HINTS = (
    "satellite",
    "ndvi",
    "vegetation index",
    "imagery",
    "remote sensing",
    "canopy",
    "geospatial",
    "crop health map",
    "field map",
)
_CALC_EXPRESSION = re.compile(r"\d\s*[\+\-\*/%\^]\s*\d|percent|percentage|convert\s+\d", re.IGNORECASE)


def _contains_any(text: str, hints: tuple) -> bool:
    return any(h in text for h in hints)


def select_tool_calls(
    task: str,
    payload: Dict[str, Any],
    scope: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Return the ordered list of tool call specs appropriate for this request.

    A tool is selected only when the request clearly requires it. Coordinates for
    the weather tool are taken from explicit payload/scope only (never invented).
    """
    text = (task or "").lower()
    selected: List[Dict[str, Any]] = []

    # 1. Calculator: only for explicit arithmetic / percentage requests.
    expression = payload.get("expression") or payload.get("calculation")
    if expression or _CALC_EXPRESSION.search(task or ""):
        args: Dict[str, Any] = {"operation": "evaluate"}
        if expression:
            args["expression"] = str(expression)
        selected.append({"tool_id": "calculator", "arguments": args})

    # 2. Weather: requires weather intent AND explicit coordinates.
    latitude = payload.get("latitude", scope.get("latitude"))
    longitude = payload.get("longitude", scope.get("longitude"))
    wants_weather = bool(payload.get("request_weather")) or _contains_any(text, _WEATHER_HINTS)
    if wants_weather and latitude is not None and longitude is not None:
        selected.append(
            {
                "tool_id": "weather",
                "arguments": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "location_name": payload.get("location_name"),
                },
            }
        )

    # 3. Satellite: requires geospatial intent (catalog search is a safe read op).
    wants_satellite = bool(payload.get("request_satellite")) or _contains_any(text, _SATELLITE_HINTS)
    if wants_satellite and latitude is not None and longitude is not None:
        selected.append(
            {
                "tool_id": "satellite_intelligence",
                "arguments": {
                    "operation": "search_catalog",
                    "latitude": latitude,
                    "longitude": longitude,
                },
            }
        )

    # 4. Web search: explicit flag or freshness/current-info intent.
    wants_web = bool(payload.get("request_web_search")) or _contains_any(text, _WEB_SEARCH_HINTS)
    if wants_web:
        query = payload.get("web_query") or payload.get("query") or task
        if query:
            selected.append(
                {
                    "tool_id": "web_search",
                    "arguments": {"query": str(query), "max_results": int(payload.get("web_max_results", 5))},
                }
            )

    return selected


def resolve_trusted_tool_metadata(
    metadata: Optional[Dict[str, Any]],
    default_permissions: List[Any],
) -> Dict[str, Any]:
    """Extract trusted tool metadata (permissions/source) from request metadata.

    Permissions come exclusively from trusted ``request.metadata`` — never from
    the payload or model output. When absent, a conservative internal default is
    applied.
    """
    metadata = metadata or {}
    permissions = metadata.get("granted_permissions")
    if not permissions:
        permissions = list(default_permissions)
    return {
        "granted_permissions": permissions,
        "tool_source": metadata.get("tool_source", "integrated_workflow"),
    }
