from modules.ai.ai_module import AIModule
from modules.memory.memory_module import MemoryModule
from modules.inspector.inspector_module import InspectorModule
from modules.ulpu.ulpu_module import ULPUModule
from modules.vision.vision_module import VisionModule
from modules.drone.drone_module import DroneModule
from modules.data_training.data_training_module import DataTrainingModule
from modules.external_services.external_services_module import ExternalServicesModule
from core.schemas.application import ApplicationRequest

def test_all_modules_initialization_and_handling():
    modules = [
        AIModule(),
        MemoryModule(),
        InspectorModule(),
        ULPUModule(),
        VisionModule(),
        DroneModule(),
        DataTrainingModule(),
        ExternalServicesModule()
    ]

    for m in modules:
        m.initialize()
        req = ApplicationRequest(
            request_id="mod-test",
            source="test",
            operation="test_op",
            payload={}
        )
        resp = m.handle(req)
        assert resp.request_id == "mod-test"
        assert resp.status in ["SUCCESS", "UNKNOWN_OPERATION"]
        m.shutdown()

def test_memory_module_store_retrieve():
    mem = MemoryModule()
    mem.initialize()

    req_store = ApplicationRequest(
        request_id="mem-1",
        source="test",
        operation="store",
        payload={"key": "soil_ph", "value": "6.5"}
    )
    resp_store = mem.handle(req_store)
    assert resp_store.status == "SUCCESS"

    req_get = ApplicationRequest(
        request_id="mem-2",
        source="test",
        operation="retrieve",
        payload={"key": "soil_ph"}
    )
    resp_get = mem.handle(req_get)
    assert resp_get.status == "SUCCESS"
    assert resp_get.response["value"] == "6.5"

    mem.shutdown()
