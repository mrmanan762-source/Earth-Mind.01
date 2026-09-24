from typing import Optional, Dict, Any
from core.errors.exceptions import (
    BoundaryValidationError,
    PromotionNotAllowedError,
    ScopeViolationBoundaryError,
    PrivacyBoundaryError,
)
from modules.context.schemas import PrivacyLevel
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


class BoundaryValidator:
    """Executable validator enforcing C.3 RAG-Memory boundary contracts and classification rules."""

    def validate_record(
        self,
        record: ContextSourceRecord,
        allow_persistent_observation: bool = False,
    ) -> None:
        """Validate a ContextSourceRecord against all C.3 boundary and classification rules."""
        if not isinstance(record, ContextSourceRecord):
            raise BoundaryValidationError("Record must be an instance of ContextSourceRecord")

        # 1. Missing mandatory fields
        if record.source_type is None:
            raise BoundaryValidationError("Missing mandatory field: source_type")
        if record.ownership is None:
            raise BoundaryValidationError("Missing mandatory field: ownership")
        if record.classification is None:
            raise BoundaryValidationError("Missing mandatory field: classification")
        if record.scope is None:
            raise BoundaryValidationError("Missing mandatory field: scope")
        if record.persistence_intent is None:
            raise BoundaryValidationError("Missing mandatory field: persistence_intent")

        # Provenance check
        if record.provenance is None or not isinstance(record.provenance, dict) or len(record.provenance) == 0:
            raise BoundaryValidationError("Missing or empty mandatory field: provenance")

        # 2. Scope vs Classification rules
        farmer_scopes = {
            ContextScope.FARMER,
            ContextScope.FARM,
            ContextScope.FIELD,
            ContextScope.CROP_CYCLE,
        }

        # Rule: RAG / GENERAL_KNOWLEDGE with farmer scope is invalid
        if record.classification == KnowledgeClassification.GENERAL_KNOWLEDGE:
            if record.scope in farmer_scopes:
                raise ScopeViolationBoundaryError(
                    scope=record.scope.value,
                    details=f"GENERAL_KNOWLEDGE cannot have farmer-specific scope '{record.scope.value}'",
                )

        # Rule: Memory / FARMER_KNOWLEDGE / FIELD_KNOWLEDGE with global/regional scope is invalid
        if record.classification in {
            KnowledgeClassification.FARMER_KNOWLEDGE,
            KnowledgeClassification.FIELD_KNOWLEDGE,
        }:
            if record.scope in {ContextScope.GLOBAL, ContextScope.REGIONAL}:
                raise ScopeViolationBoundaryError(
                    scope=record.scope.value,
                    details=f"Memory classification '{record.classification.value}' cannot have global/regional scope '{record.scope.value}'",
                )

        # 3. Ownership vs Classification rules
        if record.classification == KnowledgeClassification.GENERAL_KNOWLEDGE:
            if record.ownership not in {ContextOwnership.RAG_OWNED, ContextOwnership.EXTERNAL_OWNED}:
                raise BoundaryValidationError(
                    f"GENERAL_KNOWLEDGE must be RAG_OWNED or EXTERNAL_OWNED, got '{record.ownership.value}'"
                )

        elif record.classification in {
            KnowledgeClassification.FARMER_KNOWLEDGE,
            KnowledgeClassification.FIELD_KNOWLEDGE,
        }:
            if record.ownership != ContextOwnership.MEMORY_OWNED:
                raise BoundaryValidationError(
                    f"Farmer/Field knowledge classification must be MEMORY_OWNED, got '{record.ownership.value}'"
                )

        elif record.classification == KnowledgeClassification.SESSION_CONTEXT:
            if record.ownership != ContextOwnership.RUNTIME_OWNED:
                raise BoundaryValidationError(
                    f"SESSION_CONTEXT classification must be RUNTIME_OWNED, got '{record.ownership.value}'"
                )

        elif record.classification == KnowledgeClassification.EXTERNAL_CURRENT_DATA:
            if record.ownership not in {ContextOwnership.EXTERNAL_OWNED, ContextOwnership.RAG_OWNED}:
                raise BoundaryValidationError(
                    f"EXTERNAL_CURRENT_DATA classification must be EXTERNAL_OWNED or RAG_OWNED, got '{record.ownership.value}'"
                )

        elif record.classification == KnowledgeClassification.OBSERVATION:
            if record.ownership not in {
                ContextOwnership.RUNTIME_OWNED,
                ContextOwnership.MEMORY_OWNED,
                ContextOwnership.EXTERNAL_OWNED,
            }:
                raise BoundaryValidationError(
                    f"OBSERVATION classification has invalid ownership '{record.ownership.value}'"
                )

        # 4. Privacy metadata check for farmer/field information
        if (
            record.scope in farmer_scopes
            or record.classification
            in {KnowledgeClassification.FARMER_KNOWLEDGE, KnowledgeClassification.FIELD_KNOWLEDGE}
        ):
            if record.privacy_level is None:
                raise PrivacyBoundaryError(
                    f"Privacy metadata (privacy_level) is required for farmer/field scoped context ('{record.scope.value}')"
                )

        # 5. Observation persistence rule
        if record.classification == KnowledgeClassification.OBSERVATION:
            if record.persistence_intent == PersistenceIntent.PERSISTENT and record.ownership == ContextOwnership.MEMORY_OWNED:
                if not allow_persistent_observation:
                    raise BoundaryValidationError(
                        "OBSERVATION cannot be automatically promoted to persistent MEMORY_OWNED context without explicit Memory policy validation"
                    )

        # 6. Web Search / External Current Data non-publication rule
        if record.classification == KnowledgeClassification.EXTERNAL_CURRENT_DATA:
            if record.ownership == ContextOwnership.MEMORY_OWNED:
                raise BoundaryValidationError(
                    "EXTERNAL_CURRENT_DATA cannot be directly assigned MEMORY_OWNED ownership"
                )
            if (
                record.ownership == ContextOwnership.RAG_OWNED
                and record.persistence_intent == PersistenceIntent.PERSISTENT
            ):
                # Check provenance for formal ingestion
                if "knowledge_ingestion_pipeline" not in record.provenance:
                    raise BoundaryValidationError(
                        "EXTERNAL_CURRENT_DATA (web search evidence) cannot automatically become permanent RAG knowledge without formal ingestion and publication"
                    )

    def validate_promotion(
        self,
        source_ownership: ContextOwnership,
        target_ownership: ContextOwnership,
    ) -> None:
        """Validate whether cross-domain promotion between ownerships is allowed."""
        if source_ownership != target_ownership:
            raise PromotionNotAllowedError(
                source_ownership=source_ownership.value,
                target_ownership=target_ownership.value,
                reason="Automatic cross-domain promotion between RAG and Memory is strictly prohibited by C.3 policy.",
            )

    def validate_rag_contract(self, rag_contract: RAGContextContract) -> None:
        """Validate a RAGContextContract for C.3 compliance."""
        if not isinstance(rag_contract, RAGContextContract):
            raise BoundaryValidationError("rag_contract must be an instance of RAGContextContract")

        if rag_contract.source_type not in {ContextSourceType.RAG, ContextSourceType.EXTERNAL_SERVICE}:
            raise BoundaryValidationError(
                f"RAG contract source_type must be RAG or EXTERNAL_SERVICE, got '{rag_contract.source_type.value}'"
            )

        # Convert to source record and validate
        record = rag_contract.to_source_record()
        self.validate_record(record)

        # Verify no farmer private scope in RAG contract
        if record.scope in {
            ContextScope.FARMER,
            ContextScope.FARM,
            ContextScope.FIELD,
            ContextScope.CROP_CYCLE,
        }:
            raise ScopeViolationBoundaryError(
                scope=record.scope.value,
                details="RAG context contract cannot contain private farmer/farm/field/crop_cycle scope",
            )

    def validate_memory_contract(self, memory_contract: MemoryContextContract) -> None:
        """Validate a MemoryContextContract for C.3 compliance."""
        if not isinstance(memory_contract, MemoryContextContract):
            raise BoundaryValidationError("memory_contract must be an instance of MemoryContextContract")

        if not memory_contract.memory_id or not memory_contract.memory_id.strip():
            raise BoundaryValidationError("Memory contract must contain a non-empty memory_id")

        if memory_contract.source_type not in {
            ContextSourceType.MEMORY,
            ContextSourceType.SESSION,
            ContextSourceType.OBSERVATION,
        }:
            raise BoundaryValidationError(
                f"Memory contract source_type must be MEMORY, SESSION, or OBSERVATION, got '{memory_contract.source_type.value}'"
            )

        # Convert to source record and validate
        record = memory_contract.to_source_record()
        self.validate_record(record)

        # Verify Memory contract is not treated as global/regional general RAG knowledge
        if record.scope in {ContextScope.GLOBAL, ContextScope.REGIONAL}:
            raise ScopeViolationBoundaryError(
                scope=record.scope.value,
                details="Memory context contract cannot be classified as global or regional general knowledge",
            )
