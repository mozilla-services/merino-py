"""The middleware that records various access logs for Merino."""

import logging
import re
import time
from datetime import datetime
from typing import Pattern

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from merino.middleware import ScopeKey
from merino.utils.log_data_creators import (
    SuggestLogDataModel,
    create_suggest_log_data,
)
from merino.configs import settings
from merino.utils.query_processing.pii_detect import PIIType

# web.suggest.request is used for logs coming from the /suggest endpoint
suggest_request_logger = logging.getLogger("web.suggest.request")

# The path pattern for the suggest API
PATTERN: Pattern = re.compile(r"/api/v[1-9]\d*/suggest$")

# Whether to log `web.suggest.request`
LOG_SUGGEST_REQUEST: bool = settings.logging.log_suggest_request


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
                    LOG_SUGGEST_REQUEST
                    and PATTERN.match(request.url.path)
                    and request.query_params.get("providers", "").strip().lower() != "accuweather"
                    and request.scope.get(ScopeKey.PII_DETECTION) == PIIType.NON_PII
                ):
                    suggest_log_data: SuggestLogDataModel = create_suggest_log_data(
                        request, message, dt
                    )
                    suggest_request_logger.info("", extra=suggest_log_data.model_dump())

            await send(message)

        await self.app(scope, receive, send_wrapper)
        return
