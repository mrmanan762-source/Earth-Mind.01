# EarthMind RAG Stage R10 — Web Search Integration

## 1. Overview & Objective

Stage R10 implements the **Web Search Integration** layer for EarthMind RAG. It provides a provider-independent interface enabling the retrieval pipeline to obtain real-time, external web evidence for user queries processed by Stage R9 Query Processing.

### Target Data Flow
```text
R9 Query Processing (RetrievalQuery)
        ↓
R10 Web Search Interface (WebSearchRequest)
        ↓
Web Search Provider Adapter (IWebSearchProvider)
        ↓
External Search Service / Provider API
        ↓
Normalized Web Search Results (WebSearchResult)
        ↓
R10 Evidence Output Contract (WebSearchResponse)
        ↓
Stage R11 Evidence Builder
```

R10 is strictly a **retrieval capability** for query-time candidate evidence.

---

## 2. Hard Architectural Boundary: Web Search ≠ Knowledge Base

> **CRITICAL ARCHITECTURAL RULE:**
> Web search results are current-query transient evidence for Stage R11 Evidence Builder. They are **NEVER** automatically published to the permanent Knowledge Base, **NEVER** written to Qdrant vector index, **NEVER** stored in SQLite canonical repositories, and **NEVER** saved to Memory.

If web content ever requires permanent Knowledge Base inclusion, it must independently traverse the explicit C.2/C.3 ingestion and curation pipeline:
`Web Evidence` → `Candidate Knowledge` → `Curation/Review` → `Knowledge Ingestion` → `Publication`.

R10 itself performs **no database writes, vector upserts, or Memory modifications**.

---

## 3. Interfaces and Provider Abstractions

### `IWebSearchProvider` Protocol
Located in `core/interfaces/web_search.py`, `IWebSearchProvider` defines the stable, provider-agnostic contract for all search adapters:

```python
class IWebSearchProvider(Protocol):
    @property
    def provider_name(self) -> str: ...
    def search(self, request: WebSearchRequest) -> WebSearchResponse: ...
    def is_available(self) -> bool: ...
    def supported_capabilities(self) -> Dict[str, Any]: ...
```

### Provider Adapters
1. **`FakeWebSearchProvider`** (`modules/knowledge_base/web_search/providers/fake_provider.py`):
   - Deterministic offline mock provider generating structured agricultural search results tailored to query text and agricultural metadata (crop, disease, region).
   - Supports simulation of provider failure modes (`PROVIDER_UNAVAILABLE`, `PROVIDER_TIMEOUT`, `AUTHENTICATION_FAILURE`, `RATE_LIMITED`, `PROVIDER_ERROR`, `EMPTY_RESULT`) for testing error resilience.

2. **`APIWebSearchProvider`** (`modules/knowledge_base/web_search/providers/api_provider.py`):
   - Production HTTP API adapter connecting to external search APIs (e.g., SerpAPI, Google Custom Search, Bing, or custom JSON search endpoints).
   - Handles URL parameter encoding, User-Agent headers, timeout management, HTTP error status mapping, and JSON response normalization.

---

## 4. Data Contracts & Schemas

Defined in `core/schemas/web_search.py`:

- **`WebSearchStatus`** (Enum):
  - `SUCCESS`: Web search executed successfully with normalized candidates.
  - `PARTIAL`: Partial results retrieved due to provider constraints.
  - `INVALID_REQUEST`: Query text was empty or whitespace.
  - `PROVIDER_UNAVAILABLE`: Search provider offline or network unreachable.
  - `PROVIDER_TIMEOUT`: Execution timed out.
  - `AUTHENTICATION_FAILURE`: Invalid API key or missing credentials.
  - `RATE_LIMITED`: HTTP 429 rate limit exceeded.
  - `PROVIDER_ERROR`: Provider internal execution error.
  - `EMPTY_RESULT`: Valid query produced 0 search results.

- **`WebSearchResult`**:
  - `result_id`: Unique provider/normalized result ID.
  - `title`: Result page title.
  - `url`: Canonical source URL.
  - `snippet`: Content excerpt.
  - `source`: Publisher domain name.
  - `publication_date` / `last_updated_date`: Timestamps if provided.
  - `provider`: Provider identifier (e.g. `"fake"`, `"api"`).
  - `retrieval_timestamp`: Unix epoch timestamp.
  - `rank`: 1-based position in provider results.
  - `score`: Optional provider relevance score.
  - `content`: Optional full page extract.
  - `provenance`: Complete lineage metadata.
  - `metadata`: Additional regional/language/agri context.
  - `request_id`: Correlation tracing ID.

- **`WebSearchRequest`**:
  - `query_text`: Search query.
  - `request_id`: Correlation tracing ID.
  - `max_results`: Requested candidate count (bounded by config).
  - `language` / `region`: Language code and geographic context.
  - `agricultural_metadata`: Extracted agricultural context from R9.
  - `timeout`: Per-request timeout in seconds.
  - `from_retrieval_query()`: Convenience bridge method from Stage R9 `RetrievalQuery`.

- **`WebSearchResponse`**:
  - Contains `status`, `results` list, `result_count`, `execution_time_ms`, `provider_name`, `error_message`, and `trace_info`.

---

## 5. Master Web Search Engine

The `WebSearchEngine` (`modules/knowledge_base/web_search/engine.py`) serves as the central entry point for R10 Web Search.

Key responsibilities:
- Instantiates or receives `IWebSearchProvider`.
- Converts incoming `RetrievalQuery` (from R9) into `WebSearchRequest`.
- Validates query input and enforces maximum candidate bounds (`min(req.max_results, config.max_results)`).
- Wraps provider execution in structured exception handling, returning `WebSearchResponse` with appropriate `WebSearchStatus` on failures without crashing downstream pipelines.
- Preserves audit logging, correlation IDs, latency metrics, and candidate provenance.

---

## 6. Configuration & Security

Configured via `WebSearchConfig` in `core/config/settings.py`:

```bash
EARTHMIND_WEB_SEARCH_PROVIDER=fake      # Options: 'fake', 'api', 'serp'
EARTHMIND_WEB_SEARCH_API_KEY=""         # API key (loaded from environment)
EARTHMIND_WEB_SEARCH_ENDPOINT=""        # API endpoint URL
EARTHMIND_WEB_SEARCH_TIMEOUT=10.0       # Timeout in seconds
EARTHMIND_WEB_SEARCH_MAX_RESULTS=10     # Max result cap
EARTHMIND_WEB_SEARCH_SAFE_SEARCH=true   # Safe search filter
EARTHMIND_WEB_SEARCH_USER_AGENT="EarthMind-RAG/1.0"
```

### Security & Secrets Protection
- No credentials or API keys are committed to Git or hardcoded in source files.
- Credentials are read strictly from environment variables or secrets managers.
- Missing credentials trigger `WebSearchAuthenticationError` without exposing sensitive data in logs.

---

## 7. Error Handling Hierarchy

Defined in `core/errors/exceptions.py`:

```text
EarthMindException
    └── WebSearchError
          ├── InvalidWebSearchRequestError
          ├── WebSearchProviderUnavailableError
          ├── WebSearchConfigurationError
          ├── WebSearchExecutionError
          ├── WebSearchTimeoutError
          ├── WebSearchAuthenticationError
          └── WebSearchRateLimitError
```

---

## 8. Five EarthMind Principles Compliance

1. **Extensibility / Rubber-Band Principle**:
   - New search providers (e.g. Bing, Tavily, SerpAPI) can be added seamlessly by implementing `IWebSearchProvider`.
2. **Loose Coupling**:
   - Stage R10 communicates purely through stable Pydantic data contracts (`WebSearchRequest`, `WebSearchResponse`).
3. **Single Responsibility**:
   - Stage R10 only handles web retrieval and normalization. It does not perform reranking, fusion, reasoning, or KB publication.
4. **Controlled Dependencies**:
   - External HTTP interactions and SDKs are encapsulated entirely inside provider adapters (`modules/knowledge_base/web_search/providers/`).
5. **Replaceability + Evolution**:
   - The underlying search provider can be switched via configuration without changing downstream R11 Evidence Builder logic.

---

## 9. Verification & Testing

Validated via `tests/test_r10_web_search.py` (28 unit tests passing):
- Query validation & normalized response structures
- Multi-candidate retrieval and rank bounds enforcement
- Error simulation (timeout, offline provider, 401 auth, 429 rate limit, empty results)
- Provenance, URL, timestamp, and request correlation ID preservation
- Multilingual query handling (Hindi, Marathi, English)
- Agricultural metadata propagation
- Strict verification of ZERO KB/Memory publication and ZERO Qdrant access
- Custom provider replacement compatibility
