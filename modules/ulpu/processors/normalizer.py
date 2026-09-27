"""Standard Text Normalizer Implementation for ULPU."""

import re
import unicodedata
from core.interfaces.ulpu import INormalizer
from core.schemas.ulpu import NormalizationRequest, NormalizationResponse


class StandardNormalizer(INormalizer):
    """
    Standard text normalizer preserving meaning, numbers, units, punctuation,
    and negation while stripping excess whitespace and normalizing Unicode.
    """

    def normalize(self, request: NormalizationRequest) -> NormalizationResponse:
        original = request.text
        changes = []

        # 1. Unicode NFKC normalization
        norm = unicodedata.normalize("NFKC", original)
        if norm != original:
            changes.append("unicode_nfkc_normalization")

        # 2. Collapse internal whitespace and strip leading/trailing space
        norm_space = re.sub(r"\s+", " ", norm).strip()
        if norm_space != norm:
            changes.append("whitespace_collapse_and_trim")

        return NormalizationResponse(
            normalized_text=norm_space,
            changes_made=changes,
        )
