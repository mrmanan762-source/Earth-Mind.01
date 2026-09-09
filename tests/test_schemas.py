from datetime import datetime
from core.schemas.application import ApplicationRequest, ApplicationResponse
from core.schemas.contracts import ErrorContract

def test_application_request_creation():
    req = ApplicationRequest(
        request_id="req-101",
        source="test_source",
        operation="test_op",
        payload={"data": 123}
    )
    assert req.request_id == "req-101"
    assert req.source == "test_source"
    assert req.operation == "test_op"
    assert req.payload == {"data": 123}
    assert isinstance(req.timestamp, datetime)

def test_application_response_creation():
    res = ApplicationResponse(
        request_id="req-101",
        status="SUCCESS",
        response={"result": "ok"}
    )
    assert res.request_id == "req-101"
    assert res.status == "SUCCESS"
    assert res.response == {"result": "ok"}
    assert res.warnings == []

def test_error_contract_creation():
    err = ErrorContract(
        error_code="ERR_01",
        message="Test error",
        module="test_module",
        operation="test_op"
    )
    assert err.error_code == "ERR_01"
    assert err.retryable is False
