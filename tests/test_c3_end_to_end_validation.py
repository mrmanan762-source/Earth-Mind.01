import pytest
import sys
import importlib
from typing import List

from core.errors.exceptions import (
    BoundaryValidationError,
    PromotionNotAllowedError,
    ScopeViolationBoundaryError,
    PrivacyBoundaryError,
)
from modules.context.boundary import (
    IRAGContextProvider,
    IMemoryContextProvider,
    IBoundaryValidator,
    IPromotionGovernanceEngine,
    KnowledgeClassification,
    ContextSourceType,
    ContextOwnership,
    ContextScope,
    PersistenceIntent,
    TransitionType,
    GovernanceOutcome,
    GovernanceState,
    GovernanceFailureReason,
    ContextSourceRecord,
    RAGContextContract,
    RAGContextRequest,
    MemoryContextContract,
    MemoryContextRequest,
    PromotionCandidate,
    GovernanceDecision,
    PromotionRecord,
    BoundaryValidator,
    RAGContextProviderAdapter,
    MemoryContextProviderAdapter,
    ContextGovernanceEngine,
)
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


# Mock Providers for End-to-End Validation
class E2EMockRAGProvider(IRAGContextProvider):
    provider_name = "e2e_rag_service"

    def __init__(self, contracts: List[RAGContextContract] = None, should_fail: bool = False):
        self.contracts = contracts or []
        self.should_fail = should_fail
        self.last_request = None

    def get_rag_context(self, request: RAGContextRequest) -> List[RAGContextContract]:
        self.last_request = request
        if self.should_fail:
            raise RuntimeError("RAG index service unreachable")
        return self.contracts


class E2EMockMemoryProvider(IMemoryContextProvider):
    provider_name = "e2e_memory_service"

    def __init__(self, contracts: List[MemoryContextContract] = None, should_fail: bool = False):
        self.contracts = contracts or []
        self.should_fail = should_fail
        self.last_request = None

    def get_memory_context(self, request: MemoryContextRequest) -> List[MemoryContextContract]:
        self.last_request = request
        if self.should_fail:
            raise RuntimeError("Memory store timeout")
        return self.contracts


# 1. C.3.1 Contract Compatibility
def test_c3_1_contract_compatibility():
    validator = BoundaryValidator()
    rag_contract = RAGContextContract(
        content="General soil pH management guidelines.",
        document_id="doc_ph_01",
        collection_id="agronomy",
        publication_state="PUBLISHED",
        provenance={"source": "ICAR Handbook 2024"},
    )
    validator.validate_rag_contract(rag_contract)
    rec = rag_contract.to_source_record()
    assert rec.source_type == ContextSourceType.RAG
    assert rec.ownership == ContextOwnership.RAG_OWNED
    assert rec.classification == KnowledgeClassification.GENERAL_KNOWLEDGE


# 2. C.3.2 Routing Compatibility
def test_c3_2_routing_compatibility():
    rag_contract = RAGContextContract(
        content="Wheat irrigation schedule",
        provenance={"source": "PAU Guide"},
    )
    rag_adapter = RAGContextProviderAdapter(E2EMockRAGProvider([rag_contract]))
    manager = B2ContextManager(providers=[rag_adapter])

    req = ContextRequest(request_id="r1", task="Wheat irrigation advice")
    res = manager.prepare_context(req)
    assert res.state == ContextState.COMPLETED
    assert len(res.items) == 1
    assert res.items[0].source_type == ContextSourceType.RAG


# 3. C.3.3 Governance Compatibility
def test_c3_3_governance_compatibility():
    engine = ContextGovernanceEngine(policy_name="E2E_POLICY")
    rag_contract = RAGContextContract(
        content="Paired row planting in sugarcane",
        provenance={"source": "IISR Guide"},
    )
    candidate = PromotionCandidate.from_rag_contract(
        rag_contract=rag_contract,
        farmer_id="f_100",
    )
    decision = engine.evaluate_candidate(candidate)
    assert decision.outcome == GovernanceOutcome.AUTO_ALLOWED
    assert decision.state == GovernanceState.AUTO_ALLOWED


# 4. RAG + Memory Context Merge
def test_rag_and_memory_context_merge():
    rag_c = RAGContextContract(
        content="Recommended fertilizer NPK 120:60:60",
        provenance={"source": "Fertilizer Manual"},
    )
    mem_c = MemoryContextContract(
        memory_id="m_10",
        content={"soil_nitrogen": "Medium"},
        farmer_id="f_55",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"source": "soil_lab"},
    )
    rag_adapter = RAGContextProviderAdapter(E2EMockRAGProvider([rag_c]))
    mem_adapter = MemoryContextProviderAdapter(E2EMockMemoryProvider([mem_c]))
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])

    res = manager.prepare_context(ContextRequest(request_id="r_merge", farmer_id="f_55"))
    assert res.state == ContextState.COMPLETED
    assert len(res.items) == 2
    sources = {item.source_type for item in res.items}
    assert ContextSourceType.RAG in sources
    assert ContextSourceType.MEMORY in sources


# 5. Provenance Preservation across Boundary
def test_provenance_preservation_across_boundary():
    original_prov = {"doc_id": "d_100", "author": "Agronomist X"}
    rag_c = RAGContextContract(content="Crop rotation facts", provenance=original_prov)
    rag_adapter = RAGContextProviderAdapter(E2EMockRAGProvider([rag_c]))
    manager = B2ContextManager(providers=[rag_adapter])

    res = manager.prepare_context(ContextRequest(request_id="r_prov"))
    item = res.items[0]
    boundary_rec = item.to_boundary_record()
    assert boundary_rec.provenance["doc_id"] == "d_100"


# 6. Ownership Preservation
def test_ownership_preservation():
    rag_c = RAGContextContract(content="General weed control", provenance={"s": "PAU"})
    mem_c = MemoryContextContract(
        memory_id="m_2",
        content={"herbicide_used": "2,4-D"},
        farmer_id="f_1",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"s": "farmer_chat"},
    )
    rag_adapter = RAGContextProviderAdapter(E2EMockRAGProvider([rag_c]))
    mem_adapter = MemoryContextProviderAdapter(E2EMockMemoryProvider([mem_c]))
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])

    res = manager.prepare_context(ContextRequest(request_id="r_own", farmer_id="f_1"))
    owners = {item.ownership for item in res.items}
    assert ContextOwnership.RAG_OWNED in owners
    assert ContextOwnership.MEMORY_OWNED in owners


# 7. Classification Preservation
def test_classification_preservation():
    rag_c = RAGContextContract(
        classification=KnowledgeClassification.GENERAL_KNOWLEDGE,
        content="General pest guide",
        provenance={"s": "guide"},
    )
    mem_c = MemoryContextContract(
        memory_id="m_3",
        classification=KnowledgeClassification.FARMER_KNOWLEDGE,
        content={"preferred_crop": "Mustard"},
        farmer_id="f_1",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"s": "profile"},
    )
    rag_adapter = RAGContextProviderAdapter(E2EMockRAGProvider([rag_c]))
    mem_adapter = MemoryContextProviderAdapter(E2EMockMemoryProvider([mem_c]))
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])

    res = manager.prepare_context(ContextRequest(request_id="r_cls", farmer_id="f_1"))
    classes = {item.classification for item in res.items}
    assert KnowledgeClassification.GENERAL_KNOWLEDGE in classes
    assert KnowledgeClassification.FARMER_KNOWLEDGE in classes


# 8. Scope Preservation
def test_scope_preservation():
    rag_c = RAGContextContract(scope=ContextScope.GLOBAL, content="Global climate norm", provenance={"s": "wmo"})
    mem_c = MemoryContextContract(
        memory_id="m_4",
        scope=ContextScope.FIELD,
        content={"soil_moisture": "22%"},
        farmer_id="f_1",
        field_id="fld_A",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"s": "sensor"},
    )
    rag_adapter = RAGContextProviderAdapter(E2EMockRAGProvider([rag_c]))
    mem_adapter = MemoryContextProviderAdapter(E2EMockMemoryProvider([mem_c]))
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])

    res = manager.prepare_context(ContextRequest(request_id="r_scp", farmer_id="f_1", field_id="fld_A"))
    scopes = {item.scope for item in res.items}
    assert ContextScope.GLOBAL in scopes
    assert ContextScope.FIELD in scopes


# 9. Persistence Preservation
def test_persistence_preservation():
    rec_temp = ContextSourceRecord(
        source_type=ContextSourceType.EXTERNAL_SERVICE,
        ownership=ContextOwnership.EXTERNAL_OWNED,
        classification=KnowledgeClassification.EXTERNAL_CURRENT_DATA,
        scope=ContextScope.REGIONAL,
        persistence_intent=PersistenceIntent.TEMPORARY,
        provenance={"source": "weather_api"},
    )
    validator = BoundaryValidator()
    validator.validate_record(rec_temp)
    assert rec_temp.persistence_intent == PersistenceIntent.TEMPORARY


# 10. Privacy Preservation
def test_privacy_preservation():
    mem_c = MemoryContextContract(
        memory_id="m_pii",
        content={"farmer_phone": "+919999999999"},
        farmer_id="f_99",
        privacy_level=PrivacyLevel.FARMER_PII,
        is_pii=True,
        provenance={"source": "app_profile"},
    )
    mem_adapter = MemoryContextProviderAdapter(E2EMockMemoryProvider([mem_c]))
    manager = B2ContextManager(providers=[mem_adapter])

    # With allow_pii=True policy, PII context item is preserved and privacy_level is intact
    res = manager.prepare_context(ContextRequest(request_id="r_priv", farmer_id="f_99", policy=PolicyConfig(allow_pii=True)))
    assert len(res.items) == 1
    assert res.items[0].privacy_level == PrivacyLevel.FARMER_PII


# 11. Conflict Preservation
def test_conflict_preservation():
    rag_c = RAGContextContract(content="Recommended seeding rate is 100 kg/ha", provenance={"s": "guide"})
    mem_c = MemoryContextContract(
        memory_id="m_rate",
        content="Recommended seeding rate is 125 kg/ha",
        farmer_id="f_1",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"s": "extension_agent"},
    )
    rag_adapter = RAGContextProviderAdapter(E2EMockRAGProvider([rag_c]))
    mem_adapter = MemoryContextProviderAdapter(E2EMockMemoryProvider([mem_c]))

    items = []
    for item in rag_adapter.get_context(ContextRequest(request_id="r1")):
        item.entity_type = "crop"
        item.entity_id = "wheat"
        item.data_type = "seeding_rate"
        items.append(item)

    for item in mem_adapter.get_context(ContextRequest(request_id="r2", farmer_id="f_1")):
        item.entity_type = "crop"
        item.entity_id = "wheat"
        item.data_type = "seeding_rate"
        items.append(item)

    class FixedItemProvider:
        provider_name = "fixed_provider"
        def __init__(self, items): self.items = items
        def get_context(self, req): return self.items

    manager = B2ContextManager(providers=[FixedItemProvider(items)])
    res = manager.prepare_context(ContextRequest(request_id="r_conf"))

    assert len(res.items) == 2
    assert res.items[0].conflict_status == ConflictStatus.CONFLICTED
    assert res.items[1].conflict_status == ConflictStatus.CONFLICTED
    assert res.structured_context["conflicts_present"] is True


# 12. RAG Failure Isolation
def test_rag_failure_isolation():
    failing_rag = RAGContextProviderAdapter(E2EMockRAGProvider(should_fail=True))
    mem_c = MemoryContextContract(
        memory_id="m_ok",
        content={"crop": "Cotton"},
        farmer_id="f_1",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"s": "log"},
    )
    good_mem = MemoryContextProviderAdapter(E2EMockMemoryProvider([mem_c]))
    manager = B2ContextManager(providers=[failing_rag, good_mem])

    res = manager.prepare_context(ContextRequest(request_id="r_rag_fail", farmer_id="f_1", policy=PolicyConfig(allow_partial=True)))
    assert res.state == ContextState.PARTIAL
    assert len(res.items) == 1
    assert res.items[0].source_type == ContextSourceType.MEMORY


# 13. Memory Failure Isolation
def test_memory_failure_isolation():
    rag_c = RAGContextContract(content="Cotton pest management", provenance={"s": "guide"})
    good_rag = RAGContextProviderAdapter(E2EMockRAGProvider([rag_c]))
    failing_mem = MemoryContextProviderAdapter(E2EMockMemoryProvider(should_fail=True))
    manager = B2ContextManager(providers=[good_rag, failing_mem])

    res = manager.prepare_context(ContextRequest(request_id="r_mem_fail", farmer_id="f_1", policy=PolicyConfig(allow_partial=True)))
    assert res.state == ContextState.PARTIAL
    assert len(res.items) == 1
    assert res.items[0].source_type == ContextSourceType.RAG


# 14. RAG -> Memory Governance
def test_rag_to_memory_governance():
    engine = ContextGovernanceEngine(policy_name="RAG_MEM_POLICY")
    rag_c = RAGContextContract(content="Drip irrigation dosage for tomato", provenance={"s": "KVK Guide"})
    candidate = PromotionCandidate.from_rag_contract(rag_contract=rag_c, farmer_id="f_77")

    rec = engine.execute_governance(candidate)
    assert rec.status == GovernanceState.AUTO_ALLOWED
    assert rec.target_ownership == ContextOwnership.MEMORY_OWNED
    assert rec.target_lifecycle_reference == "MEMORY_INGESTION_AND_PERSISTENCE_LIFECYCLE"


# 15. Memory -> RAG Governance
def test_memory_to_rag_governance():
    engine = ContextGovernanceEngine(policy_name="MEM_RAG_POLICY")
    mem_c = MemoryContextContract(
        memory_id="m_obs_123",
        content={"yield": "60 quintals/ha using sub-surface drip"},
        farmer_id="f_88",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"s": "extension_report"},
    )
    candidate = PromotionCandidate.from_memory_contract(memory_contract=mem_c, target_scope=ContextScope.GLOBAL)

    decision = engine.evaluate_candidate(candidate)
    assert decision.outcome == GovernanceOutcome.REQUIRES_REVIEW

    # Upon review approval, target lifecycle reference points to C.2 ingestion/publication pipeline
    app_record = engine.approve_review(candidate, reviewer_id="curator_1", reason="Sanitized and approved")
    assert app_record.target_lifecycle_reference == "C2_INGESTION_VALIDATION_AND_PUBLICATION_PIPELINE"


# 16. Blocked Promotion Test
def test_blocked_promotion():
    engine = ContextGovernanceEngine()
    mem_c = MemoryContextContract(
        memory_id="m_pii_block",
        content={"farmer_name": "Ramesh", "bank_account": "9876543210"},
        farmer_id="f_99",
        privacy_level=PrivacyLevel.FARMER_PII,
        is_pii=True,
        provenance={"s": "kyc_doc"},
    )
    candidate = PromotionCandidate.from_memory_contract(memory_contract=mem_c, target_scope=ContextScope.GLOBAL)

    decision = engine.evaluate_candidate(candidate)
    assert decision.outcome == GovernanceOutcome.BLOCKED
    assert decision.failure_reason == GovernanceFailureReason.PRIVACY_POLICY_VIOLATION


# 17. Review-Required Promotion Test
def test_review_required_promotion():
    engine = ContextGovernanceEngine()
    mem_c = MemoryContextContract(
        memory_id="m_field_obs",
        content={"local_pest_outbreak": "Fall armyworm in maize field 2"},
        farmer_id="f_12",
        field_id="fld_2",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"s": "field_scout"},
    )
    candidate = PromotionCandidate.from_memory_contract(memory_contract=mem_c, target_scope=ContextScope.GLOBAL)

    decision = engine.evaluate_candidate(candidate)
    assert decision.outcome == GovernanceOutcome.REQUIRES_REVIEW
    assert decision.failure_reason == GovernanceFailureReason.REVIEW_REQUIRED


# 18. Invalid Promotion Test
def test_invalid_promotion():
    engine = ContextGovernanceEngine()
    candidate = PromotionCandidate(
        candidate_id="cand_invalid_no_prov",
        source_type=ContextSourceType.RAG,
        ownership=ContextOwnership.RAG_OWNED,
        classification=KnowledgeClassification.GENERAL_KNOWLEDGE,
        scope=ContextScope.GLOBAL,
        persistence_intent=PersistenceIntent.PERSISTENT,
        content="Invalid candidate test",
        provenance={},  # Empty provenance triggers INVALID
        requested_transition=TransitionType.RAG_TO_MEMORY,
        target_domain="MEMORY",
        farmer_id="f_1",
    )

    decision = engine.evaluate_candidate(candidate)
    assert decision.outcome == GovernanceOutcome.INVALID
    assert decision.failure_reason == GovernanceFailureReason.MISSING_PROVENANCE


# 19. Web Evidence Protection Test
def test_web_evidence_protection():
    engine = ContextGovernanceEngine()
    candidate = PromotionCandidate(
        candidate_id="cand_web_search_01",
        source_type=ContextSourceType.EXTERNAL_SERVICE,
        ownership=ContextOwnership.EXTERNAL_OWNED,
        classification=KnowledgeClassification.EXTERNAL_CURRENT_DATA,
        scope=ContextScope.REGIONAL,
        persistence_intent=PersistenceIntent.TEMPORARY,
        content="Live mandi price report",
        provenance={"search": "web_search_query"},
        requested_transition=TransitionType.RAG_TO_MEMORY,
        target_domain="MEMORY",
        farmer_id="f_22",
    )

    decision = engine.evaluate_candidate(candidate)
    assert decision.outcome in {GovernanceOutcome.BLOCKED, GovernanceOutcome.REQUIRES_REVIEW}


# 20. Observation Protection Test
def test_observation_protection():
    engine = ContextGovernanceEngine()
    candidate = PromotionCandidate(
        candidate_id="cand_sensor_obs_01",
        source_type=ContextSourceType.OBSERVATION,
        ownership=ContextOwnership.EXTERNAL_OWNED,
        classification=KnowledgeClassification.OBSERVATION,
        scope=ContextScope.FIELD,
        persistence_intent=PersistenceIntent.TEMPORARY,
        content={"moisture_reading": 18.5},
        provenance={"sensor_id": "moist_101"},
        requested_transition=TransitionType.RAG_TO_MEMORY,
        target_domain="MEMORY",
        farmer_id="f_22",
    )

    decision = engine.evaluate_candidate(candidate)
    assert decision.outcome in {GovernanceOutcome.BLOCKED, GovernanceOutcome.REQUIRES_REVIEW}


# 21. Storage Isolation Validation
def test_storage_isolation():
    import inspect
    import modules.context.boundary.validator as val_mod
    import modules.context.boundary.adapters as adp_mod
    import modules.context.boundary.governance as gov_mod

    for mod in [val_mod, adp_mod, gov_mod]:
        src = inspect.getsource(mod)
        assert "sqlite3" not in src
        assert "qdrant" not in src.lower()


# 22. Dependency Isolation
def test_dependency_isolation():
    import importlib
    kb_mod = importlib.import_module("modules.knowledge_base")
    mem_mod = importlib.import_module("modules.memory")

    # Ensure no direct internal dependencies between knowledge_base and memory
    assert not hasattr(kb_mod, "MemoryService")
    assert not hasattr(mem_mod, "CanonicalKnowledgeRepository")


# 23. B2 Compatibility
def test_b2_compatibility():
    rag_c = RAGContextContract(content="Wheat seeding depth 4cm", provenance={"s": "pau"})
    mem_c = MemoryContextContract(
        memory_id="m_b2",
        content={"sowing_date": "2024-11-10"},
        farmer_id="f_1",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"s": "chat"},
    )
    rag_adapter = RAGContextProviderAdapter(E2EMockRAGProvider([rag_c]))
    mem_adapter = MemoryContextProviderAdapter(E2EMockMemoryProvider([mem_c]))
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])

    res = manager.prepare_context(ContextRequest(request_id="r_b2", farmer_id="f_1"))
    assert res.state == ContextState.COMPLETED
    assert len(res.structured_context["items"]) == 2


# 24. C.2 Compatibility
def test_c2_compatibility():
    engine = ContextGovernanceEngine()
    mem_c = MemoryContextContract(
        memory_id="m_c2_test",
        content={"innovative_mulching": "Straw mulching reduced water requirement by 30%"},
        farmer_id="f_10",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"s": "extension_log"},
    )
    candidate = PromotionCandidate.from_memory_contract(memory_contract=mem_c, target_scope=ContextScope.GLOBAL)

    decision = engine.evaluate_candidate(candidate)
    assert decision.outcome == GovernanceOutcome.REQUIRES_REVIEW

    app_record = engine.approve_review(candidate, reviewer_id="curator_1", reason="Approved")
    assert app_record.target_lifecycle_reference == "C2_INGESTION_VALIDATION_AND_PUBLICATION_PIPELINE"


# 25. Five Principles Final Compliance Audit
def test_five_principles_final_audit():
    # 1. Extensibility
    engine = ContextGovernanceEngine(policy_name="EXTENSIBLE_POLICY_V2")
    assert engine.policy_name == "EXTENSIBLE_POLICY_V2"

    # 2. Loose Coupling
    assert issubclass(ContextGovernanceEngine, IPromotionGovernanceEngine)

    # 3. Single Responsibility
    validator = BoundaryValidator()
    assert issubclass(BoundaryValidator, IBoundaryValidator)

    # 4. Controlled Dependencies
    rag_prov = E2EMockRAGProvider()
    mem_prov = E2EMockMemoryProvider()
    assert isinstance(rag_prov, IRAGContextProvider)
    assert isinstance(mem_prov, IMemoryContextProvider)

    # 5. Replaceability & Evolution
    rag_adapter = RAGContextProviderAdapter(rag_prov)
    mem_adapter = MemoryContextProviderAdapter(mem_prov)
    manager = B2ContextManager(providers=[rag_adapter, mem_adapter])
    assert manager is not None
