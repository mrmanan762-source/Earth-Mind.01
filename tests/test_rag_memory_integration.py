import time
import pytest
from typing import List
from core.errors.exceptions import BoundaryValidationError, ContextProviderError
from core.interfaces.boundary import IRAGContextProvider, IMemoryContextProvider
from modules.context.boundary.adapters import (
    RAGContextProviderAdapter,
    MemoryContextProviderAdapter,
)
from modules.context.boundary.enums import (
    KnowledgeClassification,
    ContextSourceType,
    ContextOwnership,
    ContextScope,
    PersistenceIntent,
)
from modules.context.boundary.models import (
    RAGContextContract,
    RAGContextRequest,
    MemoryContextContract,
    MemoryContextRequest,
)
from modules.context.boundary.validator import BoundaryValidator
from modules.context.manager import B2ContextManager
from modules.context.schemas import (
    ConflictStatus,
    ContextItem,
    ContextRequest,
    ContextResult,
    ContextState,
    PolicyConfig,
    PrivacyLevel,
)


class MockRAGProvider:
    """Mock implementation of IRAGContextProvider for tests."""
    provider_name = "mock_rag_service"

    def __init__(self, contracts: List[RAGContextContract] = None, should_fail: bool = False, delay: float = 0.0):
        self.contracts = contracts or []
        self.should_fail = should_fail
        self.delay = delay
        self.last_request = None

    def get_rag_context(self, request: RAGContextRequest) -> List[RAGContextContract]:
        self.last_request = request
        if self.delay > 0:
            time.sleep(self.delay)
        if self.should_fail:
            raise RuntimeError("RAG service connection database error")
        return self.contracts


class MockMemoryProvider:
    """Mock implementation of IMemoryContextProvider for tests."""
    provider_name = "mock_memory_service"

    def __init__(self, contracts: List[MemoryContextContract] = None, should_fail: bool = False, delay: float = 0.0):
        self.contracts = contracts or []
        self.should_fail = should_fail
        self.delay = delay
        self.last_request = None

    def get_memory_context(self, request: MemoryContextRequest) -> List[MemoryContextContract]:
        self.last_request = request
        if self.delay > 0:
            time.sleep(self.delay)
        if self.should_fail:
            raise RuntimeError("Memory service storage timeout error")
        return self.contracts


@pytest.fixture
def sample_rag_contract():
    return RAGContextContract(
        source_type=ContextSourceType.RAG,
        ownership=ContextOwnership.RAG_OWNED,
        classification=KnowledgeClassification.GENERAL_KNOWLEDGE,
        scope=ContextScope.GLOBAL,
        persistence_intent=PersistenceIntent.PERSISTENT,
        content={"title": "Nitrogen Application Guidance", "text": "Apply 50kg/ha nitrogen prior to tillering."},
        collection_id="agronomy_v1",
        document_id="doc_nitrogen_01",
        document_version_id="ver_2025",
        knowledge_unit_id="ku_nitrogen_50",
        chunk_id="chunk_9921",
        publication_state="PUBLISHED",
        provenance={"source_name": "AgRI_Research_Db", "author": "Dr. Agronomist"},
        trace_id="trace_rag_101",
    )


@pytest.fixture
def sample_memory_contract():
    return MemoryContextContract(
        memory_id="mem_farmer_soil_77",
        source_type=ContextSourceType.MEMORY,
        ownership=ContextOwnership.MEMORY_OWNED,
        classification=KnowledgeClassification.FIELD_KNOWLEDGE,
        scope=ContextScope.FIELD,
        persistence_intent=PersistenceIntent.PERSISTENT,
        content={"soil_type": "Clay Loam", "historical_ph": 6.8, "last_fertilizer": "100kg Urea"},
        farmer_id="farmer_001",
        farm_id="farm_north",
        field_id="field_block_a",
        crop_cycle_id="cycle_wheat_2025",
        provenance={"recorded_by": "mobile_app", "entry_method": "manual"},
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        is_pii=False,
        relevance_score=0.92,
        trace_id="trace_mem_202",
    )


# 1. B2 -> RAG request scenario
def test_b2_to_rag_request(sample_rag_contract):
    rag_mock = MockRAGProvider(contracts=[sample_rag_contract])
    rag_adapter = RAGContextProviderAdapter(rag_mock)
    manager = B2ContextManager(providers=[rag_adapter])

    request = ContextRequest(
        request_id="req_rag_1",
        task="Provide nitrogen recommendation for wheat",
        requested_context_types=["crop"],
        trace_id="trace_req_1",
    )

    result = manager.prepare_context(request)
    assert result.state == ContextState.COMPLETED
    assert rag_mock.last_request is not None
    assert isinstance(rag_mock.last_request, RAGContextRequest)
    assert rag_mock.last_request.request_id == "req_rag_1"
    assert rag_mock.last_request.query_text == "Provide nitrogen recommendation for wheat"
    assert rag_mock.last_request.classification == KnowledgeClassification.GENERAL_KNOWLEDGE


# 2. B2 -> Memory request scenario
def test_b2_to_memory_request(sample_memory_contract):
    mem_mock = MockMemoryProvider(contracts=[sample_memory_contract])
    mem_adapter = MemoryContextProviderAdapter(mem_mock)
    manager = B2ContextManager(providers=[mem_adapter])

    request = ContextRequest(
        request_id="req_mem_1",
        farmer_id="farmer_001",
        farm_id="farm_north",
        field_id="field_block_a",
        task="Check field history",
        trace_id="trace_req_2",
    )

    result = manager.prepare_context(request)
    assert result.state == ContextState.COMPLETED
    assert mem_mock.last_request is not None
    assert isinstance(mem_mock.last_request, MemoryContextRequest)
    assert mem_mock.last_request.farmer_id == "farmer_001"
    assert mem_mock.last_request.field_id == "field_block_a"
    assert mem_mock.last_request.scope == ContextScope.FIELD


# 3. RAG result contract
def test_rag_result_contract(sample_rag_contract):
    rag_mock = MockRAGProvider(contracts=[sample_rag_contract])
    rag_adapter = RAGContextProviderAdapter(rag_mock)

    req = ContextRequest(request_id="req_3", task="General query")
    items = rag_adapter.get_context(req)

    assert len(items) == 1
    item = items[0]
    assert item.source_type == ContextSourceType.RAG
    assert item.ownership == ContextOwnership.RAG_OWNED
    assert item.classification == KnowledgeClassification.GENERAL_KNOWLEDGE
    assert item.scope == ContextScope.GLOBAL
    assert item.privacy_level == PrivacyLevel.PUBLIC


# 4. Memory result contract
def test_memory_result_contract(sample_memory_contract):
    mem_mock = MockMemoryProvider(contracts=[sample_memory_contract])
    mem_adapter = MemoryContextProviderAdapter(mem_mock)

    req = ContextRequest(request_id="req_4", farmer_id="farmer_001", field_id="field_block_a")
    items = mem_adapter.get_context(req)

    assert len(items) == 1
    item = items[0]
    assert item.source_type == ContextSourceType.MEMORY
    assert item.ownership == ContextOwnership.MEMORY_OWNED
    assert item.classification == KnowledgeClassification.FIELD_KNOWLEDGE
    assert item.scope == ContextScope.FIELD
    assert item.privacy_level == PrivacyLevel.FARM_PRIVATE


# 5. Source identity preservation
def test_source_identity_preservation(sample_rag_contract, sample_memory_contract):
    rag_adapter = RAGContextProviderAdapter(MockRAGProvider([sample_rag_contract]))
    mem_adapter = MemoryContextProviderAdapter(MockMemoryProvider([sample_memory_contract]))
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])

    request = ContextRequest(request_id="req_identity", farmer_id="farmer_001", field_id="field_block_a")
    result = manager.prepare_context(request)

    sources = {item["source"] for item in result.structured_context["items"]}
    assert "RAG" in sources
    assert "MEMORY" in sources


# 6. Ownership preservation
def test_ownership_preservation(sample_rag_contract, sample_memory_contract):
    rag_adapter = RAGContextProviderAdapter(MockRAGProvider([sample_rag_contract]))
    mem_adapter = MemoryContextProviderAdapter(MockMemoryProvider([sample_memory_contract]))
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])

    request = ContextRequest(request_id="req_owner", farmer_id="farmer_001", field_id="field_block_a")
    result = manager.prepare_context(request)

    ownerships = {item["ownership"] for item in result.structured_context["items"]}
    assert "RAG_OWNED" in ownerships
    assert "MEMORY_OWNED" in ownerships


# 7. Classification preservation
def test_classification_preservation(sample_rag_contract, sample_memory_contract):
    rag_adapter = RAGContextProviderAdapter(MockRAGProvider([sample_rag_contract]))
    mem_adapter = MemoryContextProviderAdapter(MockMemoryProvider([sample_memory_contract]))
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])

    request = ContextRequest(request_id="req_class", farmer_id="farmer_001", field_id="field_block_a")
    result = manager.prepare_context(request)

    classifications = {item["classification"] for item in result.structured_context["items"]}
    assert "GENERAL_KNOWLEDGE" in classifications
    assert "FIELD_KNOWLEDGE" in classifications


# 8. Scope preservation
def test_scope_preservation(sample_rag_contract, sample_memory_contract):
    rag_adapter = RAGContextProviderAdapter(MockRAGProvider([sample_rag_contract]))
    mem_adapter = MemoryContextProviderAdapter(MockMemoryProvider([sample_memory_contract]))
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])

    request = ContextRequest(request_id="req_scope", farmer_id="farmer_001", field_id="field_block_a")
    result = manager.prepare_context(request)

    scopes = {item["scope"] for item in result.structured_context["items"]}
    assert "GLOBAL" in scopes
    assert "FIELD" in scopes


# 9. Provenance preservation
def test_provenance_preservation(sample_rag_contract, sample_memory_contract):
    rag_adapter = RAGContextProviderAdapter(MockRAGProvider([sample_rag_contract]))
    mem_adapter = MemoryContextProviderAdapter(MockMemoryProvider([sample_memory_contract]))
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])

    request = ContextRequest(request_id="req_prov", farmer_id="farmer_001", field_id="field_block_a")
    result = manager.prepare_context(request)

    for item in result.items:
        boundary_rec = item.to_boundary_record()
        assert boundary_rec.provenance is not None
        assert len(boundary_rec.provenance) > 0


# 10. Privacy metadata preservation
def test_privacy_metadata_preservation(sample_memory_contract):
    mem_adapter = MemoryContextProviderAdapter(MockMemoryProvider([sample_memory_contract]))
    manager = B2ContextManager(providers=[mem_adapter])

    request = ContextRequest(
        request_id="req_priv",
        farmer_id="farmer_001",
        field_id="field_block_a",
        policy=PolicyConfig(allow_pii=False),
    )
    result = manager.prepare_context(request)

    assert len(result.items) == 1
    assert result.items[0].privacy_level == PrivacyLevel.FARM_PRIVATE


# 11. RAG + Memory context merge
def test_rag_memory_context_merge(sample_rag_contract, sample_memory_contract):
    rag_adapter = RAGContextProviderAdapter(MockRAGProvider([sample_rag_contract]))
    mem_adapter = MemoryContextProviderAdapter(MockMemoryProvider([sample_memory_contract]))
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])

    request = ContextRequest(request_id="req_merge", farmer_id="farmer_001", field_id="field_block_a")
    result = manager.prepare_context(request)

    assert result.state == ContextState.COMPLETED
    assert len(result.items) == 2

    sources = [item.source_type for item in result.items]
    assert ContextSourceType.RAG in sources
    assert ContextSourceType.MEMORY in sources


# 12. Deduplication with different provenance
def test_deduplication_different_provenance(sample_rag_contract, sample_memory_contract):
    # Two items with same text content but different sources/provenance
    content_text = "Apply 50kg/ha nitrogen."

    rag_contract = sample_rag_contract.model_copy()
    rag_contract.content = content_text

    mem_contract = sample_memory_contract.model_copy()
    mem_contract.content = content_text

    rag_adapter = RAGContextProviderAdapter(MockRAGProvider([rag_contract]))
    mem_adapter = MemoryContextProviderAdapter(MockMemoryProvider([mem_contract]))
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])

    request = ContextRequest(request_id="req_dedup_prov", farmer_id="farmer_001", field_id="field_block_a")
    result = manager.prepare_context(request)

    # Must NOT deduplicate away items from different sources/provenance
    assert len(result.items) == 2


# 13. Conflict preservation
def test_conflict_preservation(sample_rag_contract, sample_memory_contract):
    # Conflicting recommendations for same entity/property/time
    rag_contract = sample_rag_contract.model_copy()
    rag_contract.content = "Recommended pH is 7.5"

    mem_contract = sample_memory_contract.model_copy()
    mem_contract.content = "Recommended pH is 6.2"

    rag_adapter = RAGContextProviderAdapter(MockRAGProvider([rag_contract]))
    mem_adapter = MemoryContextProviderAdapter(MockMemoryProvider([mem_contract]))

    # Adjust items to have matching entity_type, entity_id, data_type to trigger conflict detector
    items = []
    for item in rag_adapter.get_context(ContextRequest(request_id="r1")):
        item.entity_type = "soil"
        item.entity_id = "field_block_a"
        item.data_type = "ph_recommendation"
        items.append(item)

    for item in mem_adapter.get_context(ContextRequest(request_id="r2", farmer_id="farmer_001")):
        item.entity_type = "soil"
        item.entity_id = "field_block_a"
        item.data_type = "ph_recommendation"
        items.append(item)

    class FixedItemProvider:
        provider_name = "fixed_provider"
        def __init__(self, items): self.items = items
        def get_context(self, req): return self.items

    manager = B2ContextManager(providers=[FixedItemProvider(items)])
    result = manager.prepare_context(ContextRequest(request_id="req_conf"))

    # Both items must be preserved and marked as CONFLICTED
    assert len(result.items) == 2
    assert result.items[0].conflict_status == ConflictStatus.CONFLICTED
    assert result.items[1].conflict_status == ConflictStatus.CONFLICTED
    assert result.structured_context["conflicts_present"] is True


# 14. RAG failure with Memory success
def test_rag_failure_memory_success(sample_memory_contract):
    rag_adapter = RAGContextProviderAdapter(MockRAGProvider(should_fail=True))
    mem_adapter = MemoryContextProviderAdapter(MockMemoryProvider([sample_memory_contract]))
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])

    request = ContextRequest(
        request_id="req_rag_fail",
        farmer_id="farmer_001",
        field_id="field_block_a",
        policy=PolicyConfig(allow_partial=True),
    )

    result = manager.prepare_context(request)
    assert result.state == ContextState.PARTIAL
    assert len(result.items) == 1
    assert result.items[0].source_type == ContextSourceType.MEMORY
    assert any("mock_rag_service" in err for err in result.errors)


# 15. Memory failure with RAG success
def test_memory_failure_rag_success(sample_rag_contract):
    rag_adapter = RAGContextProviderAdapter(MockRAGProvider([sample_rag_contract]))
    mem_adapter = MemoryContextProviderAdapter(MockMemoryProvider(should_fail=True))
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])

    request = ContextRequest(
        request_id="req_mem_fail",
        farmer_id="farmer_001",
        field_id="field_block_a",
        policy=PolicyConfig(allow_partial=True),
    )

    result = manager.prepare_context(request)
    assert result.state == ContextState.PARTIAL
    assert len(result.items) == 1
    assert result.items[0].source_type == ContextSourceType.RAG
    assert any("mock_memory_service" in err for err in result.errors)


# 16. Timeout handling
def test_timeout_handling(sample_rag_contract):
    slow_rag_adapter = RAGContextProviderAdapter(MockRAGProvider([sample_rag_contract], delay=0.5))
    manager = B2ContextManager(providers=[slow_rag_adapter])

    request = ContextRequest(
        request_id="req_timeout",
        policy=PolicyConfig(timeout_seconds=0.1, allow_partial=True),
    )

    result = manager.prepare_context(request)
    assert result.state == ContextState.PARTIAL
    assert len(result.items) == 0
    assert any("timed out" in err for err in result.errors)


# 17. Partial context handling
def test_partial_context_handling(sample_memory_contract):
    bad_rag = RAGContextProviderAdapter(MockRAGProvider(should_fail=True))
    good_mem = MemoryContextProviderAdapter(MockMemoryProvider([sample_memory_contract]))
    manager = B2ContextManager(providers=[bad_rag, good_mem])

    request = ContextRequest(
        request_id="req_part",
        farmer_id="farmer_001",
        field_id="field_block_a",
        policy=PolicyConfig(allow_partial=True),
    )

    result = manager.prepare_context(request)
    assert result.state == ContextState.PARTIAL
    assert len(result.items) == 1


# 18. Interface isolation (no direct RAG/Memory dependency)
def test_interface_isolation(sample_rag_contract, sample_memory_contract):
    rag_mock = MockRAGProvider([sample_rag_contract])
    mem_mock = MockMemoryProvider([sample_memory_contract])

    rag_adapter = RAGContextProviderAdapter(rag_mock)
    mem_adapter = MemoryContextProviderAdapter(mem_mock)

    # Verify RAG provider receives RAGContextRequest, Memory receives MemoryContextRequest
    rag_adapter.get_context(ContextRequest(request_id="r1"))
    mem_adapter.get_context(ContextRequest(request_id="r2", farmer_id="f1"))

    assert isinstance(rag_mock.last_request, RAGContextRequest)
    assert isinstance(mem_mock.last_request, MemoryContextRequest)


# 19. No Qdrant/SQLite leakage in boundary adapter contracts
def test_no_database_or_index_leakage(sample_rag_contract, sample_memory_contract):
    rag_adapter = RAGContextProviderAdapter(MockRAGProvider([sample_rag_contract]))
    mem_adapter = MemoryContextProviderAdapter(MockMemoryProvider([sample_memory_contract]))

    rag_items = rag_adapter.get_context(ContextRequest(request_id="r1"))
    mem_items = mem_adapter.get_context(ContextRequest(request_id="r2", farmer_id="f1"))

    for item in rag_items + mem_items:
        dump = item.model_dump()
        dump_str = str(dump).lower()
        assert "qdrant" not in dump_str
        assert "sqlite" not in dump_str


# 20. Five-principle compliance check
def test_five_earthmind_principles_compliance(sample_rag_contract, sample_memory_contract):
    # 1. Extensibility: New adapter types can be plugged into B2 without changing manager code
    # 2. Loose Coupling: Communication via RAGContextContract / MemoryContextContract
    # 3. Single Responsibility: B2 collects/organizes, RAG retrieves knowledge, Memory retrieves history
    # 4. Controlled Dependencies: Adapters implement approved protocols
    # 5. Replaceability: Mock RAG and Mock Memory can replace actual implementations transparently

    rag_adapter = RAGContextProviderAdapter(MockRAGProvider([sample_rag_contract]))
    mem_adapter = MemoryContextProviderAdapter(MockMemoryProvider([sample_memory_contract]))
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])

    request = ContextRequest(
        request_id="req_5p",
        farmer_id="farmer_001",
        field_id="field_block_a",
    )
    result = manager.prepare_context(request)

    assert result.state == ContextState.COMPLETED
    assert len(result.items) == 2
    assert result.structured_context["conflicts_present"] is False
