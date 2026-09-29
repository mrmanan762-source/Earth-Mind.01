"""Query Processing Engine for Stage R9 Query Processing."""

import time
import uuid
from typing import Any, Dict, List, Optional
from core.errors.exceptions import QueryValidationError
from core.interfaces.query_processor import (
    IQueryClassifier,
    IQueryExpansionStrategy,
    IQueryMetadataExtractor,
    IQueryNormalizer,
    IQueryProcessorEngine,
    IQueryValidator,
)
from core.schemas.query import (
    QueryMetadata,
    QueryProcessingRequest,
    QueryProcessingResponse,
    QueryProcessingStatus,
    RetrievalQuery,
)
from modules.knowledge_base.query_processing.builder import RetrievalQueryBuilder
from modules.knowledge_base.query_processing.classifier import QueryClassifier
from modules.knowledge_base.query_processing.expansion import DictionaryQueryExpansionStrategy
from modules.knowledge_base.query_processing.metadata_extractor import AgriculturalMetadataExtractor
from modules.knowledge_base.query_processing.normalizer import QueryNormalizer
from modules.knowledge_base.query_processing.validator import QueryValidator


class QueryProcessingEngine(IQueryProcessorEngine):
    """
    Master engine coordinating Stage R9 Query Processing.
    Executes Validator -> Normalizer -> Classifier -> Metadata Extractor -> Expansion -> Builder.
    Supports failure-tolerant fallback, strict parameter validation, and detailed execution logging.
    """

    def __init__(
        self,
        validator: Optional[IQueryValidator] = None,
        normalizer: Optional[IQueryNormalizer] = None,
        classifier: Optional[IQueryClassifier] = None,
        metadata_extractor: Optional[IQueryMetadataExtractor] = None,
        expansion_strategy: Optional[IQueryExpansionStrategy] = None,
        builder: Optional[RetrievalQueryBuilder] = None,
    ):
        self.validator = validator or QueryValidator()
        self.normalizer = normalizer or QueryNormalizer()
        self.classifier = classifier or QueryClassifier()
        self.metadata_extractor = metadata_extractor or AgriculturalMetadataExtractor()
        self.expansion_strategy = expansion_strategy or DictionaryQueryExpansionStrategy()
        self.builder = builder or RetrievalQueryBuilder()

    def process_query(self, request: QueryProcessingRequest) -> QueryProcessingResponse:
        start_time = time.perf_counter()
        req_id = request.request_id or f"req_r9_{uuid.uuid4().hex[:8]}"
        trace_steps: List[Dict[str, Any]] = []
        warnings: List[str] = []

        # 1. Validation Stage
        validation_errors = self.validator.validate(request)
        if validation_errors:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return QueryProcessingResponse(
                request_id=req_id,
                status=QueryProcessingStatus.INVALID,
                original_query=request.query_text or "",
                retrieval_query=None,
                processing_time_ms=elapsed_ms,
                warnings=warnings,
                error_message="; ".join(validation_errors),
                trace_steps=[{"step": "validation", "status": "FAILED", "errors": validation_errors}],
            )

        trace_steps.append({"step": "validation", "status": "PASSED"})

        try:
            # 2. Normalization Stage
            lang = request.language or "en"
            normalized_text = self.normalizer.normalize(request.query_text, language=lang)
            trace_steps.append({
                "step": "normalization",
                "status": "SUCCESS",
                "original_text": request.query_text,
                "normalized_text": normalized_text,
            })

            # 3. Classification Stage
            classification = self.classifier.classify(normalized_text, user_context=request.user_context)
            trace_steps.append({
                "step": "classification",
                "status": "SUCCESS",
                "classification": classification.value,
            })

            # 4. Agricultural Metadata Extraction Stage
            ag_metadata = self.metadata_extractor.extract(normalized_text, user_context=request.user_context)
            trace_steps.append({
                "step": "metadata_extraction",
                "status": "SUCCESS",
                "extracted_fields": ag_metadata.model_dump(exclude_none=True),
            })

            # Combine Metadata
            query_meta = QueryMetadata(
                classification=classification,
                agricultural_metadata=ag_metadata,
                language=lang,
                confidence=1.0,
            )

            # 5. Query Expansion / Reformulation Stage
            expansions = []
            if request.enable_expansion and request.max_expansions > 0:
                try:
                    expansions = self.expansion_strategy.expand(
                        query_text=normalized_text,
                        language=lang,
                        max_expansions=request.max_expansions,
                        metadata=ag_metadata,
                    )
                    trace_steps.append({
                        "step": "query_expansion",
                        "status": "SUCCESS",
                        "expansions_generated": len(expansions),
                    })
                except Exception as exp_err:
                    warnings.append(f"Query expansion failed: {str(exp_err)}. Proceeding with unexpanded query.")
                    trace_steps.append({
                        "step": "query_expansion",
                        "status": "WARNING",
                        "error": str(exp_err),
                    })

            # 6. Build Final RetrievalQuery
            retrieval_q = self.builder.build_retrieval_query(
                request=request,
                normalized_query=normalized_text,
                query_metadata=query_meta,
                expansions=expansions,
            )

            trace_steps.append({
                "step": "retrieval_query_building",
                "status": "SUCCESS",
                "top_k": retrieval_q.top_k,
                "filters_count": len(retrieval_q.structured_filters),
            })

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            status = QueryProcessingStatus.PARTIAL if warnings else QueryProcessingStatus.SUCCESS

            return QueryProcessingResponse(
                request_id=req_id,
                status=status,
                original_query=request.query_text,
                retrieval_query=retrieval_q,
                processing_time_ms=elapsed_ms,
                warnings=warnings,
                error_message=None,
                trace_steps=trace_steps,
            )

        except Exception as err:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return QueryProcessingResponse(
                request_id=req_id,
                status=QueryProcessingStatus.FAILED,
                original_query=request.query_text,
                retrieval_query=None,
                processing_time_ms=elapsed_ms,
                warnings=warnings,
                error_message=f"Internal query processing error: {str(err)}",
                trace_steps=trace_steps + [{"step": "execution", "status": "FAILED", "error": str(err)}],
            )
