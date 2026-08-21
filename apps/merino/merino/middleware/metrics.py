"""Middleware for request metrics."""

import logging
from asyncio import get_event_loop
from http import HTTPStatus

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from merino.utils.metrics import get_metrics_client
from merino.middleware import ScopeKey
from opentelemetry import metrics
from merino.configs import settings

logger = logging.getLogger(__name__)
is_canary = settings.deployment.canary


class MetricsMiddleware:
    """Middleware for instrumenting request level metrics. We currently collect timing
    and status codes for all known paths as well as status codes for all paths (known and unknown).
    """

    constant_tags = {
        "application": "merino-py",
        "deployment.canary": str(int(is_canary)),
    }

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the metrics middleware."""
        self.app: ASGIApp = app
        _meter = metrics.get_meter("merino")
        self._response_status_counter = _meter.create_counter("http_request_status_code")
        self._request_durations = _meter.create_histogram("http_request_duration")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Wrap the request with metrics."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # get the memoized StatsD client
        metrics_client = get_metrics_client()

        # Store `Client` instance in the request scope, so that it can be used by other
        # middleware and endpoints.
        scope[ScopeKey.METRICS_CLIENT] = metrics_client

        loop = get_event_loop()
        request = Request(scope=scope)
        started_at = loop.time()
        user_agent = scope[ScopeKey.USER_AGENT]

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                duration = (loop.time() - started_at) * 1000

                status_code = message["status"]
                # don't track NOT_FOUND statuses by path.
                # Instead we will track those within a general `response.status_codes` metric.
                if status_code != HTTPStatus.NOT_FOUND.value:
                    self._request_durations.record(
                        duration,
                        {
                            "method": request.method,
                            "path": request.url.path,
                            "form_factor": user_agent.form_factor,
                            **MetricsMiddleware.constant_tags,
                        },
                    )
                    self._response_status_counter.add(
                        1,
                        {
                            "method": request.method,
                            "path": request.url.path,
                            "status_code": status_code,
                            "form_factor": user_agent.form_factor,
                            **MetricsMiddleware.constant_tags,
                        },
                    )
                else:
                    # 404 paths are unbounded; track the counter without this tag
                    # No need to track histogram of response durations for 404s
                    self._response_status_counter.add(
                        1,
                        {
                            "method": request.method,
                            "status_code": status_code,
                            "form_factor": user_agent.form_factor,
                            **MetricsMiddleware.constant_tags,
                        },
                    )

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            status_code = HTTPStatus.INTERNAL_SERVER_ERROR.value
            duration = (loop.time() - started_at) * 1000
            self._response_status_counter.add(
                1,
                {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "form_factor": user_agent.form_factor,
                    **MetricsMiddleware.constant_tags,
                },
            )
            self._request_durations.record(
                duration,
                {
                    "method": request.method,
                    "path": request.url.path,
                    "form_factor": user_agent.form_factor,
                    **MetricsMiddleware.constant_tags,
                },
            )
            raise
