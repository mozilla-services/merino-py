import logging
import re
import time
from datetime import datetime
from typing import Pattern

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# web.suggest.request is used for logs coming from the /suggest endpoint
suggest_request_logger = logging.getLogger("web.suggest.request")
# all other requests will be logged to request.summary
logger = logging.getLogger("request.summary")

# The path pattern for the suggest API
PATTERN: Pattern = re.compile(r"/api/v[1-9]\d*/suggest$")


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Logging middleware for MozLog.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if PATTERN.match(request.url.path):
            data = {
                "sensitive": True,
                "path": request.url.path,
                "method": request.method,
                "query": request.query_params.get("q"),
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
                "client_variants": request.query_params.get(
                    "client_variants", ""
                ).split(","),
                "requested_providers": request.query_params.get("providers", "").split(
                    ","
                ),
            }
            suggest_request_logger.info("", extra=data)
        else:
            data = {
                "agent": request.headers["User-Agent"],
                "path": request.url.path,
                "method": request.method,
                "lang": request.headers.get("Accept-Language"),
                "querystring": dict(request.query_params),
                "errno": 0,
                "code": response.status_code,
                "time": datetime.fromtimestamp(time.time()).isoformat(),
            }
            logger.info("", extra=data)

        return response
