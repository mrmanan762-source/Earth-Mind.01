"""DroneModule for EarthMind System Skeleton (Stage D2: Core Foundation).

Implements ModuleInterface protocol for EarthMind lifecycle and workflow management.
"""

from typing import Any, Dict, Optional

from core.config.settings import DroneConfig, settings
from core.interfaces.module import ModuleInterface
from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest, ApplicationResponse
from core.schemas.drone import (
    AgriculturalIndicatorContract,
    DroneCameraRoutingContract,
    DroneSensorInputContract,
    FusedSensorMeasurementContract,
    MultiSensorFusionReportContract,
    NumericalAnalysisResultContract,
    ProcessedSensorMeasurementContract,
    SensorMetadataContract,
    SpectralAnalysisResultContract,
)
from modules.drone.drone_service import DroneService

logger = get_logger("modules.drone")


class DroneModule(ModuleInterface):
    """Drone module integrating DroneService with system lifecycle and workflow dispatch."""
    module_name = "drone"

    def __init__(self, service: Optional[DroneService] = None, vision_service: Optional[Any] = None):
        self._service = service or DroneService(vision_service=vision_service)
        self._is_initialized = False

    @property
    def service(self) -> DroneService:
        return self._service

    def initialize(self) -> None:
        """Initialize Drone module components and dependencies."""
        logger.info("Initializing Drone Module (Stage D2: Core Foundation)...")
        # Validate that config is healthy
        if not self._service.config.enabled:
            logger.warning("Drone module is disabled by configuration.")
        self._is_initialized = True
        logger.info("Drone module initialized successfully.")

    def shutdown(self) -> None:
        """Shutdown Drone module components cleanly."""
        logger.info("Shutting down Drone module...")
        self._is_initialized = False
        logger.info("Drone module shut down.")

    def health_check(self) -> Dict[str, Any]:
        """Module health status check."""
        status = self._service.check_health()
        status["initialized"] = self._is_initialized
        return status

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        """Workflow dispatch entry point for application requests targeting drone module."""
        op = (request.operation or "").lower().strip()
        payload = request.payload or {}

        try:
            if op == "health_check":
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=self.health_check()
                )

            elif op in ("ingest_sensor_data", "ingest"):
                if isinstance(payload, DroneSensorInputContract):
                    input_contract = payload
                else:
                    input_contract = DroneSensorInputContract(**payload)
                result = self._service.ingest_sensor_data(input_contract)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS" if result.accepted else "FAILED",
                    response=result.to_dict()
                )

            elif op in ("process_sensor_data", "process"):
                if isinstance(payload, DroneSensorInputContract):
                    input_contract = payload
                else:
                    input_contract = DroneSensorInputContract(**payload)
                result = self._service.process_sensor_data(input_contract)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=result
                )

            elif op in ("route_camera", "route_camera_data"):
                if isinstance(payload, DroneCameraRoutingContract):
                    cam_contract = payload
                else:
                    cam_contract = DroneCameraRoutingContract(**payload)
                result = self._service.route_camera_data(cam_contract)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=result
                )

            elif op in ("register_sensor", "register_sensor_profile"):
                if isinstance(payload, SensorMetadataContract):
                    meta = payload
                else:
                    meta = SensorMetadataContract(**payload)
                success = self._service.register_sensor(meta)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS" if success else "FAILED",
                    response={"sensor_id": meta.sensor_id, "registered": success}
                )

            elif op in ("get_sensor", "get_sensor_profile"):
                sensor_id = payload.get("sensor_id")
                sensor = self._service.get_sensor(sensor_id)
                if sensor:
                    return ApplicationResponse(
                        request_id=request.request_id,
                        status="SUCCESS",
                        response=sensor.model_dump()
                    )
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="NOT_FOUND",
                    response={"sensor_id": sensor_id, "error": "Sensor not found"}
                )

            elif op in ("associate_spatiotemporal", "spatiotemporal"):
                drone_id = payload.get("drone_id")
                sensor_id = payload.get("sensor_id")
                raw_meas = payload.get("measurements", [])
                meas_objs = []
                for m in raw_meas:
                    if isinstance(m, ProcessedSensorMeasurementContract):
                        meas_objs.append(m)
                    else:
                        meas_objs.append(ProcessedSensorMeasurementContract(**m))

                association = self._service.associate_spatiotemporal(
                    drone_id=drone_id,
                    sensor_id=sensor_id,
                    measurements=meas_objs,
                    field_id=payload.get("field_id"),
                    field_boundary=payload.get("field_boundary"),
                    declared_crs=payload.get("declared_crs"),
                    gap_threshold_seconds=payload.get("gap_threshold_seconds"),
                )
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=association.model_dump()
                )

            elif op in ("analyze_spectral", "spectral"):
                result = self._service.analyze_spectral(payload)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=result
                )

            elif op in ("extract_indicator", "indicator"):
                ind_name = payload.get("indicator_name")
                raw_meas = payload.get("measurements", [])
                meas_objs = [
                    m if isinstance(m, ProcessedSensorMeasurementContract)
                    else ProcessedSensorMeasurementContract(**m)
                    for m in raw_meas
                ]
                ind = self._service.extract_indicator(ind_name, meas_objs)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=ind.model_dump()
                )

            elif op in ("extract_available_indicators", "available_indicators"):
                raw_meas = payload.get("measurements", [])
                meas_objs = [
                    m if isinstance(m, ProcessedSensorMeasurementContract)
                    else ProcessedSensorMeasurementContract(**m)
                    for m in raw_meas
                ]
                inds = self._service.extract_available_indicators(meas_objs)
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=[i.model_dump() for i in inds]
                )

            elif op in ("fuse_sensor_data", "fuse_sensors", "fusion"):
                raw_streams = payload.get("sensor_streams", {})
                converted_streams = {}
                for sid, m_list in raw_streams.items():
                    converted_streams[sid] = [
                        m if isinstance(m, ProcessedSensorMeasurementContract)
                        else ProcessedSensorMeasurementContract(**m)
                        for m in m_list
                    ]
                report = self._service.fuse_sensor_data(
                    sensor_streams=converted_streams,
                    drone_id=payload.get("drone_id", "drone_default"),
                    field_id=payload.get("field_id"),
                )
                return ApplicationResponse(
                    request_id=request.request_id,
                    status="SUCCESS",
                    response=report.model_dump()
                )

            return ApplicationResponse(
                request_id=request.request_id,
                status="SUCCESS",
                response=f"Drone handled operation '{request.operation}'"
            )

        except Exception as exc:
            logger.error(f"Error handling drone operation '{request.operation}': {exc}")
            return ApplicationResponse(
                request_id=request.request_id,
                status="ERROR",
                response={"error": str(exc), "operation": request.operation}
            )
