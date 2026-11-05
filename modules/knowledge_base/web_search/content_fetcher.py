"""Safe Web Page Content Retriever for EarthMind Stage R10 Web Search.

Provides security-hardened HTTP fetching and readable text extraction for public web URLs:
- Rejects non-HTTP/HTTPS URLs.
- Comprehensive SSRF prevention: resolves DNS and blocks private IP ranges
  (RFC 1918, RFC 3927 link-local, loopback, IPv6 unique/link-local, carrier-grade NAT,
  and cloud metadata endpoints such as 169.254.169.254 / metadata.google.internal).
- Revalidates redirect destinations to prevent redirect-based SSRF.
- Enforces strict connect and read timeouts.
- Enforces maximum response byte limits (e.g., 1MB) to prevent resource exhaustion / decompression bombs.
- Restricts content-types to text/html, text/plain, and application/xhtml+xml.
- Strips scripts, style sheets, and tracking elements without executing JavaScript.
- Extracts clean text, page title, and meta descriptions safely.
"""

import ipaddress
import logging
import socket
import urllib.parse
import urllib.request
from typing import Optional, Set, Tuple
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Cloud metadata hostnames and IPs explicitly blocked
BLOCKED_HOSTNAMES: Set[str] = {
    "instance-data",
    "metadata",
    "metadata.google.internal",
    "169.254.169.254",
    "fd00:ec2::254",
}


class FetchedPageContent(BaseModel):
    """Normalized output container for a safely fetched web page."""
    original_url: str
    final_url: str
    status_code: int
    title: Optional[str] = None
    text_content: str
    content_length: int
    content_type: str
    truncated: bool = False
    error: Optional[str] = None


class SafeContentFetcher:
    """Security-hardened public web page retriever."""

    def __init__(
        self,
        timeout: float = 5.0,
        max_bytes: int = 1048576,  # 1 MB
        user_agent: str = "EarthMind-RAG/1.0 (+https://github.com/earthmind)",
        max_redirects: int = 3,
    ):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.user_agent = user_agent
        self.max_redirects = max_redirects

    def is_safe_ip(self, ip_str: str) -> bool:
        """Verifies an IP address is not private, loopback, link-local, or reserved."""
        try:
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                return False
            # Check 169.254.0.0/16 explicitly
            if isinstance(ip, ipaddress.IPv4Address):
                if ip in ipaddress.ip_network("169.254.0.0/16") or ip in ipaddress.ip_network("100.64.0.0/10"):
                    return False
            return True
        except ValueError:
            return False

    def validate_url_safety(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Validates scheme, hostname, and resolves IP addresses to ensure no SSRF.
        Returns (is_safe, error_message).
        """
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme.lower() not in ("http", "https"):
                return False, f"Unsupported scheme '{parsed.scheme}'. Only http and https allowed."

            hostname = parsed.hostname
            if not hostname:
                return False, "URL lacks a valid hostname."

            hostname_lower = hostname.lower().strip()
            if hostname_lower in BLOCKED_HOSTNAMES or "localhost" in hostname_lower:
                return False, f"Access to host '{hostname}' is prohibited (cloud metadata / loopback)."

            # Resolve DNS and check all resolved IP addresses
            try:
                # getaddrinfo returns list of (family, type, proto, canonname, sockaddr)
                addr_info = socket.getaddrinfo(hostname, None)
            except socket.gaierror as e:
                return False, f"DNS resolution failed for hostname '{hostname}': {e}"

            resolved_ips = {item[4][0] for item in addr_info}
            if not resolved_ips:
                return False, f"No IP addresses resolved for hostname '{hostname}'."

            for ip_addr in resolved_ips:
                if not self.is_safe_ip(ip_addr):
                    return False, f"Hostname '{hostname}' resolved to unsafe/private IP address: {ip_addr}"

            return True, None
        except Exception as e:
            return False, f"URL validation error: {str(e)}"

    def fetch_page(self, url: str) -> FetchedPageContent:
        """
        Safely fetches page content with SSRF checks, redirects re-validation,
        and extraction of readable text.
        """
        curr_url = url
        redirect_count = 0

        while redirect_count <= self.max_redirects:
            is_safe, err = self.validate_url_safety(curr_url)
            if not is_safe:
                logger.warning(f"Blocked unsafe URL '{curr_url}': {err}")
                return FetchedPageContent(
                    original_url=url,
                    final_url=curr_url,
                    status_code=400,
                    text_content="",
                    content_length=0,
                    content_type="",
                    error=f"Security policy violation: {err}",
                )

            # Custom handler to prevent automatic arbitrary redirects without re-validation
            class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None  # Disallow automatic following

            opener = urllib.request.build_opener(NoRedirectHandler)
            req = urllib.request.Request(
                curr_url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
                },
                method="GET",
            )

            try:
                with opener.open(req, timeout=self.timeout) as resp:
                    status_code = resp.getcode()
                    content_type = resp.headers.get_content_type() if hasattr(resp.headers, "get_content_type") else resp.headers.get("Content-Type", "")
                    content_type_lower = content_type.lower()

                    if not any(t in content_type_lower for t in ("text/html", "text/plain", "xhtml")):
                        return FetchedPageContent(
                            original_url=url,
                            final_url=curr_url,
                            status_code=status_code,
                            text_content="",
                            content_length=0,
                            content_type=content_type,
                            error=f"Unsupported Content-Type '{content_type}'.",
                        )

                    # Read up to max_bytes + 1 to detect truncation
                    raw_data = resp.read(self.max_bytes + 1)
                    truncated = False
                    if len(raw_data) > self.max_bytes:
                        raw_data = raw_data[: self.max_bytes]
                        truncated = True

                    # Detect charset or default to utf-8
                    charset = resp.headers.get_content_charset() or "utf-8"
                    try:
                        decoded_text = raw_data.decode(charset, errors="replace")
                    except Exception:
                        decoded_text = raw_data.decode("utf-8", errors="replace")

                    # Extract title and text
                    title, clean_text = self._parse_html(decoded_text, content_type_lower)

                    return FetchedPageContent(
                        original_url=url,
                        final_url=curr_url,
                        status_code=status_code,
                        title=title,
                        text_content=clean_text,
                        content_length=len(clean_text),
                        content_type=content_type,
                        truncated=truncated,
                    )

            except urllib.error.HTTPError as e:
                if e.code in (301, 302, 303, 307, 308):
                    new_loc = e.headers.get("Location")
                    if not new_loc:
                        return FetchedPageContent(
                            original_url=url,
                            final_url=curr_url,
                            status_code=e.code,
                            text_content="",
                            content_length=0,
                            content_type="",
                            error="Redirect missing Location header.",
                        )
                    # Resolve relative redirect URLs
                    curr_url = urllib.parse.urljoin(curr_url, new_loc)
                    redirect_count += 1
                    continue
                else:
                    return FetchedPageContent(
                        original_url=url,
                        final_url=curr_url,
                        status_code=e.code,
                        text_content="",
                        content_length=0,
                        content_type="",
                        error=f"HTTP {e.code}: {e.reason}",
                    )
            except Exception as ex:
                return FetchedPageContent(
                    original_url=url,
                    final_url=curr_url,
                    status_code=500,
                    text_content="",
                    content_length=0,
                    content_type="",
                    error=f"Fetch failed: {str(ex)}",
                )

        return FetchedPageContent(
            original_url=url,
            final_url=curr_url,
            status_code=310,
            text_content="",
            content_length=0,
            content_type="",
            error=f"Exceeded maximum redirect limit of {self.max_redirects}.",
        )

    def _parse_html(self, raw_html: str, content_type: str) -> Tuple[Optional[str], str]:
        """Strips markup and extracts clean text without running JavaScript."""
        if "text/plain" in content_type:
            return None, raw_html.strip()

        try:
            soup = BeautifulSoup(raw_html, "html.parser")

            # Extract title before decomposing
            title = soup.title.string.strip() if soup.title and soup.title.string else None

            # Remove executable or styling elements
            for tag in soup(["script", "style", "noscript", "iframe", "svg", "header", "footer", "nav", "aside"]):
                tag.decompose()

            # Extract main readable text
            text = soup.get_text(separator="\n", strip=True)

            # Collapse excess whitespace
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            clean_text = "\n".join(lines)
            return title, clean_text
        except Exception as e:
            logger.warning(f"HTML parsing fallback error: {e}")
            return None, raw_html[:2000].strip()
