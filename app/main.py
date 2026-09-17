import uuid
from core.config.settings import settings
from core.logging.logger import get_logger
from core.schemas.application import ApplicationRequest
from app.lifecycle import LifecycleManager
from app.workflow import WorkflowEngine

from modules.database.db_module import SQLiteDatabaseModule
from modules.ai.ai_module import AIModule
from modules.memory.memory_module import MemoryModule
from modules.inspector.inspector_module import InspectorModule
from modules.ulpu.ulpu_module import ULPUModule
from modules.vision.vision_module import VisionModule
from modules.drone.drone_module import DroneModule
from modules.data_training.data_training_module import DataTrainingModule
from modules.external_services.external_services_module import ExternalServicesModule
from modules.context.context_module import ContextModule

logger = get_logger("app.main")

def create_app():
    lifecycle = LifecycleManager()

    # Create module instances
    db_module = SQLiteDatabaseModule(db_path=settings.db_path)
    ai_module = AIModule(db_service=db_module.service)
    memory_module = MemoryModule(db_service=db_module.service)
    inspector_module = InspectorModule()
    ulpu_module = ULPUModule()
    vision_module = VisionModule()
    drone_module = DroneModule()
    data_training_module = DataTrainingModule()
    external_services_module = ExternalServicesModule()
    context_module = ContextModule()

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

    # Shutdown
    lifecycle.shutdown_all()
    logger.info("EarthMind application finished execution.")

if __name__ == "__main__":
    main()
