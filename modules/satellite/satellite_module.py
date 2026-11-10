"""SatelliteModule for EarthMind System Skeleton (Stage D2 to D5).

Implements ModuleInterface protocol for EarthMind lifecycle and workflow dispatch.
"""

from typing import Any, Dict, Optional

from core.config.settings import SatelliteConfig, settings
from core.interfaces.module import ModuleInterface
from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest, ApplicationResponse
from core.schemas.satellite import (
    EarthMindSatelliteEvidence,
    SatelliteDataQuality,
    SatelliteDataRequest,
    SatelliteDatasetMetadata,
    SatelliteIndicator,
    SatelliteProcessedData,
    SatelliteProvider,
)
from modules.satellite.satellite_service import SatelliteService

logger = get_logger("modules.satellite")


class SatelliteModule(ModuleInterface):
    module_name = "satellite"

    def __init__(self, service: Optional[SatelliteService] = None):
        self._service = service or SatelliteService()
        self._is_initialized = False

    @property
    def service(self) -> SatelliteService:
        return self._service

    @property
    def context_provider(self):
        return self._service.create_context_provider()

    def initialize(self) -> None:
        logger.info("Initializing Satellite Module (Stage D2 to D5)...")
        if not self._service.config.enabled:
            logger.warning("Satellite module is disabled by configuration.")
        self._service.lifecycle.start()
        self._is_initialized = True
        logger.info("Satellite module initialized successfully.")

    def shutdown(self) -> None:
        logger.info("Shutting down Satellite module...")
        self._service.lifecycle.stop()
        self._is_initialized = False
        logger.info("Satellite module shut down.")

    def health_check(self) -> Dict[str, Any]:
        status = self._service.check_health()
        status["initialized"] = self._is_initialized
        return status

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
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
                req_obj = payload if isinstance(payload, SatelliteDataRequest) else SatelliteDataRequest(**payload)
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

            elif op in ("process_dataset", "process_satellite_data", "process"):
                meta_dict = payload.get("metadata", {})
                meta_obj = meta_dict if isinstance(meta_dict, SatelliteDatasetMetadata) else SatelliteDatasetMetadata(**meta_dict)
                raw_matrices = payload.get("raw_band_matrices", {})
                target_bands = payload.get("target_bands")
                field_id = payload.get("field_id")
                field_boundary = payload.get("field_boundary")
                target_crs = payload.get("target_crs", "EPSG:4326")

                proc_data, _ = self._service.process_dataset(
                    metadata=meta_obj,
                    raw_band_matrices=raw_matrices,
                    target_bands=target_bands,
                    field_id=field_id,
                    field_boundary=field_boundary,
                    target_crs=target_crs,
                )
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS" if proc_data.processing_status.value != "FAILED" else "FAILED",
                    response=proc_data.model_dump(),
                )

            elif op in ("extract_indicators", "indicators", "calculate_indices"):
                proc_dict = payload.get("processed_data", {})
                proc_obj = proc_dict if isinstance(proc_dict, SatelliteProcessedData) else SatelliteProcessedData(**proc_dict)
                matrices = payload.get("band_matrices", {})
                requested = payload.get("requested_indicators")
                indicators = self._service.extract_indicators(
                    processed_data=proc_obj,
                    band_matrices=matrices,
                    requested_indicators=requested,
                )
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=[ind.model_dump() for ind in indicators],
                )

            elif op in ("assess_uncertainty", "uncertainty"):
                q_status = payload.get("quality_status", SatelliteDataQuality.GOOD)
                if isinstance(q_status, str):
                    q_status = SatelliteDataQuality(q_status)
                cloud = float(payload.get("cloud_cover_target", 0.0))
                calibrated = bool(payload.get("is_calibrated", True))
                revisit = float(payload.get("revisit_age_days", 0.0))
                res = self._service.assess_uncertainty(
                    quality_status=q_status,
                    cloud_cover_target=cloud,
                    is_calibrated=calibrated,
                    revisit_age_days=revisit,
                )
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=res,
                )

            elif op in ("generate_intelligence", "extract_agronomic_features"):
                raw_inds = payload.get("indicators", [])
                inds = [i if isinstance(i, SatelliteIndicator) else SatelliteIndicator(**i) for i in raw_inds]
                res = self._service.extract_agronomic_features(indicators=inds)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=res,
                )

            elif op in ("build_evidence", "synthesize_evidence"):
                req_d = payload.get("request", {})
                req_obj = req_d if isinstance(req_d, SatelliteDataRequest) else SatelliteDataRequest(**req_d)
                proc_d = payload.get("processed_data", {})
                proc_obj = proc_d if isinstance(proc_d, SatelliteProcessedData) else SatelliteProcessedData(**proc_d)
                raw_inds = payload.get("indicators", [])
                inds = [i if isinstance(i, SatelliteIndicator) else SatelliteIndicator(**i) for i in raw_inds]
                evidence = self._service.build_evidence(
                    request=req_obj,
                    processed_data=proc_obj,
                    indicators=inds,
                    **payload.get("kwargs", {}),
                )
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=evidence.model_dump(),
                )

            elif op in ("validate_evidence", "validate"):
                ev_d = payload.get("evidence", {})
                ev_obj = ev_d if isinstance(ev_d, EarthMindSatelliteEvidence) else EarthMindSatelliteEvidence(**ev_d)
                val_result = self._service.validate_evidence(ev_obj)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS" if val_result.is_valid else "FAILED",
                    response=val_result.model_dump(),
                )

            elif op in ("format_for_sarvam", "format_sarvam_summary"):
                ev_d = payload.get("evidence", {})
                ev_obj = ev_d if isinstance(ev_d, EarthMindSatelliteEvidence) else EarthMindSatelliteEvidence(**ev_d)
                summary_text = self._service.format_for_sarvam(ev_obj)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response={"summary": summary_text},
                )

            elif op in ("share_with_drone", "share_macro_indicators"):
                ev_d = payload.get("evidence", {})
                ev_obj = ev_d if isinstance(ev_d, EarthMindSatelliteEvidence) else EarthMindSatelliteEvidence(**ev_d)
                f_id = payload.get("field_id", ev_obj.scope.field_id or "field_default")
                res = self._service.cross_module_sharing.share_with_drone_module(ev_obj, field_id=f_id)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=res,
                )

            elif op in ("share_with_vision", "share_multispectral_overview"):
                ev_d = payload.get("evidence", {})
                ev_obj = ev_d if isinstance(ev_d, EarthMindSatelliteEvidence) else EarthMindSatelliteEvidence(**ev_d)
                f_id = payload.get("field_id", ev_obj.scope.field_id or "field_default")
                res = self._service.cross_module_sharing.share_with_vision_module(ev_obj, field_id=f_id)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=res,
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
