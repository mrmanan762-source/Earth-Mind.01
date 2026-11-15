"""Satellite Intelligence adapter tool for EarthMind Phase 3.

Exposes the existing Satellite Intelligence module (Stages D2-D7) through a
controlled tool interface. This adapter reuses the existing `SatelliteModule` /
`SatelliteService` capabilities and does not rebuild any satellite processing.

Supported operations map to existing module operations:
- "health_check"   -> module.health_check()
- "list_providers" -> service.provider_registry.list_providers()
- "search_catalog" -> service.search_catalog(SatelliteDataRequest)
- "acquire"        -> service.acquire(SatelliteDataRequest)

The tool preserves acquisition dates, observation freshness, geospatial
metadata and source information, returns structured observations, and handles
unavailable data / unsupported requests explicitly. It never invents satellite
observations. The feature-frozen Drone Module is not touched.
"""

import uuid
from typing import Any, Dict, List, Optional

from core.errors.exceptions import (
    InvalidToolRequestError,
    ToolExecutionError,
    ToolUnavailableError,
    ToolValidationError,
)
from core.schemas.tools import (
    ToolDefinition,
    ToolExecutionConfig,
    ToolPermission,
    ToolSourceReference,
)

_SUPPORTED_OPERATIONS = ("health_check", "list_providers", "search_catalog", "acquire")


class SatelliteTool:
    """Tool adapter over the EarthMind Satellite Intelligence module."""

    tool_id = "satellite_intelligence"

    def __init__(self, satellite_module: Optional[Any] = None):
        self._module = satellite_module

    def _get_module(self) -> Any:
        if self._module is not None:
            return self._module
        try:
            from modules.satellite.satellite_module import SatelliteModule

            self._module = SatelliteModule()
        except Exception as exc:  # pragma: no cover - defensive
            raise ToolExecutionError(
                self.tool_id, f"Satellite module unavailable: {exc}"
            ) from exc
        return self._module

    def is_available(self) -> bool:
        try:
            module = self._get_module()
            service = getattr(module, "service", None)
            if service is None:
                return False
            config = getattr(service, "config", None)
            return bool(getattr(config, "enabled", True))
        except Exception:
            return False

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_id=self.tool_id,
            name="Satellite Intelligence",
            description=(
                "Expose existing Satellite Intelligence capabilities (catalog search, "
                "dataset acquisition, provider listing, health) through a controlled "
                "tool interface. Returns structured satellite observations with "
                "acquisition dates, freshness, geospatial metadata and source provenance."
            ),
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": list(_SUPPORTED_OPERATIONS),
                    },
                    "provider_id": {"type": "string"},
                    "dataset_id": {"type": "string"},
                    "request": {
                        "type": "object",
                        "description": "SatelliteDataRequest fields (geospatial, temporal_window, ...)",
                    },
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                    "bounding_box": {"type": "array", "items": {"type": "number"}},
                    "acquisition_date": {"type": "string"},
                },
                "required": ["operation"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "operation": {"type": "string"},
                    "datasets": {"type": "array"},
                    "acquisition_date": {"type": ["string", "null"]},
                    "freshness_days": {"type": ["number", "null"]},
                    "geospatial": {"type": "object"},
                    "source": {"type": "object"},
                },
            },
            required_permissions=[ToolPermission.SATELLITE_DATA],
            execution=ToolExecutionConfig(
                timeout_seconds=30.0,
                max_retries=1,
                idempotent=True,
                max_concurrency=4,
                max_request_bytes=16384,
                max_result_bytes=524288,
            ),
            error_contract=[
                "INVALID_TOOL_REQUEST",
                "TOOL_VALIDATION_ERROR",
                "TOOL_UNAVAILABLE",
                "TOOL_EXECUTION_ERROR",
                "TOOL_TIMEOUT",
            ],
            tags=["satellite", "geospatial", "observations"],
        )

    def validate_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        operation = str(arguments.get("operation", "")).strip().lower()
        if operation not in _SUPPORTED_OPERATIONS:
            raise ToolValidationError(
                f"Unsupported satellite operation '{operation}'. Supported: {list(_SUPPORTED_OPERATIONS)}.",
                tool_id=self.tool_id,
            )
        cleaned: Dict[str, Any] = {"operation": operation}

        if operation in ("search_catalog", "acquire"):
            request_payload = self._build_request_payload(arguments)
            cleaned["request"] = request_payload
            if operation == "acquire":
                dataset_id = arguments.get("dataset_id")
                if not isinstance(dataset_id, str) or not dataset_id.strip():
                    raise InvalidToolRequestError(
                        "'dataset_id' is required for the acquire operation.", tool_id=self.tool_id
                    )
                cleaned["dataset_id"] = dataset_id.strip()
                provider_id = arguments.get("provider_id")
                if provider_id is not None and not isinstance(provider_id, str):
                    raise ToolValidationError("'provider_id' must be a string.", tool_id=self.tool_id)
                cleaned["provider_id"] = provider_id.strip() if isinstance(provider_id, str) else None
            else:
                provider_id = arguments.get("provider_id")
                if provider_id is not None and not isinstance(provider_id, str):
                    raise ToolValidationError("'provider_id' must be a string.", tool_id=self.tool_id)
                cleaned["provider_id"] = provider_id.strip() if isinstance(provider_id, str) else None

        return cleaned

    def _build_request_payload(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        # Accept an explicit request object, else assemble from flat inputs.
        explicit = arguments.get("request")
        if isinstance(explicit, dict) and explicit:
            return dict(explicit)

        latitude = arguments.get("latitude")
        longitude = arguments.get("longitude")
        if latitude is None or longitude is None:
            raise InvalidToolRequestError(
                "Satellite catalog/acquire operations require 'latitude' and 'longitude' "
                "(or an explicit 'request' object).",
                tool_id=self.tool_id,
            )
        if not isinstance(latitude, (int, float)) or isinstance(latitude, bool):
            raise ToolValidationError("'latitude' must be a number.", tool_id=self.tool_id)
        if not isinstance(longitude, (int, float)) or isinstance(longitude, bool):
            raise ToolValidationError("'longitude' must be a number.", tool_id=self.tool_id)

        geospatial: Dict[str, Any] = {
            "latitude": float(latitude),
            "longitude": float(longitude),
        }
        bounding_box = arguments.get("bounding_box")
        if bounding_box is not None:
            if not isinstance(bounding_box, list) or len(bounding_box) != 4:
                raise ToolValidationError(
                    "'bounding_box' must be [min_lon, min_lat, max_lon, max_lat].", tool_id=self.tool_id
                )
            geospatial["bounding_box"] = [float(v) for v in bounding_box]

        acquisition_date = arguments.get("acquisition_date")
        if acquisition_date is not None and not isinstance(acquisition_date, str):
            raise ToolValidationError("'acquisition_date' must be an ISO 8601 string.", tool_id=self.tool_id)
        if not acquisition_date:
            from datetime import datetime, timezone

            acquisition_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "request_id": f"sat_tool_{uuid.uuid4().hex[:10]}",
            "geospatial": geospatial,
            "temporal_window": {"acquisition_date": acquisition_date},
        }

    def execute(self, arguments: Dict[str, Any], request) -> Dict[str, Any]:
        module = self._get_module()
        operation = arguments["operation"]

        if operation == "health_check":
            return self._result({"operation": operation, "health": module.health_check()})

        if operation == "list_providers":
            providers = module.service.provider_registry.list_providers()
            return self._result(
                {"operation": operation, "providers": [p.model_dump(mode="json") for p in providers]}
            )

        from core.schemas.satellite import SatelliteDataRequest

        if operation == "search_catalog":
            sat_request = self._coerce_request(arguments["request"])
            results = module.service.search_catalog(sat_request, provider_id=arguments.get("provider_id"))
            return self._result(
                {
                    "operation": operation,
                    "datasets": [d.model_dump(mode="json") for d in results],
                    "acquisition_date": sat_request.temporal_window.acquisition_date,
                    "freshness_days": _freshness_days(sat_request.temporal_window.acquisition_date),
                    "geospatial": sat_request.geospatial.model_dump(mode="json"),
                    "source": {"provider_id": arguments.get("provider_id"), "module": "satellite"},
                },
                sources=self._dataset_sources(results),
            )

        if operation == "acquire":
            sat_request = self._coerce_request(arguments["request"])
            provider_id = arguments.get("provider_id")
            if provider_id:
                result = module.service.acquire_dataset(
                    arguments["dataset_id"], sat_request, provider_id=provider_id
                )
            else:
                result = module.service.acquire(sat_request)
            payload = result.model_dump(mode="json")
            meta = result.dataset_metadata
            return self._result(
                {
                    "operation": operation,
                    "acquisition": payload,
                    "acquisition_date": getattr(getattr(meta, "temporal", None), "acquisition_date", None),
                    "freshness_days": _freshness_days(
                        getattr(getattr(meta, "temporal", None), "acquisition_date", None)
                    ),
                    "geospatial": getattr(meta, "geospatial", None).model_dump(mode="json")
                    if getattr(meta, "geospatial", None)
                    else None,
                    "source": {"provider_id": result.provider_id, "module": "satellite"},
                },
                sources=self._dataset_sources([meta] if meta else []),
            )

        raise ToolExecutionError(self.tool_id, f"Unhandled operation '{operation}'.")

    @staticmethod
    def _coerce_request(payload: Dict[str, Any]):
        from core.schemas.satellite import SatelliteDataRequest

        if isinstance(payload, SatelliteDataRequest):
            return payload
        return SatelliteDataRequest(**payload)

    @staticmethod
    def _dataset_sources(datasets: List[Any]) -> List[Dict[str, Any]]:
        sources: List[Dict[str, Any]] = []
        for dataset in datasets or []:
            temporal = getattr(dataset, "temporal", None)
            geospatial = getattr(dataset, "geospatial", None)
            sources.append(
                ToolSourceReference(
                    source_type="satellite",
                    title=getattr(dataset, "dataset_id", None),
                    provider=getattr(dataset, "provider_id", None),
                    observed_at=getattr(temporal, "acquisition_date", None),
                    metadata={
                        "constellation": getattr(dataset, "constellation", None),
                        "cloud_cover_percentage": getattr(dataset, "cloud_cover_percentage", None),
                        "latitude": getattr(geospatial, "latitude", None),
                        "longitude": getattr(geospatial, "longitude", None),
                    },
                ).model_dump()
            )
        return sources

    @staticmethod
    def _result(payload: Dict[str, Any], sources: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        return {
            "__tool_result__": True,
            "payload": payload,
            "sources": sources or [],
            "warnings": [],
            "partial": False,
        }


def _freshness_days(acquisition_date: Optional[str]) -> Optional[float]:
    if not acquisition_date:
        return None
    try:
        from datetime import datetime, timezone

        parsed = acquisition_date.replace("Z", "+00:00")
        observed = datetime.fromisoformat(parsed)
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - observed).total_seconds() / 86400.0, 3)
    except (ValueError, TypeError):
        return None
