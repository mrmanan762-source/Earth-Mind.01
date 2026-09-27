from core.schemas.application import ApplicationRequest, ApplicationResponse
from core.logging.logger import get_logger
from modules.ulpu.ulpu_service import UlpuService

logger = get_logger("modules.ulpu")


class ULPUModule:
    module_name = "ulpu"

    def __init__(self) -> None:
        self.service: UlpuService = UlpuService()

    def initialize(self) -> None:
        logger.info("ULPU module initialized with language & provider registry.")

    def shutdown(self) -> None:
        logger.info("ULPU module shut down.")

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        return ApplicationResponse(
            request_id=request.request_id,
            status="SUCCESS",
            response=f"ULPU handled operation '{request.operation}'"
        )
