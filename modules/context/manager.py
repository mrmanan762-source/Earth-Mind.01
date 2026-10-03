import time
from typing import List, Optional
from core.config.settings import ContextConfig, settings
from core.errors.exceptions import (
    ContextOutputValidationError,
    ContextPrivacyViolationError,
    ContextScopeViolationError,
    EarthMindException,
    InsufficientContextError,
    InvalidContextRequestError,
)
from core.logging.logger import get_logger
from modules.context.builder import ContextBuilder
from modules.context.collector import ContextCollector
from modules.context.conflict import ConflictDetector
from modules.context.deduplicator import ContextDeduplicator
from modules.context.filter import PrivacyFilter, ScopeFilter, TimeFilter
from modules.context.interfaces import CacheProvider, CompressionProvider, ContextProvider
from modules.context.limit_manager import LimitManager
from modules.context.organizer import ContextOrganizer, Prioritizer
from modules.context.relevance import RelevanceEvaluator
from modules.context.schemas import ContextItem, ContextRequest, ContextResult, ContextState
from modules.context.validator import ItemValidator, OutputValidator

logger = get_logger("modules.context.manager")


class B2ContextManager:
    """
    Main B2 Context Manager orchestrating context collection, validation, deduplication,
    filtering, relevance evaluation, conflict detection, organization, prioritization,
    token limiting, context building, and output validation.
    """

    def __init__(
        self,
        providers: Optional[List[ContextProvider]] = None,
        cache_provider: Optional[CacheProvider] = None,
        compression_provider: Optional[CompressionProvider] = None,
        config: Optional[ContextConfig] = None,
    ):
        self.collector = ContextCollector(providers)
        self.cache_provider = cache_provider
        self.compression_provider = compression_provider
        self.config = config or getattr(settings, "context", ContextConfig())

    def register_provider(self, provider: ContextProvider) -> None:
        self.collector.register_provider(provider)

    def prepare_context(self, request: ContextRequest) -> ContextResult:
        """
        Executes the 12-stage context preparation pipeline for a ContextRequest.
        """
        start_time = time.perf_counter()
        logger.info(f"Starting B2 context preparation for request {request.request_id}")
        warnings: List[str] = []
        errors: List[str] = []

        # Apply config defaults to request if unspecified
        if request.token_limit <= 0:
            request.token_limit = self.config.default_token_limit
        if request.policy and request.policy.timeout_seconds <= 0:
            request.policy.timeout_seconds = self.config.default_timeout

        # 1. REQUESTED & VALIDATING
        if not request.request_id or not request.request_id.strip():
            raise InvalidContextRequestError("Missing request_id.")

        # 2. CACHE_CHECK
        if self.cache_provider:
            try:
                cached_result = self.cache_provider.get(request)
                if cached_result:
                    logger.info(f"Cache HIT for request {request.request_id}")
                    return cached_result
            except Exception as e:
                logger.warning(f"Cache check failed: {str(e)}. Proceeding with collection.")

        # 3. COLLECTING
        raw_items, collect_warns, collect_errs = self.collector.collect(request)
        warnings.extend(collect_warns)
        errors.extend(collect_errs)

        if collect_errs and request.policy and request.policy.required_providers:
            # Check if required provider failed
            for required in request.policy.required_providers:
                if any(required in err for err in collect_errs):
                    if not request.policy.allow_partial:
                        msg = f"Required provider '{required}' failed and partial results disallowed."
                        logger.error(msg)
                        return ContextBuilder.build_context_result(
                            request, [], state=ContextState.FAILED, warnings=warnings, errors=collect_errs + [msg]
                        )

        # 4. VALIDATING_CONTEXT
        valid_items: List[ContextItem] = []
        for item in raw_items:
            is_valid, err_msg = ItemValidator.validate_item(item)
            if is_valid:
                valid_items.append(item)
            else:
                warnings.append(err_msg)

        # 5. DEDUPLICATING
        deduped_items = ContextDeduplicator.deduplicate(valid_items)

        # 6. FILTERING (Scope, Privacy, Time)
        scope_filtered = ScopeFilter.filter(deduped_items, request)
        privacy_filtered = PrivacyFilter.filter(scope_filtered, request)
        time_filtered = TimeFilter.filter(privacy_filtered, request)

        # 7. EVALUATING_RELEVANCE
        relevance_filtered = RelevanceEvaluator.evaluate_and_filter(time_filtered, request)

        # 8. DETECTING_CONFLICTS
        conflict_checked = ConflictDetector.detect_and_mark_conflicts(relevance_filtered)

        # 9. ORGANIZING & PRIORITIZING
        prioritized = Prioritizer.assign_priorities(conflict_checked, request)
        organized = ContextOrganizer.organize_and_sort(prioritized)

        # 10. LIMITING
        items_dropped_budget = 0
        try:
            limited_items = LimitManager.enforce_limits(
                organized, request, compression_provider=self.compression_provider
            )
            items_dropped_budget = len(organized) - len(limited_items)
        except InsufficientContextError as e:
            msg = str(e)
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            metrics = {
                "b2_version": self.config.b2_version,
                "context_version": self.config.context_version,
                "items_received": len(raw_items),
                "items_filtered": len(raw_items) - len(organized),
                "items_dropped_budget": len(organized),
                "provider_statuses": getattr(self.collector, "last_provider_statuses", {}),
                "execution_latency_ms": latency_ms,
                "validation_status": "FAILED",
            }
            return ContextBuilder.build_context_result(
                request, [], state=ContextState.INSUFFICIENT_CONTEXT, warnings=warnings, errors=[msg], metrics=metrics
            )

        # Determine final state (COMPLETED or PARTIAL)
        final_state = ContextState.COMPLETED
        if errors and request.policy and request.policy.allow_partial:
            final_state = ContextState.PARTIAL

        # Compute metrics
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        items_received = len(raw_items)
        items_filtered = len(raw_items) - len(organized)
        metrics = {
            "b2_version": self.config.b2_version,
            "context_version": self.config.context_version,
            "items_received": items_received,
            "items_filtered": items_filtered,
            "items_dropped_budget": items_dropped_budget,
            "provider_statuses": getattr(self.collector, "last_provider_statuses", {}),
            "execution_latency_ms": latency_ms,
            "validation_status": "PASSED" if not errors else "PARTIAL_PASSED",
        }

        # 11. BUILDING
        result = ContextBuilder.build_context_result(
            request, limited_items, state=final_state, warnings=warnings, errors=errors, metrics=metrics
        )

        # 12. VALIDATING_OUTPUT
        is_output_valid, output_errors = OutputValidator.validate_result(result, request)
        if not is_output_valid:
            err_msg = f"Output validation failed: {'; '.join(output_errors)}"
            logger.error(err_msg)
            raise ContextOutputValidationError(request.request_id, err_msg)

        # Cache result if cache provider registered and state is COMPLETED
        if self.cache_provider and final_state == ContextState.COMPLETED:
            try:
                self.cache_provider.set(request, result)
            except Exception as e:
                logger.warning(f"Failed to write to context cache: {str(e)}")

        logger.info(f"Successfully prepared context for request {request.request_id} with {len(result.items)} items.")
        return result
