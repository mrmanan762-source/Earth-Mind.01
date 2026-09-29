"""Query Expansion and Reformulation Strategies for Stage R9 Query Processing."""

from typing import List, Optional
from core.interfaces.query_processor import IQueryExpansionStrategy
from core.schemas.query import AgriculturalMetadata, QueryExpansion


class DictionaryQueryExpansionStrategy(IQueryExpansionStrategy):
    """
    Deterministic dictionary/synonym expansion strategy.
    Maps agricultural terms, diseases, crops, and fertilizers to known synonyms,
    scientific names, or regional/Indic term variants without introducing LLM dependencies.
    """

    TERM_EXPANSIONS = {
        "yellow rust": [
            ("stripe rust", "SYNONYM", 1.0, "en"),
            ("Puccinia striiformis", "SCIENTIFIC_NAME", 0.9, "en"),
            ("पीला रतुआ", "TRANSLITERATION", 0.95, "hi"),
        ],
        "पीला रतुआ": [
            ("yellow rust", "TRANSLITERATION", 1.0, "en"),
            ("stripe rust", "SYNONYM", 0.9, "en"),
            ("Puccinia striiformis", "SCIENTIFIC_NAME", 0.85, "en"),
        ],
        "wheat": [
            ("gehun", "TRANSLITERATION", 0.9, "hi"),
            ("गेहूँ", "LOCAL_TERM", 1.0, "hi"),
            ("Triticum aestivum", "SCIENTIFIC_NAME", 0.85, "en"),
        ],
        "गेहूँ": [
            ("wheat", "TRANSLITERATION", 1.0, "en"),
            ("Triticum aestivum", "SCIENTIFIC_NAME", 0.85, "en"),
        ],
        "rice": [
            ("paddy", "SYNONYM", 1.0, "en"),
            ("धान", "LOCAL_TERM", 1.0, "hi"),
            ("Oryza sativa", "SCIENTIFIC_NAME", 0.85, "en"),
        ],
        "dap": [
            ("di-ammonium phosphate", "SYNONYM", 1.0, "en"),
            ("18-46-0 fertilizer", "DOMAIN_VARIANT", 0.9, "en"),
        ],
        "urea": [
            ("46% nitrogen fertilizer", "DOMAIN_VARIANT", 0.9, "en"),
            ("यूरिया", "LOCAL_TERM", 1.0, "hi"),
        ],
        "aphid": [
            ("aphids", "SYNONYM", 1.0, "en"),
            ("माहू", "LOCAL_TERM", 0.95, "hi"),
            ("चेपा", "LOCAL_TERM", 0.9, "hi"),
        ],
    }

    def expand(
        self,
        query_text: str,
        language: str = "en",
        max_expansions: int = 3,
        metadata: Optional[AgriculturalMetadata] = None,
    ) -> List[QueryExpansion]:
        if not query_text or max_expansions <= 0:
            return []

        expansions: List[QueryExpansion] = []
        q_lower = query_text.lower()

        # Check direct term matches
        for term, variants in self.TERM_EXPANSIONS.items():
            if term in q_lower:
                for variant_text, exp_type, weight, target_lang in variants:
                    if len(expansions) >= max_expansions:
                        break
                    # Avoid adding identical text as expansion
                    if variant_text.lower() != q_lower:
                        expansions.append(
                            QueryExpansion(
                                expanded_text=variant_text,
                                expansion_type=exp_type,
                                weight=weight,
                                target_language=target_lang,
                                source_term=term,
                            )
                        )
            if len(expansions) >= max_expansions:
                break

        # Also leverage metadata if provided and expansions limit not reached
        if metadata and len(expansions) < max_expansions:
            if metadata.crop and metadata.disease_pest:
                combo = f"{metadata.crop} {metadata.disease_pest}"
                if combo.lower() != q_lower and len(expansions) < max_expansions:
                    expansions.append(
                        QueryExpansion(
                            expanded_text=combo,
                            expansion_type="METADATA_REFORMULATION",
                            weight=0.9,
                            target_language=language,
                            source_term="crop+disease",
                        )
                    )

        return expansions[:max_expansions]


class FakeQueryExpansionStrategy(IQueryExpansionStrategy):
    """
    Test/Mock query expansion strategy for deterministic unit testing.
    """

    def __init__(self, mock_expansions: Optional[List[QueryExpansion]] = None):
        self.mock_expansions = mock_expansions or []

    def expand(
        self,
        query_text: str,
        language: str = "en",
        max_expansions: int = 3,
        metadata: Optional[AgriculturalMetadata] = None,
    ) -> List[QueryExpansion]:
        if self.mock_expansions:
            return self.mock_expansions[:max_expansions]

        if not query_text or max_expansions <= 0:
            return []

        return [
            QueryExpansion(
                expanded_text=f"{query_text} treatment",
                expansion_type="SYNONYM",
                weight=1.0,
                target_language=language,
                source_term=query_text,
            ),
            QueryExpansion(
                expanded_text=f"{query_text} guidance",
                expansion_type="DOMAIN_VARIANT",
                weight=0.8,
                target_language=language,
                source_term=query_text,
            ),
        ][:max_expansions]
