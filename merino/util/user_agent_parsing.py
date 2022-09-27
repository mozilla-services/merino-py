"""A utility module for user agent parsing."""
from typing import Any, cast

from ua_parser import user_agent_parser


def parse(ua_str: str) -> dict[str, str]:
    """Parse the "User-Agent" string for browser, os family, and form factor.

    It returns a dict with `browser`, `family`, and `form_factor` keys.
    """
    ua: dict[str, Any] = user_agent_parser.Parse(ua_str)
    browser = _parse_browser(ua["user_agent"])
    os_family = _parse_os_family(ua["os"])
    form_factor = _parse_form_factor(ua["device"], os_family)
    return {"browser": browser, "os_family": os_family, "form_factor": form_factor}


def _parse_browser(user_agent: dict[str, Any]) -> str:
    """Parse the browser family and version from the user agent dictionary."""
    match user_agent:
        case {
            "family": "Firefox" | "Firefox iOS" | "Firefox Mobile" | "Firefox Alpha",
            "major": major,
            "minor": minor,
            "patch": patch,
        }:
            version = f"{major or ''}.{minor or ''}.{patch or ''}"
            return "Firefox" if major is None else f"Firefox({version.rstrip('.')})"
        case {"family": browser}:
            # Do not bother parsing the browser version for non-Firefox user agents.
            return cast(str, browser)
        case _:  # pragma: no cover
            return "Other"


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
            # This should cover most of main-stream Linux distros
            return "linux"
        case _:
            return "other"


def _parse_form_factor(device: dict[str, Any], os_family: str) -> str:  # type: ignore
    """Parse the form factor from the device dictionary.

    It takes an extra argument `os_family` to facilitate parsing for Windows
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
