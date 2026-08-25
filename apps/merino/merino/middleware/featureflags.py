"""The middleware that configures features flags for Merino"""

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from merino.utils.featureflags import session_id_context


class FeatureFlagsMiddleware:
    """Sets a ContextVar for session_id so that it can be used
    to consistently bucket flags within a search session.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Insert session id before handing request"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope=scope)
        session_id = request.query_params.get("sid")
        session_id_context.set(session_id)

        await self.app(scope, receive, send)

        return
