"""Middleware for request metrics using FastAPI's middleware system."""

import logging
from http import HTTPStatus
from time import monotonic
from functools import cache

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from merino.utils.metrics import get_metrics_client
from merino.middleware import ScopeKey

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware for instrumenting request level metrics. We currently collect timing
    and status codes for all known paths as well as status codes for all paths (known and unknown).
    """

    @cache
    def _build_metric_name(self, method: str, path: str) -> str:
        return "{}.{}".format(method, path.lower().lstrip("/").replace("/", ".")).lower()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Capture request metrics including timing and status codes."""
        # get the memoized StatsD client
        metrics_client = get_metrics_client()

        # Store `Client` instance in the request scope, so that it can be used by other
        # middleware and endpoints.
        request.scope[ScopeKey.METRICS_CLIENT] = metrics_client
        tags = request.scope[ScopeKey.USER_AGENT].model_dump()

        # start the timer for request
        started_at = monotonic()
        try:
            # pass request to the next middleware / request handler function and wait for response.
            response = await call_next(request)

            duration = (monotonic() - started_at) * 1000
            status_code = response.status_code

            # don't track NOT_FOUND statuses by path.
            # Instead we will track those within a general `response.status_codes` metric.
            if status_code != HTTPStatus.NOT_FOUND:
                metric_name = self._build_metric_name(request.method, request.url.path)
                metrics_client.timing(f"{metric_name}.timing", value=duration)
                metrics_client.increment(f"{metric_name}.status_codes.{status_code}", tags=tags)

            metrics_client.increment(f"response.status_codes.{status_code}", tags=tags)
            return response

        except Exception:
            duration = (monotonic() - started_at) * 1000
            metric_name = self._build_metric_name(request.method, request.url.path)
            status_code = HTTPStatus.INTERNAL_SERVER_ERROR.value

            metrics_client.timing(f"{metric_name}.timing", value=duration, tags=tags)
            metrics_client.increment(f"{metric_name}.status_codes.{status_code}", tags=tags)
            metrics_client.increment(f"response.status_codes.{status_code}", tags=tags)
            raise
