from typing import Any, Dict, Optional
from core.schemas.application import ApplicationRequest, ApplicationResponse
from core.interfaces.module import DatabaseInterface
from core.logging.logger import get_logger

logger = get_logger("modules.database")

class SQLiteDatabaseModule:
    module_name = "database"

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._db_service: Optional[DatabaseInterface] = None

    def initialize(self) -> None:
        if self._db_service is None:
            from modules.database.sqlite_db import SQLiteDatabaseService
            self._db_service = SQLiteDatabaseService(self.db_path)
            self._db_service.connect()
            logger.info(f"Database module initialized with path: {self.db_path}")

    @property
    def service(self) -> Optional[DatabaseInterface]:
        return self._db_service

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        if not self._db_service:
            self.initialize()
        op = request.operation
        payload = request.payload or {}
        res = None
        if op == "execute":
            res = self._db_service.execute(payload.get("query", ""), payload.get("params", ()))
        elif op == "fetch_all":
            res = self._db_service.fetch_all(payload.get("query", ""), payload.get("params", ()))
        elif op == "fetch_one":
            res = self._db_service.fetch_one(payload.get("query", ""), payload.get("params", ()))
        else:
            return ApplicationResponse(
                request_id=request.request_id,
                status="UNKNOWN_OPERATION",
                warnings=[f"Unsupported database operation: {op}"]
            )

        return ApplicationResponse(
            request_id=request.request_id,
            status="SUCCESS",
            response=res
        )

    def shutdown(self) -> None:
        if self._db_service:
            self._db_service.disconnect()
            self._db_service = None
            logger.info("Database module shutdown complete.")
