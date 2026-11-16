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
from modules.satellite.satellite_module import SatelliteModule
from modules.data_training.data_training_module import DataTrainingModule
from modules.external_services.external_services_module import ExternalServicesModule
from modules.context.context_module import ContextModule
from modules.knowledge_base.kb_module import KnowledgeBaseModule
from modules.tools.tool_service import ToolService
from modules.tools.tool_module import ToolModule
from modules.reasoning.reasoning_module import ReasoningModule
from modules.reasoning.capability import ModelLayerReasoningCapability
from modules.planning.planning_module import PlanningModule
from modules.orchestrator.orchestrator_module import OrchestratorModule
from modules.ai.sarvam_adapter import Sarvam105BAdapter
from app.integration.capabilities import (
    B2ContextCapability,
    B3ReasoningCapability,
    B4PlanningCapability,
    InspectorCapability,
    MemoryCapability,
    SatelliteCapability,
    ToolEvidenceBuffer,
    ToolExecutionCapability,
    ULPUCapability,
)
from app.integration.tool_evidence_provider import ToolEvidenceProvider
from app.integration.workflow import IntegratedApplicationModule, IntegratedWorkflow
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
    satellite_module = SatelliteModule()
    data_training_module = DataTrainingModule()
    external_services_module = ExternalServicesModule()

    # Create ContextModule connected to memory_module's MemoryContextProvider
    context_module = ContextModule(memory_provider=memory_module.context_provider)
    if hasattr(satellite_module, "context_provider"):
        context_module.manager.register_provider(satellite_module.context_provider)

    # Phase 2: RAG Knowledge Base. Owns the retrieval stack and registers the
    # approved RAG provider with B2 via the ContextModule boundary during startup.
    knowledge_base_module = KnowledgeBaseModule(context_module=context_module)

    # Phase 3: Backend Tool Infrastructure. Reuse the already-constructed
    # satellite module so the tool adapter shares a single satellite service.
    tool_service = ToolService(satellite_module=satellite_module)
    tool_module = ToolModule(service=tool_service)

    # Phase 4: Integration layer. B5 orchestrates the completed modules through
    # typed capability adapters; the integrated workflow exposes one application
    # entry point. No module logic is duplicated here.
    tool_buffer = ToolEvidenceBuffer()
    context_module.manager.register_provider(ToolEvidenceProvider(buffer=tool_buffer))

    # Single model instance shared by the AI module and B3. It is loaded in stub
    # mode (no heavy weights); real Sarvam-105B inference is a Phase 5 concern.
    model_adapter = Sarvam105BAdapter()
    model_adapter.load()
    ai_module.sarvam_adapter = model_adapter

    reasoning_capability = ModelLayerReasoningCapability(model=model_adapter)
    reasoning_module = ReasoningModule(capability=reasoning_capability, inspector=inspector_module)
    planning_module = PlanningModule(inspector_service=inspector_module)
    orchestrator_module = OrchestratorModule(inspector_service=inspector_module)
    orchestrator_module.capability_manager.register_capability(B2ContextCapability(context_module.manager))
    orchestrator_module.capability_manager.register_capability(B3ReasoningCapability(reasoning_module))
    orchestrator_module.capability_manager.register_capability(B4PlanningCapability(planning_module))
    orchestrator_module.capability_manager.register_capability(InspectorCapability(inspector_module))
    orchestrator_module.capability_manager.register_capability(
        MemoryCapability(memory_module.context_provider)
    )
    orchestrator_module.capability_manager.register_capability(
        ULPUCapability(ulpu_module.service)
    )
    orchestrator_module.capability_manager.register_capability(
        SatelliteCapability(satellite_module)
    )
    orchestrator_module.capability_manager.register_capability(
        ToolExecutionCapability(tool_service, tool_buffer)
    )

    integrated_workflow = IntegratedWorkflow(
        orchestrator=orchestrator_module,
        tool_buffer=tool_buffer,
        ulpu_service=ulpu_module.service,
    )
    application_module = IntegratedApplicationModule(integrated_workflow)

    # Attach modules to lifecycle
    lifecycle.register_module("database", db_module)
    lifecycle.register_module("ai", ai_module)
    lifecycle.register_module("memory", memory_module)
    lifecycle.register_module("inspector", inspector_module)
    lifecycle.register_module("ulpu", ulpu_module)
    lifecycle.register_module("vision", vision_module)
    lifecycle.register_module("drone", drone_module)
    lifecycle.register_module("satellite", satellite_module)
    lifecycle.register_module("data_training", data_training_module)
    lifecycle.register_module("external_services", external_services_module)
    lifecycle.register_module("context", context_module)
    lifecycle.register_module("knowledge_base", knowledge_base_module)
    lifecycle.register_module("tools", tool_module)
    lifecycle.register_module("reasoning", reasoning_module)
    lifecycle.register_module("planning", planning_module)
    lifecycle.register_module("orchestrator", orchestrator_module)
    lifecycle.register_module("application", application_module)

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
