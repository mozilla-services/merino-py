"""A utility module for user agent parsing."""

import ua_parser
from ua_parser import DefaultedResult, UserAgent, OS, Device


def parse(ua_str: str) -> dict[str, str]:
    """Parse the "User-Agent" string for browser, os family, and form factor.

    It returns a dict with `browser`, `family`, and `form_factor` keys.
    """
    ua: DefaultedResult = ua_parser.parse(ua_str).with_defaults()
    browser = _parse_browser(ua.user_agent)
    os_family = _parse_os_family(ua.os)
    form_factor = _parse_form_factor(ua.device, os_family)
    return {"browser": browser, "os_family": os_family, "form_factor": form_factor}


def _parse_browser(user_agent: UserAgent) -> str:
    """Parse the browser family and version from the user agent dictionary."""
    match user_agent:
        case UserAgent(
            family="Firefox"
            | "Firefox iOS"
            | "Firefox Mobile"
            | "Firefox Alpha",
            major=major,
            minor=minor,
            patch=patch,
        ):
            version = f"{major or ''}.{minor or ''}.{patch or ''}"
            return "Firefox" if major is None else f"Firefox({version.rstrip('.')})"
        case UserAgent(family=browser):
            # Do not bother parsing the browser version for non-Firefox user agents.
            return browser


def _parse_os_family(operating_system: OS) -> str:
    """Parse the OS family from the os dictionary."""
    match operating_system.family:
        case "Windows":
            return "windows"
        case "iOS":
            return "ios"
        case "Mac OS X":
            return "macos"
        case "Android":
            return "android"
        case "Chrome OS":
            return "chromeos"
        case "Ubuntu" | "Fedora" | "Debian" | "Arch Linux" | "Linux":
            # This should cover most of main-stream Linux distros
            return "linux"
        case _:
            return "other"


def _parse_form_factor(device: Device, os_family: str) -> str:
    """Parse the form factor from the device dictionary.

    It takes an extra argument `os_family` to facilitate parsing for Windows
    and Linux form factors, as the underlying parser doesn't support well
    for those two platforms.
    """
    match device.family:
        case "iPhone" | "Generic Smartphone":
            return "phone"
        case "iPad" | "Generic Tablet":
            return "tablet"
        case "Mac":
            return "desktop"
        case "Other" if os_family in ["linux", "windows"]:
            # Hardcode to "desktop" if the os_family is Linux or Windows
            return "desktop"
        case _:
            return "other"
