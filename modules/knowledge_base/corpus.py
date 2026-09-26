"""R2 Real Agricultural Knowledge Corpus Catalog Manager for EarthMind.

This module manages inspection, checksum verification, duplicate/corruption detection,
and mapping of the real agricultural knowledge corpus manifest to C.2 canonical models.

Architectural Guarantees:
- Pure corpus foundation management.
- Zero retrieval, vector database, embedding, reranking, or Web Search implementation.
- Fully compatible with locked C.2 canonical knowledge domain models.
"""

import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from modules.knowledge_base.canonical_models import (
    Source,
    Artifact,
    Document,
    DocumentVersion,
)
from modules.knowledge_base.provenance import Provenance
from modules.knowledge_base.enums import (
    SourceStatus,
    ArtifactStatus,
    DocumentStatus,
    DocumentVersionStatus,
    EvidenceType,
    ReviewStatus,
)
from modules.knowledge_base.metadata import CanonicalMetadata
from modules.knowledge_base.assessment import SourceAssessment


class CorpusCorruptedError(Exception):
    """Raised when corpus files or manifests are corrupted or unreadable."""
    pass


class CorpusDuplicateError(Exception):
    """Raised when duplicate sources or artifacts are detected in the corpus."""
    pass


class CorpusCatalogManager:
    """Manages real agricultural knowledge corpus loading, verification, and C.2 mapping."""

    def __init__(self, manifest_path: Optional[str] = None):
        if manifest_path is None:
            # Default root relative path
            repo_root = Path(__file__).resolve().parents[2]
            manifest_path = str(repo_root / "data" / "knowledge" / "manifest" / "corpus_manifest.json")
        self.manifest_path = Path(manifest_path)
        self._manifest_data: Dict[str, Any] = {}
        self._sources_raw: List[Dict[str, Any]] = []

    def load_manifest(self) -> Dict[str, Any]:
        """Loads and validates the corpus manifest JSON structure."""
        if not self.manifest_path.exists():
            raise CorpusCorruptedError(f"Corpus manifest file not found at: {self.manifest_path}")

        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise CorpusCorruptedError(f"Failed to parse corpus manifest JSON: {str(e)}")

        required_keys = ["corpus_version", "total_sources", "sources"]
        for k in required_keys:
            if k not in data:
                raise CorpusCorruptedError(f"Corpus manifest missing required top-level key: '{k}'")

        self._manifest_data = data
        self._sources_raw = data.get("sources", [])
        return self._manifest_data

    def verify_corpus(self) -> Dict[str, Any]:
        """Verifies file readability, checksums, and duplicate detection for all sources.

        Returns a summary report dictionary.
        """
        if not self._manifest_data:
            self.load_manifest()

        verified_sources = 0
        verified_artifacts = 0
        seen_source_ids = set()
        seen_artifact_ids = set()
        seen_checksums = set()

        repo_root = Path(__file__).resolve().parents[2]

        for s in self._sources_raw:
            source_id = s.get("source_id")
            if not source_id or source_id in seen_source_ids:
                raise CorpusDuplicateError(f"Duplicate or invalid source_id detected: {source_id}")
            seen_source_ids.add(source_id)

            art_dict = s.get("artifact", {})
            artifact_id = art_dict.get("artifact_id")
            if not artifact_id or artifact_id in seen_artifact_ids:
                raise CorpusDuplicateError(f"Duplicate or invalid artifact_id detected: {artifact_id}")
            seen_artifact_ids.add(artifact_id)

            rel_loc = art_dict.get("location_reference")
            if not rel_loc:
                raise CorpusCorruptedError(f"Artifact {artifact_id} missing location_reference.")

            abs_loc = repo_root / rel_loc
            if not abs_loc.exists():
                raise CorpusCorruptedError(f"Artifact file does not exist at location: {abs_loc}")

            try:
                with open(abs_loc, "rb") as af:
                    content_bytes = af.read()
            except Exception as e:
                raise CorpusCorruptedError(f"Failed to read artifact file '{abs_loc}': {str(e)}")

            if len(content_bytes) == 0:
                raise CorpusCorruptedError(f"Artifact file '{abs_loc}' is empty.")

            computed_sha = hashlib.sha256(content_bytes).hexdigest()
            manifest_sha = art_dict.get("checksum")
            if manifest_sha and computed_sha != manifest_sha:
                raise CorpusCorruptedError(
                    f"Checksum mismatch for artifact {artifact_id}: "
                    f"computed {computed_sha} != manifest {manifest_sha}"
                )

            if computed_sha in seen_checksums:
                raise CorpusDuplicateError(f"Duplicate artifact content detected via checksum {computed_sha}")
            seen_checksums.add(computed_sha)

            verified_sources += 1
            verified_artifacts += 1

        return {
            "status": "VERIFIED",
            "verified_sources": verified_sources,
            "verified_artifacts": verified_artifacts,
            "total_size_bytes": sum(s["artifact"]["size_bytes"] for s in self._sources_raw),
        }

    def convert_to_c2_canonical_models(self) -> List[Tuple[Source, Artifact, Document, DocumentVersion]]:
        """Converts raw manifest sources into C.2 canonical domain object tuples."""
        if not self._manifest_data:
            self.load_manifest()

        canonical_tuples = []

        for s in self._sources_raw:
            # 1. Source Assessment
            ass_dict = s.get("assessment", {})
            assessment_obj = None
            if ass_dict:
                ev_type = EvidenceType[ass_dict["evidence_type"]] if "evidence_type" in ass_dict else EvidenceType.OFFICIAL_STANDARD
                rev_stat = ReviewStatus[ass_dict["review_status"]] if "review_status" in ass_dict else ReviewStatus.VERIFIED
                assessment_obj = SourceAssessment(
                    assessment_id=f"ass_{s['source_id']}",
                    source_id=s["source_id"],
                    authority=ass_dict.get("authority"),
                    reliability=ass_dict.get("reliability"),
                    recency=ass_dict.get("recency"),
                    domain_relevance=ass_dict.get("domain_relevance"),
                    geographic_relevance=ass_dict.get("geographic_relevance"),
                    evidence_type=ev_type,
                    review_status=rev_stat,
                    assessment_basis=ass_dict.get("assessment_basis"),
                    assessed_by="R2_CorpusCatalogManager",
                )

            # 2. Canonical Metadata
            meta_obj = CanonicalMetadata(
                domain=s.get("domain"),
                region=s.get("region"),
                language=s.get("language", "en"),
                extra_metadata={
                    "corpus_category": s.get("corpus_category"),
                    "license_name": s.get("license_info", {}).get("license_name"),
                    "license_terms": s.get("license_info", {}).get("terms"),
                    "review_required": s.get("license_info", {}).get("review_required", False),
                },
                filterable_attributes={
                    "corpus_category": s.get("corpus_category"),
                    "license_name": s.get("license_info", {}).get("license_name"),
                    "license_terms": s.get("license_info", {}).get("terms"),
                    "review_required": s.get("license_info", {}).get("review_required", False),
                },
            )

            # 3. Source
            source_obj = Source(
                source_id=s["source_id"],
                source_name=s["source_name"],
                source_type=s["source_type"],
                organization=s.get("organization"),
                origin=s.get("origin"),
                language=s.get("language", "en"),
                region=s.get("region"),
                status=SourceStatus.ACTIVE,
                metadata=meta_obj,
                assessment=assessment_obj,
            )

            # 4. Artifact
            art_dict = s["artifact"]
            artifact_obj = Artifact(
                artifact_id=art_dict["artifact_id"],
                source_id=s["source_id"],
                location_reference=art_dict["location_reference"],
                content_type=art_dict["content_type"],
                checksum=art_dict.get("checksum"),
                size_bytes=art_dict.get("size_bytes"),
                version_info=art_dict.get("version_info"),
                status=ArtifactStatus.RAW,
                metadata=meta_obj,
            )

            # 5. Document
            doc_id = f"doc_{s['source_id']}"
            document_obj = Document(
                document_id=doc_id,
                source_id=s["source_id"],
                title=s["source_name"],
                document_type=s["source_type"],
                language=s.get("language", "en"),
                region=s.get("region"),
                status=DocumentStatus.ACTIVE,
                metadata=meta_obj,
                assessment=assessment_obj,
            )

            # 6. Provenance
            ver_id = f"ver_{s['source_id']}_1_0"
            prov_obj = Provenance(
                provenance_id=f"prov_{s['source_id']}",
                source_id=s["source_id"],
                artifact_id=art_dict["artifact_id"],
                document_id=doc_id,
                version_id=ver_id,
                processing_stage="CORPUS_FOUNDATION",
                processing_steps=[
                    {
                        "step_id": f"step_init_{s['source_id']}",
                        "operation": "CORPUS_MANIFEST_REGISTRATION",
                        "processor_name": "CorpusCatalogManager",
                        "parameters": {"source_name": s["source_name"]},
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "status": "COMPLETED",
                    }
                ],
            )

            # Assign provenance
            source_obj.provenance = prov_obj
            artifact_obj.provenance = prov_obj
            document_obj.provenance = prov_obj

            # 7. DocumentVersion
            version_obj = DocumentVersion(
                version_id=ver_id,
                document_id=doc_id,
                version_number=art_dict.get("version_info", "1.0.0"),
                status=DocumentVersionStatus.ACTIVE,
                metadata=meta_obj,
                provenance=prov_obj,
            )

            canonical_tuples.append((source_obj, artifact_obj, document_obj, version_obj))

        return canonical_tuples
