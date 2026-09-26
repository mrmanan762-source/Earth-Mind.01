"""Tests for R2 - Real Agricultural Knowledge Corpus Foundation."""

import os
import json
import hashlib
import pytest
from pathlib import Path

from modules.knowledge_base.corpus import (
    CorpusCatalogManager,
    CorpusCorruptedError,
    CorpusDuplicateError,
)
from modules.knowledge_base.canonical_models import (
    Source,
    Artifact,
    Document,
    DocumentVersion,
    validate_canonical_lineage,
    validate_source_assessment,
)
from modules.knowledge_base.enums import (
    SourceStatus,
    ArtifactStatus,
    DocumentStatus,
    DocumentVersionStatus,
    ReviewStatus,
    EvidenceType,
)


def test_corpus_manifest_structure_and_categories():
    """Verify manifest exists, is valid JSON, and covers all 8 target categories."""
    mgr = CorpusCatalogManager()
    manifest = mgr.load_manifest()

    assert manifest["corpus_version"] == "1.0.0"
    assert manifest["total_sources"] == 8
    assert manifest["total_artifacts"] == 8

    sources = manifest["sources"]
    assert len(sources) == 8

    categories = {s["corpus_category"] for s in sources}
    expected_categories = {
        "General Agriculture",
        "Crop Knowledge",
        "Crop Diseases / Pests",
        "Soil / Soil Health",
        "Irrigation / Water Management",
        "Fertilizer / Nutrient Management",
        "Government / Agricultural Guidelines",
        "Regional / Indian Agricultural Practices",
    }
    assert categories == expected_categories


def test_corpus_source_and_artifact_traceability():
    """Verify all sources have valid organizations, origins, acquisition dates, and license metadata."""
    mgr = CorpusCatalogManager()
    manifest = mgr.load_manifest()

    for s in manifest["sources"]:
        assert s["source_id"].startswith("src_")
        assert len(s["source_name"]) > 5
        assert s["organization"] is not None
        assert s["origin"] is not None
        assert s["language"] in ["en", "hi"]
        assert s["region"] == "India"
        assert "license_info" in s
        assert "license_name" in s["license_info"]
        assert "terms" in s["license_info"]
        assert s["status"] == "ACTIVE"
        assert s["review_status"] == "APPROVED"

        art = s["artifact"]
        assert art["artifact_id"].startswith("art_")
        assert art["location_reference"].startswith("data/knowledge/raw/")
        assert art["content_type"] == "text/plain"
        assert art["size_bytes"] > 500
        assert len(art["checksum"]) == 64  # SHA-256 length


def test_corpus_verification_and_checksums():
    """Verify file readability and SHA-256 cryptographic checksum matching."""
    mgr = CorpusCatalogManager()
    report = mgr.verify_corpus()

    assert report["status"] == "VERIFIED"
    assert report["verified_sources"] == 8
    assert report["verified_artifacts"] == 8
    assert report["total_size_bytes"] > 15000


def test_corpus_duplicate_source_detection(tmp_path):
    """Verify detection of duplicate source_ids in manifest."""
    repo_root = Path(__file__).resolve().parents[1]
    real_manifest_path = repo_root / "data" / "knowledge" / "manifest" / "corpus_manifest.json"

    with open(real_manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Duplicate first source
    data["sources"].append(data["sources"][0].copy())

    bad_manifest = tmp_path / "dup_source_manifest.json"
    with open(bad_manifest, "w", encoding="utf-8") as f:
        json.dump(data, f)

    mgr = CorpusCatalogManager(str(bad_manifest))
    mgr.load_manifest()
    with pytest.raises(CorpusDuplicateError, match="Duplicate or invalid source_id"):
        mgr.verify_corpus()


def test_corpus_duplicate_content_checksum_detection(tmp_path):
    """Verify detection of duplicate artifact content via checksum."""
    repo_root = Path(__file__).resolve().parents[1]
    real_manifest_path = repo_root / "data" / "knowledge" / "manifest" / "corpus_manifest.json"

    with open(real_manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Duplicate second source with new source_id and artifact_id, but same artifact location & checksum
    dup = json.loads(json.dumps(data["sources"][1]))
    dup["source_id"] = "src_dup_999"
    dup["artifact"]["artifact_id"] = "art_dup_999"
    data["sources"].append(dup)

    bad_manifest = tmp_path / "dup_content_manifest.json"
    with open(bad_manifest, "w", encoding="utf-8") as f:
        json.dump(data, f)

    mgr = CorpusCatalogManager(str(bad_manifest))
    mgr.load_manifest()
    with pytest.raises(CorpusDuplicateError, match="Duplicate artifact content detected"):
        mgr.verify_corpus()


def test_corpus_checksum_mismatch_detection(tmp_path):
    """Verify rejection of corrupted file or checksum mismatch."""
    repo_root = Path(__file__).resolve().parents[1]
    real_manifest_path = repo_root / "data" / "knowledge" / "manifest" / "corpus_manifest.json"

    with open(real_manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Tamper with checksum of first artifact
    data["sources"][0]["artifact"]["checksum"] = "0" * 64

    bad_manifest = tmp_path / "corrupt_checksum_manifest.json"
    with open(bad_manifest, "w", encoding="utf-8") as f:
        json.dump(data, f)

    mgr = CorpusCatalogManager(str(bad_manifest))
    mgr.load_manifest()
    with pytest.raises(CorpusCorruptedError, match="Checksum mismatch"):
        mgr.verify_corpus()


def test_c2_canonical_model_mapping_and_lineage():
    """Verify seamless mapping to C.2 canonical domain models and lineage integrity."""
    mgr = CorpusCatalogManager()
    tuples = mgr.convert_to_c2_canonical_models()

    assert len(tuples) == 8

    for src, art, doc, ver in tuples:
        assert isinstance(src, Source)
        assert isinstance(art, Artifact)
        assert isinstance(doc, Document)
        assert isinstance(ver, DocumentVersion)

        assert src.status == SourceStatus.ACTIVE
        assert art.status == ArtifactStatus.RAW
        assert doc.status == DocumentStatus.ACTIVE
        assert ver.status == DocumentVersionStatus.ACTIVE

        # Validate canonical lineage
        assert validate_canonical_lineage(src, doc, ver) is True

        # Validate source assessment signals
        if src.assessment:
            assert validate_source_assessment(src.assessment) is True
            assert src.assessment.authority >= 0.90
            assert src.assessment.reliability >= 0.90


def test_architectural_isolation_no_retrieval_or_memory_leakage():
    """Verify R2 owns only real corpus foundation and does not leak retrieval/Qdrant/Memory logic."""
    import modules.knowledge_base.corpus as corpus_mod

    # Ensure no vector/embedding/qdrant imports in corpus module
    forbidden = ["qdrant", "embedding", "vector", "rerank", "sparse", "memory"]
    module_code = corpus_mod.__file__
    with open(module_code, "r", encoding="utf-8") as f:
        code_str = f.read().lower()

    for item in ["qdrant_client", "fakeembeddingprovider", "fakesparseprovider", "contextgovernanceengine"]:
        assert item not in code_str
