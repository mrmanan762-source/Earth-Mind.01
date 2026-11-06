"""NASA POWER Agroclimatology API Provider Adapter for EarthMind Stage R10 Web Search.

Implements IWebSearchProvider to query NASA's Prediction Of Worldwide Energy Resources (POWER) API.
Official API endpoint: https://power.larc.nasa.gov/api/temporal/daily/point

Retrieves meteorological, climatological, and solar radiation parameters for agroclimatology (AG community).
Parameters typically include:
- T2M: Temperature at 2 Meters (°C)
- T2M_MAX / T2M_MIN: Maximum and Minimum Daily Temperatures (°C)
- PRECTOTCORR: Precipitation Corrected (mm/day)
- ALLSKY_SFC_SW_DWN: All Sky Surface Shortwave Downward Irradiance (MJ/m^2/day)

CRITICAL SEPARATION RULE:
- Numerical agroclimatology data MUST NOT be represented as ordinary web-page search results.
- Returns result_type='agroclimatology'.
- Structured time series data and summary statistics are preserved in metadata and readable summary in snippet.
"""

from datetime import datetime, timedelta, timezone
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from core.config.settings import WebSearchConfig
from core.errors.exceptions import (
    InvalidWebSearchRequestError,
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

logger = logging.getLogger(__name__)

# Representative latitude/longitude mappings for common agricultural regions/states in India
REGIONAL_AGRI_COORDINATES: Dict[str, Tuple[float, float]] = {
    "punjab": (30.9010, 75.8573),
    "haryana": (29.0588, 76.0856),
    "bihar": (25.5941, 85.1376),
    "uttar pradesh": (26.8467, 80.9462),
    "up": (26.8467, 80.9462),
    "madhya pradesh": (23.2599, 77.4126),
    "mp": (23.2599, 77.4126),
    "maharashtra": (19.7515, 75.7139),
    "gujarat": (22.2587, 71.1924),
    "rajasthan": (27.0238, 74.2179),
    "tamil nadu": (11.1271, 78.6569),
    "andhra pradesh": (15.9129, 79.7400),
    "telangana": (18.1124, 79.0193),
    "karnataka": (15.3173, 75.7139),
    "west bengal": (22.9868, 87.8550),
    "odisha": (20.9517, 85.0985),
    "delhi": (28.6139, 77.2090),
}


class NasaPowerSearchProvider(IWebSearchProvider):
    """NASA POWER API adapter for agroclimatology and meteorological environmental data."""

    def __init__(
        self,
        config: Optional[WebSearchConfig] = None,
        endpoint: Optional[str] = None,
        community: Optional[str] = None,
        parameters: Optional[List[str]] = None,
        timeout: Optional[float] = None,
        user_agent: Optional[str] = None,
    ):
        cfg = config or WebSearchConfig()
        self._endpoint = endpoint or cfg.nasa_power_endpoint
        self._community = community or cfg.nasa_power_community
        self._parameters = parameters or cfg.nasa_power_parameters
        self._timeout = timeout if timeout is not None else cfg.timeout
        self._user_agent = user_agent or cfg.user_agent

    @property
    def provider_name(self) -> str:
        return "nasa_power"

    def is_available(self) -> bool:
        return bool(self._endpoint and self._endpoint.strip())

    def supported_capabilities(self) -> Dict[str, Any]:
        return {
            "agroclimatology_data": True,
            "meteorological_time_series": True,
            "solar_radiation": True,
            "precipitation": True,
            "temperature_metrics": True,
            "numerical_data_only": True,
        }

    def _resolve_coordinates(self, request: WebSearchRequest) -> Tuple[float, float, str]:
        """Resolves latitude and longitude from request filters, agricultural metadata, region, or text."""
        # 1. Direct filters or agricultural metadata coordinates
        if request.filters:
            if "latitude" in request.filters and "longitude" in request.filters:
                try:
                    return float(request.filters["latitude"]), float(request.filters["longitude"]), "filters"
                except (ValueError, TypeError):
                    pass

        if request.agricultural_metadata:
            meta = request.agricultural_metadata
            if "latitude" in meta and "longitude" in meta:
                try:
                    return float(meta["latitude"]), float(meta["longitude"]), "agricultural_metadata"
                except (ValueError, TypeError):
                    pass
            reg = str(meta.get("state") or meta.get("region") or "").lower().strip()
            if reg in REGIONAL_AGRI_COORDINATES:
                lat, lon = REGIONAL_AGRI_COORDINATES[reg]
                return lat, lon, f"region:{reg}"

        # 2. Region string in request
        if request.region:
            reg = request.region.lower().strip()
            if reg in REGIONAL_AGRI_COORDINATES:
                lat, lon = REGIONAL_AGRI_COORDINATES[reg]
                return lat, lon, f"region:{reg}"

        # 3. Match region keywords in query text
        q_lower = request.query_text.lower()
        for region_name, (lat, lon) in REGIONAL_AGRI_COORDINATES.items():
            if re.search(r"\b" + re.escape(region_name) + r"\b", q_lower):
                return lat, lon, f"text_match:{region_name}"

        # Default fallback coordinates: Central India agricultural zone (e.g., Bhopal / MP)
        return 23.2599, 77.4126, "default_central_india"

    def _resolve_date_window(self, request: WebSearchRequest) -> Tuple[str, str]:
        """Resolves start and end date in YYYYMMDD format for NASA POWER query."""
        if request.filters and "start_date" in request.filters and "end_date" in request.filters:
            s = str(request.filters["start_date"]).replace("-", "")
            e = str(request.filters["end_date"]).replace("-", "")
            if len(s) == 8 and len(e) == 8:
                return s, e

        # NASA POWER daily data typically has a processing latency of 2-5 days
        # We query the most recent 7-day stable window from 10 days ago to 3 days ago
        now = datetime.now(timezone.utc)
        end_dt = now - timedelta(days=3)
        start_dt = end_dt - timedelta(days=6)
        return start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d")

    def search(self, request: WebSearchRequest) -> WebSearchResponse:
        """Queries NASA POWER agroclimatology API and returns structured environmental data."""
        start_time = time.perf_counter()

        if not request.query_text or not request.query_text.strip():
            raise InvalidWebSearchRequestError("Query text cannot be empty.")

        timeout = request.timeout if request.timeout > 0 else self._timeout
        lat, lon, location_source = self._resolve_coordinates(request)
        start_date, end_date = self._resolve_date_window(request)

        params: Dict[str, str] = {
            "parameters": ",".join(self._parameters),
            "community": self._community,
            "longitude": f"{lon:.4f}",
            "latitude": f"{lat:.4f}",
            "start": start_date,
            "end": end_date,
            "format": "JSON",
        }

        query_str = urllib.parse.urlencode(params)
        full_url = f"{self._endpoint}?{query_str}"

        req = urllib.request.Request(
            full_url,
            headers={
                "User-Agent": self._user_agent or "EarthMind-RAG/1.0 (+https://github.com/earthmind)",
                "Accept": "application/json",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
        except urllib.error.HTTPError as http_err:
            if http_err.code == 429:
                raise WebSearchRateLimitError(self.provider_name, "NASA POWER API rate limit exceeded.")
            raise WebSearchProviderUnavailableError(
                self.provider_name, f"HTTP {http_err.code}: NASA POWER API unavailable: {http_err.reason}"
            )
        except TimeoutError:
            raise WebSearchTimeoutError(self.provider_name, timeout)
        except urllib.error.URLError as url_err:
            if isinstance(url_err.reason, TimeoutError) or "timed out" in str(url_err.reason).lower():
                raise WebSearchTimeoutError(self.provider_name, timeout)
            raise WebSearchProviderUnavailableError(
                self.provider_name, f"Network error connecting to NASA POWER: {url_err.reason}"
            )
        except json.JSONDecodeError as json_err:
            raise WebSearchExecutionError(
                self.provider_name, f"Failed to parse NASA POWER JSON response: {json_err}"
            )

        properties = data.get("properties", {})
        parameter_dict = properties.get("parameter", {})
        if not parameter_dict:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                request_id=request.request_id,
                status=WebSearchStatus.EMPTY_RESULT,
                query_text=request.query_text,
                results=[],
                result_count=0,
                provider_name=self.provider_name,
                execution_time_ms=elapsed_ms,
            )

        now_ts = time.time()
        # Compute summary metrics across parameters
        summaries: Dict[str, Dict[str, Any]] = {}
        valid_values_found = False

        for param_name, daily_series in parameter_dict.items():
            valid_vals = [
                val for val in daily_series.values()
                if val is not None and val != -999.0 and val != -999
            ]
            if valid_vals:
                valid_values_found = True
                summaries[param_name] = {
                    "mean": round(sum(valid_vals) / len(valid_vals), 2),
                    "min": round(min(valid_vals), 2),
                    "max": round(max(valid_vals), 2),
                    "latest": round(valid_vals[-1], 2),
                    "unit": properties.get("parameter_information", {}).get(param_name, {}).get("units", ""),
                }

        if not valid_values_found:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return WebSearchResponse(
                request_id=request.request_id,
                status=WebSearchStatus.EMPTY_RESULT,
                query_text=request.query_text,
                results=[],
                result_count=0,
                provider_name=self.provider_name,
                execution_time_ms=elapsed_ms,
            )

        # Build clear agroclimatology summary snippet
        summary_lines = [
            f"NASA POWER Agroclimatology Observation (Lat: {lat:.2f}, Lon: {lon:.2f}, Period: {start_date} to {end_date}):"
        ]
        if "T2M" in summaries:
            summary_lines.append(f"• Mean Temperature (T2M): {summaries['T2M']['mean']}°C (Min: {summaries.get('T2M_MIN', {}).get('min', 'N/A')}°C, Max: {summaries.get('T2M_MAX', {}).get('max', 'N/A')}°C).")
        if "PRECTOTCORR" in summaries:
            prec_sum = round(sum(v for v in parameter_dict["PRECTOTCORR"].values() if v > 0), 2)
            summary_lines.append(f"• Total Precipitation: {prec_sum} mm (Daily mean: {summaries['PRECTOTCORR']['mean']} mm/day).")
        if "ALLSKY_SFC_SW_DWN" in summaries:
            summary_lines.append(f"• All-Sky Solar Insolation: {summaries['ALLSKY_SFC_SW_DWN']['mean']} MJ/m²/day.")

        snippet_text = " \n".join(summary_lines)
        portal_url = f"https://power.larc.nasa.gov/data-access-viewer/?lat={lat:.4f}&lon={lon:.4f}"

        res_id = f"nasa_power_{lat:.2f}_{lon:.2f}_{start_date}_{end_date}"
        result_item = WebSearchResult(
            result_id=res_id,
            title=f"NASA POWER Agroclimatology Data (Lat: {lat:.2f}, Lon: {lon:.2f})",
            url=portal_url,
            canonical_url=portal_url,
            result_type="agroclimatology",
            snippet=snippet_text,
            source="power.larc.nasa.gov",
            provider=self.provider_name,
            retrieval_timestamp=now_ts,
            rank=1,
            provenance={
                "provider": self.provider_name,
                "api_endpoint": self._endpoint,
                "community": self._community,
                "latitude": lat,
                "longitude": lon,
                "location_resolution": location_source,
                "start_date": start_date,
                "end_date": end_date,
                "query": request.query_text,
                "retrieval_timestamp": now_ts,
            },
            metadata={
                "is_numerical_agroclimatology": True,
                "latitude": lat,
                "longitude": lon,
                "start_date": start_date,
                "end_date": end_date,
                "location_source": location_source,
                "parameter_summaries": summaries,
                "raw_time_series": parameter_dict,
            },
            request_id=request.request_id,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return WebSearchResponse(
            request_id=request.request_id,
            status=WebSearchStatus.SUCCESS,
            query_text=request.query_text,
            results=[result_item],
            result_count=1,
            provider_name=self.provider_name,
            execution_time_ms=elapsed_ms,
        )
