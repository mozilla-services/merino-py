"""The middleware that records various access logs for Merino."""
import logging
import re
import time
from datetime import datetime
from typing import Pattern

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from merino.middleware.geolocation import ctxvar_geolocation
from merino.middleware.user_agent import ctxvar_user_agent

# web.suggest.request is used for logs coming from the /suggest endpoint
suggest_request_logger = logging.getLogger("web.suggest.request")
# all other requests will be logged to request.summary
logger = logging.getLogger("request.summary")

# The path pattern for the suggest API
PATTERN: Pattern = re.compile(r"/api/v[1-9]\d*/suggest$")


class LoggingMiddleware:
    """An ASGI middleware for logging."""

    def __init__(self, app: ASGIApp) -> None:
        """Initilize."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        """Log requests."""
        if scope["type"] != "http":  # pragma: no cover
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                request = Request(scope=scope)
                if PATTERN.match(request.url.path):
                    location = ctxvar_geolocation.get()
                    ua = ctxvar_user_agent.get()
                    data = {
                        "sensitive": True,
                        "path": request.url.path,
                        "method": request.method,
                        "query": request.query_params.get("q"),
                        "errno": 0,
                        "code": message["status"],
                        "time": datetime.fromtimestamp(time.time()).isoformat(),
                        # Provided by the asgi-correlation-id middleware.
                        "rid": Headers(scope=message)["X-Request-ID"],
                        "session_id": request.query_params.get("sid"),
                        "sequence_no": int(seq)
                        if (seq := request.query_params.get("seq"))
                        else None,
                        "country": location.country,
                        "region": location.region,
                        "city": location.city,
                        "dma": location.dma,
                        "client_variants": request.query_params.get(
                            "client_variants", ""
                        ),
                        "requested_providers": request.query_params.get(
                            "providers", ""
                        ),
                        "browser": ua.browser,
                        "os_family": ua.os_family,
                        "form_factor": ua.form_factor,
                    }
                    suggest_request_logger.info("", extra=data)
                else:
                    data = {
                        "agent": request.headers.get("User-Agent"),
                        "path": request.url.path,
                        "method": request.method,
                        "lang": request.headers.get("Accept-Language"),
                        "querystring": dict(request.query_params),
                        "errno": 0,
                        "code": message["status"],
                        "time": datetime.fromtimestamp(time.time()).isoformat(),
                    }
                    logger.info("", extra=data)

            await send(message)

        await self.app(scope, receive, send_wrapper)
        return
