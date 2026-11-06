"""Unit tests for newly implemented Web Search Provider Adapters.

Tests:
1. BraveWebSearchProvider (auth validation, parameter handling, response parsing, status mapping)
2. WikipediaSearchProvider (multilingual routing, snippet extraction, URL formatting)
3. CrossrefSearchProvider (metadata extraction, authors, DOI, error handling)
4. OpenAlexSearchProvider (works parsing, abstract reconstruction, citation counts)
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from core.config.settings import WebSearchConfig
from core.errors.exceptions import (
    WebSearchAuthenticationError,
    WebSearchProviderUnavailableError,
    WebSearchRateLimitError,
)
from core.schemas.web_search import WebSearchRequest, WebSearchStatus
from modules.knowledge_base.web_search.providers.brave_provider import BraveWebSearchProvider
from modules.knowledge_base.web_search.providers.scholarly_provider import (
    CrossrefSearchProvider,
    OpenAlexSearchProvider,
)
from modules.knowledge_base.web_search.providers.wikipedia_provider import WikipediaSearchProvider


# --- 1. BraveWebSearchProvider Tests ---

def test_brave_provider_auth_missing():
    cfg = WebSearchConfig(brave_api_key=None, api_key=None)
    provider = BraveWebSearchProvider(config=cfg)
    assert not provider.is_available()

    req = WebSearchRequest(query_text="rice blast control")
    with pytest.raises(WebSearchAuthenticationError):
        provider.search(req)


@patch("urllib.request.urlopen")
def test_brave_provider_success(mock_urlopen):
    mock_body = json.dumps({
        "web": {
            "results": [
                {
                    "title": "ICAR Rice Advisory",
                    "url": "https://icar.org.in/rice-bulletin",
                    "description": "ICAR recommendations for paddy blast prevention.",
                    "extra_snippets": ["Spray tricyclazole 75 WP at 0.6g/L."],
                    "page_age": "2025-01-20",
                }
            ]
        }
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = mock_body
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    cfg = WebSearchConfig(brave_api_key="test_brave_key")
    provider = BraveWebSearchProvider(config=cfg)
    assert provider.is_available()

    req = WebSearchRequest(query_text="rice blast spray", request_id="req_brave_1", max_results=5)
    res = provider.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    assert res.result_count == 1
    item = res.results[0]
    assert item.title == "ICAR Rice Advisory"
    assert item.url == "https://icar.org.in/rice-bulletin"
    assert "tricyclazole" in item.snippet
    assert item.publication_date == "2025-01-20"
    assert item.provider == "brave"


# --- 2. WikipediaSearchProvider Tests ---

@patch("urllib.request.urlopen")
def test_wikipedia_provider_multilingual_and_success(mock_urlopen):
    mock_body = json.dumps({
        "query": {
            "search": [
                {
                    "title": "Cicer arietinum",
                    "pageid": 12345,
                    "snippet": "<span>Cicer arietinum</span> is commonly known as the chickpea.",
                    "wordcount": 3500,
                }
            ]
        }
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_body
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    provider = WikipediaSearchProvider()
    assert provider.is_available()

    # Test Hindi language routing
    req_hi = WebSearchRequest(query_text="चना की खेती", language="hi")
    res_hi = provider.search(req_hi)

    assert res_hi.status == WebSearchStatus.SUCCESS
    assert res_hi.result_count == 1
    item = res_hi.results[0]
    assert item.result_type == "encyclopedic"
    assert "hi.wikipedia.org" in item.url
    assert "chickpea" in item.snippet
    assert "<span>" not in item.snippet  # HTML stripped


# --- 3. CrossrefSearchProvider Tests ---

@patch("urllib.request.urlopen")
def test_crossref_provider_success(mock_urlopen):
    mock_body = json.dumps({
        "message": {
            "items": [
                {
                    "title": ["Management of Yellow Rust in Bread Wheat"],
                    "DOI": "10.1007/s10681-024-00123-x",
                    "URL": "https://doi.org/10.1007/s10681-024-00123-x",
                    "author": [{"given": "Rajesh", "family": "Kumar"}],
                    "container-title": ["Euphytica"],
                    "created": {"date-parts": [[2024, 11, 10]]},
                    "abstract": "Yellow rust caused by Puccinia striiformis is a major threat...",
                }
            ]
        }
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_body
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    provider = CrossrefSearchProvider()
    req = WebSearchRequest(query_text="wheat yellow rust puccinia")
    res = provider.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    assert res.result_count == 1
    item = res.results[0]
    assert item.result_type == "scholarly"
    assert "Rajesh Kumar" in item.snippet
    assert "Euphytica" in item.snippet
    assert item.metadata.get("doi") == "10.1007/s10681-024-00123-x"


# --- 4. OpenAlexSearchProvider Tests ---

@patch("urllib.request.urlopen")
def test_openalex_provider_success(mock_urlopen):
    mock_body = json.dumps({
        "results": [
            {
                "id": "https://openalex.org/W2741809807",
                "title": "Integrated pest management in cotton",
                "doi": "https://doi.org/10.1016/j.cropro.2023.106540",
                "authorships": [{"author": {"display_name": "Anita Sharma"}}],
                "primary_location": {
                    "source": {"display_name": "Crop Protection"},
                    "landing_page_url": "https://doi.org/10.1016/j.cropro.2023.106540",
                },
                "abstract_inverted_index": {
                    "Pink": [0],
                    "bollworm": [1],
                    "is": [2],
                    "controlled": [3],
                    "effectively.": [4],
                },
                "cited_by_count": 42,
                "publication_date": "2023-10-01",
            }
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_body
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    # Test with optional api key
    cfg = WebSearchConfig(openalex_api_key="optional_openalex_key_123")
    provider = OpenAlexSearchProvider(config=cfg)
    assert provider.is_available()
    assert provider.supported_capabilities()["optional_api_key"] is True

    req = WebSearchRequest(query_text="cotton pink bollworm ipm")
    res = provider.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    assert res.result_count == 1
    item = res.results[0]
    assert item.result_type == "scholarly"
    assert "Anita Sharma" in item.snippet
    assert "Pink bollworm is controlled effectively." in item.snippet
    assert item.metadata.get("cited_by_count") == 42


# --- 5. WikidataSearchProvider Tests ---

from modules.knowledge_base.web_search.providers.wikidata_provider import WikidataSearchProvider

@patch("urllib.request.urlopen")
def test_wikidata_provider_success(mock_urlopen):
    mock_body = json.dumps({
        "results": {
            "bindings": [
                {
                    "item": {"value": "http://www.wikidata.org/entity/Q81375"},
                    "itemLabel": {"value": "cicer arietinum"},
                    "itemDescription": {"value": "species of legume plant"},
                    "taxonName": {"value": "Cicer arietinum"},
                }
            ]
        }
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_body
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    provider = WikidataSearchProvider()
    assert provider.is_available()

    req = WebSearchRequest(query_text="chickpea", language="en")
    res = provider.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    assert res.result_count == 1
    item = res.results[0]
    assert item.result_type == "structured_fact"
    assert item.metadata["is_structured_fact"] is True
    assert item.metadata["qid"] == "Q81375"
    assert "cicer arietinum (Q81375)" in item.snippet
    assert item.url == "https://www.wikidata.org/wiki/Q81375"


# --- 6. NasaPowerSearchProvider Tests ---

from modules.knowledge_base.web_search.providers.nasa_power_provider import NasaPowerSearchProvider

@patch("urllib.request.urlopen")
def test_nasa_power_provider_success(mock_urlopen):
    mock_body = json.dumps({
        "properties": {
            "parameter": {
                "T2M": {"20240101": 15.2, "20240102": 16.0},
                "T2M_MAX": {"20240101": 22.1, "20240102": 23.0},
                "T2M_MIN": {"20240101": 8.5, "20240102": 9.1},
                "PRECTOTCORR": {"20240101": 0.0, "20240102": 1.5},
                "ALLSKY_SFC_SW_DWN": {"20240101": 14.5, "20240102": 15.2},
            },
            "parameter_information": {
                "T2M": {"units": "C"},
                "PRECTOTCORR": {"units": "mm/day"},
            }
        }
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_body
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    provider = NasaPowerSearchProvider()
    assert provider.is_available()

    req = WebSearchRequest(
        query_text="punjab rainfall and temperature for wheat sowing",
        region="punjab",
        filters={"start_date": "2024-01-01", "end_date": "2024-01-02"},
    )
    res = provider.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    assert res.result_count == 1
    item = res.results[0]
    assert item.result_type == "agroclimatology"
    assert item.metadata["is_numerical_agroclimatology"] is True
    assert "Mean Temperature (T2M): 15.6°C" in item.snippet
    assert "Total Precipitation: 1.5 mm" in item.snippet
    assert item.metadata["parameter_summaries"]["T2M"]["mean"] == 15.6


# --- 7. TavilySearchProvider Tests ---

from modules.knowledge_base.web_search.providers.tavily_provider import TavilySearchProvider

def test_tavily_provider_unconfigured():
    provider = TavilySearchProvider(config=WebSearchConfig(tavily_api_key=None))
    assert not provider.is_available()

    req = WebSearchRequest(query_text="rice stem borer")
    with pytest.raises(WebSearchAuthenticationError) as exc_info:
        provider.search(req)
    assert "Tavily API key is not configured" in str(exc_info.value)


@patch("urllib.request.urlopen")
def test_tavily_provider_with_mock_credentials(mock_urlopen):
    mock_body = json.dumps({
        "answer": "Pheromone traps and Cartap Hydrochloride effectively manage stem borer.",
        "results": [
            {
                "title": "Stem Borer Management - IRRI",
                "url": "https://irri.org/stem-borer",
                "content": "Stem borer causes dead heart in vegetative stage.",
                "score": 0.95,
            }
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = mock_body
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    cfg = WebSearchConfig(tavily_api_key="tvly-mock-key-1234")
    provider = TavilySearchProvider(config=cfg)
    assert provider.is_available()

    req = WebSearchRequest(query_text="rice stem borer management")
    res = provider.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    assert res.result_count == 1
    item = res.results[0]
    assert item.result_type == "web"
    assert item.score == 0.95
    assert item.metadata["tavily_answer_summary"] is not None
    assert item.url == "https://irri.org/stem-borer"


# --- 8. GeminiGroundingSearchProvider Tests ---

from modules.knowledge_base.web_search.providers.gemini_grounding_provider import GeminiGroundingSearchProvider

def test_gemini_grounding_unconfigured():
    provider = GeminiGroundingSearchProvider(config=WebSearchConfig(gemini_api_key=None))
    assert not provider.is_available()

    req = WebSearchRequest(query_text="cotton whitefly management")
    with pytest.raises(WebSearchAuthenticationError) as exc_info:
        provider.search(req)
    assert "Gemini API key is not configured" in str(exc_info.value)


@patch("urllib.request.urlopen")
def test_gemini_grounding_with_mock_credentials(mock_urlopen):
    mock_body = json.dumps({
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Whitefly in cotton can be monitored with yellow sticky traps."}
                    ]
                },
                "grounding_metadata": {
                    "web_search_queries": ["cotton whitefly sticky traps ICAR"],
                    "grounding_chunks": [
                        {
                            "web": {
                                "uri": "https://cicr.icar.gov.in/whitefly-advisory",
                                "title": "ICAR-CICR Whitefly Advisory",
                            }
                        }
                    ],
                    "grounding_supports": [
                        {
                            "segment": {
                                "text": "Whitefly in cotton can be monitored with yellow sticky traps."
                            },
                            "grounding_chunk_indices": [0],
                        }
                    ]
                }
            }
        ]
    }).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = mock_body
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    cfg = WebSearchConfig(gemini_api_key="AIzaSyMockKey12345")
    provider = GeminiGroundingSearchProvider(config=cfg)
    assert provider.is_available()

    req = WebSearchRequest(query_text="cotton whitefly management")
    res = provider.search(req)

    assert res.status == WebSearchStatus.SUCCESS
    assert res.result_count == 1
    item = res.results[0]
    assert item.result_type == "grounded_search"
    assert item.url == "https://cicr.icar.gov.in/whitefly-advisory"
    assert "Whitefly in cotton" in item.snippet
    assert item.metadata["web_search_queries"] == ["cotton whitefly sticky traps ICAR"]
