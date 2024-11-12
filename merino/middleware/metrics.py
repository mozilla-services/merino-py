"""Middleware for request metrics."""

import logging
from asyncio import get_event_loop
from functools import cache
from http import HTTPStatus

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from merino.utils.metrics import get_metrics_client
from merino.middleware import ScopeKey

logger = logging.getLogger(__name__)


class MetricsMiddleware:
    """Middleware for instrumenting request level metrics. We currently collect timing
    and status codes for all known paths as well as status codes for all paths (known and unknown).
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the metrics middleware."""
        self.app: ASGIApp = app

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

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                duration = (loop.time() - started_at) * 1000

                status_code = message["status"]
                # don't track NOT_FOUND statuses by path.
                # Instead we will track those within a general `response.status_codes` metric.
                if status_code != HTTPStatus.NOT_FOUND.value:
                    metric_name = self._build_metric_name(request.method, request.url.path)
                    metrics_client.timing(
                        f"{metric_name}.timing",
                        value=duration,
                    )
                    metrics_client.increment(
                        f"{metric_name}.status_codes.{status_code}",
                    )

                # track all status codes here.
                metrics_client.increment(f"response.status_codes.{status_code}")

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            status_code = HTTPStatus.INTERNAL_SERVER_ERROR.value
            duration = (loop.time() - started_at) * 1000
            metric_name = self._build_metric_name(request.method, request.url.path)
            metrics_client.timing(f"{metric_name}.timing", value=duration)
            metrics_client.increment(f"{metric_name}.status_codes.{status_code}")
            metrics_client.increment(f"response.status_codes.{status_code}")
            raise

    @cache
    def _build_metric_name(self, method: str, path: str) -> str:
        return "{}.{}".format(method, path.lower().lstrip("/").replace("/", ".")).lower()
