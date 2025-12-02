"""Constants for navigational suggestions job"""

# Scraper selectors
LINK_SELECTOR: str = (
    "link[rel=apple-touch-icon], link[rel=apple-touch-icon-precomposed],"
    'link[rel="icon shortcut"], link[rel="shortcut icon"], link[rel="icon"],'
    'link[rel="SHORTCUT ICON"], link[rel="fluid-icon"], link[rel="mask-icon"],'
    'link[rel="apple-touch-startup-image"]'
)

META_SELECTOR: str = "meta[name=apple-touch-icon], meta[name=msapplication-TileImage]"

MANIFEST_SELECTOR: str = 'link[rel="manifest"]'

ALLOW_REDIRECTS: bool = True

PARSER: str = "html.parser"

# A non-exhaustive list of substrings of invalid titles
INVALID_TITLES: list[str] = [
    "Attention Required",
    "Access denied",
    "Access Denied",
    "Access to this page has been denied",
    "Loading…",
    "Page loading",
    "Just a moment...",
    "Site Maintenance",
    "502 Bad Gateway",
    "503 Service Temporarily Unavailable",
    "Your request has been blocked",
    "This page is either unavailable or restricted",
    "Let's Get Your Identity Verified",
    "Your Access To This Website Has Been Blocked",
    "Error",
    "This page is not allowed",
    "Robot or human",
    "Captcha Challenge",
    "Let us know you're not a robot",
    "Verification",
    "404",
    "Please try again",
    "Access to this page",
    "We'll be right back",
    "Bot or Not?",
    "Too Many Requests",
    "IP blocked",
    "Service unavailable",
    "Unsupported browser",
]

# Constants for favicon URL validation
MANIFEST_JSON_BASE64_MARKER: str = "/application/manifest+json;base64,"

# Processing configuration
DEFAULT_MAX_FAVICON_ICONS: int = 5
DEFAULT_CHUNK_SIZE: int = 25
FAVICON_BATCH_SIZE: int = 5

# Source priority for favicon selection (lower is better)
FAVICON_SOURCE_PRIORITY: dict[str, int] = {
    "link": 1,
    "meta": 2,
    "manifest": 3,
    "default": 4,
}

# HTTP request configuration
REQUEST_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/114.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
}

TIMEOUT: int = 15
