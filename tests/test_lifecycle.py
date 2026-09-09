import pytest
from app.lifecycle import LifecycleManager
from core.schemas.application import ApplicationRequest, ApplicationResponse
from core.errors.exceptions import ModuleNotFoundError

class DummyModule:
    module_name = "dummy"
    def __init__(self):
        self.initialized = False
        self.shutdown_called = False

    def initialize(self):
        self.initialized = True

    def handle(self, request: ApplicationRequest) -> ApplicationResponse:
        return ApplicationResponse(request_id=request.request_id, status="SUCCESS")

    def shutdown(self):
        self.shutdown_called = True

def test_lifecycle_manager():
    lifecycle = LifecycleManager()
    dummy = DummyModule()

    lifecycle.register_module("dummy", dummy)
    assert lifecycle.get_module("dummy") == dummy

    lifecycle.initialize_all()
    assert dummy.initialized is True
    assert lifecycle.is_running is True

    lifecycle.shutdown_all()
    assert dummy.shutdown_called is True
    assert lifecycle.is_running is False

def test_module_not_found():
    lifecycle = LifecycleManager()
    with pytest.raises(ModuleNotFoundError):
        lifecycle.get_module("nonexistent")
