"""The middleware that records various access logs for Merino."""
import logging
import re
import time
from datetime import datetime
from typing import Pattern

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from merino.util.log_data_creators import (
    create_request_summary_log_data,
    create_suggest_log_data,
)

# web.suggest.request is used for logs coming from the /suggest endpoint
suggest_request_logger = logging.getLogger("web.suggest.request")
# all other requests will be logged to request.summary
logger = logging.getLogger("request.summary")

# The path pattern for the suggest API
PATTERN: Pattern = re.compile(r"/api/v[1-9]\d*/suggest$")


class LoggingMiddleware:
    """An ASGI middleware for logging."""

    def __init__(self, app: ASGIApp) -> None:
        """Initialize."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        """Log requests."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                request = Request(scope=scope)
                dt: datetime = datetime.fromtimestamp(time.time())
                if PATTERN.match(request.url.path):
                    data = create_suggest_log_data(request, message, dt)
                    suggest_request_logger.info("", extra=data)
                else:
                    data = create_request_summary_log_data(request, message, dt)
                    logger.info("", extra=data)

            await send(message)

        await self.app(scope, receive, send_wrapper)
        return
