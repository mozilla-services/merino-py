"""The middleware that parses the "User-Agent" from the HTTP request header.

Note that Merino is a service made for Firefox users, this middleware only
focuses on Firefox related user agents.
"""
from pydantic import BaseModel
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from merino.middleware import ScopeKey
from merino.util.user_agent_parsing import parse


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


class UserAgentMiddleware:
    """An ASGI middleware to parse and populate user agent information from
    `User-Agent` header.

    The user agent result `UserAgent` (if any) is stored in
    `scope[ScopeKey.USER_AGENT]`.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Parse user agent information through "User-Agent" and store the result
        to `scope`.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        ua = parse(Headers(scope=scope).get("User-Agent", ""))

        scope[ScopeKey.USER_AGENT] = UserAgent(**ua)

        await self.app(scope, receive, send)
        return
