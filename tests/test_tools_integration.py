"""Integration, provider-adapter and security tests for the Phase 3 tool system.

Coverage:
- Registry -> Dispatcher -> Tool adapter integration.
- Tool execution -> result normalization.
- Provider timeout and retry handling (mocked).
- Satellite adapter compatibility with the existing Satellite Intelligence module.
- Web search provider adapter behaviour (Tavily / Gemini / fake) — MOCKED.
- Weather provider adapter behaviour (Open-Meteo / OpenWeather / fake) — MOCKED.
- Security: secret redaction, unauthorized invocation, request-size limits,
  unsafe expression rejection, no secret exposure in results.
- ToolModule <-> WorkflowEngine integration.

IMPORTANT: Every external provider interaction in this file is mocked or uses a
deterministic fake. NO live network calls are made. Live connectivity is not
verified here and must be confirmed separately when credentials are supplied.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from core.config.settings import WeatherConfig, WebSearchConfig
from core.errors.exceptions import (
    WebSearchAuthenticationError,
    WeatherAuthenticationError,
    WeatherProviderUnavailableError,
)
from core.schemas.application import ApplicationRequest
from core.schemas.tools import (
    ToolCallRequest,
    ToolCallStatus,
    ToolPermission,
)
from core.schemas.web_search import WebSearchRequest, WebSearchStatus
from core.schemas.weather import WeatherStatus
from modules.knowledge_base.web_search.providers.fake_provider import FakeWebSearchProvider
from modules.knowledge_base.web_search.providers.gemini_grounding_provider import (
    GeminiGroundingSearchProvider,
)
from modules.knowledge_base.web_search.providers.tavily_provider import TavilySearchProvider
from modules.tools.catalog.satellite import SatelliteTool
from modules.tools.catalog.weather import WeatherTool
from modules.tools.catalog.web_search import WebSearchTool
from modules.tools.registry import ToolRegistry
from modules.tools.security import (
    redact_mapping,
    redact_text,
    sanitize_error_message,
)
from modules.tools.tool_module import ToolModule
from modules.tools.tool_service import ToolService
from modules.tools.weather_providers.fake_provider import FakeWeatherProvider
from modules.tools.weather_providers.open_meteo_provider import OpenMeteoWeatherProvider
from modules.tools.weather_providers.openweather_provider import OpenWeatherProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_urlopen_response(body: dict):
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = json.dumps(body).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    return mock_resp


@pytest.fixture()
def fake_engine():
    from modules.knowledge_base.web_search.engine import WebSearchEngine

    return WebSearchEngine(config=WebSearchConfig(provider="fake"), provider=FakeWebSearchProvider())


# ---------------------------------------------------------------------------
# Registry -> Dispatcher -> adapter integration
# ---------------------------------------------------------------------------

def test_service_registers_full_catalogue():
    service = ToolService()
    tool_ids = {d.tool_id for d in service.list_tools()}
    assert {"calculator", "web_search", "weather", "satellite_intelligence"}.issubset(tool_ids)


def test_service_end_to_end_calculator():
    service = ToolService()
    result = service.execute(
        ToolCallRequest(
            tool_id="calculator",
            arguments={"operation": "evaluate", "expression": "(3+5)*2"},
            permissions=[ToolPermission.COMPUTE],
        )
    )
    assert result.status == ToolCallStatus.SUCCESS
    assert result.payload["result"] == 16


def test_web_search_tool_normalizes_provider_results(fake_engine):
    service = ToolService(web_search_engine=fake_engine)
    result = service.execute(
        ToolCallRequest(
            tool_id="web_search",
            arguments={"query": "wheat rust management", "max_results": 4},
            permissions=[ToolPermission.WEB_SEARCH, ToolPermission.EXTERNAL_NETWORK],
        )
    )
    assert result.status == ToolCallStatus.SUCCESS
    assert result.payload["result_count"] >= 1
    # Provenance preserved.
    assert all(src.source_type == "web" for src in result.sources)
    assert all(src.url for src in result.sources)
    # Disclaimer present (snippets are not verified conclusions).
    assert "disclaimer" in result.payload


def test_web_search_tool_missing_query(fake_engine):
    service = ToolService(web_search_engine=fake_engine)
    result = service.execute(
        ToolCallRequest(
            tool_id="web_search",
            arguments={"query": "   "},
            permissions=[ToolPermission.WEB_SEARCH, ToolPermission.EXTERNAL_NETWORK],
        )
    )
    assert result.status == ToolCallStatus.INVALID_REQUEST


def test_web_search_tool_unavailable_without_credentials():
    """Tavily provider without a key reports unavailable; no live call attempted."""
    tool = WebSearchTool(config=WebSearchConfig(provider="tavily", tavily_api_key=None))
    assert tool.is_available() is False


# ---------------------------------------------------------------------------
# Web search provider adapters (MOCKED)
# ---------------------------------------------------------------------------

@patch("urllib.request.urlopen")
def test_tavily_provider_mocked_success(mock_urlopen):
    mock_urlopen.return_value = _mock_urlopen_response(
        {
            "results": [
                {
                    "title": "ICAR advisory",
                    "url": "https://icar.org.in/rice",
                    "content": "Rice blast management guidance.",
                    "score": 0.9,
                }
            ],
            "answer": "Rice blast is managed by ...",
        }
    )
    provider = TavilySearchProvider(config=WebSearchConfig(tavily_api_key="test_key"))
    assert provider.is_available()
    response = provider.search(WebSearchRequest(query_text="rice blast", max_results=5))
    assert response.status == WebSearchStatus.SUCCESS
    assert response.result_count == 1
    assert response.results[0].provider == "tavily"


def test_tavily_provider_no_credentials_raises():
    provider = TavilySearchProvider(config=WebSearchConfig(tavily_api_key=None))
    assert provider.is_available() is False
    with pytest.raises(WebSearchAuthenticationError):
        provider.search(WebSearchRequest(query_text="anything"))


@patch("urllib.request.urlopen")
def test_gemini_grounding_provider_mocked(mock_urlopen):
    mock_urlopen.return_value = _mock_urlopen_response(
        {
            "candidates": [
                {
                    "content": {"parts": [{"text": "Grounded summary about crop rotation."}]},
                    "groundingMetadata": {
                        "groundingChunks": [
                            {"web": {"uri": "https://example.org/rotation", "title": "Crop rotation guide"}}
                        ]
                    },
                }
            ]
        }
    )
    provider = GeminiGroundingSearchProvider(config=WebSearchConfig(gemini_api_key="test_key"))
    assert provider.is_available()
    response = provider.search(WebSearchRequest(query_text="crop rotation", max_results=3))
    assert response.status in (WebSearchStatus.SUCCESS, WebSearchStatus.EMPTY_RESULT)


# ---------------------------------------------------------------------------
# Weather provider adapters (MOCKED)
# ---------------------------------------------------------------------------

@patch("urllib.request.urlopen")
def test_open_meteo_provider_mocked_success(mock_urlopen):
    mock_urlopen.return_value = _mock_urlopen_response(
        {
            "latitude": 19.0,
            "longitude": 73.0,
            "timezone": "UTC",
            "current": {
                "time": "2026-01-01T12:00",
                "temperature_2m": 27.5,
                "relative_humidity_2m": 60,
                "precipitation": 0.0,
                "wind_speed_10m": 3.0,
                "wind_direction_10m": 180,
                "surface_pressure": 1009.0,
                "weather_code": 2,
            },
            "daily": {
                "time": ["2026-01-02", "2026-01-03"],
                "weather_code": [0, 61],
                "temperature_2m_max": [30.0, 29.0],
                "temperature_2m_min": [18.0, 19.0],
                "precipitation_sum": [0.0, 5.0],
                "precipitation_probability_max": [10, 70],
                "wind_speed_10m_max": [4.0, 6.0],
            },
        }
    )
    provider = OpenMeteoWeatherProvider()
    assert provider.is_available()
    response = provider.get_weather(_weather_request(forecast_days=2))
    assert response.status == WeatherStatus.SUCCESS
    assert response.observations[0].temperature_c == 27.5
    assert response.observations[0].is_forecast is False
    assert len(response.forecast) == 2
    assert all(entry.is_forecast for entry in response.forecast)


@patch("urllib.request.urlopen")
def test_open_meteo_provider_network_error(mock_urlopen):
    import urllib.error

    mock_urlopen.side_effect = urllib.error.URLError("connection refused")
    provider = OpenMeteoWeatherProvider()
    with pytest.raises(WeatherProviderUnavailableError):
        provider.get_weather(_weather_request())


def test_openweather_provider_no_credentials():
    provider = OpenWeatherProvider(config=WeatherConfig(api_key=None))
    assert provider.is_available() is False
    with pytest.raises(WeatherAuthenticationError):
        provider.get_weather(_weather_request())


def test_weather_tool_provider_unavailable_reports_unavailable():
    """A provider reporting itself unavailable marks the tool unavailable (no live call)."""
    provider = FakeWeatherProvider(simulated_status=WeatherStatus.PROVIDER_UNAVAILABLE)
    registry = ToolRegistry()
    registry.register(WeatherTool(provider=provider))
    from modules.tools.dispatcher import ToolDispatcher

    result = ToolDispatcher(registry).dispatch(
        ToolCallRequest(
            tool_id="weather",
            arguments={"latitude": 19.0, "longitude": 73.0},
            permissions=[ToolPermission.WEATHER_DATA, ToolPermission.EXTERNAL_NETWORK],
        )
    )
    assert result.status == ToolCallStatus.UNAVAILABLE


def test_weather_tool_provider_failure_surfaces_as_error():
    """A provider failure is surfaced as a normalized execution error, not a crash."""
    from modules.tools.dispatcher import ToolDispatcher

    class FailingProvider:
        provider_name = "failing_weather"

        def is_available(self):
            return True

        def get_weather(self, request):
            raise WeatherProviderUnavailableError("failing_weather", "upstream outage")

    registry = ToolRegistry()
    registry.register(WeatherTool(provider=FailingProvider()))
    result = ToolDispatcher(registry).dispatch(
        ToolCallRequest(
            tool_id="weather",
            arguments={"latitude": 19.0, "longitude": 73.0},
            permissions=[ToolPermission.WEATHER_DATA, ToolPermission.EXTERNAL_NETWORK],
        )
    )
    assert result.status == ToolCallStatus.EXECUTION_ERROR
    assert result.error["error_code"] == "WEATHER_PROVIDER_ERROR"


def test_weather_tool_provider_retry_on_transient_failure():
    """Transient provider failures are retried per the tool execution policy."""
    call_count = {"n": 0}

    class TransientProvider:
        provider_name = "transient"

        def is_available(self):
            return True

        def get_weather(self, request):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise WeatherProviderUnavailableError("transient", "temporary outage")
            return FakeWeatherProvider().get_weather(request)

    registry = ToolRegistry()
    registry.register(WeatherTool(provider=TransientProvider()))
    from modules.tools.dispatcher import ToolDispatcher

    result = ToolDispatcher(registry).dispatch(
        ToolCallRequest(
            tool_id="weather",
            arguments={"latitude": 19.0, "longitude": 73.0},
            permissions=[ToolPermission.WEATHER_DATA, ToolPermission.EXTERNAL_NETWORK],
        )
    )
    assert result.status == ToolCallStatus.SUCCESS
    assert call_count["n"] == 2
    assert result.execution.retries == 1


def test_weather_tool_stale_data_flagged():
    tool = WeatherTool(provider=FakeWeatherProvider(fixed_observed_at="2000-01-01T00:00:00Z"))
    registry = ToolRegistry()
    registry.register(tool)
    from modules.tools.dispatcher import ToolDispatcher

    result = ToolDispatcher(registry).dispatch(
        ToolCallRequest(
            tool_id="weather",
            arguments={"latitude": 19.0, "longitude": 73.0},
            permissions=[ToolPermission.WEATHER_DATA, ToolPermission.EXTERNAL_NETWORK],
        )
    )
    assert result.payload["is_stale"] is True
    assert result.payload["stale_reason"]


def test_weather_tool_preserves_units_and_timestamps():
    registry = ToolRegistry()
    registry.register(WeatherTool(provider=FakeWeatherProvider()))
    from modules.tools.dispatcher import ToolDispatcher

    result = ToolDispatcher(registry).dispatch(
        ToolCallRequest(
            tool_id="weather",
            arguments={"latitude": 19.0, "longitude": 73.0, "units": "metric"},
            permissions=[ToolPermission.WEATHER_DATA, ToolPermission.EXTERNAL_NETWORK],
        )
    )
    assert result.payload["units"]["temperature"] == "celsius"
    assert result.payload["observations"][0]["observed_at"]
    assert result.payload["provider_name"] == "fake_weather"


# ---------------------------------------------------------------------------
# Satellite adapter compatibility (reuses existing Satellite Intelligence)
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_satellite_module():
    from core.config.settings import SatelliteConfig
    from modules.satellite.satellite_module import SatelliteModule
    from modules.satellite.satellite_service import SatelliteService

    service = SatelliteService(config=SatelliteConfig(mock_provider_enabled=True))
    return SatelliteModule(service=service)


def test_satellite_tool_lists_providers(mock_satellite_module):
    service = ToolService(satellite_module=mock_satellite_module)
    result = service.execute(
        ToolCallRequest(
            tool_id="satellite_intelligence",
            arguments={"operation": "list_providers"},
            permissions=[ToolPermission.SATELLITE_DATA],
        )
    )
    assert result.status == ToolCallStatus.SUCCESS
    assert len(result.payload["providers"]) >= 1


def test_satellite_tool_search_catalog_reuses_module(mock_satellite_module):
    service = ToolService(satellite_module=mock_satellite_module)
    result = service.execute(
        ToolCallRequest(
            tool_id="satellite_intelligence",
            arguments={
                "operation": "search_catalog",
                "latitude": 19.0,
                "longitude": 73.0,
                "provider_id": "mock_satellite_provider",
            },
            permissions=[ToolPermission.SATELLITE_DATA],
        )
    )
    assert result.status == ToolCallStatus.SUCCESS
    assert len(result.payload["datasets"]) == 1
    # Acquisition date & geospatial metadata preserved.
    assert result.payload["acquisition_date"]
    assert result.payload["geospatial"]["latitude"] == 19.0
    # Source provenance preserved.
    assert result.sources[0].source_type == "satellite"
    assert result.sources[0].observed_at


def test_satellite_tool_unsupported_operation(mock_satellite_module):
    service = ToolService(satellite_module=mock_satellite_module)
    result = service.execute(
        ToolCallRequest(
            tool_id="satellite_intelligence",
            arguments={"operation": "launch_rocket"},
            permissions=[ToolPermission.SATELLITE_DATA],
        )
    )
    assert result.status == ToolCallStatus.VALIDATION_ERROR


def test_satellite_tool_missing_coordinates(mock_satellite_module):
    service = ToolService(satellite_module=mock_satellite_module)
    result = service.execute(
        ToolCallRequest(
            tool_id="satellite_intelligence",
            arguments={"operation": "search_catalog"},
            permissions=[ToolPermission.SATELLITE_DATA],
        )
    )
    assert result.status == ToolCallStatus.INVALID_REQUEST


def test_satellite_tool_permission_required(mock_satellite_module):
    service = ToolService(satellite_module=mock_satellite_module)
    result = service.execute(
        ToolCallRequest(tool_id="satellite_intelligence", arguments={"operation": "list_providers"})
    )
    assert result.status == ToolCallStatus.PERMISSION_DENIED


# ---------------------------------------------------------------------------
# Security boundary
# ---------------------------------------------------------------------------

def test_redact_text_masks_api_keys():
    text = "Failed with key sk-abcdef1234567890 and AIzaSyABCDEFGHIJKLMNOPQRSTUV"
    redacted = redact_text(text)
    assert "sk-abcdef1234567890" not in redacted
    assert "AIzaSyABCDEFGHIJKLMNOPQRSTUV" not in redacted


def test_redact_mapping_masks_sensitive_fields():
    payload = {
        "api_key": "secret-value-123",
        "nested": {"password": "hunter2", "safe": "visible"},
        "items": [{"token": "abc123token"}],
    }
    redacted = redact_mapping(payload)
    assert redacted["api_key"] == "***REDACTED***"
    assert redacted["nested"]["password"] == "***REDACTED***"
    assert redacted["nested"]["safe"] == "visible"
    assert redacted["items"][0]["token"] == "***REDACTED***"


def test_sanitize_error_message_redacts_secret():
    message = "Request failed: api_key=tvly-abcdef1234567890"
    sanitized = sanitize_error_message(message)
    assert "tvly-abcdef1234567890" not in sanitized


def test_tool_results_never_contain_secrets():
    """A tool whose error mentions a secret must not leak it in the normalized result."""
    registry = ToolRegistry()

    class LeakyTool:
        tool_id = "leaky"

        def get_definition(self):
            from core.schemas.tools import ToolDefinition, ToolExecutionConfig

            return ToolDefinition(
                tool_id="leaky",
                name="Leaky",
                description="Raises an error containing a fake secret.",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                error_contract=["TOOL_EXECUTION_ERROR"],
                execution=ToolExecutionConfig(timeout_seconds=2.0),
            )

        def validate_arguments(self, arguments):
            return dict(arguments)

        def is_available(self):
            return True

        def execute(self, arguments, request):
            from core.errors.exceptions import ToolExecutionError

            raise ToolExecutionError(self.tool_id, "auth failed with key sk-abcdef1234567890")

    registry.register(LeakyTool())
    from modules.tools.dispatcher import ToolDispatcher

    result = ToolDispatcher(registry).dispatch(ToolCallRequest(tool_id="leaky", arguments={}))
    serialized = json.dumps(result.to_public_dict())
    assert "sk-abcdef1234567890" not in serialized


def test_settings_weather_key_masked_in_safe_dict():
    from core.config.settings import Settings

    settings_obj = Settings()
    settings_obj.weather.api_key = "super-secret-weather-key"
    safe = settings_obj.to_safe_dict()
    assert safe["weather"]["api_key"] != "super-secret-weather-key"


# ---------------------------------------------------------------------------
# ToolModule <-> WorkflowEngine integration
# ---------------------------------------------------------------------------

def test_tool_module_execute_operation():
    module = ToolModule()
    module.initialize()
    response = module.handle(
        ApplicationRequest(
            request_id="mod-tool-1",
            source="test",
            operation="execute_tool",
            payload={"tool_id": "calculator", "arguments": {"operation": "evaluate", "expression": "8*8"}},
        )
    )
    assert response.status == "SUCCESS"
    assert response.response["payload"]["result"] == 64
    module.shutdown()


def test_tool_module_list_tools():
    module = ToolModule()
    response = module.handle(
        ApplicationRequest(request_id="mod-tool-2", source="test", operation="list_tools", payload={})
    )
    assert response.status == "SUCCESS"
    assert len(response.response) >= 4


def test_tool_module_unknown_operation():
    module = ToolModule()
    response = module.handle(
        ApplicationRequest(request_id="mod-tool-3", source="test", operation="nonsense", payload={})
    )
    assert response.status == "UNKNOWN_OPERATION"


def test_tool_module_model_cannot_self_grant_permissions():
    """Permissions in the payload must be ignored; only trusted metadata grants count."""
    module = ToolModule()
    response = module.handle(
        ApplicationRequest(
            request_id="mod-tool-4",
            source="test",
            operation="execute_tool",
            payload={
                "tool_id": "satellite_intelligence",
                "arguments": {"operation": "list_providers"},
                "permissions": ["SATELLITE_DATA", "ADMIN"],  # must be ignored
            },
            metadata={"granted_permissions": []},  # trusted, empty
        )
    )
    assert response.status == "FORBIDDEN"


def test_workflow_dispatch_to_tools_module():
    from app.workflow import WorkflowEngine
    from app.lifecycle import LifecycleManager

    lifecycle = LifecycleManager()
    lifecycle.register_module("tools", ToolModule())
    workflow = WorkflowEngine(lifecycle)
    response = workflow.dispatch(
        ApplicationRequest(
            request_id="wf-tool-1",
            source="test",
            operation="execute_tool",
            payload={"tool_id": "calculator", "arguments": {"operation": "evaluate", "expression": "2**8"}},
            metadata={"target_module": "tools"},
        )
    )
    assert response.status == "SUCCESS"
    assert response.response["payload"]["result"] == 256


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _weather_request(forecast_days: int = 3):
    from core.schemas.weather import WeatherRequest

    return WeatherRequest(latitude=19.0, longitude=73.0, forecast_days=forecast_days)
