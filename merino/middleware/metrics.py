"""Middleware for request metrics."""

import logging
from asyncio import get_event_loop
from functools import cache
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

    constant_tags: dict[str, str | int] = {
        "application": "merino-py",
        "deployment.canary": int(is_canary),
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
        tags = user_agent.model_dump()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                duration = (loop.time() - started_at) * 1000

                status_code = message["status"]
                # don't track NOT_FOUND statuses by path.
                # Instead we will track those within a general `response.status_codes` metric.
                if status_code != HTTPStatus.NOT_FOUND.value:
                    # Migrating to otel metrics, emit otel + original statsd_metrics side by side
                    # for a period while we transition
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
                    metric_name = self._build_metric_name(request.method, request.url.path)
                    metrics_client.timing(
                        f"{metric_name}.timing",
                        value=duration,
                    )
                    metrics_client.increment(
                        f"{metric_name}.status_codes.{status_code}", tags=tags
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
                # track all status codes here.
                metrics_client.increment(f"response.status_codes.{status_code}", tags=tags)

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            status_code = HTTPStatus.INTERNAL_SERVER_ERROR.value
            duration = (loop.time() - started_at) * 1000
            metric_name = self._build_metric_name(request.method, request.url.path)
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
            metrics_client.timing(f"{metric_name}.timing", value=duration, tags=tags)
            metrics_client.increment(f"{metric_name}.status_codes.{status_code}", tags=tags)
            metrics_client.increment(f"response.status_codes.{status_code}", tags=tags)
            raise

    @cache
    def _build_metric_name(self, method: str, path: str) -> str:
        return "{}.{}".format(method, path.lower().lstrip("/").replace("/", ".")).lower()
