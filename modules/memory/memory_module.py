from typing import Any, Optional, Dict
from core.schemas.application import ApplicationRequest, ApplicationResponse
from core.interfaces.services import MemoryInterface
from core.interfaces.module import DatabaseInterface
from core.interfaces.memory_storage import IMemoryStorageAdapter
from core.logging.logger import get_logger
from modules.memory.storage_adapter import InMemoryMemoryStorageAdapter
from modules.memory.memory_service import MemoryService
from modules.memory.context_provider import MemoryContextProvider

logger = get_logger("modules.memory")


class MemoryModule(MemoryInterface):
    """
    EarthMind Memory Module.
    Conforms to MemoryInterface (and ModuleInterface) for lifecycle management,
    while hosting the canonical MemoryService, IMemoryStorageAdapter, and
    MemoryContextProvider for B2 Context Manager integration.
    """

    module_name = "memory"

    def __init__(
        self,
        db_service: Optional[DatabaseInterface] = None,
        storage_adapter: Optional[IMemoryStorageAdapter] = None,
        service: Optional[MemoryService] = None,
    ):
        self.db_service = db_service
        self._in_memory_store: Dict[str, Any] = {}

        # Initialize storage adapter
        self.storage = storage_adapter or InMemoryMemoryStorageAdapter()

        # Initialize canonical MemoryService
        self.service = service or MemoryService(storage_adapter=self.storage)

        # Initialize MemoryContextProvider for B2 Context Manager
        self.context_provider = MemoryContextProvider(memory_service=self.service)

        self._is_initialized = False

    def initialize(self) -> None:
        """Initialize the memory module and storage resources."""
        if self.db_service:
            try:
                self.db_service.execute(
                    "CREATE TABLE IF NOT EXISTS memories (key TEXT PRIMARY KEY, value TEXT)"
                )
            except Exception as e:
                logger.warning(f"Database table initialization warning in MemoryModule: {e}")

        self._is_initialized = True
        logger.info("Memory module initialized successfully.")

    def shutdown(self) -> None:
        """Cleanly shutdown the memory module and release resources."""
        self._is_initialized = False
        logger.info("Memory module shut down cleanly.")

    def store_memory(self, key: str, value: Any) -> bool:
        """Legacy MemoryInterface method for storing simple key-value memories."""
        self._in_memory_store[key] = value
        if self.db_service:
            try:
                self.db_service.execute(
                    "INSERT OR REPLACE INTO memories (key, value) VALUES (?, ?)",
                    (key, str(value))
                )
            except Exception as e:
                logger.warning(f"Failed to persist legacy memory to db_service: {e}")
        return True

    def retrieve_memory(self, key: str) -> Optional[Any]:
        """Legacy MemoryInterface method for retrieving simple key-value memories."""
        if key in self._in_memory_store:
            return self._in_memory_store[key]
        if self.db_service:
            try:
                row = self.db_service.fetch_one(
                    "SELECT value FROM memories WHERE key = ?",
                    (key,)
                )
                if row:
                    return row["value"]
            except Exception as e:
                logger.warning(f"Failed to fetch legacy memory from db_service: {e}")
        return None

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        """Handle incoming application requests dispatched to memory module."""
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
