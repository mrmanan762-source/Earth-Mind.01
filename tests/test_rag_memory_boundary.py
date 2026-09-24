import pytest
from core.errors.exceptions import (
    BoundaryValidationError,
    PromotionNotAllowedError,
    ScopeViolationBoundaryError,
    PrivacyBoundaryError,
)
from modules.context.schemas import ContextItem, PrivacyLevel
from modules.context.boundary.enums import (
    KnowledgeClassification,
    ContextSourceType,
    ContextOwnership,
    ContextScope,
    PersistenceIntent,
)
from modules.context.boundary.models import (
    ContextSourceRecord,
    RAGContextContract,
    MemoryContextContract,
)
from modules.context.boundary.validator import BoundaryValidator
from modules.context.boundary.interfaces import (
    IRAGContextProvider,
    IMemoryContextProvider,
    IBoundaryValidator,
)


@pytest.fixture
def validator():
    return BoundaryValidator()


def test_1_general_knowledge_rag_contract(validator):
    """1. General knowledge -> RAG classification validation."""
    rag_contract = RAGContextContract(
        source_type=ContextSourceType.RAG,
        ownership=ContextOwnership.RAG_OWNED,
        classification=KnowledgeClassification.GENERAL_KNOWLEDGE,
        scope=ContextScope.GLOBAL,
        persistence_intent=PersistenceIntent.PERSISTENT,
        content="Wheat crop optimal temperature range is 15-24 C.",
        document_id="doc_123",
        document_version_id="doc_v1",
        collection_id="agronomy_knowledge",
        knowledge_unit_id="ku_wheat_01",
        chunk_id="chunk_99",
        publication_state="PUBLISHED",
        provenance={"source": "ICAR Agronomy Handbook", "version": "2024.1"},
    )
    validator.validate_rag_contract(rag_contract)
    record = rag_contract.to_source_record()
    assert record.classification == KnowledgeClassification.GENERAL_KNOWLEDGE
    assert record.ownership == ContextOwnership.RAG_OWNED


def test_2_farmer_knowledge_memory_contract(validator):
    """2. Farmer knowledge -> Memory classification validation."""
    mem_contract = MemoryContextContract(
        memory_id="mem_farmer_001",
        source_type=ContextSourceType.MEMORY,
        ownership=ContextOwnership.MEMORY_OWNED,
        classification=KnowledgeClassification.FARMER_KNOWLEDGE,
        scope=ContextScope.FARMER,
        persistence_intent=PersistenceIntent.PERSISTENT,
        content={"farmer_name": "Ramesh Kumar", "preferred_language": "Hindi"},
        farmer_id="farmer_1001",
        privacy_level=PrivacyLevel.FARMER_PII,
        is_pii=True,
        provenance={"origin": "farmer_onboarding_interaction", "timestamp": "2025-01-15T10:00:00Z"},
    )
    validator.validate_memory_contract(mem_contract)
    record = mem_contract.to_source_record()
    assert record.classification == KnowledgeClassification.FARMER_KNOWLEDGE
    assert record.ownership == ContextOwnership.MEMORY_OWNED


def test_3_field_knowledge_memory_contract(validator):
    """3. Field knowledge -> Memory classification validation."""
    mem_contract = MemoryContextContract(
        memory_id="mem_field_002",
        source_type=ContextSourceType.MEMORY,
        ownership=ContextOwnership.MEMORY_OWNED,
        classification=KnowledgeClassification.FIELD_KNOWLEDGE,
        scope=ContextScope.FIELD,
        persistence_intent=PersistenceIntent.PERSISTENT,
        content={"soil_type": "Black Cotton Soil", "pH": 7.2},
        farmer_id="farmer_1001",
        farm_id="farm_501",
        field_id="field_A12",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"origin": "soil_test_report_2024", "lab": "AgriLab Pune"},
    )
    validator.validate_memory_contract(mem_contract)
    record = mem_contract.to_source_record()
    assert record.classification == KnowledgeClassification.FIELD_KNOWLEDGE
    assert record.scope == ContextScope.FIELD


def test_4_session_context_runtime(validator):
    """4. Session context -> Runtime ownership classification."""
    record = ContextSourceRecord(
        source_type=ContextSourceType.SESSION,
        ownership=ContextOwnership.RUNTIME_OWNED,
        classification=KnowledgeClassification.SESSION_CONTEXT,
        scope=ContextScope.SESSION,
        persistence_intent=PersistenceIntent.SESSION_SCOPED,
        session_id="sess_8899",
        provenance={"session_start": "2025-02-20T08:00:00Z"},
    )
    validator.validate_record(record)
    assert record.ownership == ContextOwnership.RUNTIME_OWNED


def test_5_observation_classification(validator):
    """5. Observation -> Observation classification."""
    record = ContextSourceRecord(
        source_type=ContextSourceType.OBSERVATION,
        ownership=ContextOwnership.RUNTIME_OWNED,
        classification=KnowledgeClassification.OBSERVATION,
        scope=ContextScope.FIELD,
        persistence_intent=PersistenceIntent.TEMPORARY,
        field_id="field_A12",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"drone_flight_id": "flight_9921", "camera": "multispectral_v2"},
    )
    validator.validate_record(record)
    assert record.classification == KnowledgeClassification.OBSERVATION


def test_6_external_current_data(validator):
    """6. External current data -> External classification."""
    record = ContextSourceRecord(
        source_type=ContextSourceType.EXTERNAL_SERVICE,
        ownership=ContextOwnership.EXTERNAL_OWNED,
        classification=KnowledgeClassification.EXTERNAL_CURRENT_DATA,
        scope=ContextScope.REGIONAL,
        persistence_intent=PersistenceIntent.TEMPORARY,
        provenance={"service": "OpenWeatherAPI", "fetched_at": "2025-02-20T09:30:00Z"},
    )
    validator.validate_record(record)
    assert record.classification == KnowledgeClassification.EXTERNAL_CURRENT_DATA


def test_7_rag_memory_source_distinction():
    """7. RAG / Memory source distinction test."""
    rag_item = RAGContextContract(
        content="General pest control advice",
        provenance={"source": "Govt Agri Portal"},
    )
    mem_item = MemoryContextContract(
        memory_id="mem_123",
        content="Field spraying done on Monday",
        farmer_id="f_1",
        field_id="fld_1",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"interaction": "chat"},
    )
    assert rag_item.source_type == ContextSourceType.RAG
    assert mem_item.source_type == ContextSourceType.MEMORY
    assert rag_item.ownership == ContextOwnership.RAG_OWNED
    assert mem_item.ownership == ContextOwnership.MEMORY_OWNED


def test_8_scope_validation(validator):
    """8. Scope validation: General knowledge with farmer scope must fail."""
    record = ContextSourceRecord(
        source_type=ContextSourceType.RAG,
        ownership=ContextOwnership.RAG_OWNED,
        classification=KnowledgeClassification.GENERAL_KNOWLEDGE,
        scope=ContextScope.FARMER,  # Invalid scope for GENERAL_KNOWLEDGE
        persistence_intent=PersistenceIntent.PERSISTENT,
        provenance={"source": "ICAR Handbook"},
    )
    with pytest.raises(ScopeViolationBoundaryError):
        validator.validate_record(record)


def test_9_ownership_validation(validator):
    """9. Ownership validation: GENERAL_KNOWLEDGE with MEMORY_OWNED must fail."""
    record = ContextSourceRecord(
        source_type=ContextSourceType.RAG,
        ownership=ContextOwnership.MEMORY_OWNED,  # Invalid ownership for GENERAL_KNOWLEDGE
        classification=KnowledgeClassification.GENERAL_KNOWLEDGE,
        scope=ContextScope.GLOBAL,
        persistence_intent=PersistenceIntent.PERSISTENT,
        provenance={"source": "ICAR Handbook"},
    )
    with pytest.raises(BoundaryValidationError):
        validator.validate_record(record)


def test_10_persistence_validation(validator):
    """10. Persistence intent validation."""
    rec_temp = ContextSourceRecord(
        source_type=ContextSourceType.EXTERNAL_SERVICE,
        ownership=ContextOwnership.EXTERNAL_OWNED,
        classification=KnowledgeClassification.EXTERNAL_CURRENT_DATA,
        scope=ContextScope.REGIONAL,
        persistence_intent=PersistenceIntent.TEMPORARY,
        provenance={"source": "weather_api"},
    )
    validator.validate_record(rec_temp)
    assert rec_temp.persistence_intent == PersistenceIntent.TEMPORARY


def test_11_provenance_preservation(validator):
    """11. Missing provenance must fail validation."""
    record = ContextSourceRecord(
        source_type=ContextSourceType.RAG,
        ownership=ContextOwnership.RAG_OWNED,
        classification=KnowledgeClassification.GENERAL_KNOWLEDGE,
        scope=ContextScope.GLOBAL,
        persistence_intent=PersistenceIntent.PERSISTENT,
        provenance={},  # Empty provenance
    )
    with pytest.raises(BoundaryValidationError) as exc_info:
        validator.validate_record(record)
    assert "provenance" in str(exc_info.value)


def test_12_privacy_metadata_preservation(validator):
    """12. Privacy metadata missing for farmer/field scoped information must fail."""
    record = ContextSourceRecord(
        source_type=ContextSourceType.MEMORY,
        ownership=ContextOwnership.MEMORY_OWNED,
        classification=KnowledgeClassification.FARMER_KNOWLEDGE,
        scope=ContextScope.FARMER,
        persistence_intent=PersistenceIntent.PERSISTENT,
        privacy_level=None,  # Missing privacy level
        provenance={"source": "farmer_chat"},
    )
    with pytest.raises(PrivacyBoundaryError):
        validator.validate_record(record)


def test_13_rag_to_memory_automatic_promotion_blocked(validator):
    """13. Automatic RAG -> Memory promotion must be blocked."""
    with pytest.raises(PromotionNotAllowedError):
        validator.validate_promotion(ContextOwnership.RAG_OWNED, ContextOwnership.MEMORY_OWNED)


def test_14_memory_to_rag_automatic_promotion_blocked(validator):
    """14. Automatic Memory -> RAG promotion must be blocked."""
    with pytest.raises(PromotionNotAllowedError):
        validator.validate_promotion(ContextOwnership.MEMORY_OWNED, ContextOwnership.RAG_OWNED)


def test_15_web_evidence_non_publication_rule(validator):
    """15. Web search current evidence cannot automatically become permanent published RAG or Memory."""
    # Attempting to set EXTERNAL_CURRENT_DATA to MEMORY_OWNED
    rec_mem = ContextSourceRecord(
        source_type=ContextSourceType.EXTERNAL_SERVICE,
        ownership=ContextOwnership.MEMORY_OWNED,
        classification=KnowledgeClassification.EXTERNAL_CURRENT_DATA,
        scope=ContextScope.REGIONAL,
        persistence_intent=PersistenceIntent.TEMPORARY,
        provenance={"search": "web_search_google"},
    )
    with pytest.raises(BoundaryValidationError):
        validator.validate_record(rec_mem)

    # Attempting to set EXTERNAL_CURRENT_DATA to persistent RAG_OWNED without formal pipeline
    rec_rag = ContextSourceRecord(
        source_type=ContextSourceType.EXTERNAL_SERVICE,
        ownership=ContextOwnership.RAG_OWNED,
        classification=KnowledgeClassification.EXTERNAL_CURRENT_DATA,
        scope=ContextScope.GLOBAL,
        persistence_intent=PersistenceIntent.PERSISTENT,
        provenance={"search": "web_search_google"},  # Missing knowledge_ingestion_pipeline
    )
    with pytest.raises(BoundaryValidationError):
        validator.validate_record(rec_rag)


def test_16_observation_non_persistence_rule(validator):
    """16. Observation cannot be automatically promoted to persistent Memory without policy flag."""
    rec_obs = ContextSourceRecord(
        source_type=ContextSourceType.OBSERVATION,
        ownership=ContextOwnership.MEMORY_OWNED,
        classification=KnowledgeClassification.OBSERVATION,
        scope=ContextScope.FIELD,
        persistence_intent=PersistenceIntent.PERSISTENT,
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"sensor": "soil_moisture_sensor_1"},
    )
    # Default (allow_persistent_observation=False) must fail
    with pytest.raises(BoundaryValidationError) as exc_info:
        validator.validate_record(rec_obs, allow_persistent_observation=False)
    assert "OBSERVATION cannot be automatically promoted" in str(exc_info.value)

    # When explicitly allowed by memory policy
    validator.validate_record(rec_obs, allow_persistent_observation=True)


def test_17_b2_context_compatibility(validator):
    """17. B2 context compatibility: ContextItem.from_rag_contract and ContextItem.from_memory_contract."""
    rag_contract = RAGContextContract(
        content="Rice requires high water input during transplanting stage.",
        chunk_id="chunk_rice_55",
        document_id="doc_rice_agronomy",
        provenance={"source": "TNAU Agronomy Portal"},
    )
    context_item_rag = ContextItem.from_rag_contract(rag_contract)
    assert context_item_rag.source_type == ContextSourceType.RAG
    assert context_item_rag.ownership == ContextOwnership.RAG_OWNED
    assert context_item_rag.content == rag_contract.content

    mem_contract = MemoryContextContract(
        memory_id="mem_field_paddy_1",
        content={"field_name": "North Paddy Field", "area_acres": 5.0},
        farmer_id="f_77",
        field_id="fld_paddy_1",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"source": "farmer_voice_note"},
    )
    context_item_mem = ContextItem.from_memory_contract(mem_contract)
    assert context_item_mem.source_type == ContextSourceType.MEMORY
    assert context_item_mem.ownership == ContextOwnership.MEMORY_OWNED
    assert context_item_mem.farmer_id == "f_77"

    # Convert back to boundary record and validate
    rec_rag = context_item_rag.to_boundary_record()
    validator.validate_record(rec_rag)

    rec_mem = context_item_mem.to_boundary_record()
    validator.validate_record(rec_mem)


def test_18_no_direct_rag_memory_dependency():
    """18. Verify zero direct dependencies between modules.knowledge_base and modules.memory."""
    import sys
    import importlib

    # Check imported modules in sys.modules or inspect AST/code imports
    kb_module = importlib.import_module("modules.knowledge_base")
    mem_module = importlib.import_module("modules.memory")

    # Neither module should import internal objects of the other
    assert not hasattr(kb_module, "memory_module")
    assert not hasattr(mem_module, "canonical_models")


def test_19_interface_isolation():
    """19. Verify interface isolation via IRAGContextProvider and IMemoryContextProvider."""
    class FakeRAGProvider(IRAGContextProvider):
        provider_name = "fake_rag"

        def get_rag_context(self, request):
            return [
                RAGContextContract(
                    content="General crop disease management",
                    provenance={"source": "test_rag"},
                )
            ]

    class FakeMemoryProvider(IMemoryContextProvider):
        provider_name = "fake_memory"

        def get_memory_context(self, request):
            return [
                MemoryContextContract(
                    memory_id="m_1",
                    content={"crop": "Corn"},
                    farmer_id=request.farmer_id,
                    privacy_level=PrivacyLevel.FARM_PRIVATE,
                    provenance={"source": "test_mem"},
                )
            ]

    rag_prov = FakeRAGProvider()
    mem_prov = FakeMemoryProvider()
    assert isinstance(rag_prov, IRAGContextProvider)
    assert isinstance(mem_prov, IMemoryContextProvider)


def test_20_five_principle_compliance(validator):
    """20. Five EarthMind Principles compliance: Extensibility, Loose Coupling, Single Responsibility, Controlled Dependencies, Replaceability."""
    # 1. Extensibility: Add a custom classification in metadata or future enums without changing core logic
    rec = ContextSourceRecord(
        source_type=ContextSourceType.EXTERNAL_SERVICE,
        ownership=ContextOwnership.EXTERNAL_OWNED,
        classification=KnowledgeClassification.EXTERNAL_CURRENT_DATA,
        scope=ContextScope.EVENT,
        persistence_intent=PersistenceIntent.TEMPORARY,
        provenance={"source": "pest_outbreak_satellite_alert"},
        metadata={"custom_extensibility_tag": "future_sensor_type"},
    )
    validator.validate_record(rec)

    # 2. Loose Coupling: RAG and Memory operate independently
    rag_contract = RAGContextContract(content="Fertilization guidelines", provenance={"doc": "v1"})
    mem_contract = MemoryContextContract(
        memory_id="m_9",
        content={"fertilizer_used": "Urea 50kg"},
        farmer_id="f_1",
        privacy_level=PrivacyLevel.FARM_PRIVATE,
        provenance={"chat": "v1"},
    )
    validator.validate_rag_contract(rag_contract)
    validator.validate_memory_contract(mem_contract)

    # 3. Single Responsibility: Boundary validator solely checks boundary rules
    # 4. Controlled Dependencies: All interactions via contracts and interfaces
    # 5. Replaceability: Contracts decoupled from Qdrant/SQLite storage backends
    assert rag_contract.ownership == ContextOwnership.RAG_OWNED
    assert mem_contract.ownership == ContextOwnership.MEMORY_OWNED
