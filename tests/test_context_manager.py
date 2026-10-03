import pytest
from typing import List, Optional
from core.config.settings import ContextConfig
from core.errors.exceptions import (
    ContextConfigurationError,
    ContextOutputValidationError,
    ContextTimeoutError,
    InsufficientContextError,
    InvalidContextRequestError,
    UnsupportedContextTypeError,
)
from core.schemas.application import ApplicationRequest
from app.lifecycle import LifecycleManager
from app.workflow import WorkflowEngine
from modules.context.context_module import ContextModule
from modules.context.interfaces import CacheProvider, CompressionProvider, ContextProvider
from modules.context.manager import B2ContextManager
from modules.context.providers import (
    DictContextProvider,
    InMemoryCacheProvider,
    SimpleCompressionProvider,
)
from modules.context.schemas import (
    ConflictStatus,
    ContextItem,
    ContextRequest,
    ContextResult,
    ContextState,
    PolicyConfig,
    PriorityLevel,
    PrivacyLevel,
)
from modules.context.boundary.models import RAGContextContract, MemoryContextContract
from modules.context.boundary.enums import (
    KnowledgeClassification,
    ContextSourceType,
    ContextOwnership,
    ContextScope,
    PersistenceIntent,
)
from modules.context.validator import ItemValidator, OutputValidator


# Mock Providers for Testing
class DummyProvider:
    def __init__(self, name: str, items: List[ContextItem], should_fail: bool = False):
        self.provider_name = name
        self.items = items
        self.should_fail = should_fail

    def get_context(self, request: ContextRequest) -> List[ContextItem]:
        if self.should_fail:
            raise RuntimeError(f"Provider '{self.provider_name}' artificial failure")
        return self.items


class DummyCache:
    def __init__(self, cached_result: Optional[ContextResult] = None):
        self.cached_result = cached_result
        self.set_called = False

    def get(self, request: ContextRequest) -> Optional[ContextResult]:
        return self.cached_result

    def set(self, request: ContextRequest, result: ContextResult) -> bool:
        self.set_called = True
        return True


class DummyCompressor:
    def compress(self, items: List[ContextItem], target_tokens: int) -> List[ContextItem]:
        for item in items:
            item.token_count = max(1, item.token_count // 2)
            item.is_compressed = True
        return items


@pytest.fixture
def sample_item():
    return ContextItem(
        context_id="item_1",
        entity_type="field",
        entity_id="field_101",
        data_type="soil_moisture",
        content={"moisture_percent": 24.5},
        farmer_id="farmer_1",
        farm_id="farm_1",
        field_id="field_101",
        event_time="2025-05-10T10:00:00Z",
        source="soil_sensor_network",
        confidence=0.95,
        token_count=20,
    )


# 1. Item Validation Tests
def test_item_validator(sample_item):
    valid, err = ItemValidator.validate_item(sample_item)
    assert valid is True
    assert err is None

    invalid_item = sample_item.model_copy()
    invalid_item.context_id = ""
    valid, err = ItemValidator.validate_item(invalid_item)
    assert valid is False
    assert "missing context_id" in err


# 2. Scope Isolation Test
def test_scope_isolation(sample_item):
    item_other_farmer = sample_item.model_copy()
    item_other_farmer.context_id = "item_2"
    item_other_farmer.farmer_id = "farmer_2"

    provider = DummyProvider("sensor", [sample_item, item_other_farmer])
    manager = B2ContextManager(providers=[provider])

    request = ContextRequest(
        request_id="req_1",
        farmer_id="farmer_1",
        farm_id="farm_1",
        requested_context_types=["field"],
    )

    result = manager.prepare_context(request)
    assert result.state == ContextState.COMPLETED
    assert len(result.items) == 1
    assert result.items[0].farmer_id == "farmer_1"


# 3. Privacy Filter Test
def test_privacy_filter(sample_item):
    pii_item = sample_item.model_copy()
    pii_item.context_id = "item_pii"
    pii_item.privacy_level = PrivacyLevel.FARMER_PII
    pii_item.is_pii = True

    provider = DummyProvider("source", [sample_item, pii_item])
    manager = B2ContextManager(providers=[provider])

    # Case A: PII disallowed by default
    request_no_pii = ContextRequest(
        request_id="req_no_pii",
        farmer_id="farmer_1",
        policy=PolicyConfig(allow_pii=False),
    )
    res_no_pii = manager.prepare_context(request_no_pii)
    assert len(res_no_pii.items) == 1
    assert res_no_pii.items[0].context_id == "item_1"

    # Case B: PII explicitly allowed
    request_allow_pii = ContextRequest(
        request_id="req_allow_pii",
        farmer_id="farmer_1",
        policy=PolicyConfig(allow_pii=True),
    )
    res_allow_pii = manager.prepare_context(request_allow_pii)
    assert len(res_allow_pii.items) == 2


# 4. Temporal Filter Test
def test_time_filter(sample_item):
    old_item = sample_item.model_copy()
    old_item.context_id = "item_old"
    old_item.event_time = "2024-01-01T00:00:00Z"

    provider = DummyProvider("source", [sample_item, old_item])
    manager = B2ContextManager(providers=[provider])

    request = ContextRequest(
        request_id="req_time",
        farmer_id="farmer_1",
        time_range={"start_time": "2025-01-01T00:00:00Z", "end_time": "2025-12-31T23:59:59Z"},
    )

    result = manager.prepare_context(request)
    assert len(result.items) == 1
    assert result.items[0].context_id == "item_1"


# 5. Cache Hit Test
def test_cache_hit(sample_item):
    cached_res = ContextResult(
        request_id="req_cached",
        state=ContextState.COMPLETED,
        items=[sample_item],
        total_tokens=20,
    )
    cache = DummyCache(cached_result=cached_res)
    manager = B2ContextManager(cache_provider=cache)

    request = ContextRequest(request_id="req_cached", farmer_id="farmer_1")
    result = manager.prepare_context(request)
    assert result == cached_res


# 6. Provider Failure & Isolation Test
def test_provider_failure_isolation(sample_item):
    good_provider = DummyProvider("good", [sample_item])
    bad_provider = DummyProvider("bad", [], should_fail=True)

    # Allow partial results
    manager = B2ContextManager(providers=[good_provider, bad_provider])
    request = ContextRequest(
        request_id="req_partial",
        farmer_id="farmer_1",
        policy=PolicyConfig(allow_partial=True),
    )

    result = manager.prepare_context(request)
    assert result.state == ContextState.PARTIAL
    assert len(result.items) == 1
    assert len(result.errors) == 1


# 7. Deduplication Test
def test_deduplication(sample_item):
    duplicate_item = sample_item.model_copy()

    provider = DummyProvider("source", [sample_item, duplicate_item])
    manager = B2ContextManager(providers=[provider])

    request = ContextRequest(request_id="req_dedup", farmer_id="farmer_1")
    result = manager.prepare_context(request)
    assert len(result.items) == 1


# 8. Relevance Threshold and Mandatory Overrides
def test_relevance_and_mandatory(sample_item):
    low_rel_item = sample_item.model_copy()
    low_rel_item.context_id = "item_low"
    low_rel_item.entity_type = "historical_note"
    low_rel_item.content = "unrelated historic fact"

    mandatory_item = sample_item.model_copy()
    mandatory_item.context_id = "item_mandatory"
    mandatory_item.entity_type = "historical_note"
    mandatory_item.content = "unrelated historic fact"

    provider = DummyProvider("source", [low_rel_item, mandatory_item])
    manager = B2ContextManager(providers=[provider])

    request = ContextRequest(
        request_id="req_rel",
        farmer_id="farmer_1",
        requested_context_types=["field"],
        relevance_threshold=0.8,
        policy=PolicyConfig(mandatory_item_ids=["item_mandatory"]),
    )

    result = manager.prepare_context(request)
    # low_rel_item excluded because score < 0.8; mandatory_item included despite score < 0.8
    assert len(result.items) == 1
    assert result.items[0].context_id == "item_mandatory"


# 9. Conflict Detection Test
def test_conflict_detection(sample_item):
    conflicting_item = sample_item.model_copy()
    conflicting_item.context_id = "item_2"
    conflicting_item.source = "drone_infrared"
    conflicting_item.content = {"moisture_percent": 85.0}  # Different value for same time & entity

    provider = DummyProvider("source", [sample_item, conflicting_item])
    manager = B2ContextManager(providers=[provider])

    request = ContextRequest(request_id="req_conflict", farmer_id="farmer_1")
    result = manager.prepare_context(request)

    assert len(result.items) == 2
    assert result.items[0].conflict_status == ConflictStatus.CONFLICTED
    assert result.items[1].conflict_status == ConflictStatus.CONFLICTED
    assert result.structured_context["conflicts_present"] is True


# 10. Organization and Deterministic Sorting Test
def test_organization_and_sorting(sample_item):
    item_low = sample_item.model_copy()
    item_low.context_id = "item_low"
    item_low.entity_type = "unrelated"
    item_low.relevance_score = 0.2

    item_high = sample_item.model_copy()
    item_high.context_id = "item_high"
    item_high.entity_type = "field"
    item_high.relevance_score = 0.9

    provider = DummyProvider("source", [item_low, item_high])
    manager = B2ContextManager(providers=[provider])

    request = ContextRequest(
        request_id="req_sort",
        farmer_id="farmer_1",
        requested_context_types=["field"],
        relevance_threshold=0.0,
    )
    result = manager.prepare_context(request)

    assert len(result.items) == 2
    assert result.items[0].context_id == "item_high"  # High priority comes first
    assert result.items[1].context_id == "item_low"


# 11. Token Budget and Reduction Steps Test
def test_token_limit_and_compression(sample_item):
    item_1 = sample_item.model_copy()
    item_1.context_id = "item_1"
    item_1.entity_type = "field"
    item_1.token_count = 1000

    item_2 = sample_item.model_copy()
    item_2.context_id = "item_2"
    item_2.entity_type = "unrelated"
    item_2.token_count = 1000

    provider = DummyProvider("source", [item_1, item_2])
    compressor = DummyCompressor()
    manager = B2ContextManager(providers=[provider], compression_provider=compressor)

    # Budget is 1500 tokens (item_1 + item_2 = 2000)
    request = ContextRequest(
        request_id="req_budget",
        farmer_id="farmer_1",
        requested_context_types=["field"],
        token_limit=1500,
        relevance_threshold=0.2,
    )
    result = manager.prepare_context(request)

    # item_2 is dropped during reduction step because entity_type="unrelated" (score < threshold)
    assert len(result.items) == 1
    assert result.items[0].context_id == "item_1"
    assert result.total_tokens == 1000


def test_insufficient_context_error(sample_item):
    mandatory_item = sample_item.model_copy()
    mandatory_item.context_id = "mandatory_1"
    mandatory_item.token_count = 5000

    provider = DummyProvider("source", [mandatory_item])
    manager = B2ContextManager(providers=[provider])

    request = ContextRequest(
        request_id="req_over_budget",
        farmer_id="farmer_1",
        token_limit=1000,
        policy=PolicyConfig(mandatory_item_ids=["mandatory_1"]),
    )

    result = manager.prepare_context(request)
    assert result.state == ContextState.INSUFFICIENT_CONTEXT
    assert len(result.errors) == 1


# 12. Context Module Workflow Dispatch Integration
def test_workflow_dispatch_context_module(sample_item):
    provider = DummyProvider("sensor", [sample_item])
    b2_manager = B2ContextManager(providers=[provider])
    context_module = ContextModule(manager=b2_manager)

    lifecycle = LifecycleManager()
    lifecycle.register_module("context", context_module)
    lifecycle.initialize_all()

    workflow = WorkflowEngine(lifecycle)

    app_req = ApplicationRequest(
        request_id="req_app_1",
        source="user",
        actor="farmer_1",
        operation="prepare_context",
        payload={
            "farmer_id": "farmer_1",
            "task": "Check soil moisture for field 101",
            "requested_context_types": ["field"],
        },
        metadata={"target_module": "context"},
    )

    response = workflow.dispatch(app_req)
    assert response.status == "COMPLETED"
    assert response.response is not None
    assert response.response["scope"]["farmer_id"] == "farmer_1"
    assert len(response.response["items"]) == 1

    lifecycle.shutdown_all()


# 13. Observability Metrics Verification
def test_observability_metrics(sample_item):
    item_2 = sample_item.model_copy()
    item_2.context_id = "item_2"
    item_2.farmer_id = "farmer_2"  # filtered out by scope

    provider = DictContextProvider("test_dict_provider", [sample_item, item_2])
    manager = B2ContextManager(providers=[provider])

    request = ContextRequest(
        request_id="req_obs",
        farmer_id="farmer_1",
    )

    result = manager.prepare_context(request)
    assert "metadata" in result.model_dump()
    meta = result.metadata
    assert meta["b2_version"] == "1.0.0"
    assert meta["context_version"] == "1.0.0"
    assert meta["items_received"] == 2
    assert meta["items_retained"] == 1
    assert meta["items_filtered"] == 1
    assert meta["items_dropped_budget"] == 0
    assert meta["execution_latency_ms"] >= 0.0
    assert "test_dict_provider" in meta["provider_statuses"]
    assert meta["provider_statuses"]["test_dict_provider"] == "SUCCESS"


# 14. Configuration Integration Test
def test_context_config_integration(sample_item):
    custom_config = ContextConfig(
        default_token_limit=2048,
        default_relevance_threshold=0.6,
        b2_version="2.0.0-test",
    )
    provider = DictContextProvider("test_provider", [sample_item])
    manager = B2ContextManager(providers=[provider], config=custom_config)

    request = ContextRequest(
        request_id="req_cfg",
        farmer_id="farmer_1",
        token_limit=4096,
    )

    result = manager.prepare_context(request)
    assert result.metadata["b2_version"] == "2.0.0-test"


# 15. Reusable Provider Implementations Test
def test_reusable_providers(sample_item):
    cache = InMemoryCacheProvider()
    comp = SimpleCompressionProvider()
    dict_prov = DictContextProvider("static_src", [sample_item])

    manager = B2ContextManager(
        providers=[dict_prov],
        cache_provider=cache,
        compression_provider=comp,
    )

    request = ContextRequest(request_id="req_reusable", farmer_id="farmer_1")
    res1 = manager.prepare_context(request)
    assert len(res1.items) == 1

    # Second call should hit cache
    res2 = manager.prepare_context(request)
    assert res2 == res1


# 16. ULPU Metadata Preservation Test
def test_ulpu_metadata_preservation(sample_item):
    ulpu_item = sample_item.model_copy()
    ulpu_item.context_id = "ulpu_1"
    ulpu_item.metadata = {
        "ulpu_detected_language": "hi",
        "ulpu_canonical_query": "What is the soil moisture requirement for wheat?",
        "ulpu_source_language": "hi",
    }

    provider = DictContextProvider("ulpu_source", [ulpu_item])
    manager = B2ContextManager(providers=[provider])

    request = ContextRequest(request_id="req_ulpu", farmer_id="farmer_1")
    result = manager.prepare_context(request)

    assert len(result.items) == 1
    assert result.items[0].metadata["ulpu_detected_language"] == "hi"
    assert result.items[0].metadata["ulpu_canonical_query"] == "What is the soil moisture requirement for wheat?"


# 17. Non-Reasoning Boundary Assurance Test
def test_non_reasoning_boundary_guarantees(sample_item):
    # Verify B2 organizes raw diagnostic observations without producing diagnoses or recommendations
    symptom_item = ContextItem(
        context_id="symp_1",
        entity_type="crop_symptom",
        entity_id="field_101",
        data_type="observation",
        content="Yellow spots on leaves and mild leaf curling observed on paddy crop.",
        farmer_id="farmer_1",
        source="field_extension_agent",
    )

    provider = DictContextProvider("obs_source", [symptom_item])
    manager = B2ContextManager(providers=[provider])

    request = ContextRequest(request_id="req_no_reasoning", farmer_id="farmer_1")
    result = manager.prepare_context(request)

    assert result.state == ContextState.COMPLETED
    # Output content must strictly reflect the input observation content without inferred diagnosis
    assert result.items[0].content == "Yellow spots on leaves and mild leaf curling observed on paddy crop."
    # Output structured context must contain items without generated treatments or decisions
    assert "treatment" not in result.structured_context
    assert "diagnosis" not in result.structured_context


# 18. Structured Exception Tests
def test_structured_exceptions():
    err_cfg = ContextConfigurationError("Invalid token limit setting")
    assert err_cfg.error_contract.error_code == "CONTEXT_CONFIGURATION_ERROR"

    err_timeout = ContextTimeoutError("req_999", 5.0)
    assert err_timeout.error_contract.error_code == "CONTEXT_TIMEOUT"

    err_type = UnsupportedContextTypeError("unknown_type")
    assert err_type.error_contract.error_code == "UNSUPPORTED_CONTEXT_TYPE"


# 19. Mocked RAG and Memory Boundary Contracts Test
def test_rag_and_memory_boundary_contracts():
    rag_contract = RAGContextContract(
        knowledge_unit_id="ku_100",
        chunk_id="chunk_100",
        document_id="doc_100",
        content="PMKSY guidelines for micro-irrigation subsidies in arid zones.",
        source_type=ContextSourceType.RAG,
        ownership=ContextOwnership.RAG_OWNED,
        classification=KnowledgeClassification.GENERAL_KNOWLEDGE,
        scope=ContextScope.GLOBAL,
        persistence_intent=PersistenceIntent.PERSISTENT,
        relevance_score=0.88,
    )

    mem_contract = MemoryContextContract(
        memory_id="mem_200",
        farmer_id="farmer_1",
        content="Farmer prefers drip irrigation for cotton crop.",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        is_pii=False,
        relevance_score=0.92,
        source_type=ContextSourceType.MEMORY,
        ownership=ContextOwnership.MEMORY_OWNED,
        classification=KnowledgeClassification.FARMER_KNOWLEDGE,
        scope=ContextScope.FARMER,
        persistence_intent=PersistenceIntent.PERSISTENT,
    )

    item_rag = ContextItem.from_rag_contract(rag_contract)
    item_mem = ContextItem.from_memory_contract(mem_contract)

    assert item_rag.context_id.startswith("rag_")
    assert item_rag.ownership == ContextOwnership.RAG_OWNED
    assert item_mem.context_id == "mem_mem_200"
    assert item_mem.farmer_id == "farmer_1"

    provider = DictContextProvider("boundary_source", [item_rag, item_mem])
    manager = B2ContextManager(providers=[provider])

    request = ContextRequest(request_id="req_boundary", farmer_id="farmer_1")
    result = manager.prepare_context(request)

    assert len(result.items) == 2
