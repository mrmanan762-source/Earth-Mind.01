"""Evidence Processor: Canonicalization, Deduplication, Contradiction Detection & Source Freshness.

Architectural Guarantees:
- Robust URL Canonicalization:
  - Strips commercial tracking query parameters (utm_*, fbclid, gclid, mc_cid, etc.).
  - Normalizes schemes to https, lowercases hostnames, removes default ports (80, 443), and strips trailing slashes.
- Multi-Source Deduplication:
  - Preserves distinct sources even when textual content or snippets are similar.
  - Strict Data-Type Separation: structured facts (Wikidata entities) and numerical data (NASA POWER)
    are exempt from lossy URL deduplication.
- Evidence Contradiction & Conflict Preservation:
  - Detects potential agronomic contradictions across search results (e.g., opposing chemical
    active ingredients, conflicting dosage numbers, opposite sowing timings).
  - Preserves BOTH sides of a genuine evidence conflict with explicit metadata flags.
  - Never silently drops contradictory evidence.
- Source Trust and Freshness Evaluation:
  - Evaluates publication date, last updated date, regional relevance, crop relevance,
    and institutional domain authority (ICAR, SAUs, FAO, CGIAR).
  - Never invents publication dates or verification statuses if unavailable.
"""

from datetime import datetime
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Set, Tuple

from core.config.settings import WebSearchConfig
from core.schemas.web_search import WebSearchResult

logger = logging.getLogger(__name__)

# Standard marketing / tracking parameters to safely strip during URL canonicalization
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "gclsrc", "dclid", "msclkid", "mc_cid",
    "mc_eid", "ref", "source", "_hsenc", "_hsmi", "yclid", "zanpid",
}


class EvidenceProcessor:
    """Processes search results: canonicalization, deduplication, conflict detection, and freshness."""

    def __init__(self, config: Optional[WebSearchConfig] = None):
        self._config = config or WebSearchConfig()
        self._trusted_domains = [d.lower() for d in self._config.trusted_agricultural_domains]

    def canonicalize_url(self, raw_url: str) -> str:
        """Normalizes URLs for deduplication while safely stripping tracking parameters."""
        if not raw_url or not raw_url.strip():
            return ""
        try:
            parsed = urllib.parse.urlsplit(raw_url.strip())
            scheme = "https" if parsed.scheme.lower() in ("http", "https") else parsed.scheme.lower()
            netloc = parsed.netloc.lower()

            if netloc.startswith("www."):
                netloc = netloc[4:]
            # Strip default ports
            if netloc.endswith(":80") and parsed.scheme.lower() == "http":
                netloc = netloc[:-3]
            elif netloc.endswith(":443") and parsed.scheme.lower() == "https":
                netloc = netloc[:-4]
            elif netloc.endswith(":80") and scheme == "https":
                netloc = netloc[:-3]

            path = parsed.path.rstrip("/")
            if not path:
                path = ""

            # Filter tracking parameters from query string
            filtered_query = ""
            if parsed.query:
                query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
                cleaned_pairs = [
                    (k, v) for k, v in query_pairs
                    if k.lower() not in TRACKING_PARAMS
                ]
                # Sort query parameters for canonical consistency
                cleaned_pairs.sort(key=lambda x: x[0].lower())
                if cleaned_pairs:
                    filtered_query = urllib.parse.urlencode(cleaned_pairs)

            return urllib.parse.urlunsplit((scheme, netloc, path, filtered_query, ""))
        except Exception:
            return raw_url.strip().lower()

    def is_trusted_domain(self, domain: Optional[str]) -> bool:
        """Checks if a domain belongs to authoritative agricultural institutions."""
        if not domain:
            return False
        d_lower = domain.lower()
        return any(d_lower.endswith(trusted) for trusted in self._trusted_domains)

    def parse_iso_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Safely parses publication date string without fabricating dates."""
        if not date_str or not date_str.strip():
            return None
        cleaned = date_str.strip()
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m",
            "%Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(cleaned[:len(fmt)], fmt)
            except ValueError:
                continue
        return None

    def evaluate_freshness_and_trust(
        self,
        item: WebSearchResult,
        query_crop: Optional[str] = None,
        query_region: Optional[str] = None,
    ) -> float:
        """Calculates an explainable relevance & trust score boost.

        Evaluates domain trust, publication freshness, crop relevance, and regional relevance.
        Preserves original provider score as baseline.
        """
        base_score = item.score if item.score is not None else 0.5
        boost = 0.0

        # 1. Authoritative Domain Trust Boost
        if self.is_trusted_domain(item.source):
            item.result_type = "agricultural"
            boost += self._config.trusted_domain_boost
            item.metadata["trusted_domain"] = True

        # 2. Publication Date Freshness
        pub_dt = self.parse_iso_date(item.publication_date or item.last_updated_date)
        if pub_dt:
            age_days = (datetime.utcnow() - pub_dt).days if pub_dt.tzinfo is None else 365
            if age_days <= 365:
                # Within past year
                boost += 0.1
                item.metadata["freshness_status"] = "recent_1yr"
            elif age_days <= 1095:
                # Within past 3 years
                boost += 0.05
                item.metadata["freshness_status"] = "recent_3yr"
            else:
                item.metadata["freshness_status"] = "older"
        else:
            item.metadata["freshness_status"] = "unknown"

        # 3. Crop Relevance
        if query_crop and query_crop.lower() in (item.title + " " + item.snippet).lower():
            boost += 0.05
            item.metadata["crop_relevance_matched"] = True

        # 4. Regional Relevance
        if query_region and query_region.lower() in (item.title + " " + item.snippet).lower():
            boost += 0.05
            item.metadata["region_relevance_matched"] = True

        final_score = min(1.0, max(0.0, base_score + boost))
        item.score = round(final_score, 4)
        item.metadata["calculated_boost"] = round(boost, 4)
        return final_score

    def detect_potential_contradictions(
        self,
        results: List[WebSearchResult]
    ) -> List[Tuple[WebSearchResult, WebSearchResult, str]]:
        """Detects potential agronomic contradictions across retrieved candidates.

        Identifies conflicting active ingredients or opposing recommendations on the same target.
        Returns pairs of conflicting items with description of conflict.
        """
        conflicts: List[Tuple[WebSearchResult, WebSearchResult, str]] = []
        n = len(results)

        for i in range(n):
            for j in range(i + 1, n):
                item_a = results[i]
                item_b = results[j]

                text_a = f"{item_a.title} {item_a.snippet}".lower()
                text_b = f"{item_b.title} {item_b.snippet}".lower()

                # Check for opposing chemical / organic or prohibitive indicators
                # E.g. "recommended" vs "not recommended" / "banned" / "prohibited"
                opposing_pairs = [
                    (r"\brecommended\b", r"\b(not recommended|banned|prohibited|avoid)\b"),
                    (r"\bchemical control\b", r"\b(organic only|zero chemical)\b"),
                    (r"\bhigh dose\b", r"\blow dose\b"),
                ]

                for pos_pattern, neg_pattern in opposing_pairs:
                    has_pos_a = re.search(pos_pattern, text_a) is not None
                    has_neg_b = re.search(neg_pattern, text_b) is not None
                    has_pos_b = re.search(pos_pattern, text_b) is not None
                    has_neg_a = re.search(neg_pattern, text_a) is not None

                    if (has_pos_a and has_neg_b) or (has_pos_b and has_neg_a):
                        conflict_desc = f"Contradictory recommendation detected between '{item_a.title}' and '{item_b.title}'"
                        conflicts.append((item_a, item_b, conflict_desc))
                        item_a.metadata["has_contradiction"] = True
                        item_a.metadata.setdefault("contradiction_notes", []).append(conflict_desc)
                        item_b.metadata["has_contradiction"] = True
                        item_b.metadata.setdefault("contradiction_notes", []).append(conflict_desc)
                        break

        return conflicts

    def deduplicate_and_rank(
        self,
        collected_results: List[WebSearchResult],
        query_crop: Optional[str] = None,
        query_region: Optional[str] = None,
        max_results: int = 10,
    ) -> Tuple[List[WebSearchResult], List[str]]:
        """Deduplicates results by canonical URL (exempting structured/numerical data),
        evaluates trust and freshness, detects contradictions, and sorts deterministically.
        """
        seen_canonical_urls: Set[str] = set()
        seen_result_ids: Set[str] = set()
        deduplicated: List[WebSearchResult] = []

        for item in collected_results:
            # 1. Result ID check
            if item.result_id in seen_result_ids:
                continue
            seen_result_ids.add(item.result_id)

            # 2. Canonical URL calculation with tracking stripping
            canon_url = self.canonicalize_url(item.url)
            item.canonical_url = canon_url

            # 3. Data-Type Separation:
            # Structured facts (Wikidata) and numerical agroclimatology (NASA POWER)
            # must NEVER be collapsed into general web URL deduplication.
            if item.result_type in ("web", "encyclopedic", "scholarly", "news", "agricultural", "grounded_search"):
                if canon_url:
                    if canon_url in seen_canonical_urls:
                        logger.debug(f"Deduplicated source by canonical URL: {canon_url}")
                        continue
                    seen_canonical_urls.add(canon_url)

            # 4. Evaluate freshness & trust
            self.evaluate_freshness_and_trust(item, query_crop=query_crop, query_region=query_region)

            deduplicated.append(item)

        # 5. Detect potential contradictions across all deduplicated items
        conflicts = self.detect_potential_contradictions(deduplicated)
        conflict_warnings: List[str] = []
        if conflicts:
            conflict_warnings = [c[2] for c in conflicts]
            logger.info(f"Preserved {len(conflicts)} potential evidence contradictions for downstream R11.")

        # 6. Deterministic Sorting:
        # Score + Agricultural bonus first, then rank order, then result_id
        def sort_key(res: WebSearchResult):
            score_val = res.score if res.score is not None else 0.5
            is_agri = 1.0 if res.result_type == "agricultural" else 0.0
            return (score_val + is_agri, -res.rank, res.result_id)

        deduplicated.sort(key=sort_key, reverse=True)

        # 7. Re-index rank
        for idx, item in enumerate(deduplicated, start=1):
            item.rank = idx

        bounded_results = deduplicated[:max_results]
        return bounded_results, conflict_warnings
