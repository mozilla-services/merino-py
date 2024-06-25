"""The middleware that records various access logs for Merino."""

import logging
import re
import time
from datetime import datetime
from typing import Pattern

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from merino.utils.log_data_creators import (
    RequestSummaryLogDataModel,
    SuggestLogDataModel,
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
        """Initialize the middleware and store the ASGI app instance."""
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
                # https://mozilla-hub.atlassian.net/browse/DISCO-2489
                if (
                    PATTERN.match(request.url.path)
                    and request.query_params.get("providers", "").strip().lower() != "accuweather"
                ):
                    suggest_log_data: SuggestLogDataModel = create_suggest_log_data(
                        request, message, dt
                    )
                    suggest_request_logger.info("", extra=suggest_log_data.model_dump())
                else:
                    request_log_data: RequestSummaryLogDataModel = create_request_summary_log_data(
                        request, message, dt
                    )
                    logger.info("", extra=request_log_data.model_dump())

            await send(message)

        await self.app(scope, receive, send_wrapper)
        return
