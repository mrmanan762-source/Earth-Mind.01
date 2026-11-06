"""Intelligent Freshness-Aware Caching Subsystem for EarthMind Stage R10 Web Search.

Architectural Guarantees:
- Avoids repeated external API requests for identical or equivalent queries.
- Normalized multi-factor query fingerprinting: includes query text, language, region/location,
  crop, season, and query category.
- Strict Tenant / User Isolation: If user/farmer context is private, farmer identifiers
  prevent private farm context from leaking across user boundaries.
- Information-Category Freshness Policies:
  - Stable reference knowledge (taxa, botanical details): long TTL (default 24h).
  - Crop advisories & pest/disease management: moderate TTL (default 4h).
  - Weather & agroclimatology: short TTL (default 30m).
  - Market prices & real-time notices: zero TTL (never cached or 0s).
- Preserves original source attribution, provider identity, and retrieval timestamps.
- Caches validated raw retrieval candidates distinctly from final synthesized AI advice.
- Replaceable design: Clean IWebSearchCache protocol backed by an in-memory thread-safe LRU,
  allowing seamless drop-in of Redis or external cache without modifying engine code.
- Zero Memory or C.2 Knowledge Base writes.
"""

from collections import OrderedDict
import hashlib
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from core.config.settings import WebSearchConfig
from core.schemas.web_search import WebSearchRequest, WebSearchResponse, WebSearchResult

logger = logging.getLogger(__name__)


class InformationCategory:
    """Categories of agricultural search queries mapped to freshness policies."""
    STABLE_REFERENCE = "stable_reference"
    ADVISORY_DISEASE = "advisory_disease"
    WEATHER = "weather"
    MARKET_REALTIME = "market_realtime"
    GENERAL = "general"


@runtime_checkable
class IWebSearchCache(Protocol):
    """Protocol defining the web search cache interface."""

    def get(self, request: WebSearchRequest) -> Optional[WebSearchResponse]:
        """Retrieve cached WebSearchResponse if present and valid."""
        ...

    def set(self, request: WebSearchRequest, response: WebSearchResponse) -> None:
        """Cache a WebSearchResponse with appropriate freshness TTL."""
        ...

    def invalidate(self, key_or_pattern: Optional[str] = None) -> int:
        """Invalidate specific or all entries in the cache."""
        ...

    def get_stats(self) -> Dict[str, Any]:
        """Return cache performance statistics (hits, misses, evictions, size)."""
        ...


class InMemoryWebSearchCache(IWebSearchCache):
    """Thread-safe, bounded in-memory LRU cache with multi-tier TTL freshness."""

    def __init__(self, config: Optional[WebSearchConfig] = None):
        self._config = config or WebSearchConfig()
        self._max_entries = self._config.cache_max_entries
        self._enabled = self._config.cache_enabled
        self._lock = threading.RLock()

        # Internal storage: key -> (cached_response, expiry_timestamp, category)
        self._store: OrderedDict[str, Tuple[WebSearchResponse, float, str]] = OrderedDict()

        # Telemetry stats
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._expirations = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def classify_category(self, request: WebSearchRequest) -> str:
        """Classifies request into an information category for TTL resolution."""
        # 1. Check explicit search_mode or filters
        if request.search_mode in ("weather", "climate", "agroclimatology") or getattr(request, "include_agroclimatology", False):
            return InformationCategory.WEATHER

        q_lower = request.query_text.lower()

        # 2. Market and real-time announcements
        market_keywords = ("mandi", "market price", "bhav", "rate today", "apmc", "msp", "price")
        if any(kw in q_lower for kw in market_keywords):
            return InformationCategory.MARKET_REALTIME

        # 3. Weather & rainfall
        weather_keywords = ("weather", "rainfall", "temperature", "precipitation", "solar radiation", "forecast", "frost", "drought")
        if any(kw in q_lower for kw in weather_keywords):
            return InformationCategory.WEATHER

        # 4. Advisories, pest, disease, chemical recommendations
        advisory_keywords = ("disease", "pest", "spray", "fungicide", "insecticide", "advisory", "blight", "rust", "borer", "wilt", "rot", "dosage", "infestation")
        if any(kw in q_lower for kw in advisory_keywords):
            return InformationCategory.ADVISORY_DISEASE

        # 5. Stable reference (taxa, botanical names, historical practices)
        reference_keywords = ("botanical", "scientific name", "taxonomy", "family", "chromosome", "origin", "history", "subspecies")
        if any(kw in q_lower for kw in reference_keywords) or getattr(request, "include_structured", False):
            return InformationCategory.STABLE_REFERENCE

        return InformationCategory.GENERAL

    def get_ttl_for_category(self, category: str) -> float:
        """Resolves TTL in seconds based on category configuration."""
        if category == InformationCategory.MARKET_REALTIME:
            return self._config.cache_ttl_market_realtime
        elif category == InformationCategory.WEATHER:
            return self._config.cache_ttl_weather
        elif category == InformationCategory.ADVISORY_DISEASE:
            return self._config.cache_ttl_advisory_disease
        elif category == InformationCategory.STABLE_REFERENCE:
            return self._config.cache_ttl_stable_reference
        else:
            # General default
            return self._config.cache_ttl_advisory_disease

    def generate_cache_key(self, request: WebSearchRequest) -> str:
        """Generates a deterministic normalized query fingerprint.

        Includes query text, language, region, crop, season, category,
        and tenant user context to prevent cross-farmer data leakage.
        """
        norm_query = " ".join(request.query_text.strip().lower().split())
        lang = (request.language or "en").strip().lower()
        reg = (request.region or "").strip().lower()

        crop = ""
        season = ""
        if request.agricultural_metadata:
            crop = str(request.agricultural_metadata.get("crop") or "").strip().lower()
            season = str(request.agricultural_metadata.get("season") or "").strip().lower()

        # Farmer / Tenant Context Isolation:
        # If request contains a user_id or farm_id, bind it into the cache key so private
        # farm advisories are never returned to a different farmer.
        user_tenant = ""
        if request.user_context:
            user_id = request.user_context.get("user_id") or request.user_context.get("owner_id")
            farm_id = request.user_context.get("farm_id")
            if user_id or farm_id:
                user_tenant = f"{user_id or ''}:{farm_id or ''}"

        payload = {
            "query": norm_query,
            "lang": lang,
            "region": reg,
            "crop": crop,
            "season": season,
            "search_mode": request.search_mode or "standard",
            "include_scholarly": getattr(request, "include_scholarly", False),
            "include_agroclimatology": getattr(request, "include_agroclimatology", False),
            "tenant": user_tenant,
        }

        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, request: WebSearchRequest) -> Optional[WebSearchResponse]:
        """Retrieve cached response if present, fresh, and enabled."""
        if not self._enabled:
            return None

        # Check category TTL: if market/real-time (0s TTL), bypass cache entirely
        category = self.classify_category(request)
        ttl = self.get_ttl_for_category(category)
        if ttl <= 0.0:
            with self._lock:
                self._misses += 1
            return None

        key = self.generate_cache_key(request)
        now = time.time()

        with self._lock:
            if key not in self._store:
                self._misses += 1
                return None

            cached_resp, expiry, _ = self._store[key]

            # Check expiration
            if now >= expiry:
                del self._store[key]
                self._expirations += 1
                self._misses += 1
                return None

            # Move to end (LRU hit)
            self._store.move_to_end(key)
            self._hits += 1

            # Return a copy with fresh request_id and cached flag in trace_info
            resp_copy = cached_resp.model_copy(deep=True)
            resp_copy.request_id = request.request_id
            if resp_copy.trace_info is None:
                resp_copy.trace_info = {}
            resp_copy.trace_info["from_cache"] = True
            resp_copy.trace_info["cached_at_expiry"] = expiry
            resp_copy.trace_info["cache_category"] = category
            return resp_copy

    def set(self, request: WebSearchRequest, response: WebSearchResponse) -> None:
        """Cache response with TTL based on classified category."""
        if not self._enabled:
            return

        # Do not cache empty or failed responses
        if not response.results or response.status not in ("SUCCESS", "PARTIAL"):
            return

        category = self.classify_category(request)
        ttl = self.get_ttl_for_category(category)
        if ttl <= 0.0:
            return  # No caching for this category

        key = self.generate_cache_key(request)
        expiry = time.time() + ttl

        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            elif len(self._store) >= self._max_entries:
                # Evict oldest entry (LRU)
                self._store.popitem(last=False)
                self._evictions += 1

            # Store a clean deep copy
            resp_to_cache = response.model_copy(deep=True)
            self._store[key] = (resp_to_cache, expiry, category)

    def invalidate(self, key_or_pattern: Optional[str] = None) -> int:
        """Invalidates all entries or specific key."""
        with self._lock:
            if key_or_pattern is None:
                count = len(self._store)
                self._store.clear()
                return count
            elif key_or_pattern in self._store:
                del self._store[key_or_pattern]
                return 1
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Returns snapshot of cache performance metrics."""
        with self._lock:
            total = self._hits + self._misses
            hit_ratio = round(self._hits / total, 4) if total > 0 else 0.0
            return {
                "size": len(self._store),
                "max_entries": self._max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio": hit_ratio,
                "evictions": self._evictions,
                "expirations": self._expirations,
                "enabled": self._enabled,
            }
