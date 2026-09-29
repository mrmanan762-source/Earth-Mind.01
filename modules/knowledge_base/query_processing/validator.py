"""Query Validator for Stage R9 Query Processing."""

from typing import List, Optional, Set
from core.interfaces.query_processor import IQueryValidator
from core.schemas.query import QueryProcessingRequest
from core.config.settings import QueryProcessingConfig


class QueryValidator(IQueryValidator):
    """
    Validates incoming QueryProcessingRequest against system constraints,
    length requirements, parameter sanity, and language support.
    """

    def __init__(self, config: Optional[QueryProcessingConfig] = None):
        from core.config.settings import settings
        self.config = config or settings.query_processing

    def validate(self, request: QueryProcessingRequest) -> List[str]:
        errors: List[str] = []

        # 1. Null / type check
        if request.query_text is None or not isinstance(request.query_text, str):
            errors.append("Query text must be a non-null string.")
            return errors

        # 2. Empty / whitespace check
        trimmed = request.query_text.strip()
        if not trimmed:
            errors.append("Query text cannot be empty or whitespace-only.")
            return errors

        # 3. Null bytes or control characters check
        if "\x00" in request.query_text:
            errors.append("Query text contains invalid null characters.")

        # 4. Length constraints
        if len(trimmed) < self.config.min_query_length:
            errors.append(f"Query length ({len(trimmed)}) is below minimum allowed length ({self.config.min_query_length}).")

        if len(request.query_text) > self.config.max_query_length:
            errors.append(f"Query length ({len(request.query_text)}) exceeds maximum allowed length ({self.config.max_query_length}).")

        # 5. Parameter sanity checks
        if request.top_k <= 0:
            errors.append(f"top_k must be a positive integer, got {request.top_k}.")

        if request.dense_top_k <= 0:
            errors.append(f"dense_top_k must be a positive integer, got {request.dense_top_k}.")

        if request.sparse_top_k <= 0:
            errors.append(f"sparse_top_k must be a positive integer, got {request.sparse_top_k}.")

        if request.timeout <= 0:
            errors.append(f"timeout must be greater than zero, got {request.timeout}.")

        if request.max_expansions < 0:
            errors.append(f"max_expansions cannot be negative, got {request.max_expansions}.")

        # 6. Language check if explicit
        if request.language:
            lang_clean = request.language.strip().lower()
            if lang_clean not in self.config.supported_languages:
                errors.append(f"Unsupported language code '{request.language}'. Supported languages: {self.config.supported_languages}")

        # 7. Explicit filters validation
        if request.filters is not None:
            if not isinstance(request.filters, dict):
                errors.append("Explicit filters must be a valid dictionary.")
            else:
                for k, v in request.filters.items():
                    if not isinstance(k, str) or not k.strip():
                        errors.append("Filter keys must be non-empty strings.")

        return errors
