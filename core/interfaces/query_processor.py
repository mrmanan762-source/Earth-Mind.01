"""Interfaces and Protocols for EarthMind Stage R9 Query Processing.

Defines protocol interfaces for:
- IQueryValidator: Query validation interface
- IQueryNormalizer: Query normalization interface
- IQueryClassifier: Query classification interface
- IQueryMetadataExtractor: Agricultural query metadata extraction interface
- IQueryExpansionStrategy: Query expansion and reformulation strategy interface
- IQueryProcessorEngine: Master R9 Query Processing Engine interface
"""

from typing import Dict, List, Optional, Protocol, runtime_checkable

from core.schemas.query import (
    AgriculturalMetadata,
    QueryClassification,
    QueryExpansion,
    QueryMetadata,
    QueryProcessingRequest,
    QueryProcessingResponse,
    RetrievalQuery,
)


@runtime_checkable
class IQueryValidator(Protocol):
    """Protocol for validating incoming retrieval queries."""

    def validate(self, request: QueryProcessingRequest) -> List[str]:
        """
        Validates request parameter structures and input text.
        Returns a list of error strings if invalid; empty list if valid.
        """
        ...


@runtime_checkable
class IQueryNormalizer(Protocol):
    """Protocol for normalizing retrieval queries while preserving domain terminology."""

    def normalize(self, query_text: str, language: str = "en") -> str:
        """
        Normalizes query text (whitespace, casing, unicode, punctuation)
        without destroying agricultural terminology or Indic character meanings.
        """
        ...


@runtime_checkable
class IQueryClassifier(Protocol):
    """Protocol for classifying query intent/topic category."""

    def classify(self, query_text: str, user_context: Optional[Dict] = None) -> QueryClassification:
        """Classifies query into a QueryClassification category."""
        ...


@runtime_checkable
class IQueryMetadataExtractor(Protocol):
    """Protocol for extracting agricultural query metadata without hallucination."""

    def extract(self, query_text: str, user_context: Optional[Dict] = None) -> AgriculturalMetadata:
        """Extracts structured agricultural attributes from query text and context."""
        ...


@runtime_checkable
class IQueryExpansionStrategy(Protocol):
    """Protocol for expanding and reformulating retrieval queries."""

    def expand(
        self,
        query_text: str,
        language: str = "en",
        max_expansions: int = 3,
        metadata: Optional[AgriculturalMetadata] = None,
    ) -> List[QueryExpansion]:
        """Generates bounded expanded query variants or terms."""
        ...


@runtime_checkable
class IQueryProcessorEngine(Protocol):
    """Master protocol for Stage R9 Query Processing Engine."""

    def process_query(self, request: QueryProcessingRequest) -> QueryProcessingResponse:
        """Executes full R9 Query Processing pipeline to produce RetrievalQuery."""
        ...
