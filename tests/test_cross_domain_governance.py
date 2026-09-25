import pytest
from core.errors.exceptions import (
    BoundaryValidationError,
    PromotionNotAllowedError,
)
from modules.context.schemas import PrivacyLevel
from modules.context.boundary import (
    KnowledgeClassification,
    ContextSourceType,
    ContextOwnership,
    ContextScope,
    PersistenceIntent,
    TransitionType,
    GovernanceOutcome,
    GovernanceState,
    GovernanceFailureReason,
    RAGContextContract,
    MemoryContextContract,
    PromotionCandidate,
    GovernanceDecision,
    PromotionRecord,
    ContextGovernanceEngine,
    IPromotionGovernanceEngine,
)


@pytest.fixture
def governance_engine():
    return ContextGovernanceEngine(policy_name="TEST_GOVERNANCE_POLICY")


def test_1_rag_to_memory_candidate_creation():
    """1. RAG -> Memory candidate creation."""
    rag_contract = RAGContextContract(
        content="Optimum wheat seeding depth is 3-5 cm.",
        chunk_id="chunk_depth_101",
        provenance={"source": "PAU Agronomy Guide 2024"},
    )
    candidate = PromotionCandidate.from_rag_contract(
        rag_contract=rag_contract,
        farmer_id="farmer_88",
        farm_id="farm_01",
        target_scope=ContextScope.FARMER,
    )
    assert candidate.requested_transition == TransitionType.RAG_TO_MEMORY
    assert candidate.target_domain == "MEMORY"
    assert candidate.ownership == ContextOwnership.RAG_OWNED
    assert candidate.target_ownership == ContextOwnership.MEMORY_OWNED
    assert candidate.farmer_id == "farmer_88"
    assert candidate.provenance["source"] == "PAU Agronomy Guide 2024"


def test_2_memory_to_rag_candidate_creation():
    """2. Memory -> RAG candidate creation."""
    mem_contract = MemoryContextContract(
        memory_id="mem_organic_fertilizer_99",
        content={"practice": "Neem cake application for pest resistance"},
        farmer_id="farmer_202",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"recorded_by": "extension_agent_04"},
    )
    candidate = PromotionCandidate.from_memory_contract(
        memory_contract=mem_contract,
        target_scope=ContextScope.GLOBAL,
    )
    assert candidate.requested_transition == TransitionType.MEMORY_TO_RAG
    assert candidate.target_domain == "RAG"
    assert candidate.ownership == ContextOwnership.MEMORY_OWNED
    assert candidate.target_ownership == ContextOwnership.RAG_OWNED
    assert candidate.source_id == "mem_organic_fertilizer_99"


def test_3_allowed_promotion(governance_engine):
    """3. Allowed promotion: RAG -> Memory with farmer reference."""
    rag_contract = RAGContextContract(
        content="General soil health guidelines.",
        provenance={"source": "ICAR Soil Science Bulletin"},
    )
    candidate = PromotionCandidate.from_rag_contract(
        rag_contract=rag_contract,
        farmer_id="farmer_441",
    )
    decision = governance_engine.evaluate_candidate(candidate)
    assert decision.outcome == GovernanceOutcome.AUTO_ALLOWED
    assert decision.state == GovernanceState.AUTO_ALLOWED
    assert decision.target_lifecycle_requirements == "MEMORY_INGESTION_AND_PERSISTENCE_LIFECYCLE"


def test_4_blocked_promotion(governance_engine):
    """4. Blocked promotion: Private Memory containing PII to broad RAG."""
    mem_contract = MemoryContextContract(
        memory_id="mem_pii_123",
        content={"farmer_name": "Suresh", "aadhaar_last4": "1234"},
        farmer_id="farmer_555",
        privacy_level=PrivacyLevel.FARMER_PII,
        is_pii=True,
        provenance={"source": "registration_form"},
    )
    candidate = PromotionCandidate.from_memory_contract(
        memory_contract=mem_contract,
        target_scope=ContextScope.GLOBAL,
    )
    decision = governance_engine.evaluate_candidate(candidate)
    assert decision.outcome == GovernanceOutcome.BLOCKED
    assert decision.state == GovernanceState.BLOCKED
    assert decision.failure_reason == GovernanceFailureReason.PRIVACY_POLICY_VIOLATION


def test_5_review_required_promotion(governance_engine):
    """5. Review-required promotion: Memory farmer knowledge to RAG requiring curation."""
    mem_contract = MemoryContextContract(
        memory_id="mem_farm_obs_01",
        content={"crop_yield_2024": "45 quintals per hectare"},
        farmer_id="farmer_101",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"source": "harvest_log"},
    )
    candidate = PromotionCandidate.from_memory_contract(
        memory_contract=mem_contract,
        target_scope=ContextScope.GLOBAL,
    )
    decision = governance_engine.evaluate_candidate(candidate)
    assert decision.outcome == GovernanceOutcome.REQUIRES_REVIEW
    assert decision.state == GovernanceState.REQUIRES_REVIEW
    assert decision.failure_reason == GovernanceFailureReason.REVIEW_REQUIRED


def test_6_invalid_candidate(governance_engine):
    """6. Invalid candidate: Missing provenance."""
    candidate = PromotionCandidate(
        candidate_id="cand_invalid_01",
        source_type=ContextSourceType.RAG,
        ownership=ContextOwnership.RAG_OWNED,
        classification=KnowledgeClassification.GENERAL_KNOWLEDGE,
        scope=ContextScope.GLOBAL,
        persistence_intent=PersistenceIntent.PERSISTENT,
        content="Some content",
        provenance={},  # Empty provenance
        requested_transition=TransitionType.RAG_TO_MEMORY,
        target_domain="MEMORY",
        farmer_id="farmer_1",
    )
    decision = governance_engine.evaluate_candidate(candidate)
    assert decision.outcome == GovernanceOutcome.INVALID
    assert decision.failure_reason == GovernanceFailureReason.MISSING_PROVENANCE


def test_7_ownership_preservation(governance_engine):
    """7. Ownership preservation: Original source ownership and target ownership recorded."""
    rag_contract = RAGContextContract(
        content="General pest control",
        provenance={"source": "Govt Circular"},
    )
    candidate = PromotionCandidate.from_rag_contract(
        rag_contract=rag_contract,
        farmer_id="f_007",
    )
    record = governance_engine.execute_governance(candidate)
    assert record.source_ownership == ContextOwnership.RAG_OWNED
    assert record.target_ownership == ContextOwnership.MEMORY_OWNED


def test_8_ownership_transition_validation(governance_engine):
    """8. Ownership transition validation: Attempting RAG_TO_MEMORY with MEMORY_OWNED source must be blocked."""
    candidate = PromotionCandidate(
        candidate_id="cand_bad_owner_01",
        source_type=ContextSourceType.MEMORY,
        ownership=ContextOwnership.MEMORY_OWNED,  # Mismatched source ownership for RAG_TO_MEMORY
        classification=KnowledgeClassification.GENERAL_KNOWLEDGE,
        scope=ContextScope.GLOBAL,
        persistence_intent=PersistenceIntent.PERSISTENT,
        content="Invalid transition request",
        provenance={"source": "test"},
        requested_transition=TransitionType.RAG_TO_MEMORY,
        target_domain="MEMORY",
        farmer_id="f_1",
    )
    decision = governance_engine.evaluate_candidate(candidate)
    assert decision.outcome == GovernanceOutcome.BLOCKED
    assert decision.failure_reason == GovernanceFailureReason.OWNERSHIP_TRANSITION_BLOCKED


def test_9_scope_transition_validation(governance_engine):
    """9. Scope transition validation: RAG->Memory without farmer_id for farmer scope must be blocked."""
    rag_contract = RAGContextContract(
        content="General agronomy advice",
        provenance={"source": "ICAR Guide"},
    )
    candidate = PromotionCandidate.from_rag_contract(
        rag_contract=rag_contract,
        farmer_id=None,  # Missing farmer_id for FARMER target scope
        target_scope=ContextScope.FARMER,
    )
    decision = governance_engine.evaluate_candidate(candidate)
    assert decision.outcome == GovernanceOutcome.BLOCKED
    assert decision.failure_reason == GovernanceFailureReason.INVALID_SCOPE_TRANSITION


def test_10_persistence_transition_validation(governance_engine):
    """10. Persistence transition validation: TEMPORARY evidence cannot become PERSISTENT."""
    candidate = PromotionCandidate(
        candidate_id="cand_temp_01",
        source_type=ContextSourceType.EXTERNAL_SERVICE,
        ownership=ContextOwnership.EXTERNAL_OWNED,
        classification=KnowledgeClassification.EXTERNAL_CURRENT_DATA,
        scope=ContextScope.REGIONAL,
        persistence_intent=PersistenceIntent.TEMPORARY,
        content="Temporary weather ping",
        provenance={"source": "weather_api"},
        requested_transition=TransitionType.RAG_TO_MEMORY,
        target_domain="MEMORY",
        farmer_id="farmer_10",
        target_persistence_intent=PersistenceIntent.PERSISTENT,
    )
    decision = governance_engine.evaluate_candidate(candidate)
    assert decision.outcome == GovernanceOutcome.BLOCKED
    assert decision.failure_reason == GovernanceFailureReason.PERSISTENCE_TRANSITION_BLOCKED


def test_11_provenance_preservation(governance_engine):
    """11. Provenance preservation: Original provenance survives and is enriched with governance trace."""
    original_prov = {
        "document_id": "doc_99",
        "author": "Agri Ministry",
        "ingested_at": "2024-12-01T00:00:00Z",
    }
    rag_contract = RAGContextContract(
        content="Water management in paddy",
        provenance=original_prov,
    )
    candidate = PromotionCandidate.from_rag_contract(
        rag_contract=rag_contract,
        farmer_id="f_77",
    )
    record = governance_engine.execute_governance(candidate)
    for k, v in original_prov.items():
        assert record.source_provenance[k] == v
    assert "governance_decision_id" in record.source_provenance


def test_12_privacy_metadata_preservation(governance_engine):
    """12. Privacy metadata preservation: PII and privacy level survive in candidate and decision."""
    mem_contract = MemoryContextContract(
        memory_id="mem_p_01",
        content={"phone": "+919876543210"},
        farmer_id="f_888",
        privacy_level=PrivacyLevel.FARMER_PII,
        is_pii=True,
        provenance={"source": "sms_bot"},
    )
    candidate = PromotionCandidate.from_memory_contract(
        memory_contract=mem_contract,
        target_scope=ContextScope.GLOBAL,
    )
    assert candidate.privacy_level == PrivacyLevel.FARMER_PII
    assert candidate.is_pii is True
    decision = governance_engine.evaluate_candidate(candidate)
    assert decision.failure_reason == GovernanceFailureReason.PRIVACY_POLICY_VIOLATION


def test_13_session_to_persistent_blocking(governance_engine):
    """13. Session-to-persistent promotion requires review or is blocked."""
    candidate = PromotionCandidate(
        candidate_id="cand_sess_01",
        source_type=ContextSourceType.RAG,
        ownership=ContextOwnership.RAG_OWNED,
        classification=KnowledgeClassification.SESSION_CONTEXT,
        scope=ContextScope.SESSION,
        persistence_intent=PersistenceIntent.SESSION_SCOPED,
        content="Chat session summary",
        provenance={"session_id": "sess_100"},
        requested_transition=TransitionType.RAG_TO_MEMORY,
        target_domain="MEMORY",
        farmer_id="farmer_12",
        target_persistence_intent=PersistenceIntent.PERSISTENT,
    )
    decision = governance_engine.evaluate_candidate(candidate)
    assert decision.outcome in {GovernanceOutcome.REQUIRES_REVIEW, GovernanceOutcome.BLOCKED}


def test_14_farmer_to_global_blocking(governance_engine):
    """14. Farmer-to-global promotion blocking."""
    mem_contract = MemoryContextContract(
        memory_id="mem_f_89",
        content={"farmer_note": "Soil organic carbon level 0.45%"},
        farmer_id="farmer_89",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"source": "field_test"},
    )
    candidate = PromotionCandidate.from_memory_contract(
        memory_contract=mem_contract,
        target_scope=ContextScope.GLOBAL,
    )
    decision = governance_engine.evaluate_candidate(candidate)
    assert decision.outcome == GovernanceOutcome.REQUIRES_REVIEW or decision.outcome == GovernanceOutcome.BLOCKED


def test_15_field_to_global_blocking(governance_engine):
    """15. Field-to-global promotion blocking."""
    mem_contract = MemoryContextContract(
        memory_id="mem_fld_12",
        content={"field_disease": "Bacterial Leaf Blight detected"},
        farmer_id="farmer_89",
        field_id="field_A1",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"source": "scouting_report"},
    )
    candidate = PromotionCandidate.from_memory_contract(
        memory_contract=mem_contract,
        target_scope=ContextScope.GLOBAL,
    )
    decision = governance_engine.evaluate_candidate(candidate)
    assert decision.outcome in {GovernanceOutcome.BLOCKED, GovernanceOutcome.REQUIRES_REVIEW}


def test_16_observation_persistence_blocking(governance_engine):
    """16. Observation persistence requires review."""
    candidate = PromotionCandidate(
        candidate_id="cand_obs_01",
        source_type=ContextSourceType.OBSERVATION,
        ownership=ContextOwnership.EXTERNAL_OWNED,
        classification=KnowledgeClassification.OBSERVATION,
        scope=ContextScope.FIELD,
        persistence_intent=PersistenceIntent.TEMPORARY,
        content={"drone_ndVI": 0.68},
        provenance={"flight_id": "fl_88"},
        requested_transition=TransitionType.RAG_TO_MEMORY,
        target_domain="MEMORY",
        farmer_id="farmer_10",
    )
    decision = governance_engine.evaluate_candidate(candidate)
    assert decision.outcome in {GovernanceOutcome.BLOCKED, GovernanceOutcome.REQUIRES_REVIEW}


def test_17_web_evidence_permanent_knowledge_blocking(governance_engine):
    """17. Web search evidence permanent memory/RAG promotion requires review/blocking."""
    candidate = PromotionCandidate(
        candidate_id="cand_web_01",
        source_type=ContextSourceType.EXTERNAL_SERVICE,
        ownership=ContextOwnership.EXTERNAL_OWNED,
        classification=KnowledgeClassification.EXTERNAL_CURRENT_DATA,
        scope=ContextScope.REGIONAL,
        persistence_intent=PersistenceIntent.TEMPORARY,
        content="Current wheat mandi price in Ludhiana is 2275 INR/quintal",
        provenance={"search": "web_search_mandi"},
        requested_transition=TransitionType.RAG_TO_MEMORY,
        target_domain="MEMORY",
        farmer_id="farmer_50",
    )
    decision = governance_engine.evaluate_candidate(candidate)
    assert decision.outcome in {GovernanceOutcome.BLOCKED, GovernanceOutcome.REQUIRES_REVIEW}


def test_18_promotion_record_creation(governance_engine):
    """18. Promotion record creation and state tracking."""
    rag_contract = RAGContextContract(
        content="Fertilizer dose calculation for mustard",
        provenance={"source": "PAU Bulletin"},
    )
    candidate = PromotionCandidate.from_rag_contract(
        rag_contract=rag_contract,
        farmer_id="f_300",
    )
    record = governance_engine.execute_governance(candidate)
    assert isinstance(record, PromotionRecord)
    assert record.promotion_id.startswith("prom_")
    assert record.status == GovernanceState.AUTO_ALLOWED
    assert record.policy_reference == "TEST_GOVERNANCE_POLICY"


def test_19_governance_failure_handling(governance_engine):
    """19. Governance failure handling & review approval flow."""
    mem_contract = MemoryContextContract(
        memory_id="mem_rev_01",
        content={"soil_pH": 6.8},
        farmer_id="farmer_777",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"source": "lab_test"},
    )
    candidate = PromotionCandidate.from_memory_contract(
        memory_contract=mem_contract,
        target_scope=ContextScope.GLOBAL,
    )
    initial_decision = governance_engine.evaluate_candidate(candidate)
    assert initial_decision.outcome == GovernanceOutcome.REQUIRES_REVIEW

    # Approve review
    approved_record = governance_engine.approve_review(
        candidate=candidate,
        reviewer_id="curator_alice",
        reason="Sanitized and approved for RAG knowledge base",
    )
    assert approved_record.status == GovernanceState.APPROVED
    assert approved_record.reviewer == "curator_alice"
    assert approved_record.outcome == GovernanceOutcome.AUTO_ALLOWED

    # Reject review
    rejected_record = governance_engine.reject_review(
        candidate=candidate,
        reviewer_id="curator_bob",
        reason="Contains sensitive field coordinates",
    )
    assert rejected_record.status == GovernanceState.REJECTED
    assert rejected_record.reviewer == "curator_bob"
    assert rejected_record.outcome == GovernanceOutcome.BLOCKED


def test_20_target_lifecycle_protection(governance_engine):
    """20. Target lifecycle protection: Governance engine only outputs governance approval, never direct DB write."""
    rag_contract = RAGContextContract(
        content="Paddy seed treatment procedure",
        provenance={"source": "KVK Portal"},
    )
    candidate = PromotionCandidate.from_rag_contract(
        rag_contract=rag_contract,
        farmer_id="f_999",
    )
    record = governance_engine.execute_governance(candidate)
    # Ensures governance engine sets requirement string for target system to execute
    assert record.target_lifecycle_reference == "MEMORY_INGESTION_AND_PERSISTENCE_LIFECYCLE"


def test_21_no_direct_sqlite_access():
    """21. Verify no direct SQLite or DB import/usage in governance module."""
    import inspect
    import modules.context.boundary.governance as gov_mod

    source_code = inspect.getsource(gov_mod)
    assert "sqlite3" not in source_code
    assert "execute(" not in source_code
    assert "cursor" not in source_code


def test_22_no_direct_qdrant_access():
    """22. Verify no direct Qdrant or vector index import/usage in governance module."""
    import inspect
    import modules.context.boundary.governance as gov_mod

    source_code = inspect.getsource(gov_mod)
    assert "qdrant" not in source_code.lower()
    assert "vector" not in source_code.lower()


def test_23_no_rag_memory_direct_dependency():
    """23. Verify zero direct dependencies between RAG and Memory internal modules."""
    import sys
    import importlib

    kb_mod = importlib.import_module("modules.knowledge_base")
    mem_mod = importlib.import_module("modules.memory")

    # Neither internal module directly imports or references the other
    assert not hasattr(kb_mod, "MemoryService")
    assert not hasattr(mem_mod, "CanonicalKnowledgeRepository")


def test_24_five_principle_compliance(governance_engine):
    """24. Verify Five EarthMind Principles compliance in C.3.3."""
    # 1. Extensibility: Engine accepts custom policy name or metadata
    custom_engine = ContextGovernanceEngine(policy_name="CUSTOM_STATE_AGRI_POLICY")
    assert custom_engine.policy_name == "CUSTOM_STATE_AGRI_POLICY"

    # 2. Loose Coupling & Interface Isolation:
    assert isinstance(custom_engine, IPromotionGovernanceEngine)

    # 3. Single Responsibility: Evaluates cross-domain promotion rules without agronomic reasoning
    rag_contract = RAGContextContract(
        content="Agronomic fact without reasoning",
        provenance={"doc": "manual"},
    )
    cand = PromotionCandidate.from_rag_contract(
        rag_contract=rag_contract,
        farmer_id="farmer_1",
    )
    dec = custom_engine.evaluate_candidate(cand)
    assert dec.applicable_policy == "CUSTOM_STATE_AGRI_POLICY"

    # 4. Controlled Dependencies: All inputs via PromotionCandidate, outputs via GovernanceDecision/PromotionRecord
    # 5. Replaceability: Engine can be replaced with any class implementing IPromotionGovernanceEngine
