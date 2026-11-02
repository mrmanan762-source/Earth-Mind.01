import uuid
from core.config.settings import settings
from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest
from app.lifecycle import LifecycleManager
from app.workflow import WorkflowEngine

import os
from modules.database.db_module import SQLiteDatabaseModule
from modules.database.postgres_db import PostgresDatabaseService
from modules.ai.ai_module import AIModule
from modules.memory.memory_module import MemoryModule
from modules.memory.storage_adapter import InMemoryMemoryStorageAdapter
from modules.memory.supabase_adapter import SupabasePostgresMemoryStorageAdapter
from modules.inspector.inspector_module import InspectorModule
from modules.ulpu.ulpu_module import ULPUModule
from modules.vision.vision_module import VisionModule
from modules.drone.drone_module import DroneModule
from modules.data_training.data_training_module import DataTrainingModule
from modules.external_services.external_services_module import ExternalServicesModule
from modules.context.context_module import ContextModule
from core.errors.exceptions import ConfigurationError

logger = get_logger("app.main")

def resolve_memory_storage_adapter(environment: str):
    """Resolve and initialize the appropriate memory storage adapter based on environment and config.

    Production:
        Requires persistent Supabase / PostgreSQL storage.
        Initializes PostgresDatabaseService and SupabasePostgresMemoryStorageAdapter.
        Fails fast if connection or persistence cannot be established; never silently
        substitutes in-memory storage.

    Development / Testing:
        Uses SupabasePostgresMemoryStorageAdapter if explicitly selected or configured;
        otherwise defaults to InMemoryMemoryStorageAdapter.
    """
    env = (environment or "development").lower().strip()
    is_prod = env in ("production", "prod")
    explicit_adapter = os.getenv("EARTHMIND_STORAGE_ADAPTER", "").lower().strip()

    use_postgres = is_prod or explicit_adapter in ("postgres", "postgresql", "supabase")

    if use_postgres:
        logger.info("Initializing Supabase / PostgreSQL persistent storage adapter for Memory Module...")
        try:
            pg_service = PostgresDatabaseService(config=settings.postgres)
            pg_service.connect()
            storage_adapter = SupabasePostgresMemoryStorageAdapter(db_service=pg_service)
            health = storage_adapter.check_health()
            if not health.is_healthy:
                raise ConfigurationError(
                    f"PostgreSQL storage health check failed during bootstrap: {health.details}",
                    details=health.details,
                )
            logger.info("Supabase / PostgreSQL storage adapter successfully verified and attached.")
            return storage_adapter, pg_service
        except Exception as exc:
            if is_prod:
                logger.error(f"FATAL: Production memory persistence bootstrap failed: {exc}")
                raise ConfigurationError(
                    f"Production memory persistence bootstrap failed: {exc}. "
                    "Silent fallback to in-memory storage is strictly prohibited in production mode.",
                    details={"error": str(exc)},
                ) from exc
            logger.warning(
                f"PostgreSQL storage initialization failed in {env} mode ({exc}); "
                "falling back to InMemoryMemoryStorageAdapter for development."
            )
            return InMemoryMemoryStorageAdapter(), None

    logger.info("Initializing InMemoryMemoryStorageAdapter for Memory Module (development/test mode).")
    return InMemoryMemoryStorageAdapter(), None


def create_app():
    lifecycle = LifecycleManager()

    # Determine environment and resolve storage adapter
    storage_adapter, pg_service = resolve_memory_storage_adapter(settings.environment)

    # Create module instances
    db_module = SQLiteDatabaseModule(db_path=settings.db_path)
    ai_module = AIModule(db_service=db_module.service)
    memory_module = MemoryModule(
        db_service=db_module.service,
        storage_adapter=storage_adapter,
    )
    # Retain reference to pg_service for clean shutdown if created
    memory_module._pg_service = pg_service
    inspector_module = InspectorModule()
    ulpu_module = ULPUModule()
    vision_module = VisionModule()
    drone_module = DroneModule()
    data_training_module = DataTrainingModule()
    external_services_module = ExternalServicesModule()

    # Create ContextModule connected to memory_module's MemoryContextProvider
    context_module = ContextModule(memory_provider=memory_module.context_provider)

    # Attach modules to lifecycle
    lifecycle.register_module("database", db_module)
    lifecycle.register_module("ai", ai_module)
    lifecycle.register_module("memory", memory_module)
    lifecycle.register_module("inspector", inspector_module)
    lifecycle.register_module("ulpu", ulpu_module)
    lifecycle.register_module("vision", vision_module)
    lifecycle.register_module("drone", drone_module)
    lifecycle.register_module("data_training", data_training_module)
    lifecycle.register_module("external_services", external_services_module)
    lifecycle.register_module("context", context_module)

    workflow = WorkflowEngine(lifecycle)
    return lifecycle, workflow

def main():
    logger.info(f"Starting {settings.app_name} v{settings.version} ({settings.environment})")
    lifecycle, workflow = create_app()

    # Initialize all modules
    lifecycle.initialize_all()

    # Evaluate system health
    health_report = lifecycle.get_system_health()
    logger.info(f"System Health Status: readiness={health_report.readiness_status}, ready_e2e={health_report.is_ready_e2e}")

    # Execute sample request through workflow
    sample_request = ApplicationRequest(
        request_id=str(uuid.uuid4()),
        source="system_check",
        actor="admin",
        operation="process_text",
        payload={"prompt": "Analyze crop health status for Zone 4"},
        metadata={"target_module": "ai"}
    )

    logger.info("Executing sample workflow request...")
    response = workflow.dispatch(sample_request)
    logger.info(f"Workflow Response: {response}")

    metrics_summary = lifecycle.get_metrics()
    logger.info(f"Telemetry Metrics Summary: {metrics_summary.get('counters', {})}")

    # Shutdown
    lifecycle.shutdown_all()
    logger.info("EarthMind application finished execution.")

if __name__ == "__main__":
    main()
