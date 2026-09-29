"""Query Normalizer for Stage R9 Query Processing."""

import re
import unicodedata
from typing import Optional
from core.interfaces.query_processor import IQueryNormalizer
from core.config.settings import QueryProcessingConfig


class QueryNormalizer(IQueryNormalizer):
    """
    Normalizes query text (whitespace, casing, unicode, punctuation)
    while preserving domain terminology, chemical formulas, pH values,
    dosage rates, scientific names, and Indic scripts.
    """

    def __init__(self, config: Optional[QueryProcessingConfig] = None):
        from core.config.settings import settings
        self.config = config or settings.query_processing

    def normalize(self, query_text: str, language: str = "en") -> str:
        if not query_text:
            return ""

        # 1. Strip leading/trailing whitespace
        text = query_text.strip()

        # 2. Unicode normalization (NFKC) to unify Devanagari/Indic composite glyphs & characters
        text = unicodedata.normalize("NFKC", text)

        # 3. Preserve meaningful punctuation (e.g. pH 6.5, 10kg/acre, 0.5%, N-P-K, e.g.)
        # Clean repeated control/special characters while protecting decimals, slashes, hyphens, and percent signs
        text = re.sub(r'[\r\n\t]+', ' ', text)
        text = re.sub(r' +', ' ', text)

        # 4. Casing normalization
        # Lowercase English words, BUT protect scientific names, acronyms, or formulas if uppercase
        # E.g. pH, NPK, NPV, ICAR, KVK, EC
        if language in ("en", "hi", "mr", "pa", "te", "ta", "gu", "bn", "kn", "ml"):
            text = self._safe_casing(text)

        # 5. Clean punctuation at start/end unless sentence ending
        text = text.strip(" \t\n\r,;:!")

        return text

    def _safe_casing(self, text: str) -> str:
        """
        Applies lowercase to standard words while protecting protected domain tokens.
        """
        protected_tokens = {"pH", "NPK", "NPV", "ICAR", "IARI", "KVK", "EC", "PPM", "DNA", "RNA"}
        words = text.split(" ")
        normalized_words = []

        for word in words:
            # Check if word matches protected exact token or pattern (e.g., pH)
            if word in protected_tokens:
                normalized_words.append(word)
            elif word.isupper() and len(word) <= 5 and word.isalpha():
                # Keep short acronyms intact (e.g. ICAR, NPK)
                normalized_words.append(word)
            elif word.startswith("pH") or word.startswith("pH="):
                normalized_words.append(word)
            else:
                normalized_words.append(word.lower())

        return " ".join(normalized_words)
