"""Master Web Search Engine for EarthMind Stage R10 Web Search Integration.

Coordinating web search queries from R9 Query Processing to external web search providers,
normalizing provider responses into stable data contracts for downstream Stage R11 Evidence Builder.

HARD ARCHITECTURAL RULE:
Web search results are query-time candidate evidence for R11.
Web Search Engine NEVER publishes web results to the permanent Knowledge Base,
NEVER writes to Qdrant, and NEVER writes to Memory.
"""

import time
from typing import Any, Dict, List, Optional, Union

from core.config.settings import WebSearchConfig, settings
from core.errors.exceptions import (
    InvalidWebSearchRequestError,
    WebSearchAuthenticationError,
    WebSearchConfigurationError,
    WebSearchError,
    WebSearchExecutionError,
    WebSearchProviderUnavailableError,
    WebSearchRateLimitError,
    WebSearchTimeoutError,
)
from core.interfaces.web_search import IWebSearchProvider
from core.schemas.query import RetrievalQuery
from core.schemas.web_search import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
    WebSearchStatus,
)
from modules.knowledge_base.web_search.providers.api_provider import APIWebSearchProvider
from modules.knowledge_base.web_search.providers.fake_provider import FakeWebSearchProvider


class WebSearchEngine:
    """
    Master engine for Stage R10 Web Search Integration.
    Acts as the entry point for retrieving real-time external web search evidence.
    """

    def __init__(
        self,
        config: Optional[WebSearchConfig] = None,
        provider: Optional[IWebSearchProvider] = None,
    ):
        self._config = config or getattr(settings, "web_search", WebSearchConfig())
        self._provider = provider or self._resolve_provider(self._config)

    @property
    def config(self) -> WebSearchConfig:
        return self._config

    @property
    def provider(self) -> IWebSearchProvider:
        return self._provider

    def _resolve_provider(self, config: WebSearchConfig) -> IWebSearchProvider:
        """Instantiates provider adapter based on configuration."""
        p_name = (config.provider or "fake").lower().strip()
        if p_name in ("fake", "mock"):
            return FakeWebSearchProvider()
        elif p_name in ("api", "serp", "serpapi", "google", "bing"):
            return APIWebSearchProvider(config=config)
        else:
            raise WebSearchConfigurationError(f"Unsupported web search provider '{config.provider}'.")

    def search(
        self,
        request_input: Union[WebSearchRequest, RetrievalQuery],
        max_results: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> WebSearchResponse:
        """
        Executes web search query and returns normalized response ready for Stage R11 Evidence Builder.

        Args:
            request_input: WebSearchRequest or Stage R9 RetrievalQuery.
            max_results: Optional override limit on returned candidates.
            timeout: Optional override request timeout in seconds.

        Returns:
            Normalized WebSearchResponse container.
        """
        start_time = time.perf_counter()

        # Convert RetrievalQuery if necessary
        if isinstance(request_input, RetrievalQuery):
            limit = max_results if max_results is not None else self._config.max_results
            t_out = timeout if timeout is not None else self._config.timeout
            req = WebSearchRequest.from_retrieval_query(
                request_input, max_results=limit, timeout=t_out
            )
        elif isinstance(request_input, WebSearchRequest):
            req = request_input
            if max_results is not None:
                req = req.model_copy(update={"max_results": max_results})
            if timeout is not None:
                req = req.model_copy(update={"timeout": timeout})
        else:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                status=WebSearchStatus.INVALID_REQUEST,
                query_text="",
                results=[],
                result_count=0,
                provider_name=self._provider.provider_name if self._provider else "unknown",
                execution_time_ms=elapsed_ms,
                error_message=f"Invalid request input type: {type(request_input)}",
            )

        # Enforce result limits from configuration
        bounded_max_results = min(req.max_results, self._config.max_results)
        req = req.model_copy(update={"max_results": bounded_max_results})

        # Validate query text
        if not req.query_text or not req.query_text.strip():
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                request_id=req.request_id,
                status=WebSearchStatus.INVALID_REQUEST,
                query_text="",
                results=[],
                result_count=0,
                provider_name=self._provider.provider_name,
                execution_time_ms=elapsed_ms,
                error_message="Search query text cannot be empty or whitespace.",
            )

        try:
            response = self._provider.search(req)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            # Enrich response metadata
            trace = dict(response.trace_info)
            trace["engine_latency_ms"] = elapsed_ms
            trace["engine_bounded_max_results"] = bounded_max_results

            return response.model_copy(
                update={
                    "execution_time_ms": elapsed_ms,
                    "trace_info": trace,
                }
            )

        except InvalidWebSearchRequestError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                request_id=req.request_id,
                status=WebSearchStatus.INVALID_REQUEST,
                query_text=req.query_text,
                results=[],
                result_count=0,
                provider_name=self._provider.provider_name,
                execution_time_ms=elapsed_ms,
                error_message=str(e),
            )
        except WebSearchProviderUnavailableError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                request_id=req.request_id,
                status=WebSearchStatus.PROVIDER_UNAVAILABLE,
                query_text=req.query_text,
                results=[],
                result_count=0,
                provider_name=self._provider.provider_name,
                execution_time_ms=elapsed_ms,
                error_message=str(e),
            )
        except WebSearchTimeoutError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                request_id=req.request_id,
                status=WebSearchStatus.PROVIDER_TIMEOUT,
                query_text=req.query_text,
                results=[],
                result_count=0,
                provider_name=self._provider.provider_name,
                execution_time_ms=elapsed_ms,
                error_message=str(e),
            )
        except WebSearchAuthenticationError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                request_id=req.request_id,
                status=WebSearchStatus.AUTHENTICATION_FAILURE,
                query_text=req.query_text,
                results=[],
                result_count=0,
                provider_name=self._provider.provider_name,
                execution_time_ms=elapsed_ms,
                error_message=str(e),
            )
        except WebSearchRateLimitError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                request_id=req.request_id,
                status=WebSearchStatus.RATE_LIMITED,
                query_text=req.query_text,
                results=[],
                result_count=0,
                provider_name=self._provider.provider_name,
                execution_time_ms=elapsed_ms,
                error_message=str(e),
            )
        except (WebSearchExecutionError, WebSearchError) as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                request_id=req.request_id,
                status=WebSearchStatus.PROVIDER_ERROR,
                query_text=req.query_text,
                results=[],
                result_count=0,
                provider_name=self._provider.provider_name,
                execution_time_ms=elapsed_ms,
                error_message=str(e),
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                request_id=req.request_id,
                status=WebSearchStatus.PROVIDER_ERROR,
                query_text=req.query_text,
                results=[],
                result_count=0,
                provider_name=self._provider.provider_name,
                execution_time_ms=elapsed_ms,
                error_message=f"Unexpected engine error: {str(e)}",
            )
