"""Reranking Engine Implementation for Stage R8."""

import math
import time
from typing import Any, Dict, List, Optional
from core.config.settings import RerankConfig, settings
from core.errors.exceptions import (
    InvalidRerankRequestError,
    InvalidRerankerResponseError,
    RerankerConfigurationError,
    RerankerExecutionError,
    RerankerProviderUnavailableError,
    RerankerTimeoutError,
)
from core.interfaces.reranker import IRerankerProvider
from core.schemas.hybrid import HybridCandidate, HybridRetrievalResponse
from core.schemas.rerank import (
    RerankCandidate,
    RerankRequest,
    RerankResponse,
    RerankScoreResult,
    RerankStatus,
)
from modules.knowledge_base.reranking.providers.cross_encoder_provider import CrossEncoderRerankerProvider
from modules.knowledge_base.reranking.providers.fake_provider import FakeRerankerProvider


class RerankEngine:
    """Coordinator and execution engine for Stage R8 Reranking."""

    def __init__(
        self,
        provider: Optional[IRerankerProvider] = None,
        config: Optional[RerankConfig] = None,
    ):
        self.config = config or getattr(settings, "rerank", RerankConfig())

        if provider is not None:
            self.provider = provider
        else:
            if self.config.provider == "fake":
                self.provider = FakeRerankerProvider(
                    provider_name="fake_reranker",
                    model_name=self.config.model,
                )
            elif self.config.provider in ("cross_encoder", "self_hosted"):
                self.provider = CrossEncoderRerankerProvider(
                    model_name=self.config.model,
                    device=self.config.device,
                    max_length=self.config.max_input_length,
                    allow_download=self.config.allow_download,
                )
            else:
                self.provider = FakeRerankerProvider(
                    provider_name=self.config.provider,
                    model_name=self.config.model,
                )

    def rerank(self, request: RerankRequest) -> RerankResponse:
        """Execute Stage R8 candidate reranking over an incoming RerankRequest."""
        start_time = time.time()
        warnings: List[str] = []

        # --- 1. Validate Input Request ---
        if not request.query_text or not request.query_text.strip():
            raise InvalidRerankRequestError("Query text cannot be empty or whitespace.")

        if len(request.candidates) > self.config.max_candidate_count:
            raise InvalidRerankRequestError(
                f"Candidate count ({len(request.candidates)}) exceeds maximum allowed limit ({self.config.max_candidate_count})."
            )

        seen_candidate_ids = set()
        for c in request.candidates:
            if c.candidate_id in seen_candidate_ids:
                raise InvalidRerankRequestError(
                    f"Duplicate candidate ID '{c.candidate_id}' detected in rerank request."
                )
            seen_candidate_ids.add(c.candidate_id)

        info = self.provider.get_provider_info() if self.provider else {}
        provider_name = info.get("provider_name", "unknown")
        model_name = info.get("model_name", "unknown")

        if len(request.candidates) == 0:
            elapsed_ms = (time.time() - start_time) * 1000.0
            return RerankResponse(
                request_id=request.request_id,
                query_text=request.query_text,
                status=RerankStatus.SUCCESS,
                candidates=[],
                total_candidates_received=0,
                total_candidates_reranked=0,
                provider_used=provider_name,
                model_used=model_name,
                is_fallback=False,
                processing_time_ms=round(elapsed_ms, 2),
                warnings=[],
                error_message=None,
            )

        # --- 2. Prepare Candidate Documents for Provider ---
        doc_dicts: List[Dict[str, Any]] = []
        for c in request.candidates:
            text_content = ""
            if c.record and getattr(c.record, "content", None):
                text_content = c.record.content
            elif c.payload_metadata:
                text_content = (
                    c.payload_metadata.get("text")
                    or c.payload_metadata.get("content")
                    or c.payload_metadata.get("summary")
                    or ""
                )
            if not text_content:
                text_content = c.candidate_id

            doc_dicts.append({"candidate_id": c.candidate_id, "text": text_content})

        # --- 3. Execute Provider Reranking & Validate Output ---
        raw_score_results: List[RerankScoreResult] = []
        score_map: Dict[str, float] = {}
        execution_failed = False
        failure_error: Optional[Exception] = None

        try:
            if not self.provider or not self.provider.is_available():
                raise RerankerProviderUnavailableError(
                    provider_name, "Provider is not available or offline."
                )

            raw_score_results = self.provider.rerank(
                query_text=request.query_text,
                documents=doc_dicts,
                top_k=None,
                timeout=request.timeout,
            )
            if raw_score_results is None:
                raise InvalidRerankerResponseError("Provider returned None instead of score results.")

            # Validate Provider Output
            for res in raw_score_results:
                if not isinstance(res.score, (int, float)) or math.isnan(res.score) or math.isinf(res.score):
                    raise InvalidRerankerResponseError(
                        f"Invalid non-finite score '{res.score}' for candidate '{res.candidate_id}'."
                    )
                score_map[res.candidate_id] = float(res.score)

            for c in request.candidates:
                if c.candidate_id not in score_map:
                    raise InvalidRerankerResponseError(
                        f"Reranker provider did not return score for candidate '{c.candidate_id}'."
                    )
        except Exception as e:
            execution_failed = True
            failure_error = e

        # --- 4. Handle Failure / Timeout / Fallback Strategy ---
        if execution_failed:
            err_msg = str(failure_error) if failure_error else "Unknown reranker execution failure."
            warnings.append(f"Reranking failed on provider '{provider_name}': {err_msg}")

            if request.allow_fallback and self.config.fallback_policy == "PRESERVE_FUSED_ORDER":
                warnings.append("Executing configured fallback strategy: preserving R7 fused candidate ordering.")
                sorted_by_fused = sorted(request.candidates, key=lambda x: x.fused_rank)
                fallback_candidates: List[RerankCandidate] = []
                for candidate in sorted_by_fused:
                    r_cand = RerankCandidate.from_hybrid_candidate(
                        candidate=candidate,
                        rerank_score=None,  # Do not fabricate scores!
                        rerank_rank=candidate.fused_rank,
                        rerank_provider=provider_name,
                        rerank_model=model_name,
                        is_fallback=True,
                    )
                    fallback_candidates.append(r_cand)

                limit = request.top_k if request.top_k > 0 else len(fallback_candidates)
                fallback_candidates = fallback_candidates[:limit]
                elapsed_ms = (time.time() - start_time) * 1000.0

                return RerankResponse(
                    request_id=request.request_id,
                    query_text=request.query_text,
                    status=RerankStatus.FALLBACK,
                    candidates=fallback_candidates,
                    total_candidates_received=len(request.candidates),
                    total_candidates_reranked=0,
                    provider_used=provider_name,
                    model_used=model_name,
                    is_fallback=True,
                    processing_time_ms=round(elapsed_ms, 2),
                    warnings=warnings,
                    error_message=None,
                )
            else:
                # Fallback disabled or set to FAIL
                status = RerankStatus.FAILED
                if isinstance(failure_error, RerankerProviderUnavailableError):
                    status = RerankStatus.UNAVAILABLE
                elif isinstance(failure_error, RerankerTimeoutError):
                    status = RerankStatus.TIMEOUT

                if failure_error and isinstance(
                    failure_error,
                    (InvalidRerankRequestError, RerankerConfigurationError),
                ):
                    raise failure_error

                elapsed_ms = (time.time() - start_time) * 1000.0
                return RerankResponse(
                    request_id=request.request_id,
                    query_text=request.query_text,
                    status=status,
                    candidates=[],
                    total_candidates_received=len(request.candidates),
                    total_candidates_reranked=0,
                    provider_used=provider_name,
                    model_used=model_name,
                    is_fallback=False,
                    processing_time_ms=round(elapsed_ms, 2),
                    warnings=warnings,
                    error_message=err_msg,
                )

        # --- 6. Normalize Scores if Configured ---
        normalized_scores = self._normalize_scores(
            score_map=score_map,
            policy=self.config.score_normalization_policy,
        )

        # --- 7. Deterministically Order Candidates ---
        # Sorting key:
        # 1. Normalized rerank_score DESCENDING (-score)
        # 2. fused_rank ASCENDING (lower rank = better R7 score)
        # 3. candidate_id ASCENDING (stable alphabetical ordering)
        candidate_tuples = []
        for c in request.candidates:
            score = normalized_scores[c.candidate_id]
            candidate_tuples.append((c, score))

        sorted_candidates = sorted(
            candidate_tuples,
            key=lambda item: (-item[1], item[0].fused_rank, item[0].candidate_id),
        )

        # --- 8. Assign Final Rerank Rank & Build RerankCandidates ---
        final_candidates: List[RerankCandidate] = []
        for idx, (candidate, score) in enumerate(sorted_candidates):
            rank = idx + 1
            r_cand = RerankCandidate.from_hybrid_candidate(
                candidate=candidate,
                rerank_score=score,
                rerank_rank=rank,
                rerank_provider=provider_name,
                rerank_model=model_name,
                is_fallback=False,
            )
            final_candidates.append(r_cand)

        limit = request.top_k if request.top_k > 0 else len(final_candidates)
        final_candidates = final_candidates[:limit]
        elapsed_ms = (time.time() - start_time) * 1000.0

        return RerankResponse(
            request_id=request.request_id,
            query_text=request.query_text,
            status=RerankStatus.SUCCESS,
            candidates=final_candidates,
            total_candidates_received=len(request.candidates),
            total_candidates_reranked=len(final_candidates),
            provider_used=provider_name,
            model_used=model_name,
            is_fallback=False,
            processing_time_ms=round(elapsed_ms, 2),
            warnings=warnings,
            error_message=None,
        )

    def _normalize_scores(
        self,
        score_map: Dict[str, float],
        policy: str,
    ) -> Dict[str, float]:
        """Apply deterministic score normalization according to policy."""
        if not score_map:
            return {}

        policy_upper = policy.upper() if policy else "NONE"

        if policy_upper == "NONE":
            return dict(score_map)

        elif policy_upper == "MIN_MAX":
            scores = list(score_map.values())
            min_s = min(scores)
            max_s = max(scores)
            range_s = max_s - min_s
            normalized = {}
            for cid, s in score_map.items():
                if range_s > 1e-9:
                    normalized[cid] = round((s - min_s) / range_s, 6)
                else:
                    normalized[cid] = 1.0
            return normalized

        elif policy_upper == "SIGMOID":
            normalized = {}
            for cid, s in score_map.items():
                # Sigmoid 1 / (1 + e^-x)
                try:
                    val = 1.0 / (1.0 + math.exp(-s))
                except OverflowError:
                    val = 1.0 if s > 0 else 0.0
                normalized[cid] = round(val, 6)
            return normalized

        else:
            raise RerankerConfigurationError(
                f"Unsupported score_normalization_policy '{policy}'. Must be one of 'NONE', 'MIN_MAX', 'SIGMOID'."
            )
