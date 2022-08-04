import logging
import time
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("request.summary")


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Logging middleware for MozLog.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        data = {
            "agent": request.headers["User-Agent"],
            "path": request.url.path,
            "method": request.method,
            "lang": request.headers.get("Accept-Language"),
            "querystring": dict(request.query_params),
            "errno": 0,
            "code": response.status_code,
            "time": datetime.fromtimestamp(time.time()).isoformat(),
            # Provided by the asgi-correlation-id middleware.
            "rid": response.headers["X-Request-ID"],
        }
        logger.info("", extra=data)

        return response
