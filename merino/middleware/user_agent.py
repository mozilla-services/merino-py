"""The middleware that parses the "User-Agent" from the HTTP request header.

Note that Merino is a service made for Firefox users, this middleware only
focuses on Firefox related user agents.
"""
from typing import Any

from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from ua_parser import user_agent_parser


class UserAgent(BaseModel):
    """Data model for user agent information.

    `browser`: The browser and possibly the version if detected. E.g. 'Firefox(104.0.1)'.
               'Other' is used if the browser cannot be parsed.
    `os_family`: The OS family, One of "windows", "macos", "linux", "ios", "android",
                 "chromeos", or "other".
    `form_factor`: One of "desktop", "phone", "tablet", or "other".
    """

    browser: str
    os_family: str
    form_factor: str


class UserAgentMiddleware(BaseHTTPMiddleware):
    """A middleware to populate user agent information from the HTTP request header.

    The parsed result `UserAgent` is stored in `Request.state.user_agent`.
    """

    async def dispatch(self, request: Request, call_next):
        """Provide user agent information before handling request"""
        browser, os_family, form_factor = UserAgentMiddleware.parse(
            request.headers["User-Agent"]
        )
        request.state.user_agent = UserAgent(
            browser=browser, os_family=os_family, form_factor=form_factor
        )

        return await call_next(request)

    @staticmethod
    def parse(ua_str: str) -> tuple[str, str, str]:
        """Parse the "User-Agent" string for browser, os family, and form factor."""
        ua = user_agent_parser.Parse(ua_str)
        browser = UserAgentMiddleware._parse_browser(ua["user_agent"])
        os_family = UserAgentMiddleware._parse_os_family(ua["os"])
        form_factor = UserAgentMiddleware._parse_form_factor(ua["device"], os_family)
        return browser, os_family, form_factor

    @staticmethod
    def _parse_browser(user_agent: dict[str, Any]) -> str:
        """Parse the browser family and version from the user agent dictionary."""
        match user_agent:
            case {
                "family": "Firefox"
                | "Firefox iOS"
                | "Firefox Mobile"
                | "Firefox Alpha",
                "major": major,
                "minor": minor,
                "patch": patch,
            }:
                version = f"{major or ''}.{minor or ''}.{patch or ''}"
                return "Firefox" if major is None else f"Firefox({version.rstrip('.')})"
            case {"family": browser}:
                # Do not bother parsing the browser version for non-Firefox user agents.
                return browser
            case _:
                return "Other"

    @staticmethod
    def _parse_os_family(operating_system: dict[str, Any]) -> str:
        """Parse the OS family from the os dictionary."""
        match operating_system:
            case {"family": "Windows"}:
                return "windows"
            case {"family": "iOS"}:
                return "ios"
            case {"family": "Mac OS X"}:
                return "macos"
            case {"family": "Android"}:
                return "android"
            case {"family": "Chrome OS"}:
                return "chromeos"
            case {"family": "Ubuntu" | "Fedora" | "Debian" | "Arch Linux" | "Linux"}:
                # This should cover the most of main-stream Linux distros
                return "linux"
            case _:
                return "other"

    @staticmethod
    def _parse_form_factor(device: dict[str, Any], os_family: str) -> str:
        """Parse the form factor from the device dictionary.

        It akes an extra argument `os_family` to facilitate parsing for Windows
        and Linux form factors, as the underlying parser doesn't support well
        for those two platforms.
        """
        match device:
            case {"family": "iPhone" | "Generic Smartphone"}:
                return "phone"
            case {"family": "iPad" | "Generic Tablet"}:
                return "tablet"
            case {"family": "Mac"}:
                return "desktop"
            case {"family": "Other"} if os_family in ["linux", "windows"]:
                # Hardcode to "desktop" if the os_family is Linux or Windows
                return "desktop"
            case _:
                return "other"
