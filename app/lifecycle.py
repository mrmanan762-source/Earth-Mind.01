from typing import Dict, Any
from core.config.settings import settings
from core.interfaces.module import ModuleInterface
from core.logging.logger import get_logger
from core.errors.exceptions import ModuleNotFoundError

logger = get_logger("app.lifecycle")

class LifecycleManager:
    """Manages system startup, module registration, and shutdown lifecycle."""

    def __init__(self):
        self._modules: Dict[str, ModuleInterface] = {}
        self._is_running: bool = False

    def register_module(self, name: str, module: ModuleInterface) -> None:
        """Register a module instance into the application lifecycle."""
        self._modules[name] = module
        logger.info(f"Registered module: {name}")

    def get_module(self, name: str) -> ModuleInterface:
        if name not in self._modules:
            raise ModuleNotFoundError(name)
        return self._modules[name]

    def initialize_all(self) -> None:
        """Initialize all registered modules."""
        logger.info("Initializing EarthMind System Skeleton...")
        # Validate startup configuration
        settings.validate_config()
        for name, module in self._modules.items():
            logger.info(f"Initializing module: {name}")
            if hasattr(module, "initialize") and callable(module.initialize):
                module.initialize()
        self._is_running = True
        logger.info("All modules initialized successfully.")

    def shutdown_all(self) -> None:
        """Shutdown all registered modules cleanly."""
        logger.info("Shutting down EarthMind System Skeleton...")
        for name, module in reversed(list(self._modules.items())):
            logger.info(f"Shutting down module: {name}")
            if hasattr(module, "shutdown") and callable(module.shutdown):
                module.shutdown()
        self._is_running = False
        logger.info("All modules shut down cleanly.")

    @property
    def is_running(self) -> bool:
        return self._is_running
