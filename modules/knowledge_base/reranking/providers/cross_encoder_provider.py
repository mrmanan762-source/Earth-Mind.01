"""Self-Hosted Cross-Encoder Reranker Provider Adapter for Stage R8."""

import logging
import time
from typing import Any, Dict, List, Optional
from core.errors.exceptions import (
    RerankerProviderUnavailableError,
    RerankerExecutionError,
    RerankerTimeoutError,
)
from core.interfaces.reranker import IRerankerProvider
from core.schemas.rerank import RerankScoreResult

logger = logging.getLogger(__name__)

# Safely check for sentence_transformers CrossEncoder dependency
try:
    from sentence_transformers import CrossEncoder
    CROSS_ENCODER_AVAILABLE = True
except ImportError:
    CrossEncoder = None
    CROSS_ENCODER_AVAILABLE = False


class CrossEncoderRerankerProvider(IRerankerProvider):
    """Self-hosted CrossEncoder model provider adapter for R8 Reranking."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-base",
        device: str = "cpu",
        max_length: int = 512,
        allow_download: bool = False,
        model_instance: Optional[Any] = None,
    ):
        self.model_name = model_name
        self.device = device
        self.max_length = max_length
        self.allow_download = allow_download
        self._model = model_instance

        if self._model is None and CROSS_ENCODER_AVAILABLE and self.allow_download:
            try:
                self._model = CrossEncoder(
                    model_name,
                    max_length=self.max_length,
                    device=self.device,
                )
            except Exception as e:
                logger.warning(f"Failed to load CrossEncoder model '{model_name}': {e}")
                self._model = None

    def is_available(self) -> bool:
        """Return operational availability status."""
        return CROSS_ENCODER_AVAILABLE and self._model is not None

    def rerank(
        self,
        query_text: str,
        documents: List[Dict[str, Any]],
        top_k: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> List[RerankScoreResult]:
        """Execute cross-encoder reranking over query-document pairs."""
        if not self.is_available():
            raise RerankerProviderUnavailableError(
                "cross_encoder",
                f"CrossEncoder model '{self.model_name}' is not loaded or sentence_transformers is unavailable."
            )

        if not documents:
            return []

        start_time = time.time()
        pairs = []
        valid_candidates = []

        for doc in documents:
            candidate_id = doc.get("candidate_id")
            text = doc.get("text", "")
            if candidate_id and text:
                pairs.append((query_text, text))
                valid_candidates.append(candidate_id)

        if not pairs:
            return []

        try:
            scores = self._model.predict(pairs)
            elapsed = time.time() - start_time
            if timeout is not None and elapsed > timeout:
                raise RerankerTimeoutError("cross_encoder", timeout)
        except Exception as e:
            if isinstance(e, RerankerTimeoutError):
                raise
            raise RerankerExecutionError("cross_encoder", f"Model prediction failed: {str(e)}")

        results: List[RerankScoreResult] = []
        for candidate_id, score in zip(valid_candidates, scores):
            results.append(RerankScoreResult(candidate_id=candidate_id, score=float(score)))

        if top_k is not None and top_k > 0:
            results = results[:top_k]

        return results

    def get_provider_info(self) -> Dict[str, Any]:
        """Return provider identification metadata."""
        return {
            "provider_name": "cross_encoder",
            "model_name": self.model_name,
            "device": self.device,
            "max_length": self.max_length,
            "available": self.is_available(),
            "dependency_available": CROSS_ENCODER_AVAILABLE,
        }
