"""The middleware that parses the "User-Agent" from the HTTP request header.

Note that Merino is a service made for Firefox users, this middleware only
focuses on Firefox related user agents.
"""
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

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


class UserAgentMiddleware(BaseHTTPMiddleware):
    """A middleware to populate user agent information from the HTTP request header.

    The parsed result `UserAgent` is stored in `Request.state.user_agent`.
    """

    async def dispatch(self, request: Request, call_next):
        """Provide user agent information before handling request"""
        ua = parse(request.headers.get("User-Agent", ""))

        request.state.user_agent = UserAgent(**ua)

        return await call_next(request)
