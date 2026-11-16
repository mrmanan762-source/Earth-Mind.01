#!/usr/bin/env python3
"""Generate the Phase 2 agricultural corpus coverage report.

Reports, per domain and per target crop: approved source documents, indexed
documents, chunks, unique publishers, license/verification status, publication
date coverage and missing knowledge categories. Coverage is derived from the
actual corpus manifest and the real ingestion pipeline, not from metadata alone.

Usage:
    python3 scripts/corpus_coverage_report.py [--json-out PATH] [--md-out PATH]
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.knowledge_base.ingestion import CorpusIngestionEngine

TARGET_CROPS = [
    "Rice", "Wheat", "Maize", "Potato", "Onion", "Tomato", "Pea", "Chickpea",
    "Pigeon Pea", "Mustard", "Groundnut", "Soybean", "Sugarcane", "Cotton", "Lentil",
]

CROP_ALIASES = {
    "Rice": ["rice", "paddy"],
    "Wheat": ["wheat"],
    "Maize": ["maize", "corn"],
    "Potato": ["potato"],
    "Onion": ["onion"],
    "Tomato": ["tomato"],
    "Pea": ["pea"],
    "Chickpea": ["chickpea", "gram"],
    "Pigeon Pea": ["pigeon pea", "pigeonpea", "tur", "arhar"],
    "Mustard": ["mustard"],
    "Groundnut": ["groundnut", "peanut"],
    "Soybean": ["soybean"],
    "Sugarcane": ["sugarcane"],
    "Cotton": ["cotton"],
    "Lentil": ["lentil", "masoor"],
}

KNOWLEDGE_CATEGORIES = [
    "crop_identification", "growth_stages", "climate", "soil", "nutrients",
    "water_irrigation", "pests", "diseases", "symptoms", "preventive_practices",
    "ipm", "harvest_post_harvest", "crop_calendar", "research_advisories",
]

CATEGORY_KEYWORDS = {
    "crop_identification": ["botanical name", "scientific name", "cultivation in india", "is a ", "package of practices"],
    "growth_stages": ["growth stage", "germination", "tillering", "vegetative", "flowering", "maturity", "tuber"],
    "climate": ["climate", "temperature", "rainfall", "frost"],
    "soil": ["soil", "ph", "texture", "drainage"],
    "nutrients": ["nutrient", "fertil", "nitrogen", "phosphorus", "potassium", "npk", "sulphur", "zinc"],
    "water_irrigation": ["water", "irrigat", "mm"],
    "pests": ["pest", "borer", "aphid", "thrips", "whitefly", "armyworm", "mite", "termite", "bug"],
    "diseases": ["disease", "blight", "rust", "wilt", "mildew", "rot", "smut", "mosaic", "virus"],
    "symptoms": ["symptom", "lesion", "yellowing", "chlorot", "spot"],
    "preventive_practices": ["preventive", "prevention", "treat seed", "seed treatment", "rotate"],
    "ipm": ["integrated pest management", "ipm", "economic threshold", "natural enemies"],
    "harvest_post_harvest": ["harvest", "storage", "post-harvest", "store"],
    "crop_calendar": ["crop calendar", "sow", "sowing", "transplant", "planting"],
    "research_advisories": ["icar", "advisory", "recommendation", "research"],
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_report() -> dict:
    repo_root = _repo_root()
    manifest_path = repo_root / "data" / "knowledge" / "manifest" / "corpus_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    sources = manifest.get("sources", [])

    engine = CorpusIngestionEngine()
    summary = engine.ingest_corpus()
    chunks = engine.get_ingested_chunks()

    # Map each chunk to its source via the manifest document_id convention.
    doc_to_source = {f"doc_{s['source_id']}": s["source_id"] for s in sources}
    chunks_by_source = defaultdict(list)
    for c in chunks:
        chunks_by_source[doc_to_source.get(c.document_id)].append(str(c.content))

    def _match_alias(blob: str, aliases: list) -> bool:
        for a in aliases:
            if re.search(r"\b" + re.escape(a) + r"\b", blob):
                return True
        return False

    domain_rows = defaultdict(lambda: {
        "approved_sources": 0, "indexed_documents": 0, "chunks": 0,
        "publishers": set(), "license_status": defaultdict(int),
        "verification_status": defaultdict(int), "publication_dates": [],
    })

    for s in sources:
        dom = s.get("domain") or s.get("corpus_category") or "Unknown"
        row = domain_rows[dom]
        row["approved_sources"] += 1
        sid = s["source_id"]
        if sid in chunks_by_source and chunks_by_source[sid]:
            row["indexed_documents"] += 1
            row["chunks"] += len(chunks_by_source[sid])
        row["publishers"].add(s.get("organization", "Unknown"))
        lic = s.get("license_info", {})
        row["license_status"][lic.get("license_name", "UNKNOWN")] += 1
        row["verification_status"][s.get("review_status", "UNKNOWN")] += 1
        vinfo = s.get("artifact", {}).get("version_info")
        if vinfo:
            row["publication_dates"].append(str(vinfo))

    crop_rows = {}
    for crop in TARGET_CROPS:
        aliases = CROP_ALIASES[crop]
        matched_sources = set()
        for s in sources:
            if crop in (s.get("crops_covered") or []):
                matched_sources.add(s["source_id"])
            blob = (s.get("source_name", "") + " " + (s.get("domain", "") or "")).lower()
            if _match_alias(blob, aliases):
                matched_sources.add(s["source_id"])
        matched_chunks = 0
        categories_found = set()
        for sid in matched_sources:
            for text in chunks_by_source.get(sid, []):
                matched_chunks += 1
                blob = text.lower()
                for cat, kws in CATEGORY_KEYWORDS.items():
                    if any(k in blob for k in kws):
                        categories_found.add(cat)
        crop_rows[crop] = {
            "source_documents": len(matched_sources),
            "chunks": matched_chunks,
            "knowledge_categories_present": sorted(categories_found),
            "missing_knowledge_categories": sorted(set(KNOWLEDGE_CATEGORIES) - categories_found),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_version": manifest.get("corpus_version"),
        "total_sources": len(sources),
        "ingestion": {
            "sources_registered": summary.sources_registered,
            "documents_created": summary.documents_created,
            "chunks_created": summary.chunks_created,
            "failed_count": summary.failed_count,
        },
        "domains": {
            dom: {
                "approved_sources": r["approved_sources"],
                "indexed_documents": r["indexed_documents"],
                "chunks": r["chunks"],
                "unique_publishers": len(r["publishers"]),
                "license_status": dict(r["license_status"]),
                "verification_status": dict(r["verification_status"]),
                "publication_date_coverage": sorted(set(r["publication_dates"])),
            }
            for dom, r in sorted(domain_rows.items())
        },
        "crops": crop_rows,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Phase 2 — Agricultural Corpus Coverage Report",
        "",
        f"Generated: {report['generated_at']}",
        f"Corpus version: {report['corpus_version']}",
        f"Total sources: {report['total_sources']}",
        "",
        "## Ingestion summary",
        "",
        f"- Sources registered: {report['ingestion']['sources_registered']}",
        f"- Documents created: {report['ingestion']['documents_created']}",
        f"- Chunks created: {report['ingestion']['chunks_created']}",
        f"- Failed: {report['ingestion']['failed_count']}",
        "",
        "## Domain coverage",
        "",
        "| Domain | Approved sources | Indexed docs | Chunks | Publishers | Publication dates |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for dom, r in report["domains"].items():
        lines.append(
            f"| {dom} | {r['approved_sources']} | {r['indexed_documents']} | "
            f"{r['chunks']} | {r['unique_publishers']} | {len(r['publication_date_coverage'])} |"
        )

    lines += [
        "",
        "## Crop coverage (15 target crops)",
        "",
        "| Crop | Source documents | Chunks | Missing knowledge categories |",
        "| --- | --- | --- | --- |",
    ]
    for crop, r in report["crops"].items():
        missing = ", ".join(r["missing_knowledge_categories"]) or "none"
        lines.append(f"| {crop} | {r['source_documents']} | {r['chunks']} | {missing} |")

    lines += [
        "",
        "## Notes",
        "",
        "- Coverage is derived from the actual corpus manifest and the real ingestion pipeline.",
        "- A smaller verified corpus is preferred over a large collection of unreliable material.",
        "- Missing categories are reported honestly; they are not fabricated.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate corpus coverage report.")
    parser.add_argument("--json-out", default="docs/phase2_corpus_coverage.json")
    parser.add_argument("--md-out", default="docs/phase2_corpus_coverage.md")
    args = parser.parse_args()

    report = build_report()
    repo_root = _repo_root()
    json_path = repo_root / args.json_out
    md_path = repo_root / args.md_out
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Chunks: {report['ingestion']['chunks_created']} | Sources: {report['total_sources']}")


if __name__ == "__main__":
    main()
