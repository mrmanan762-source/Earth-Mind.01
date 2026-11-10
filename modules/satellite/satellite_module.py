"""SatelliteModule for EarthMind System Skeleton (Stage D2: Core Foundation).

Implements ModuleInterface protocol for EarthMind lifecycle and workflow dispatch.
"""

from typing import Any, Dict, Optional

from core.config.settings import SatelliteConfig, settings
from core.interfaces.module import ModuleInterface
from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest, ApplicationResponse
from core.schemas.satellite import (
    SatelliteDataRequest,
    SatelliteProvider,
)
from modules.satellite.satellite_service import SatelliteService

logger = get_logger("modules.satellite")


class SatelliteModule(ModuleInterface):
    """Satellite module integrating SatelliteService with EarthMind system lifecycle."""
    module_name = "satellite"

    def __init__(self, service: Optional[SatelliteService] = None):
        self._service = service or SatelliteService()
        self._is_initialized = False

    @property
    def service(self) -> SatelliteService:
        return self._service

    def initialize(self) -> None:
        """Initialize Satellite module components and dependencies."""
        logger.info("Initializing Satellite Module (Stage D2: Core Foundation)...")
        if not self._service.config.enabled:
            logger.warning("Satellite module is disabled by configuration.")
        self._service.lifecycle.start()
        self._is_initialized = True
        logger.info("Satellite module initialized successfully.")

    def shutdown(self) -> None:
        """Shutdown Satellite module components cleanly."""
        logger.info("Shutting down Satellite module...")
        self._service.lifecycle.stop()
        self._is_initialized = False
        logger.info("Satellite module shut down.")

    def health_check(self) -> Dict[str, Any]:
        """Module health status check."""
        status = self._service.check_health()
        status["initialized"] = self._is_initialized
        return status

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        """Workflow dispatch entry point for application requests targeting satellite module."""
        op = (request.operation or "").lower().strip()
        payload = request.payload or {}

        try:
            if op == "health_check":
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=self.health_check(),
                )

            elif op in ("search_catalog", "search", "discover"):
                if isinstance(payload, SatelliteDataRequest):
                    req_obj = payload
                else:
                    req_obj = SatelliteDataRequest(**payload)
                provider_id = payload.get("provider_id") if isinstance(payload, dict) else None
                results = self._service.search_catalog(req_obj, provider_id=provider_id)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=[r.model_dump() for r in results],
                )

            elif op in ("acquire_dataset", "acquire"):
                dataset_id = payload.get("dataset_id")
                provider_id = payload.get("provider_id")
                req_dict = payload.get("request", {})
                req_obj = req_dict if isinstance(req_dict, SatelliteDataRequest) else SatelliteDataRequest(**req_dict)
                result = self._service.acquire_dataset(dataset_id, req_obj, provider_id=provider_id)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS" if result.status.value != "FAILED" else "FAILED",
                    response=result.model_dump(),
                )

            elif op in ("list_providers", "providers"):
                status_filter = payload.get("status") if isinstance(payload, dict) else None
                providers = self._service.provider_registry.list_providers(status=status_filter)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=[p.model_dump() for p in providers],
                )

            elif op in ("get_provider", "provider"):
                provider_id = payload.get("provider_id") if isinstance(payload, dict) else None
                prov = self._service.provider_registry.get_provider(provider_id)
                if prov:
                    return ApplicationResponse(
                        request_id=request.request_id,
                        status="SUCCESS",
                        response=prov.model_dump(),
                    )
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="NOT_FOUND",
                    response={"provider_id": provider_id, "error": "Provider not found"},
                )

            return ApplicationResponse(
                request_id=request.request_id,
                status="SUCCESS",
                response=f"Satellite handled operation '{request.operation}'",
            )

        except Exception as exc:
            logger.error(f"Error handling satellite operation '{request.operation}': {exc}")
            return ApplicationResponse(
                request_id=request.request_id,
                status="ERROR",
                response={"error": str(exc), "operation": request.operation},
            )
