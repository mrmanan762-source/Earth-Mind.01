"""Standard Canonicalizer Implementation for ULPU."""

from core.interfaces.ulpu import ICanonicalizer
from core.schemas.ulpu import CanonicalizationRequest, CanonicalizationResponse


class StandardCanonicalizer(ICanonicalizer):
    """
    Standard Canonicalizer mapping normalized input into a controlled English canonical representation.
    Preserves verbatim user intent without inventing missing facts or resolving agricultural ambiguity.
    """

    def canonicalize(self, request: CanonicalizationRequest) -> CanonicalizationResponse:
        normalized = request.normalized_text
        source_lang = request.source_language.lower().strip()

        # For English source language, canonical text matches normalized text
        if source_lang == "en":
            canonical = normalized
        else:
            # For non-English languages, canonicalization will be handled via translation stage in pipeline
            canonical = normalized

        return CanonicalizationResponse(
            canonical_text=canonical,
            target_language="en",
            confidence=1.0,
        )
