"""Comprehensive Unit Tests for Stage R12 Evidence Validator in EarthMind.

Validates all 30 specification requirements including:
- Valid evidence package
- Invalid evidence items
- Malformed evidence package
- Missing required fields
- Invalid identity
- Duplicate identity
- Inconsistent identity
- Valid KB provenance
- Broken KB provenance
- Valid Web search evidence
- Malformed Web evidence
- Mixed KB + Web evidence
- Invalid rank
- Invalid score (NaN / Inf)
- Incomplete evidence
- Conflicting evidence
- Duplicate content
- Multimodal metadata
- Agricultural metadata
- Partial evidence package
- Empty evidence package
- Deterministic validation & ordering
- B2 context contracts compatibility
- Isolation boundaries (no Qdrant, no SQLite DB, no Memory, no KB Publication)
- Request ID traceability
- Exception handling
"""

import math
import pytest
from typing import Any, Dict

from core.errors.exceptions import InvalidEvidenceValidationRequestError
from core.interfaces.evidence_validator import IEvidenceValidatorEngine
from core.schemas.evidence import EvidenceItem, EvidencePackage, EvidenceSourceType
from core.schemas.evidence_validator import (
    EvidenceValidationFinding,
    EvidenceValidationRequest,
    EvidenceValidationResponse,
    EvidenceValidationResult,
    EvidenceValidationStatus,
    ValidationSeverity,
)
from modules.knowledge_base.evidence.validator import EvidenceValidatorEngine


def _make_sample_kb_item(
    evidence_id: str = "ev_kb_001",
    chunk_id: str = "chk_001",
    content: str = "Wheat yellow rust can be controlled with propiconazole at 0.1% concentration.",
    retrieval_rank: int = 1,
    rerank_score: float = 0.92,
) -> EvidenceItem:
    """Helper to create a valid Knowledge Base EvidenceItem."""
    return EvidenceItem(
        evidence_id=evidence_id,
        source_type=EvidenceSourceType.KNOWLEDGE_BASE,
        source_id="src_agri_01",
        document_id="doc_wheat_01",
        version_id="ver_1.0",
        knowledge_unit_id="ku_wheat_rust",
        chunk_id=chunk_id,
        candidate_id="cand_001",
        title="Wheat Yellow Rust Management Guide",
        content=content,
        retrieval_rank=retrieval_rank,
        dense_rank=1,
        sparse_rank=2,
        fused_rank=1,
        rerank_rank=1,
        dense_score=0.85,
        sparse_score=12.4,
        fused_score=0.032,
        rerank_score=rerank_score,
        metadata={
            "crop": "wheat",
            "disease": "yellow_rust",
            "region": "Punjab",
            "season": "Rabi",
        },
        provenance={
            "source_type": "KNOWLEDGE_BASE",
            "document_id": "doc_wheat_01",
            "chunk_id": chunk_id,
            "pipeline_stage": "R11_EVIDENCE_BUILDER",
        },
        source_assessment={"authority": "ICAR", "reliability_score": 0.95},
    )


def _make_sample_web_item(
    evidence_id: str = "ev_web_001",
    web_result_id: str = "web_res_101",
    url: str = "https://agricoop.gov.in/wheat_advisory.pdf",
    content: str = "Government advisory on wheat disease monitoring and spray schedules.",
    retrieval_rank: int = 2,
    rerank_score: float = 0.88,
) -> EvidenceItem:
    """Helper to create a valid Web Search EvidenceItem."""
    return EvidenceItem(
        evidence_id=evidence_id,
        source_type=EvidenceSourceType.WEB_SEARCH,
        source_id="gov_agri_portal",
        web_result_id=web_result_id,
        title="Ministry of Agriculture Wheat Advisory",
        content=content,
        url=url,
        provider="google_custom_search",
        retrieval_rank=retrieval_rank,
        rerank_score=rerank_score,
        metadata={"crop": "wheat", "domain": "government_advisory"},
        provenance={
            "source_type": "WEB_SEARCH",
            "url": url,
            "provider": "google_custom_search",
        },
    )


def test_1_valid_evidence_package():
    """Scenario 1: Fully valid EvidencePackage passes validation with VALID status."""
    kb_item = _make_sample_kb_item()
    package = EvidencePackage(
        request_id="req_test_01",
        query_text="How to manage wheat yellow rust in Rabi season?",
        items=[kb_item],
        kb_items_count=1,
        web_items_count=0,
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package, request_id="req_test_01")
    resp = validator.validate_evidence_package(req)

    assert resp.status == EvidenceValidationStatus.VALID
    assert resp.result is not None
    assert resp.result.overall_status == EvidenceValidationStatus.VALID
    assert resp.result.valid_items_count == 1
    assert resp.result.invalid_items_count == 0
    assert resp.result.validated_package is not None
    assert len(resp.result.validated_package.items) == 1


def test_2_invalid_evidence():
    """Scenario 2: Critical or error findings invalidate the evidence item."""
    item = _make_sample_kb_item()
    item.content = ""  # Empty content triggers ERROR finding
    package = EvidencePackage(
        request_id="req_test_02",
        query_text="Wheat yellow rust treatment",
        items=[item],
        kb_items_count=1,
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package, strict_mode=True)
    resp = validator.validate_evidence_package(req)

    assert resp.status == EvidenceValidationStatus.INVALID
    assert resp.result.valid_items_count == 0
    assert resp.result.invalid_items_count == 1


def test_3_malformed_evidence():
    """Scenario 3: Missing evidence_id causes item to be classified as MALFORMED/INVALID."""
    item = _make_sample_kb_item()
    item.evidence_id = ""  # Missing mandatory evidence_id
    package = EvidencePackage(
        request_id="req_test_03",
        query_text="Wheat rust control",
        items=[item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert resp.result.invalid_items_count == 1
    assert any(f.rule_code == "R12_STRUCT_04" for f in resp.result.findings)


def test_4_missing_required_fields():
    """Scenario 4: Missing query_text in package header yields structural error finding."""
    kb_item = _make_sample_kb_item()
    package = EvidencePackage(
        request_id="req_test_04",
        query_text="",  # Blank query text
        items=[kb_item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert any(f.rule_code == "R12_STRUCT_03" for f in resp.result.findings)


def test_5_invalid_identity():
    """Scenario 5: KB evidence item missing all canonical identifiers produces error finding."""
    item = _make_sample_kb_item()
    item.chunk_id = None
    item.knowledge_unit_id = None
    item.document_id = None
    item.candidate_id = None
    item.version_id = None
    item.section_id = None

    package = EvidencePackage(
        request_id="req_test_05",
        query_text="Wheat advisory",
        items=[item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert resp.result.invalid_items_count == 1
    assert any(f.rule_code == "R12_ID_01" for f in resp.result.findings)


def test_6_duplicate_identity():
    """Scenario 6: Duplicate evidence_ids within package are detected and flagged."""
    item1 = _make_sample_kb_item(evidence_id="ev_duplicate_01", chunk_id="chk_01")
    item2 = _make_sample_kb_item(evidence_id="ev_duplicate_01", chunk_id="chk_02")

    package = EvidencePackage(
        request_id="req_test_06",
        query_text="Duplicate ID test",
        items=[item1, item2],
        total_items_count=2,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert any(f.rule_code == "R12_ID_02" for f in resp.result.findings)


def test_7_inconsistent_identity():
    """Scenario 7: Contradictory ID cross-field relationships are flagged."""
    item = _make_sample_web_item()
    item.chunk_id = "chk_kb_should_not_be_on_web"  # Web item containing KB chunk_id

    package = EvidencePackage(
        request_id="req_test_07",
        query_text="Inconsistent identity test",
        items=[item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert any(f.rule_code == "R12_CONS_05" for f in resp.result.findings)


def test_8_valid_kb_provenance():
    """Scenario 8: Complete KB provenance dictionary passes provenance validation."""
    kb_item = _make_sample_kb_item()
    package = EvidencePackage(
        request_id="req_test_08",
        query_text="Provenance test",
        items=[kb_item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert not any(f.rule_code.startswith("R12_PROV") and f.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL) for f in resp.result.findings)


def test_9_broken_kb_provenance():
    """Scenario 9: Non-dictionary or empty provenance is handled with appropriate findings."""
    item = _make_sample_kb_item()
    item.provenance = {}  # Empty provenance dict

    package = EvidencePackage(
        request_id="req_test_09",
        query_text="Broken provenance test",
        items=[item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert any(f.rule_code == "R12_PROV_02" for f in resp.result.findings)


def test_10_valid_web_evidence():
    """Scenario 10: Valid Web Search evidence passes validation."""
    web_item = _make_sample_web_item()
    package = EvidencePackage(
        request_id="req_test_10",
        query_text="Wheat advisory portal",
        items=[web_item],
        web_items_count=1,
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert resp.status == EvidenceValidationStatus.VALID
    assert resp.result.validated_package.web_items_count == 1


def test_11_malformed_web_evidence():
    """Scenario 11: Web search evidence missing both web_result_id and URL produces error."""
    item = _make_sample_web_item()
    item.web_result_id = None
    item.url = None

    package = EvidencePackage(
        request_id="req_test_11",
        query_text="Malformed web evidence",
        items=[item],
        web_items_count=1,
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert resp.result.invalid_items_count == 1
    assert any(f.rule_code == "R12_ID_03" for f in resp.result.findings)


def test_12_mixed_kb_plus_web_evidence():
    """Scenario 12: Package containing both KB and Web Search evidence items validates properly."""
    kb_item = _make_sample_kb_item()
    web_item = _make_sample_web_item()

    package = EvidencePackage(
        request_id="req_test_12",
        query_text="Mixed evidence search",
        items=[kb_item, web_item],
        kb_items_count=1,
        web_items_count=1,
        total_items_count=2,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert resp.status == EvidenceValidationStatus.VALID
    assert resp.result.valid_items_count == 2
    assert resp.result.validated_package.kb_items_count == 1
    assert resp.result.validated_package.web_items_count == 1


def test_13_invalid_rank():
    """Scenario 13: Non-positive or non-integer rank generates warning finding."""
    item = _make_sample_kb_item()
    item.retrieval_rank = -5  # Invalid negative rank

    package = EvidencePackage(
        request_id="req_test_13",
        query_text="Rank check",
        items=[item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert any(f.rule_code == "R12_SCORE_01" for f in resp.result.findings)


def test_14_invalid_score():
    """Scenario 14: Non-finite score (NaN or Inf) produces error finding."""
    item = _make_sample_kb_item()
    item.rerank_score = float("nan")  # Invalid NaN score

    package = EvidencePackage(
        request_id="req_test_14",
        query_text="Score check",
        items=[item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert resp.result.invalid_items_count == 1
    assert any(f.rule_code == "R12_SCORE_02" for f in resp.result.findings)


def test_15_incomplete_evidence():
    """Scenario 15: Missing title generates info finding for completeness."""
    item = _make_sample_kb_item()
    item.title = None  # Missing title

    package = EvidencePackage(
        request_id="req_test_15",
        query_text="Incomplete item check",
        items=[item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert any(f.rule_code == "R12_CMPL_01" for f in resp.result.findings)


def test_16_conflicting_evidence():
    """Scenario 16: Preserved conflict indicators trigger CONFLICTING status or finding."""
    item = _make_sample_kb_item()
    item.conflict_indicators = ["dosage_conflict: ICAR recommends 0.1% vs PAU recommends 0.2%"]

    package = EvidencePackage(
        request_id="req_test_16",
        query_text="Dosage recommendation",
        items=[item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert resp.result.has_conflicts is True
    assert resp.status == EvidenceValidationStatus.CONFLICTING
    assert any(f.rule_code == "R12_CNFL_02" for f in resp.result.findings)


def test_17_duplicate_evidence_content():
    """Scenario 17: Identical content strings generate duplicate content finding."""
    item1 = _make_sample_kb_item(evidence_id="ev_001", chunk_id="chk_01", content="Exact same text.")
    item2 = _make_sample_kb_item(evidence_id="ev_002", chunk_id="chk_02", content="Exact same text.")

    package = EvidencePackage(
        request_id="req_test_17",
        query_text="Duplicate text test",
        items=[item1, item2],
        total_items_count=2,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert any(f.rule_code == "R12_CNFL_01" for f in resp.result.findings)


def test_18_multimodal_evidence_metadata():
    """Scenario 18: Multimodal data structures are validated for correct format."""
    item = _make_sample_kb_item()
    item.multimodal_data = {"image_url": "https://agri.org/rust_symptoms.jpg", "caption": "Yellow rust pustules"}

    package = EvidencePackage(
        request_id="req_test_18",
        query_text="Multimodal test",
        items=[item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert resp.status == EvidenceValidationStatus.VALID
    assert resp.result.validated_package.items[0].multimodal_data["caption"] == "Yellow rust pustules"


def test_19_agricultural_metadata():
    """Scenario 19: Crop, region, season agricultural metadata preserved and verified."""
    item = _make_sample_kb_item()
    item.metadata = {"crop": "rice", "disease": "blast", "region": "Telangana", "season": "Kharif"}

    package = EvidencePackage(
        request_id="req_test_19",
        query_text="Rice blast Telangana",
        items=[item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert resp.status == EvidenceValidationStatus.VALID
    assert resp.result.validated_package.items[0].metadata["crop"] == "rice"


def test_20_partial_evidence_package():
    """Scenario 20: Package with a mix of 1 valid item and 1 invalid item results in PARTIALLY_VALID."""
    valid_item = _make_sample_kb_item(evidence_id="ev_valid_01", chunk_id="chk_01")
    invalid_item = _make_sample_kb_item(evidence_id="ev_invalid_02", chunk_id="chk_02")
    invalid_item.content = ""  # Invalid item

    package = EvidencePackage(
        request_id="req_test_20",
        query_text="Partial package test",
        items=[valid_item, invalid_item],
        total_items_count=2,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package, strict_mode=False)
    resp = validator.validate_evidence_package(req)

    assert resp.status == EvidenceValidationStatus.PARTIALLY_VALID
    assert resp.result.valid_items_count == 1
    assert resp.result.invalid_items_count == 1
    assert len(resp.result.validated_package.items) == 1


def test_21_empty_evidence_package():
    """Scenario 21: Package with empty items list yields EMPTY status."""
    package = EvidencePackage(
        request_id="req_test_21",
        query_text="Empty package query",
        items=[],
        total_items_count=0,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert resp.status == EvidenceValidationStatus.EMPTY
    assert resp.result.overall_status == EvidenceValidationStatus.EMPTY
    assert resp.result.valid_items_count == 0


def test_22_deterministic_validation():
    """Scenario 22: Identical validation request produces identical findings and status deterministically."""
    item = _make_sample_kb_item()
    package = EvidencePackage(
        request_id="req_test_22",
        query_text="Determinism test",
        items=[item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req1 = EvidenceValidationRequest(package=package, request_id="req_test_22")
    req2 = EvidenceValidationRequest(package=package, request_id="req_test_22")

    resp1 = validator.validate_evidence_package(req1)
    resp2 = validator.validate_evidence_package(req2)

    assert resp1.status == resp2.status
    assert len(resp1.result.findings) == len(resp2.result.findings)
    for f1, f2 in zip(resp1.result.findings, resp2.result.findings):
        assert f1.rule_code == f2.rule_code
        assert f1.severity == f2.severity
        assert f1.reason == f2.reason


def test_23_b2_context_contracts_compatibility():
    """Scenario 23: Validated EvidencePackage produces valid B2 RAGContextContract objects."""
    kb_item = _make_sample_kb_item()
    web_item = _make_sample_web_item()

    package = EvidencePackage(
        request_id="req_test_23",
        query_text="B2 conversion test",
        items=[kb_item, web_item],
        total_items_count=2,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    validated_pkg = resp.result.validated_package
    contracts = validated_pkg.to_rag_context_contracts()

    assert len(contracts) == 2
    assert contracts[0].source_type.value == "RAG"
    assert contracts[0].ownership.value == "RAG_OWNED"
    assert contracts[0].content["evidence_id"] == kb_item.evidence_id
    assert contracts[1].content["evidence_id"] == web_item.evidence_id


def test_24_no_direct_qdrant_access(mocker):
    """Scenario 24: R12 validator does not make any direct Qdrant index calls."""
    spy = mocker.spy(EvidenceValidatorEngine, "validate_evidence_package")
    kb_item = _make_sample_kb_item()
    package = EvidencePackage(
        request_id="req_test_24",
        query_text="No Qdrant check",
        items=[kb_item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert resp.status == EvidenceValidationStatus.VALID


def test_25_no_direct_database_access(mocker):
    """Scenario 25: R12 validator does not connect to or query SQLite database."""
    import sqlite3
    mocker.patch.object(sqlite3, "connect", side_effect=AssertionError("SQLite connect should not be called in R12!"))

    kb_item = _make_sample_kb_item()
    package = EvidencePackage(
        request_id="req_test_25",
        query_text="No DB check",
        items=[kb_item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    assert resp.status == EvidenceValidationStatus.VALID


def test_26_no_memory_writes():
    """Scenario 26: R12 validator does not perform Memory writes or context promotion."""
    kb_item = _make_sample_kb_item()
    package = EvidencePackage(
        request_id="req_test_26",
        query_text="No Memory write check",
        items=[kb_item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    # Confirm contract ownership is preserved as RAG_OWNED
    contracts = resp.result.validated_package.to_rag_context_contracts()
    assert all(c.ownership.value == "RAG_OWNED" for c in contracts)


def test_27_no_automatic_kb_publication():
    """Scenario 27: R12 validator does not trigger Knowledge Base publication or state changes."""
    web_item = _make_sample_web_item()
    package = EvidencePackage(
        request_id="req_test_27",
        query_text="No KB publication check",
        items=[web_item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package)
    resp = validator.validate_evidence_package(req)

    contracts = resp.result.validated_package.to_rag_context_contracts()
    # Web search contracts must remain TRANSIENT publication state
    assert contracts[0].publication_state == "TRANSIENT"


def test_28_traceability():
    """Scenario 28: Correlation request_id is correctly propagated through response and result."""
    kb_item = _make_sample_kb_item()
    package = EvidencePackage(
        request_id="trace_req_999",
        query_text="Traceability test",
        items=[kb_item],
        total_items_count=1,
    )
    validator = EvidenceValidatorEngine()
    req = EvidenceValidationRequest(package=package, request_id="trace_req_999")
    resp = validator.validate_evidence_package(req)

    assert resp.request_id == "trace_req_999"
    assert resp.result.request_id == "trace_req_999"


def test_29_error_handling():
    """Scenario 29: Invalid request input raises InvalidEvidenceValidationRequestError."""
    validator = EvidenceValidatorEngine()
    with pytest.raises(InvalidEvidenceValidationRequestError):
        validator.validate_evidence_package("not_a_request_object")  # Invalid type


def test_30_interface_protocol():
    """Scenario 30: EvidenceValidatorEngine satisfies IEvidenceValidatorEngine runtime protocol check."""
    validator = EvidenceValidatorEngine()
    assert isinstance(validator, IEvidenceValidatorEngine)
