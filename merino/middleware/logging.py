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
            "session_id": request.query_params.get("sid"),
            "sequence_no": int(seq)
            if (seq := request.query_params.get("seq"))
            else None,
            "country": request.state.location.country,
            "region": request.state.location.region,
            "city": request.state.location.city,
            "dma": request.state.location.dma,
        }
        logger.info("", extra=data)

        return response
