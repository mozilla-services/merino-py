"""URL manipulation utilities for navigational suggestions job"""

from urllib.parse import urljoin, urlparse, urlunparse
from typing import Optional


def get_base_url(url: str) -> str:
    """Extract base URL (e.g., "https://example.com" from "https://example.com/path")."""
    parsed_url = urlparse(url)
    return f"{parsed_url.scheme}://{parsed_url.netloc}"


def fix_url(url: str, base_url: Optional[str] = None) -> str:
    """Fix and normalize URLs by adding missing protocols and handling relative paths.

    Handles protocol-relative URLs (//example.com), URLs without protocol,
    absolute paths, and fully qualified URLs.
    """
    # Skip empty URLs or single slash
    if not url or url == "/":
        return ""

    # Handle protocol-relative URLs (e.g., "//example.com/favicon.ico")
    if url.startswith("//"):
        return f"https:{url}"

    # Handle URLs that already have a protocol - normalize path
    if url.startswith(("http://", "https://")):
        parsed = urlparse(url)
        # Normalize path to remove .. and .
        normalized_path = urlparse(urljoin("http://dummy", parsed.path)).path
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                normalized_path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )

    # Handle absolute paths (start with /) or relative paths - use urljoin
    if url.startswith("/") or (base_url and not ("://" in url or url.count(".") > 1)):
        if base_url:
            return urljoin(base_url, url)
        else:
            return ""

    # Handle URLs without protocol that look like domains (e.g., "example.com/favicon.ico")
    # These typically have multiple dots or common TLDs
    if "." in url and not url.startswith("."):
        # First add https, then normalize the path
        full_url = f"https://{url}"
        parsed = urlparse(full_url)
        normalized_path = urlparse(urljoin("http://dummy", parsed.path)).path
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                normalized_path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )

    # Default: treat as relative path if we have a base_url
    if base_url:
        return urljoin(base_url, url)
    else:
        return ""


def is_valid_url(url: str) -> bool:
    """Check if URL is valid and has a protocol."""
    return bool(url and "://" in url)


def join_url(base: str, path: str) -> str:
    """Join base URL with path."""
    return urljoin(base, path)


def is_problematic_favicon_url(favicon_url: str) -> bool:
    """Check if favicon URL is a data URL, base64 manifest, or invalid scheme (can't be processed)."""
    from merino.jobs.navigational_suggestions.constants import MANIFEST_JSON_BASE64_MARKER

    if not favicon_url:
        return False

    favicon_lower = favicon_url.lower()

    # Check for problematic schemes
    if favicon_lower.startswith(("javascript:", "mailto:", "data:")):
        return True

    # Check for base64 manifest marker
    return MANIFEST_JSON_BASE64_MARKER in favicon_lower


def process_favicon_url(favicon_url: str, base_url: str, source: str) -> Optional[dict[str, str]]:
    """Process favicon URL with common pattern: validate, fix relative URLs, add source.

    Args:
        favicon_url: The favicon URL to process
        base_url: Base URL for resolving relative paths
        source: Source type ("link", "meta", "manifest", "default")

    Returns:
        Dictionary with processed favicon data, or None if URL is problematic
    """
    try:
        # Check if URL is problematic
        if is_problematic_favicon_url(favicon_url):
            return None
    except Exception:
        # If validation fails, treat as problematic and skip
        return None

    # Resolve relative URLs using urljoin which handles edge cases better
    if not favicon_url.startswith(("http://", "https://", "//")):
        processed_url = join_url(base_url, favicon_url)
    else:
        processed_url = favicon_url

    return {"href": processed_url, "_source": source}
