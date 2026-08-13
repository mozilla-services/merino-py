"""The middleware that records various access logs for Merino."""

import logging
import re
import time
from datetime import datetime
from typing import Pattern

from opentelemetry import metrics
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from merino.middleware import ScopeKey
from merino.message_handlers.search_terms import get_message_handler
from merino.utils.log_data_creators import create_suggest_log_data
from merino_common.models.suggest_logging import (
    SuggestLogDataModel,
    SuggestRequestParams,
)
from merino_common.utils.async_batch_queue import (
    QueueFullException,
    QueueShutDownException,
)
from merino.configs import settings
from merino_common.utils.query_processing.pii_detect import PIIType

logger = logging.getLogger(__name__)

# web.suggest.request is used for logs coming from the /suggest endpoint
suggest_request_logger = logging.getLogger("web.suggest.request")

# The path pattern for the suggest API
PATTERN: Pattern = re.compile(r"/api/v[1-9]\d*/suggest$")

# Whether to log `web.suggest.request`
LOG_SUGGEST_REQUEST: bool = settings.logging.log_suggest_request

# Whether to submit search terms to merino-fleece for sanitization.
SUBMIT_SEARCH_TERMS: bool = settings.message_handler.enabled

# Excluded providers for logging
EXCLUDED_PROVIDERS: frozenset[str] = frozenset(settings.logging.excluded_providers)

_meter = metrics.get_meter("merino.middleware.logging")
_enqueue_counter = _meter.create_counter(
    name="search_term.enqueue.count",
    unit="{search_term}",
    description="Search terms enqueued for submission to merino-fleece, labeled by outcome.",
)


def _submit_search_term(request_params: SuggestRequestParams) -> None:
    """Enqueue a search term for asynchronous submission, without failing the request."""
    try:
        get_message_handler().put(request_params)
    except (QueueFullException, QueueShutDownException) as ex:
        _enqueue_counter.add(1, {"outcome": "error", "error.type": type(ex).__name__})
        logger.warning("Failed to enqueue search term for submission", exc_info=True)
    else:
        _enqueue_counter.add(1, {"outcome": "success"})


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
                    (LOG_SUGGEST_REQUEST or SUBMIT_SEARCH_TERMS)
                    and PATTERN.match(request.url.path)
                    and request.query_params.get("providers", "").strip().lower()
                    not in EXCLUDED_PROVIDERS
                ):
                    suggest_log_data: SuggestLogDataModel = create_suggest_log_data(
                        request, message, dt
                    )
                    if (
                        LOG_SUGGEST_REQUEST
                        and request.scope.get(ScopeKey.PII_DETECTION) == PIIType.NON_PII
                    ):
                        suggest_request_logger.info("", extra=suggest_log_data.model_dump())
                    if SUBMIT_SEARCH_TERMS:
                        _submit_search_term(suggest_log_data.request_params)

            await send(message)

        await self.app(scope, receive, send_wrapper)
        return
