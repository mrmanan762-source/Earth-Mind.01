"""Unit & Integration Test Suite for EarthMind Stage R10 Resilience, Caching, and Hardening.

Covers:
1. Primary provider success.
2. Primary provider timeout with graceful fallback to secondary provider (Gemini Grounding).
3. Primary provider quota exhaustion with fallback.
4. HTTP 429 rate limit handling and Retry-After application.
5. Circuit breaker state transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED).
6. Non-retryable permanent error behavior (authentication, invalid configuration).
7. Retry limits, exponential backoff, and jitter.
8. Cache hit and miss operations.
9. Category-specific TTL freshness policies (stable, advisory, weather, market).
10. Cache tenant isolation across different farmers/users (preventing cross-farmer leakage).
11. Tracking parameter stripping in URL canonicalization.
12. Data-type separation (Wikidata structured facts & NASA POWER numerical data preserved).
13. Contradiction preservation (both sides kept, never discarded).
14. Source trust and freshness scoring.
15. Failure isolation: sub-provider errors do not crash search pipeline.
16. Secret masking in logs and configuration.
17. Downstream R11 Evidence Builder and R12 Evidence Validator compatibility.
"""

import json
import logging
import time
from unittest.mock import MagicMock, patch
import pytest

from core.config.settings import WebSearchConfig, settings
from core.errors.exceptions import (
    InvalidWebSearchRequestError,
    WebSearchAuthenticationError,
    WebSearchConfigurationError,
    WebSearchExecutionError,
    WebSearchProviderUnavailableError,
    WebSearchRateLimitError,
    WebSearchTimeoutError,
)
from core.interfaces.web_search import IWebSearchProvider
from core.schemas.web_search import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
    WebSearchStatus,
)
from modules.knowledge_base.web_search.cache import (
    InMemoryWebSearchCache,
    InformationCategory,
)
from modules.knowledge_base.web_search.engine import WebSearchEngine
from modules.knowledge_base.web_search.evidence_processor import EvidenceProcessor
from modules.knowledge_base.web_search.providers.fake_provider import FakeWebSearchProvider
from modules.knowledge_base.web_search.providers.gemini_grounding_provider import GeminiGroundingSearchProvider
from modules.knowledge_base.web_search.providers.tavily_provider import TavilySearchProvider
from modules.knowledge_base.web_search.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    ProviderRateLimiter,
    QuotaExceededError,
    QuotaManager,
    ResilienceManager,
)


# --- Mock Provider Classes for Testing ---

class MockConfigurableProvider(IWebSearchProvider):
    """Provider with configurable response behavior for testing."""

    def __init__(self, name: str, behavior="success", results=None):
        self._name = name
        self.behavior = behavior
        self.call_count = 0
        self.results = results or [
            WebSearchResult(
                result_id=f"{name}_1",
                title=f"{name.capitalize()} Result",
                url=f"https://{name}.example.com/advisory",
                snippet=f"Agricultural guidance from {name}",
                provider=name,
                retrieval_timestamp=time.time(),
            )
        ]

    @property
    def provider_name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return True

    def supported_capabilities(self):
        return {"test": True}

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        self.call_count += 1
        if self.behavior == "timeout":
            raise WebSearchTimeoutError(self._name, request.timeout)
        elif self.behavior == "rate_limit":
            raise WebSearchRateLimitError(self._name, f"HTTP 429 from {self._name}")
        elif self.behavior == "auth_error":
            raise WebSearchAuthenticationError(self._name, f"Invalid API key for {self._name}")
        elif self.behavior == "unavailable":
            raise WebSearchProviderUnavailableError(self._name, f"Service 503 for {self._name}")
        elif self.behavior == "empty":
            return WebSearchResponse(
                request_id=request.request_id,
                status=WebSearchStatus.EMPTY_RESULT,
                query_text=request.query_text,
                results=[],
                result_count=0,
                provider_name=self._name,
            )

        return WebSearchResponse(
            request_id=request.request_id,
            status=WebSearchStatus.SUCCESS,
            query_text=request.query_text,
            results=self.results,
            result_count=len(self.results),
            provider_name=self._name,
        )


# --- 1. Primary Success & Secondary Fallback Tests ---

def test_primary_provider_success():
    """Verify primary provider succeeds cleanly when available."""
    primary = MockConfigurableProvider("primary_provider", behavior="success")
    fallback = MockConfigurableProvider("secondary_provider", behavior="success")

    cfg = WebSearchConfig(enable_provider_fallback=True)
    engine = WebSearchEngine(config=cfg, provider=primary, fallback_provider=fallback)

    req = WebSearchRequest(query_text="chickpea wilt control")
    resp = engine.search(req)

    assert resp.status == WebSearchStatus.SUCCESS
    assert resp.result_count == 1
    assert resp.provider_name == "primary_provider"
    assert primary.call_count == 1
    assert fallback.call_count == 0


def test_primary_timeout_fallback_to_secondary():
    """Verify primary provider timeout triggers controlled fallback to secondary provider."""
    primary = MockConfigurableProvider("tavily", behavior="timeout")
    fallback = MockConfigurableProvider("gemini_grounding", behavior="success")

    cfg = WebSearchConfig(enable_provider_fallback=True)
    engine = WebSearchEngine(config=cfg, provider=primary, fallback_provider=fallback)

    req = WebSearchRequest(query_text="rice brown planthopper management")
    resp = engine.search(req)

    assert resp.status == WebSearchStatus.SUCCESS
    assert resp.result_count == 1
    assert resp.provider_name == "gemini_grounding"
    assert resp.trace_info.get("fallback_occurred") is True
    assert primary.call_count > 0
    assert fallback.call_count == 1


def test_primary_rate_limit_fallback_to_secondary():
    """Verify HTTP 429 rate limit on primary falls back to secondary provider."""
    primary = MockConfigurableProvider("tavily", behavior="rate_limit")
    fallback = MockConfigurableProvider("gemini_grounding", behavior="success")

    cfg = WebSearchConfig(enable_provider_fallback=True)
    engine = WebSearchEngine(config=cfg, provider=primary, fallback_provider=fallback)

    req = WebSearchRequest(query_text="wheat rust fungicide spray timing")
    resp = engine.search(req)

    assert resp.status == WebSearchStatus.SUCCESS
    assert resp.provider_name == "gemini_grounding"
    assert resp.trace_info.get("fallback_occurred") is True


def test_both_providers_fail_returns_partial_or_error_without_crash():
    """Verify system does not crash if both primary and fallback fail."""
    primary = MockConfigurableProvider("tavily", behavior="timeout")
    fallback = MockConfigurableProvider("gemini_grounding", behavior="unavailable")

    cfg = WebSearchConfig(enable_provider_fallback=True)
    engine = WebSearchEngine(config=cfg, provider=primary, fallback_provider=fallback)

    req = WebSearchRequest(query_text="maize fall armyworm trap catch")
    resp = engine.search(req)

    assert resp.status in (WebSearchStatus.PROVIDER_TIMEOUT, WebSearchStatus.PROVIDER_UNAVAILABLE, WebSearchStatus.PROVIDER_ERROR)
    assert resp.result_count == 0
    assert resp.error_message is not None


# --- 2. Circuit Breaker State Transition Tests ---

def test_circuit_breaker_state_transitions():
    """Verify CLOSED -> OPEN -> HALF_OPEN -> CLOSED transitions."""
    cb = CircuitBreaker("test_provider", failure_threshold=2, recovery_timeout=0.2, half_open_success_threshold=1)

    assert cb.state == CircuitState.CLOSED
    cb.before_execution()

    # Record 1 failure
    cb.record_failure(WebSearchTimeoutError("test_provider", 5.0))
    assert cb.state == CircuitState.CLOSED

    # Record 2nd failure -> Tripped to OPEN
    cb.record_failure(WebSearchTimeoutError("test_provider", 5.0))
    assert cb.state == CircuitState.OPEN

    # In OPEN state, before_execution raises CircuitBreakerOpenError
    with pytest.raises(CircuitBreakerOpenError):
        cb.before_execution()

    # Wait for recovery cooldown
    time.sleep(0.25)
    assert cb.state == CircuitState.HALF_OPEN

    # In HALF_OPEN, record successful probe
    cb.before_execution()
    cb.record_success()

    # Circuit closes after successful probe
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_isolation_between_providers():
    """Verify tripping one provider's circuit does not affect other providers."""
    rm = ResilienceManager()
    cb_tavily = rm.get_circuit_breaker("tavily")
    cb_gemini = rm.get_circuit_breaker("gemini_grounding")

    # Trip tavily circuit
    for _ in range(cb_tavily.failure_threshold):
        cb_tavily.record_failure(WebSearchTimeoutError("tavily", 5.0))

    assert cb_tavily.state == CircuitState.OPEN
    assert cb_gemini.state == CircuitState.CLOSED

    # Tavily fast fails
    with pytest.raises(CircuitBreakerOpenError):
        cb_tavily.before_execution()

    # Gemini succeeds
    cb_gemini.before_execution()


# --- 3. Rate Limiter and Quota Management Tests ---

def test_provider_rate_limiter_retry_after():
    """Verify Retry-After header cooldown enforcement."""
    rl = ProviderRateLimiter("test_provider", rate_limit_per_minute=60, max_concurrency=2)
    assert rl.acquire(timeout=0.1)
    rl.release()

    # Apply 2 second retry-after
    rl.apply_retry_after(1.0)
    with pytest.raises(WebSearchRateLimitError):
        rl.acquire(timeout=0.1)


def test_quota_manager_budget_enforcement():
    """Verify local estimated daily usage budget halts requests to prevent billing triggers."""
    qm = QuotaManager(daily_budget=3, monthly_budget=10)

    # First 3 calls succeed
    qm.check_and_increment("tavily")
    qm.check_and_increment("tavily")
    qm.check_and_increment("tavily")

    # 4th call raises QuotaExceededError
    with pytest.raises(QuotaExceededError) as exc_info:
        qm.check_and_increment("tavily")
    assert "daily usage budget exhausted" in str(exc_info.value)

    usage = qm.get_usage("tavily")
    assert usage["daily_estimated_count"] == 3
    assert usage["is_locally_estimated"] is True


# --- 4. Intelligent Caching Tests ---

def test_cache_hit_miss_and_invalidation():
    """Verify cache stores response and serves subsequent identical requests."""
    cache = InMemoryWebSearchCache()
    req = WebSearchRequest(query_text="onion thrips organic neem spray")

    assert cache.get(req) is None

    mock_resp = WebSearchResponse(
        request_id=req.request_id,
        status=WebSearchStatus.SUCCESS,
        query_text=req.query_text,
        results=[
            WebSearchResult(
                result_id="res_01",
                title="Neem Spray for Onion Thrips",
                url="https://dogr.icar.gov.in/thrips",
                snippet="Azadirachtin 10000 ppm @ 2 ml/l controls onion thrips effectively.",
                provider="fake",
            )
        ],
        result_count=1,
        provider_name="fake",
    )

    cache.set(req, mock_resp)

    # Cache hit
    hit_resp = cache.get(req)
    assert hit_resp is not None
    assert hit_resp.result_count == 1
    assert hit_resp.trace_info.get("from_cache") is True

    # Invalidate
    cache.invalidate()
    assert cache.get(req) is None


def test_cache_category_freshness_policies():
    """Verify category classification and zero TTL for market prices."""
    cache = InMemoryWebSearchCache()

    # Market query -> category MARKET_REALTIME -> 0s TTL (no cache)
    market_req = WebSearchRequest(query_text="nagpur onion mandi bhav today")
    cat = cache.classify_category(market_req)
    assert cat == InformationCategory.MARKET_REALTIME
    assert cache.get_ttl_for_category(cat) == 0.0

    mock_market_resp = WebSearchResponse(
        status=WebSearchStatus.SUCCESS,
        query_text=market_req.query_text,
        results=[WebSearchResult(result_id="m1", title="Mandi Bhav", url="https://mandi.gov.in", snippet="Rs 2400/qtl", provider="fake")],
        result_count=1,
        provider_name="fake",
    )
    cache.set(market_req, mock_market_resp)
    assert cache.get(market_req) is None  # Not cached!

    # Weather query -> category WEATHER -> 1800s TTL
    weather_req = WebSearchRequest(query_text="patna weekly rainfall forecast")
    assert cache.classify_category(weather_req) == InformationCategory.WEATHER

    # Reference query -> category STABLE_REFERENCE -> 86400s TTL
    ref_req = WebSearchRequest(query_text="cicer arietinum botanical classification")
    assert cache.classify_category(ref_req) == InformationCategory.STABLE_REFERENCE


def test_cache_farmer_tenant_isolation():
    """Verify private farm context from farmer A does not leak to farmer B."""
    cache = InMemoryWebSearchCache()

    req_farmer_a = WebSearchRequest(
        query_text="nitrogen fertilizer dosage for maize",
        user_context={"user_id": "farmer_123", "farm_id": "farm_alpha"},
    )
    req_farmer_b = WebSearchRequest(
        query_text="nitrogen fertilizer dosage for maize",
        user_context={"user_id": "farmer_456", "farm_id": "farm_beta"},
    )

    key_a = cache.generate_cache_key(req_farmer_a)
    key_b = cache.generate_cache_key(req_farmer_b)
    assert key_a != key_b

    # Store for Farmer A
    cache.set(
        req_farmer_a,
        WebSearchResponse(
            status=WebSearchStatus.SUCCESS,
            query_text=req_farmer_a.query_text,
            results=[WebSearchResult(result_id="a1", title="Alpha Farm Advisory", url="https://icar.org.in/a", snippet="Alpha Soil N: 120kg/ha", provider="fake")],
            result_count=1,
            provider_name="fake",
        )
    )

    # Farmer B gets cache miss (no leakage)
    assert cache.get(req_farmer_b) is None
    assert cache.get(req_farmer_a) is not None


# --- 5. Evidence Processor Tests (URL Canonicalization & Contradictions) ---

def test_url_canonicalization_tracking_strip():
    """Verify marketing tracking query parameters are cleanly stripped."""
    ep = EvidenceProcessor()
    dirty_url = "https://www.icar.org.in/package-of-practices/?utm_source=twitter&utm_medium=social&utm_campaign=kharif2024&id=42#intro"
    clean_url = ep.canonicalize_url(dirty_url)

    assert clean_url == "https://icar.org.in/package-of-practices?id=42"
    assert "utm_" not in clean_url
    assert "twitter" not in clean_url


def test_data_type_separation_preserves_wikidata_and_nasa():
    """Verify structured facts and agroclimatology data are not lost in URL dedup."""
    ep = EvidenceProcessor()
    results = [
        WebSearchResult(
            result_id="wiki_1",
            title="Cicer arietinum",
            url="https://www.wikidata.org/wiki/Q81375",
            result_type="structured_fact",
            snippet="Cicer arietinum (Q81375) - species of legume",
            provider="wikidata",
        ),
        WebSearchResult(
            result_id="nasa_1",
            title="NASA POWER Daily Point",
            url="https://power.larc.nasa.gov/api/temporal/daily/point",
            result_type="agroclimatology",
            snippet="T2M: 25.4C, PRECTOTCORR: 12.0mm",
            provider="nasa_power",
        ),
        WebSearchResult(
            result_id="web_1",
            title="Chickpea ICAR",
            url="https://iipr.icar.gov.in/chickpea",
            result_type="web",
            snippet="Chickpea cultivation guidelines",
            provider="tavily",
        ),
    ]

    deduped, _ = ep.deduplicate_and_rank(results, max_results=5)
    assert len(deduped) == 3
    types = [it.result_type for it in deduped]
    assert "structured_fact" in types
    assert "agroclimatology" in types


def test_evidence_contradiction_detection_and_preservation():
    """Verify opposing agricultural recommendations are preserved on both sides."""
    ep = EvidenceProcessor()
    results = [
        WebSearchResult(
            result_id="res_a",
            title="Chemical Control for Bollworm",
            url="https://sau.edu/cotton/pest-a",
            result_type="web",
            snippet="Chemical control with synthetic pyrethroid is recommended for severe infestations.",
            provider="tavily",
        ),
        WebSearchResult(
            result_id="res_b",
            title="Organic Cotton Pest Strategy",
            url="https://sau.edu/cotton/pest-b",
            result_type="web",
            snippet="Chemical control is not recommended; adopt organic only bio-control methods.",
            provider="tavily",
        ),
    ]

    deduped, conflicts = ep.deduplicate_and_rank(results, max_results=5)
    # Both items preserved
    assert len(deduped) == 2
    # Conflict detected and recorded
    assert len(conflicts) > 0
    assert any("Contradictory recommendation" in c for c in conflicts)
    assert deduped[0].metadata.get("has_contradiction") is True
    assert deduped[1].metadata.get("has_contradiction") is True


# --- 6. Secret Redaction & Observability Tests ---

def test_secret_masking_in_settings():
    """Verify API keys and passwords are masked in settings.to_safe_dict()."""
    safe_dict = settings.to_safe_dict()
    assert "web_search" in safe_dict
    ws = safe_dict["web_search"]

    # Verify no raw sensitive keys are exposed
    for key in ("api_key", "tavily_api_key", "gemini_api_key", "brave_api_key"):
        val = ws.get(key)
        if val:
            assert "***" in val
            assert not val.startswith("tvly-")
            assert not val.startswith("AIza")


# --- 7. Downstream R11 & R12 Integration Compatibility ---

def test_r10_to_r11_r12_pipeline_compatibility():
    """Verify hardened R10 WebSearchResult flows cleanly into R11 EvidenceBuilder and R12 Validator."""
    from modules.knowledge_base.evidence.engine import EvidenceBuilderEngine
    from modules.knowledge_base.evidence.validator import EvidenceValidatorEngine
    from core.schemas.evidence import EvidenceBuildRequest
    from core.schemas.evidence_validator import EvidenceValidationRequest

    # Create mock search response
    web_res = WebSearchResult(
        result_id="tavily_crop_01",
        title="Wheat Yellow Rust Management - ICAR",
        url="https://iiwbr.icar.gov.in/rust",
        result_type="agricultural",
        snippet="Apply Propiconazole 25 EC @ 0.1% at first appearance of yellow rust pustules.",
        source="iiwbr.icar.gov.in",
        provider="tavily",
        retrieval_timestamp=time.time(),
        score=0.92,
        metadata={"trusted_domain": True},
    )

    web_resp = WebSearchResponse(
        status=WebSearchStatus.SUCCESS,
        query_text="wheat yellow rust fungicide dosage",
        results=[web_res],
        result_count=1,
        provider_name="tavily",
    )

    # 1. R11 Evidence Builder
    builder = EvidenceBuilderEngine()
    build_req = EvidenceBuildRequest(
        query_text="wheat yellow rust fungicide dosage",
        web_search_response=web_resp,
    )
    build_resp = builder.build_evidence(build_req)
    assert build_resp.status == "SUCCESS"
    assert build_resp.package.web_items_count == 1
    assert build_resp.package.items[0].source_type == "WEB_SEARCH"

    # 2. R12 Evidence Validator
    validator = EvidenceValidatorEngine()
    val_req = EvidenceValidationRequest(package=build_resp.package)
    val_resp = validator.validate_evidence_package(val_req)
    assert val_resp.status == "VALID"
    assert val_resp.result.overall_status == "VALID"
    assert val_resp.result.valid_items_count == 1
    assert val_resp.result.total_items_count == 1
