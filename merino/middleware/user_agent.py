"""The middleware that parses the "User-Agent" from the HTTP request header.

Note that Merino is a service made for Firefox users, this middleware only
focuses on Firefox related user agents.
"""
from contextvars import ContextVar

from pydantic import BaseModel
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

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


# A `ContextVar` to store the user agent parsing result.
ctxvar_user_agent: ContextVar[UserAgent] = ContextVar("merino_user_agent")


class UserAgentMiddleware:
    """An ASGI middleware to parse and populate user agent information from
    `User-Agent` header.

    The user agent result `UserAgent` (if any) is stored in a `ContextVar` called
    `merino_user_agent`.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        """Parse user agent information through "User-Agent" and store the result
        (if any) to the `ContextVar`.
        """
        if scope["type"] != "http":  # pragma: no cover
            await self.app(scope, receive, send)
            return

        ua = parse(Headers(scope=scope).get("User-Agent", ""))

        ctxvar_user_agent.set(UserAgent(**ua))

        await self.app(scope, receive, send)
        return
