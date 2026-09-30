"""Stage R12 Evidence Validator Engine implementation for EarthMind.

Validates Evidence Packages produced by Stage R11 Evidence Builder before
handoff to B2 Context Manager and B3 Reasoning Engine.

Enforces structural, identity, provenance, web evidence, rank/score, completeness,
consistency, duplicate/conflict, and multimodal metadata checks without performing
agricultural reasoning, truth evaluation, database access, or model inference.
"""

import math
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from core.config.settings import EvidenceValidatorConfig, settings
from core.errors.exceptions import (
    EvidenceValidationExecutionError,
    InvalidEvidenceValidationRequestError,
)
from core.interfaces.evidence_validator import IEvidenceValidatorEngine
from core.schemas.evidence import EvidenceItem, EvidencePackage, EvidenceSourceType
from core.schemas.evidence_validator import (
    EvidenceItemValidationOutcome,
    EvidenceValidationFinding,
    EvidenceValidationRequest,
    EvidenceValidationResponse,
    EvidenceValidationResult,
    EvidenceValidationStatus,
    ValidationSeverity,
)


class EvidenceValidatorEngine(IEvidenceValidatorEngine):
    """
    Production-grade Stage R12 Evidence Validator Engine.
    Validates evidence package structure, identity, provenance, ranks/scores,
    web evidence, completeness, consistency, duplicate/conflict indicators,
    and metadata formatting deterministically.
    """

    def __init__(self, config: Optional[EvidenceValidatorConfig] = None):
        """Initialize the validator engine with optional configuration override."""
        self.config = config or settings.evidence_validator

    def validate_evidence_package(
        self, request: EvidenceValidationRequest
    ) -> EvidenceValidationResponse:
        """
        Main entry point to validate an EvidencePackage.

        Args:
            request: EvidenceValidationRequest containing EvidencePackage and runtime policy settings.

        Returns:
            EvidenceValidationResponse with overall status, validation findings, item outcomes,
            and sanitized EvidencePackage ready for B2.
        """
        start_time = time.time()

        if not isinstance(request, EvidenceValidationRequest):
            raise InvalidEvidenceValidationRequestError(
                "Request must be an instance of EvidenceValidationRequest."
            )

        # Tracing ID resolution
        request_id = request.request_id
        if not request_id and request.package:
            request_id = request.package.request_id

        strict_mode = request.strict_mode or self.config.strict_mode

        # Handle None package
        if request.package is None:
            exec_time = (time.time() - start_time) * 1000.0
            finding = EvidenceValidationFinding(
                rule_code="R12_STRUCT_01",
                severity=ValidationSeverity.CRITICAL,
                reason="EvidencePackage is None.",
            )
            result = EvidenceValidationResult(
                request_id=request_id,
                overall_status=EvidenceValidationStatus.INVALID,
                validated_package=None,
                item_outcomes=[],
                findings=[finding],
                valid_items_count=0,
                invalid_items_count=0,
                total_items_count=0,
                has_conflicts=False,
                execution_time_ms=exec_time,
            )
            return EvidenceValidationResponse(
                request_id=request_id,
                status=EvidenceValidationStatus.INVALID,
                result=result,
                warnings=["EvidencePackage is missing."],
                error_message="EvidencePackage is None.",
                execution_time_ms=exec_time,
            )

        package = request.package
        all_findings: List[EvidenceValidationFinding] = []
        item_outcomes: List[EvidenceItemValidationOutcome] = []

        # Step 1: Package Header Validation
        pkg_findings = self._validate_package_header(package)
        all_findings.extend(pkg_findings)

        # Check for empty package
        if not package.items:
            exec_time = (time.time() - start_time) * 1000.0
            finding = EvidenceValidationFinding(
                rule_code="R12_STRUCT_02",
                severity=ValidationSeverity.INFO,
                reason="EvidencePackage contains no evidence items.",
            )
            all_findings.append(finding)

            # Sort findings deterministically
            sorted_findings = self._sort_findings(all_findings)
            empty_status = (
                EvidenceValidationStatus.EMPTY
                if not any(f.severity == ValidationSeverity.CRITICAL for f in sorted_findings)
                else EvidenceValidationStatus.INVALID
            )

            # Return empty sanitized package
            sanitized_empty_pkg = package.model_copy(deep=True)
            sanitized_empty_pkg.items = []
            sanitized_empty_pkg.total_items_count = 0
            sanitized_empty_pkg.kb_items_count = 0
            sanitized_empty_pkg.web_items_count = 0

            result = EvidenceValidationResult(
                request_id=request_id,
                overall_status=empty_status,
                validated_package=sanitized_empty_pkg,
                item_outcomes=[],
                findings=sorted_findings,
                valid_items_count=0,
                invalid_items_count=0,
                total_items_count=0,
                has_conflicts=False,
                execution_time_ms=exec_time,
            )
            return EvidenceValidationResponse(
                request_id=request_id,
                status=empty_status,
                result=result,
                execution_time_ms=exec_time,
            )

        # Step 2: Global Package Analysis (Duplicate evidence_ids, identical content, conflict indicators)
        global_findings, duplicate_ev_ids, duplicate_content_hashes = self._validate_global_package_checks(package)
        all_findings.extend(global_findings)

        # Step 3: Per-Item Validation
        valid_items: List[EvidenceItem] = []
        invalid_items_count = 0
        has_conflicts_flag = False

        for idx, item in enumerate(package.items):
            item_findings, is_valid, item_status = self._validate_evidence_item(
                item=item,
                package_request_id=request_id,
                is_duplicate_id=(item.evidence_id in duplicate_ev_ids),
                is_duplicate_content=(hash(item.content.strip()) in duplicate_content_hashes),
            )

            all_findings.extend(item_findings)

            if item.conflict_indicators:
                has_conflicts_flag = True

            outcome = EvidenceItemValidationOutcome(
                evidence_id=item.evidence_id if item and getattr(item, "evidence_id", None) else f"item_{idx}",
                is_valid=is_valid,
                status=item_status,
                findings=item_findings,
                item=item if is_valid else None,
            )
            item_outcomes.append(outcome)

            if is_valid:
                valid_items.append(item)
            else:
                invalid_items_count += 1

        # Step 4: Overall Status Calculation & Package Sanitization
        sorted_findings = self._sort_findings(all_findings)
        overall_status, validated_pkg = self._calculate_overall_status_and_package(
            original_package=package,
            valid_items=valid_items,
            item_outcomes=item_outcomes,
            all_findings=sorted_findings,
            strict_mode=strict_mode,
            has_conflicts=has_conflicts_flag,
        )

        exec_time = (time.time() - start_time) * 1000.0

        # Construct ValidationResult
        result = EvidenceValidationResult(
            request_id=request_id,
            overall_status=overall_status,
            validated_package=validated_pkg,
            item_outcomes=item_outcomes,
            findings=sorted_findings,
            valid_items_count=len(valid_items),
            invalid_items_count=invalid_items_count,
            total_items_count=len(package.items),
            has_conflicts=has_conflicts_flag,
            execution_time_ms=exec_time,
            metadata={
                "validator_version": self.config.validator_version,
                "strict_mode": strict_mode,
                "total_findings_count": len(sorted_findings),
            },
        )

        warnings_list = [
            f.reason for f in sorted_findings if f.severity in (ValidationSeverity.WARNING, ValidationSeverity.INFO)
        ]

        return EvidenceValidationResponse(
            request_id=request_id,
            status=overall_status,
            result=result,
            warnings=warnings_list,
            execution_time_ms=exec_time,
        )

    # -------------------------------------------------------------------------
    # Helper Validation Methods
    # -------------------------------------------------------------------------

    def _validate_package_header(
        self, package: EvidencePackage
    ) -> List[EvidenceValidationFinding]:
        """Validate top-level package fields and count consistency."""
        findings: List[EvidenceValidationFinding] = []

        if not package.query_text or not package.query_text.strip():
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_STRUCT_03",
                    severity=ValidationSeverity.ERROR,
                    field_path="query_text",
                    reason="Package query_text is empty or blank.",
                )
            )

        actual_items_count = len(package.items)
        if package.total_items_count != actual_items_count:
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_CONS_01",
                    severity=ValidationSeverity.WARNING,
                    field_path="total_items_count",
                    reason=f"Package total_items_count header ({package.total_items_count}) does not match actual items list length ({actual_items_count}).",
                    metadata={"header_count": package.total_items_count, "actual_count": actual_items_count},
                )
            )

        kb_count = sum(1 for item in package.items if item.source_type == EvidenceSourceType.KNOWLEDGE_BASE)
        web_count = sum(1 for item in package.items if item.source_type == EvidenceSourceType.WEB_SEARCH)

        if package.kb_items_count != kb_count:
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_CONS_02",
                    severity=ValidationSeverity.INFO,
                    field_path="kb_items_count",
                    reason=f"Package kb_items_count header ({package.kb_items_count}) mismatch actual count ({kb_count}).",
                )
            )

        if package.web_items_count != web_count:
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_CONS_03",
                    severity=ValidationSeverity.INFO,
                    field_path="web_items_count",
                    reason=f"Package web_items_count header ({package.web_items_count}) mismatch actual count ({web_count}).",
                )
            )

        return findings

    def _validate_global_package_checks(
        self, package: EvidencePackage
    ) -> Tuple[List[EvidenceValidationFinding], Set[str], Set[int]]:
        """Perform package-wide checks for duplicate IDs, duplicate content, and conflicting indicators."""
        findings: List[EvidenceValidationFinding] = []
        seen_ids: Set[str] = set()
        duplicate_ids: Set[str] = set()

        seen_content_hashes: Set[int] = set()
        duplicate_content_hashes: Set[int] = set()

        for item in package.items:
            # Duplicate evidence_id check
            if item.evidence_id:
                if item.evidence_id in seen_ids:
                    duplicate_ids.add(item.evidence_id)
                    findings.append(
                        EvidenceValidationFinding(
                            rule_code="R12_ID_02",
                            severity=ValidationSeverity.ERROR,
                            evidence_id=item.evidence_id,
                            field_path="evidence_id",
                            reason=f"Duplicate evidence_id '{item.evidence_id}' detected in EvidencePackage.",
                        )
                    )
                else:
                    seen_ids.add(item.evidence_id)

            # Duplicate content check
            if item.content and item.content.strip():
                c_hash = hash(item.content.strip())
                if c_hash in seen_content_hashes:
                    duplicate_content_hashes.add(c_hash)
                    findings.append(
                        EvidenceValidationFinding(
                            rule_code="R12_CNFL_01",
                            severity=ValidationSeverity.INFO,
                            evidence_id=item.evidence_id,
                            field_path="content",
                            reason=f"Duplicate content detected for evidence_id '{item.evidence_id}'.",
                        )
                    )
                else:
                    seen_content_hashes.add(c_hash)

        return findings, duplicate_ids, duplicate_content_hashes

    def _validate_evidence_item(
        self,
        item: EvidenceItem,
        package_request_id: Optional[str],
        is_duplicate_id: bool,
        is_duplicate_content: bool,
    ) -> Tuple[List[EvidenceValidationFinding], bool, EvidenceValidationStatus]:
        """Validate an individual EvidenceItem across all 10 R12 check categories."""
        findings: List[EvidenceValidationFinding] = []

        # Check category 1: Structure & Mandatory Fields
        f_struct = self._check_item_structure(item)
        findings.extend(f_struct)

        # Check category 2: Identity & Taxonomy
        f_id = self._check_item_identity(item)
        findings.extend(f_id)

        # Check category 3: Provenance & KB Lineage
        f_prov = self._check_item_provenance(item, package_request_id)
        findings.extend(f_prov)

        # Check category 4: Web Search Specific Validation
        if item.source_type == EvidenceSourceType.WEB_SEARCH:
            f_web = self._check_item_web_search(item)
            findings.extend(f_web)

        # Check category 5: Source Assessment Validation
        f_src = self._check_item_source_assessment(item)
        findings.extend(f_src)

        # Check category 6: Ranks and Scores Validation
        f_scores = self._check_item_ranks_and_scores(item)
        findings.extend(f_scores)

        # Check category 7: Completeness Validation
        f_cmpl = self._check_item_completeness(item)
        findings.extend(f_cmpl)

        # Check category 8: Consistency & Category Alignment
        f_cons = self._check_item_consistency(item)
        findings.extend(f_cons)

        # Check category 9: Conflict Indicators Preservation
        f_cnfl = self._check_item_conflicts(item)
        findings.extend(f_cnfl)

        # Check category 10: Multimodal and Agricultural Metadata
        f_meta = self._check_item_metadata(item)
        findings.extend(f_meta)

        # Determine validity and item-level status
        has_critical = any(f.severity == ValidationSeverity.CRITICAL for f in findings)
        has_error = any(f.severity == ValidationSeverity.ERROR for f in findings)
        has_warning = any(f.severity == ValidationSeverity.WARNING for f in findings)

        if has_critical:
            is_valid = False
            item_status = EvidenceValidationStatus.MALFORMED
        elif has_error or is_duplicate_id:
            is_valid = False
            item_status = EvidenceValidationStatus.INVALID
        elif any(f.rule_code in ("R12_PROV_01", "R12_PROV_02") for f in findings if f.severity == ValidationSeverity.WARNING):
            is_valid = True
            item_status = EvidenceValidationStatus.UNTRACEABLE
        elif item.conflict_indicators:
            is_valid = True
            item_status = EvidenceValidationStatus.CONFLICTING
        elif has_warning:
            is_valid = True
            item_status = EvidenceValidationStatus.PARTIALLY_VALID
        else:
            is_valid = True
            item_status = EvidenceValidationStatus.VALID

        return findings, is_valid, item_status

    def _check_item_structure(self, item: EvidenceItem) -> List[EvidenceValidationFinding]:
        """Category 1: Structural field checks."""
        findings: List[EvidenceValidationFinding] = []

        if not item.evidence_id or not str(item.evidence_id).strip():
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_STRUCT_04",
                    severity=ValidationSeverity.CRITICAL,
                    field_path="evidence_id",
                    reason="Evidence item is missing mandatory evidence_id.",
                )
            )

        if not item.source_type or item.source_type not in (EvidenceSourceType.KNOWLEDGE_BASE, EvidenceSourceType.WEB_SEARCH):
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_STRUCT_05",
                    severity=ValidationSeverity.CRITICAL,
                    evidence_id=item.evidence_id,
                    field_path="source_type",
                    reason=f"Evidence item has invalid source_type '{item.source_type}'.",
                )
            )

        if item.content is None or not isinstance(item.content, str) or not item.content.strip():
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_STRUCT_06",
                    severity=ValidationSeverity.ERROR,
                    evidence_id=item.evidence_id,
                    field_path="content",
                    reason="Evidence item content is missing or blank.",
                )
            )

        if item.retrieval_timestamp is None or not isinstance(item.retrieval_timestamp, (int, float)) or item.retrieval_timestamp <= 0:
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_STRUCT_07",
                    severity=ValidationSeverity.WARNING,
                    evidence_id=item.evidence_id,
                    field_path="retrieval_timestamp",
                    reason=f"Invalid retrieval_timestamp '{item.retrieval_timestamp}'.",
                )
            )

        if item.is_truncated and not item.truncation_reason:
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_STRUCT_08",
                    severity=ValidationSeverity.INFO,
                    evidence_id=item.evidence_id,
                    field_path="truncation_reason",
                    reason="item is_truncated is True, but truncation_reason is missing.",
                )
            )

        return findings

    def _check_item_identity(self, item: EvidenceItem) -> List[EvidenceValidationFinding]:
        """Category 2: Identity and ID taxonomy checks."""
        findings: List[EvidenceValidationFinding] = []

        if item.source_type == EvidenceSourceType.KNOWLEDGE_BASE:
            has_kb_id = any([
                item.chunk_id,
                item.knowledge_unit_id,
                item.document_id,
                item.candidate_id,
            ])
            if not has_kb_id:
                findings.append(
                    EvidenceValidationFinding(
                        rule_code="R12_ID_01",
                        severity=ValidationSeverity.ERROR,
                        evidence_id=item.evidence_id,
                        field_path="chunk_id",
                        reason="Knowledge Base evidence item is missing canonical identifiers (chunk_id/knowledge_unit_id/document_id/candidate_id).",
                    )
                )

        if item.source_type == EvidenceSourceType.WEB_SEARCH:
            if not item.web_result_id and not item.url:
                findings.append(
                    EvidenceValidationFinding(
                        rule_code="R12_ID_03",
                        severity=ValidationSeverity.ERROR,
                        evidence_id=item.evidence_id,
                        field_path="web_result_id",
                        reason="Web Search evidence item is missing both web_result_id and url reference.",
                    )
                )

        return findings

    def _check_item_provenance(
        self, item: EvidenceItem, package_request_id: Optional[str]
    ) -> List[EvidenceValidationFinding]:
        """Category 3: Provenance & Lineage checks."""
        findings: List[EvidenceValidationFinding] = []

        if not isinstance(item.provenance, dict):
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_PROV_01",
                    severity=ValidationSeverity.ERROR,
                    evidence_id=item.evidence_id,
                    field_path="provenance",
                    reason="Evidence item provenance must be a dictionary structure.",
                )
            )
            return findings

        if item.source_type == EvidenceSourceType.KNOWLEDGE_BASE:
            if not item.provenance and self.config.require_provenance:
                findings.append(
                    EvidenceValidationFinding(
                        rule_code="R12_PROV_02",
                        severity=ValidationSeverity.WARNING,
                        evidence_id=item.evidence_id,
                        field_path="provenance",
                        reason="Knowledge Base evidence item provenance dictionary is empty.",
                    )
                )

        if package_request_id and item.request_id and item.request_id != package_request_id:
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_PROV_03",
                    severity=ValidationSeverity.WARNING,
                    evidence_id=item.evidence_id,
                    field_path="request_id",
                    reason=f"Item request_id ('{item.request_id}') does not match package request_id ('{package_request_id}').",
                )
            )

        return findings

    def _check_item_web_search(self, item: EvidenceItem) -> List[EvidenceValidationFinding]:
        """Category 4: Web Search specific checks."""
        findings: List[EvidenceValidationFinding] = []

        if not item.url or not str(item.url).strip():
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_WEB_01",
                    severity=ValidationSeverity.WARNING,
                    evidence_id=item.evidence_id,
                    field_path="url",
                    reason="Web evidence item is missing URL reference.",
                )
            )

        if not item.provider and not item.source_id:
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_WEB_02",
                    severity=ValidationSeverity.INFO,
                    evidence_id=item.evidence_id,
                    field_path="provider",
                    reason="Web evidence item missing provider/source identification.",
                )
            )

        return findings

    def _check_item_source_assessment(self, item: EvidenceItem) -> List[EvidenceValidationFinding]:
        """Category 5: Source Assessment structural check."""
        findings: List[EvidenceValidationFinding] = []

        if item.source_assessment is not None and not isinstance(item.source_assessment, dict):
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_SRC_01",
                    severity=ValidationSeverity.WARNING,
                    evidence_id=item.evidence_id,
                    field_path="source_assessment",
                    reason="Source assessment metadata must be a valid dictionary structure if provided.",
                )
            )

        return findings

    def _check_item_ranks_and_scores(self, item: EvidenceItem) -> List[EvidenceValidationFinding]:
        """Category 6: Ranks and Scores checks."""
        findings: List[EvidenceValidationFinding] = []

        ranks = {
            "retrieval_rank": item.retrieval_rank,
            "dense_rank": item.dense_rank,
            "sparse_rank": item.sparse_rank,
            "fused_rank": item.fused_rank,
            "rerank_rank": item.rerank_rank,
        }

        for rank_name, val in ranks.items():
            if val is not None:
                if not isinstance(val, int) or val <= 0:
                    findings.append(
                        EvidenceValidationFinding(
                            rule_code="R12_SCORE_01",
                            severity=ValidationSeverity.WARNING,
                            evidence_id=item.evidence_id,
                            field_path=rank_name,
                            reason=f"Invalid rank value '{val}' for field '{rank_name}' (must be a positive integer).",
                        )
                    )

        scores = {
            "dense_score": item.dense_score,
            "sparse_score": item.sparse_score,
            "fused_score": item.fused_score,
            "rerank_score": item.rerank_score,
        }

        for score_name, val in scores.items():
            if val is not None:
                if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
                    findings.append(
                        EvidenceValidationFinding(
                            rule_code="R12_SCORE_02",
                            severity=ValidationSeverity.ERROR,
                            evidence_id=item.evidence_id,
                            field_path=score_name,
                            reason=f"Invalid non-finite score value '{val}' for field '{score_name}'.",
                        )
                    )

        return findings

    def _check_item_completeness(self, item: EvidenceItem) -> List[EvidenceValidationFinding]:
        """Category 7: Completeness checks."""
        findings: List[EvidenceValidationFinding] = []

        if not item.title:
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_CMPL_01",
                    severity=ValidationSeverity.INFO,
                    evidence_id=item.evidence_id,
                    field_path="title",
                    reason="Evidence item title is missing or empty.",
                )
            )

        return findings

    def _check_item_consistency(self, item: EvidenceItem) -> List[EvidenceValidationFinding]:
        """Category 8: Consistency checks."""
        findings: List[EvidenceValidationFinding] = []

        if item.source_type == EvidenceSourceType.KNOWLEDGE_BASE and item.web_result_id:
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_CONS_04",
                    severity=ValidationSeverity.INFO,
                    evidence_id=item.evidence_id,
                    field_path="web_result_id",
                    reason="Knowledge Base item contains web_result_id.",
                )
            )

        if item.source_type == EvidenceSourceType.WEB_SEARCH and item.chunk_id:
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_CONS_05",
                    severity=ValidationSeverity.WARNING,
                    evidence_id=item.evidence_id,
                    field_path="chunk_id",
                    reason="Web Search evidence item contains Knowledge Base chunk_id.",
                )
            )

        return findings

    def _check_item_conflicts(self, item: EvidenceItem) -> List[EvidenceValidationFinding]:
        """Category 9: Conflict Indicators checks."""
        findings: List[EvidenceValidationFinding] = []

        if item.conflict_indicators:
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_CNFL_02",
                    severity=ValidationSeverity.INFO,
                    evidence_id=item.evidence_id,
                    field_path="conflict_indicators",
                    reason=f"Preserved conflict indicators detected ({len(item.conflict_indicators)} indicators).",
                    metadata={"conflict_indicators": list(item.conflict_indicators)},
                )
            )

        return findings

    def _check_item_metadata(self, item: EvidenceItem) -> List[EvidenceValidationFinding]:
        """Category 10: Multimodal and Agricultural Metadata structural checks."""
        findings: List[EvidenceValidationFinding] = []

        if item.multimodal_data is not None and not isinstance(item.multimodal_data, dict):
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_META_01",
                    severity=ValidationSeverity.WARNING,
                    evidence_id=item.evidence_id,
                    field_path="multimodal_data",
                    reason="multimodal_data must be a dictionary structure if supplied.",
                )
            )

        if not isinstance(item.metadata, dict):
            findings.append(
                EvidenceValidationFinding(
                    rule_code="R12_META_02",
                    severity=ValidationSeverity.WARNING,
                    evidence_id=item.evidence_id,
                    field_path="metadata",
                    reason="item metadata must be a dictionary structure.",
                )
            )

        return findings

    # -------------------------------------------------------------------------
    # Status Calculation & Package Sanitization
    # -------------------------------------------------------------------------

    def _calculate_overall_status_and_package(
        self,
        original_package: EvidencePackage,
        valid_items: List[EvidenceItem],
        item_outcomes: List[EvidenceItemValidationOutcome],
        all_findings: List[EvidenceValidationFinding],
        strict_mode: bool,
        has_conflicts: bool,
    ) -> Tuple[EvidenceValidationStatus, Optional[EvidencePackage]]:
        """Calculate overall package status and construct sanitized EvidencePackage."""
        total_items = len(original_package.items)
        valid_count = len(valid_items)

        has_critical = any(f.severity == ValidationSeverity.CRITICAL for f in all_findings)
        has_error = any(f.severity == ValidationSeverity.ERROR for f in all_findings)

        # Strict Mode Evaluation
        if strict_mode and (has_critical or has_error or valid_count < total_items):
            status = EvidenceValidationStatus.INVALID
            sanitized_pkg = original_package.model_copy(deep=True)
            sanitized_pkg.items = valid_items
            sanitized_pkg.total_items_count = len(valid_items)
            sanitized_pkg.kb_items_count = sum(1 for item in valid_items if item.source_type == EvidenceSourceType.KNOWLEDGE_BASE)
            sanitized_pkg.web_items_count = sum(1 for item in valid_items if item.source_type == EvidenceSourceType.WEB_SEARCH)
            sanitized_pkg.is_partial = True
            return status, sanitized_pkg

        if valid_count == 0:
            status = EvidenceValidationStatus.MALFORMED if has_critical else EvidenceValidationStatus.INVALID
            sanitized_pkg = original_package.model_copy(deep=True)
            sanitized_pkg.items = []
            sanitized_pkg.total_items_count = 0
            sanitized_pkg.kb_items_count = 0
            sanitized_pkg.web_items_count = 0
            sanitized_pkg.is_partial = True
            return status, sanitized_pkg

        if valid_count < total_items:
            status = EvidenceValidationStatus.PARTIALLY_VALID
        elif has_conflicts:
            status = EvidenceValidationStatus.CONFLICTING
        elif any(f.severity == ValidationSeverity.WARNING for f in all_findings):
            status = EvidenceValidationStatus.PARTIALLY_VALID
        else:
            status = EvidenceValidationStatus.VALID

        # Build sanitized package
        sanitized_pkg = original_package.model_copy(deep=True)
        sanitized_pkg.items = valid_items
        sanitized_pkg.total_items_count = len(valid_items)
        sanitized_pkg.kb_items_count = sum(1 for item in valid_items if item.source_type == EvidenceSourceType.KNOWLEDGE_BASE)
        sanitized_pkg.web_items_count = sum(1 for item in valid_items if item.source_type == EvidenceSourceType.WEB_SEARCH)
        sanitized_pkg.is_partial = original_package.is_partial or (valid_count < total_items)

        return status, sanitized_pkg

    def _sort_findings(
        self, findings: List[EvidenceValidationFinding]
    ) -> List[EvidenceValidationFinding]:
        """Sort findings deterministically by evidence_id, severity, rule_code, and field_path."""
        severity_order = {
            ValidationSeverity.CRITICAL: 0,
            ValidationSeverity.ERROR: 1,
            ValidationSeverity.WARNING: 2,
            ValidationSeverity.INFO: 3,
        }

        return sorted(
            findings,
            key=lambda f: (
                f.evidence_id or "",
                severity_order.get(f.severity, 99),
                f.rule_code,
                f.field_path or "",
                f.reason,
            ),
        )
