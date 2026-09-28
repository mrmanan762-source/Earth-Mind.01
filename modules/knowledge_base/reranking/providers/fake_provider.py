"""Fake Reranker Provider for Stage R8 Unit Testing and Offline Prototyping."""

import time
from typing import Any, Dict, List, Optional
from core.errors.exceptions import (
    RerankerProviderUnavailableError,
    RerankerTimeoutError,
    RerankerExecutionError,
)
from core.interfaces.reranker import IRerankerProvider
from core.schemas.rerank import RerankScoreResult


class FakeRerankerProvider(IRerankerProvider):
    """Deterministic offline fake reranker provider for testing R8 Reranking."""

    def __init__(
        self,
        scores: Optional[Dict[str, float]] = None,
        is_available_flag: bool = True,
        should_raise: Optional[Exception] = None,
        delay_seconds: float = 0.0,
        provider_name: str = "fake_reranker",
        model_name: str = "fake-cross-encoder-v1",
    ):
        self._scores = scores or {}
        self._is_available_flag = is_available_flag
        self._should_raise = should_raise
        self._delay_seconds = delay_seconds
        self._provider_name = provider_name
        self._model_name = model_name

    def rerank(
        self,
        query_text: str,
        documents: List[Dict[str, Any]],
        top_k: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> List[RerankScoreResult]:
        """Compute deterministic mock relevance scores for documents."""
        if self._should_raise:
            raise self._should_raise

        if not self._is_available_flag:
            raise RerankerProviderUnavailableError(
                self._provider_name, "Provider is configured as unavailable."
            )

        if self._delay_seconds > 0.0:
            if timeout is not None and self._delay_seconds > timeout:
                time.sleep(timeout)
                raise RerankerTimeoutError(self._provider_name, timeout)
            time.sleep(self._delay_seconds)

        results: List[RerankScoreResult] = []
        query_terms = set(query_text.lower().split())

        for doc in documents:
            candidate_id = doc.get("candidate_id")
            if not candidate_id:
                continue

            text = doc.get("text", "")
            if candidate_id in self._scores:
                score = float(self._scores[candidate_id])
            else:
                # Deterministic term overlap ratio heuristic
                text_terms = set(text.lower().split())
                if query_terms and text_terms:
                    overlap = len(query_terms.intersection(text_terms))
                    score = round(0.1 + 0.9 * (overlap / max(len(query_terms), 1)), 4)
                else:
                    score = 0.1

            results.append(RerankScoreResult(candidate_id=candidate_id, score=score))

        if top_k is not None and top_k > 0:
            results = results[:top_k]

        return results

    def is_available(self) -> bool:
        """Return operational availability status."""
        return self._is_available_flag

    def get_provider_info(self) -> Dict[str, Any]:
        """Return provider identification metadata."""
        return {
            "provider_name": self._provider_name,
            "model_name": self._model_name,
            "is_fake": True,
            "available": self._is_available_flag,
        }
