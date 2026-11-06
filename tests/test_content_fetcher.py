"""Unit tests for SafeContentFetcher SSRF protection and web content extraction."""

import socket
from unittest.mock import MagicMock, patch
import pytest

from modules.knowledge_base.web_search.content_fetcher import SafeContentFetcher


@pytest.fixture
def fetcher() -> SafeContentFetcher:
    return SafeContentFetcher(timeout=2.0, max_bytes=5000)


def test_validate_url_scheme(fetcher):
    safe, err = fetcher.validate_url_safety("ftp://example.com/file")
    assert not safe
    assert "Unsupported scheme" in err

    safe, err = fetcher.validate_url_safety("file:///etc/passwd")
    assert not safe
    assert "Unsupported scheme" in err


def test_validate_url_cloud_metadata(fetcher):
    safe, err = fetcher.validate_url_safety("http://169.254.169.254/latest/meta-data/")
    assert not safe
    assert "prohibited" in err

    safe, err = fetcher.validate_url_safety("http://metadata.google.internal/computeMetadata/v1/")
    assert not safe
    assert "prohibited" in err


def test_validate_url_loopback_and_private_ip(fetcher):
    with patch("socket.getaddrinfo") as mock_dns:
        # Loopback 127.0.0.1
        mock_dns.return_value = [(2, 1, 6, "", ("127.0.0.1", 80))]
        safe, err = fetcher.validate_url_safety("http://localhost:8080/admin")
        assert not safe

        # Private 10.0.0.5
        mock_dns.return_value = [(2, 1, 6, "", ("10.0.0.5", 80))]
        safe, err = fetcher.validate_url_safety("http://internal-portal.local/test")
        assert not safe
        assert "private" in err.lower() or "unsafe" in err.lower()

        # Private 192.168.1.1
        mock_dns.return_value = [(2, 1, 6, "", ("192.168.1.1", 80))]
        safe, err = fetcher.validate_url_safety("http://router.home/setup")
        assert not safe
        assert "private" in err.lower() or "unsafe" in err.lower()


def test_validate_url_public_ip(fetcher):
    with patch("socket.getaddrinfo") as mock_dns:
        # Public IP (e.g. 93.184.216.34)
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 80))]
        safe, err = fetcher.validate_url_safety("https://example.com/advisory")
        assert safe
        assert err is None


def test_parse_html_cleans_scripts(fetcher):
    html = """
    <html>
        <head><title>Wheat Rust Advisory</title></head>
        <body>
            <script>alert('malicious')</script>
            <style>body { color: red; }</style>
            <h1>Yellow Rust Protection</h1>
            <p>Apply propiconazole 25 EC at 0.1% concentration.</p>
        </body>
    </html>
    """
    title, text = fetcher._parse_html(html, "text/html")
    assert title == "Wheat Rust Advisory"
    assert "Yellow Rust Protection" in text
    assert "propiconazole" in text
    assert "alert" not in text
    assert "color: red" not in text


@patch("urllib.request.build_opener")
def test_fetch_page_success(mock_build_opener, fetcher):
    with patch.object(fetcher, "validate_url_safety", return_value=(True, None)):
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.headers.get_content_type.return_value = "text/html"
        mock_resp.headers.get_content_charset.return_value = "utf-8"
        mock_resp.read.return_value = b"<html><head><title>Test Title</title></head><body><p>Content Body</p></body></html>"
        mock_resp.__enter__.return_value = mock_resp

        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_build_opener.return_value = mock_opener

        res = fetcher.fetch_page("https://example.org/test")
        assert res.status_code == 200
        assert res.title == "Test Title"
        assert "Content Body" in res.text_content
        assert res.error is None
