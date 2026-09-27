"""Standard Disfluency Processor Implementation for ULPU."""

import re
from core.interfaces.ulpu import IDisfluencyProcessor
from core.schemas.ulpu import DisfluencyRequest, DisfluencyResponse


class StandardDisfluencyProcessor(IDisfluencyProcessor):
    """
    Conservative speech disfluency processor removing common filler words (e.g. 'um', 'uh', 'like')
    without rewriting or altering sentence meaning.
    """

    # Common filler words/patterns in English
    FILLER_PATTERNS = [
        r"\b(um+)\b",
        r"\b(uh+)\b",
        r"\b(ah+)\b",
        r"\b(er+)\b",
    ]

    def remove_disfluencies(self, request: DisfluencyRequest) -> DisfluencyResponse:
        text = request.text
        removed = []

        if request.language.lower() == "en":
            for pattern in self.FILLER_PATTERNS:
                matches = re.findall(pattern, text, flags=re.IGNORECASE)
                if matches:
                    removed.extend(matches)
                    text = re.sub(pattern, "", text, flags=re.IGNORECASE)

            # Clean up residual double spaces created by filler removal
            text = re.sub(r"\s+", " ", text).strip()

        return DisfluencyResponse(
            cleaned_text=text,
            disfluencies_removed=removed,
        )
