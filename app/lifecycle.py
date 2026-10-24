from typing import Dict, Any, Optional
from core.config.settings import settings
from core.interfaces.module import ModuleInterface
from core.logging.logger import get_logger
from core.errors.exceptions import ModuleNotFoundError
from core.observability.health import HealthDiagnostics, SystemHealthReport
from core.observability.metrics import metrics_collector

logger = get_logger("app.lifecycle")

class LifecycleManager:
    """Manages system startup, module registration, shutdown lifecycle, health diagnostics, and metrics."""

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

    def get_system_health(self) -> SystemHealthReport:
        """Evaluate system health and readiness across registered modules."""
        qdrant_adapter = None
        emb_provider = None
        sparse_provider = None
        reranker_provider = None
        reasoning_model = None

        if "context" in self._modules and hasattr(self._modules["context"], "rag_provider"):
            rag_p = getattr(self._modules["context"], "rag_provider")
            if hasattr(rag_p, "embedding_provider"):
                emb_provider = rag_p.embedding_provider
            if hasattr(rag_p, "sparse_provider"):
                sparse_provider = rag_p.sparse_provider
            if hasattr(rag_p, "reranker"):
                reranker_provider = rag_p.reranker
            if hasattr(rag_p, "hybrid_retriever") and hasattr(rag_p.hybrid_retriever, "dense_adapter"):
                qdrant_adapter = rag_p.hybrid_retriever.dense_adapter

        if "ai" in self._modules and hasattr(self._modules["ai"], "sarvam_adapter"):
            reasoning_model = self._modules["ai"].sarvam_adapter

        return HealthDiagnostics.evaluate_system_health(
            qdrant_adapter=qdrant_adapter,
            embedding_provider=emb_provider,
            sparse_provider=sparse_provider,
            reranker_provider=reranker_provider,
            reasoning_model=reasoning_model,
        )

    def get_metrics(self) -> Dict[str, Any]:
        """Return system telemetry metric summary."""
        return metrics_collector.get_summary()
