from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from merino.featureflags import session_id_context


class FeatureFlagsMiddleware(BaseHTTPMiddleware):
    """
    Sets the a ContextVar for session_id so that it can be used
    to consistently bucket flags within a search session
    """

    async def dispatch(self, request: Request, call_next):
        session_id = request.query_params.get("sid")
        session_id_context.set(str(session_id))
        return await call_next(request)
