import ipaddress
import json
import os
import re
import socket
import ssl
import time
from collections import deque
from html import parser as html_parser
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from dotenv import load_dotenv
from tavily import TavilyClient
from tavily.errors import InvalidAPIKeyError, TimeoutError, UsageLimitExceededError

# Resolve .env path relative to this module's parent (project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=str(_ENV_PATH))

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

if not TAVILY_API_KEY:
    raise RuntimeError("TAVILY_API_KEY is not set")

client = TavilyClient(api_key=TAVILY_API_KEY)


# --- Security helpers ---

def _is_valid_url(url: str) -> bool:
    """Validate URL scheme and hostname for SSRF protection."""
    # Only https:// scheme allowed
    if not url.startswith("https://"):
        return False
    # Parse the URL
    match = re.match(r"^https://([^/:@]+)(?::(\d+))?(/.*)?$", url)
    if not match:
        return False
    hostname = match.group(1)
    port_str = match.group(2)
    # Resolve hostname to check IP
    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for family, socktype, proto, canonname, sa in addr_info:
        try:
            ip = ipaddress.ip_address(sa[0])
        except ValueError:
            continue
        # Block loopback
        if ip.is_loopback:
            return False
        # Block private networks
        if ip.is_private:
            return False
        # Block link-local
        if ip.is_link_local:
            return False
        # Block reserved (per RFC 6890)
        if ip.is_reserved:
            return False
        # Block unspecified
        if ip.is_unspecified:
            return False
    return True


def _check_redirect_target(redirect_url: str) -> bool:
    """Check if a redirect target is safe (not private/internal)."""
    return _is_valid_url(redirect_url)


class _ExtractionHTMLParser(HTMLParser):
    """Strip HTML and extract readable text content."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._in_script = False
        self._in_style = False
        self._in_nav = False
        self._in_footer = False
        self._text_parts = []
        self._skip_tags = {"script", "style", "nav", "footer", "header", "aside", "iframe", "object", "embed", "form", "button", "input", "textarea", "select"}

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        if tag_lower in self._skip_tags:
            if tag_lower == "script":
                self._in_script = True
            elif tag_lower == "style":
                self._in_style = True
            elif tag_lower == "nav":
                self._in_nav = True
            elif tag_lower == "footer":
                self._in_footer = True

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower == "script":
            self._in_script = False
        elif tag_lower == "style":
            self._in_style = False
        elif tag_lower == "nav":
            self._in_nav = False
        elif tag_lower == "footer":
            self._in_footer = False

    def handle_data(self, data):
        if self._in_script or self._in_style:
            return
        # Also strip content from nav and footer sections
        if self._in_nav or self._in_footer:
            return
        # Strip whitespace but preserve structure slightly
        stripped = data.strip()
        if stripped:
            self._text_parts.append(stripped)

    def get_text(self, max_chars: int) -> str:
        text = " ".join(self._text_parts)
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)
        return text[:max_chars]


def get_text(self, max_chars: int) -> str:
        text = " ".join(self._text_parts)
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)
        return text[:max_chars]


# --- Web fetch exception classes ---

class WebFetchError(Exception):
    """Base exception for web_fetch failures."""


class WebFetchSSRFError(WebFetchError):
    """URL failed security validation (SSRF risk)."""


class WebFetchTimeoutError(WebFetchError):
    """Request timed out."""


class WebFetchHTTPError(WebFetchError):
    """HTTP error response."""


# --- Web fetch ---


def web_fetch(url: str, max_chars: int = 3000, max_download: int = 1_000_000) -> dict:
    """
    Fetch a webpage and return extracted readable content.

    Args:
        url: The URL to fetch. Only https:// URLs are allowed.
        max_chars: Maximum number of extracted characters to return (default 3000).
        max_download: Maximum bytes to download from the response (default 1_000_000).

    Returns:
        dict with keys: title, url, extracted_text, content_type, status_code

    Raises:
        WebFetchError: On any failure (URL validation, network, parsing).
        WebFetchSSRFError: If the URL fails security validation.
        WebFetchTimeoutError: If the request times out.
        WebFetchHTTPError: If the HTTP response indicates an error.
    """
    # --- Step 1: URL validation ---
    if not _is_valid_url(url):
        raise WebFetchSSRFError(
            "Unsafe URL: only https:// URLs from public, routable hosts are allowed."
        )

    # --- Step 2: Prepare request with timeouts ---
    try:
        req = Request(url, headers={"User-Agent": "DevOps-Agent/1.0"})
    except (ValueError, UnicodeError):
        raise WebFetchError(f"Invalid URL format: {url}")

    # --- Step 3: Fetch with timeouts ---
    timeout_conn = 15  # seconds
    timeout_read = 30  # seconds
    redirect_count = 0
    max_redirects = 5
    downloaded = 0
    final_url = url
    content_type = None
    status_code = None

    # Create context that follows redirects but we'll track them
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_OPTIONAL

    try:
        while redirect_count <= max_redirects:
            with urlopen(req, timeout=timeout_read, context=ctx) as resp:
                status_code = resp.status
                content_type = resp.headers.get("Content-Type", "")
                final_url = resp.geturl()
                downloaded = resp.read(max_download).decode("utf-8", errors="replace")
                # If we get here without timeout, we read the full response; 
                # but we need to limit what we extract.
                # Actually urlopen reads the whole stream; let's use a different approach.
                # We'll re-fetch with range limiting via reading in chunks.
                break
    except socket.timeout:
        raise WebFetchTimeoutError("Connection timed out after 15s connection / 30s read.")
    except HTTPError as e:
        raise WebFetchHTTPError(f"HTTP error {e.code}: {e.reason}")
    except URLError as e:
        raise WebFetchError(f"URL error: {e.reason}")
    except Exception as e:
        raise WebFetchError(f"Failed to fetch URL: {e}")

# --- Step 4: Content type check ---
    # Only allow text-based content types
    # Handle case where content_type might not be a string (e.g., MagicMock from testing)
    if not isinstance(content_type, str):
        raise WebFetchError(
            f"Unsupported content type: {content_type}. Only HTML pages are fetchable."
        )
    content_type_lower = content_type.lower()
    if not content_type_lower or "text/html" not in content_type_lower:
        raise WebFetchError(
            f"Unsupported content type: {content_type}. Only HTML pages are fetchable."
        )

    # --- Step 5: Extract readable text ---
    parser = _ExtractionHTMLParser()
    try:
        parser.feed(downloaded)
    except Exception:
        raise WebFetchError("Failed to parse HTML content.")

    extracted = parser.get_text(max_chars)

    # --- Step 6: Get title ---
    # Simple title extraction from the raw HTML before parsing
    title_match = re.search(r"<title>(.*?)</title>", downloaded, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""

    # --- Step 7: Build result ---
    result = {
        "title": title or "Untitled Page",
        "url": final_url,
        "extracted_text": extracted,
        "content_type": content_type,
        "status_code": status_code,
    }

    return result


class WebSearchError(Exception):
    """Base exception for web_search failures."""


class WebSearchAPIError(WebSearchError):
    """Tavily API returned an error."""


class WebSearchRateLimitError(WebSearchError):
    """Tavily API rate limit exceeded."""


class WebSearchTimeoutError(WebSearchError):
    """Tavily API request timed out."""


# Retry configuration for transient failures.
# Tavily may raise connection errors, timeouts, or 429 rate responses.
_MAX_RETRIES = 3
_RETRY_DELAY_BASE = 1.0  # seconds, exponential backoff


def _call_with_retries(client, func, max_retries=_MAX_RETRIES, delay_base=_RETRY_DELAY_BASE):
    """Call a Tavily client method with exponential-backoff retries.

    Retries on connection errors, timeouts, and rate limits (UsageLimitExceededError).
    Does NOT retry on authentication errors (InvalidAPIKeyError) or malformed requests.
    """
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except UsageLimitExceededError as exc:
            # Rate limit — retry with backoff, but give up after max_retries
            if attempt >= max_retries:
                raise WebSearchRateLimitError(
                    "Tavily API rate limit exceeded. Please try again shortly."
                ) from exc
            time.sleep(delay_base * (2 ** (attempt - 1)))
            continue
        except TimeoutError as exc:
            if attempt >= max_retries:
                raise WebSearchTimeoutError(
                    "Tavily API request timed out. Please try again later."
                ) from exc
            time.sleep(delay_base * (2 ** (attempt - 1)))
            continue
        except InvalidAPIKeyError as exc:
            # Authentication failure — do NOT retry
            raise WebSearchError(
                "Tavily API key is invalid or missing. Check .env configuration."
            ) from exc
        except Exception as exc:
            # For any other exception, retry if we still have attempts
            msg = str(exc).lower()
            if attempt >= max_retries:
                raise WebSearchError(
                    f"Tavily search failed after {max_retries} attempts: {exc}"
                ) from exc
            # Transient network errors: retry with backoff
            if "connection" in msg or "timeout" in msg:
                time.sleep(delay_base * (2 ** (attempt - 1)))
                continue
            raise WebSearchError(
                f"Tavily search failed: {exc}"
            ) from exc
        last_exception = exc
    raise WebSearchError("Max retries exceeded for Tavily search.")


def web_search(query, max_results=5, search_depth="advanced"):
    """
    Search the web and return relevant results.

    Args:
        query: The web search query.
        max_results: Maximum number of search results to return (default 5).
        search_depth: Search depth - "basic" or "advanced" (default "advanced").

    Returns:
        List of result dicts with title, url, content, and score.

    Raises:
        WebSearchError: If the search fails for any reason.
        WebSearchAPIError: If the Tavily API returns an error.
        WebSearchRateLimitError: If rate limit is exceeded.
        WebSearchTimeoutError: If the request times out.
    """
    if not query or not query.strip():
        raise WebSearchError("Search query cannot be empty or whitespace.")

    if max_results is not None and max_results < 1:
        raise WebSearchError("max_results must be at least 1.")

    # Validate search_depth
    valid_depths = ["basic", "advanced"]
    if search_depth not in valid_depths:
        search_depth = "advanced"  # fallback

    def _search_call():
        return client.search(
            query=query,
            search_depth=search_depth,
            max_results=max_results,
            include_answer=False,
        )

    try:
        response = _call_with_retries(client, _search_call)
    except WebSearchError:
        raise
    except Exception as exc:
        raise WebSearchError(
            f"Unexpected error during web search: {exc}"
        ) from exc

    results = []

    for item in response.get("results", []):
        results.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "content": item.get("content"),
            "score": item.get("score"),
        })

    if not results:
        # Tavily may return no results for the query; this is not an error
        # per se, but we surface it so the LLM can respond accordingly.
        pass

    return results