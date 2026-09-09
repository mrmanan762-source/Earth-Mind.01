from typing import Any, Optional, Dict
from core.schemas.application import ApplicationRequest, ApplicationResponse
from core.interfaces.services import MemoryInterface
from core.interfaces.module import DatabaseInterface
from core.logging.logger import get_logger

logger = get_logger("modules.memory")

class MemoryModule(MemoryInterface):
    module_name = "memory"

    def __init__(self, db_service: Optional[DatabaseInterface] = None):
        self.db_service = db_service
        self._in_memory_store: Dict[str, Any] = {}

    def initialize(self) -> None:
        if self.db_service:
            self.db_service.execute(
                "CREATE TABLE IF NOT EXISTS memories (key TEXT PRIMARY KEY, value TEXT)"
            )
        logger.info("Memory module initialized.")

    def shutdown(self) -> None:
        logger.info("Memory module shut down.")

    def store_memory(self, key: str, value: Any) -> bool:
        self._in_memory_store[key] = value
        if self.db_service:
            self.db_service.execute(
                "INSERT OR REPLACE INTO memories (key, value) VALUES (?, ?)",
                (key, str(value))
            )
        return True

    def retrieve_memory(self, key: str) -> Optional[Any]:
        if key in self._in_memory_store:
            return self._in_memory_store[key]
        if self.db_service:
            row = self.db_service.fetch_one(
                "SELECT value FROM memories WHERE key = ?",
                (key,)
            )
            if row:
                return row["value"]
        return None

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        op = request.operation
        payload = request.payload or {}

        if op == "store":
            key = payload.get("key")
            val = payload.get("value")
            success = self.store_memory(key, val)
            return ApplicationResponse(
                request_id=request.request_id,
                status="SUCCESS" if success else "FAILED",
                response={"key": key, "stored": success}
            )
        elif op == "retrieve":
            key = payload.get("key")
            val = self.retrieve_memory(key)
            return ApplicationResponse(
                request_id=request.request_id,
                status="SUCCESS" if val is not None else "NOT_FOUND",
                response={"key": key, "value": val}
            )
        return ApplicationResponse(
            request_id=request.request_id,
            status="UNKNOWN_OPERATION",
            warnings=[f"Unsupported memory operation: {op}"]
        )
