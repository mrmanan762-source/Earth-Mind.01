"""Camera Data Routing Foundation for EarthMind Drone Module (Stage D2).

Enforces the architectural boundary:
Drone Camera Data -> Camera Data Router -> Vision Module.
The Drone Module performs NO image interpretation, crop disease detection,
or visual diagnosis.
"""

from typing import Any, Dict, Optional

from core.logging.logger import get_logger
from core.schemas.drone import DroneCameraRoutingContract, SensorCategory
from modules.drone.errors import DroneInvalidArgumentError, DroneInternalError

logger = get_logger("modules.drone.camera_router")


class CameraDataRouter:
    """Router responsible for safely packaging and delegating optical camera data to the Vision Module."""

    def __init__(self, vision_service: Optional[Any] = None):
        self._vision_service = vision_service

    def set_vision_service(self, vision_service: Any) -> None:
        """Inject or update the Vision service boundary adapter."""
        self._vision_service = vision_service

    def route_camera_data(self, contract: DroneCameraRoutingContract) -> Dict[str, Any]:
        """Validate camera routing contract and dispatch to Vision Module without image decoding."""
        # 1. Structural and category validation
        if contract.sensor_category != SensorCategory.RGB:
            raise DroneInvalidArgumentError(
                details=f"CameraDataRouter only handles optical camera categories (RGB), got '{contract.sensor_category.value}'.",
                operation="route_camera_data",
            )

        if not contract.image_reference:
            raise DroneInvalidArgumentError(
                details="Camera image reference URI or path is missing.",
                operation="route_camera_data",
            )

        logger.info(
            f"Routing drone camera data (routing_id={contract.routing_id}, drone_id={contract.drone_id}, "
            f"camera_id={contract.camera_id}) to Vision Module."
        )

        # 2. Check Vision Module endpoint availability
        if self._vision_service is not None:
            # If Vision service has a designated ingestion or handle method, invoke it safely
            if hasattr(self._vision_service, "ingest_camera_frame") and callable(self._vision_service.ingest_camera_frame):
                try:
                    vision_res = self._vision_service.ingest_camera_frame(contract)
                    return {
                        "status": "ROUTED",
                        "routing_id": contract.routing_id,
                        "destination_module": "vision",
                        "vision_response": vision_res,
                        "metadata_preserved": {
                            "drone_id": contract.drone_id,
                            "camera_id": contract.camera_id,
                            "mission_reference": contract.mission_reference,
                            "field_id": contract.field_id,
                            "collection_timestamp": contract.collection_timestamp,
                            "has_spatial": bool(contract.spatial_metadata),
                        }
                    }
                except Exception as exc:
                    logger.error(f"Vision service failed to receive camera frame: {exc}")
                    raise DroneInternalError(
                        operation="route_camera_data",
                        details=f"Failed to deliver camera frame to Vision module: {exc}"
                    ) from exc

        # 3. If Vision service is absent or not yet exposing an ingestion endpoint,
        # report clean structured handoff status without fabricating visual results.
        return {
            "status": "HANDOFF_PENDING",
            "routing_id": contract.routing_id,
            "destination_module": "vision",
            "message": "Camera routing contract prepared; Vision module receiver pending integration.",
            "metadata_preserved": {
                "drone_id": contract.drone_id,
                "camera_id": contract.camera_id,
                "mission_reference": contract.mission_reference,
                "field_id": contract.field_id,
                "collection_timestamp": contract.collection_timestamp,
                "has_spatial": bool(contract.spatial_metadata),
            }
        }
