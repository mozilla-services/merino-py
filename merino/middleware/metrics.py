"""Middleware for request metrics."""
import logging
from asyncio import get_event_loop
from functools import cache
from http import HTTPStatus

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from merino.metrics import get_metrics_client

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware for instrumenting request level metrics. We currently collect timing
    and status codes for all known paths as well as status codes for all paths (known and unknown).
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Wrap the request with metrics"""
        client = get_metrics_client()

        loop = get_event_loop()
        started_at = loop.time()

        # 500 errors raise as non HTTPException so we can avoid a catchall `except`
        # by defaulting to 500 and overwriting on a successful request or an HTTPException
        status_code = HTTPStatus.INTERNAL_SERVER_ERROR.value

        try:
            response = await call_next(request)
            status_code = response.status_code
        except HTTPException as e:
            status_code = e.status_code
            raise e
        finally:
            duration = (loop.time() - started_at) * 1000
            # don't track NOT_FOUND statuses by path.
            # Instead we will track those within a general `status_codes` bucket.
            if status_code != HTTPStatus.NOT_FOUND.value:
                metric_name = self._build_metric_name(request.method, request.url.path)
                client.timing(f"{metric_name}.timing", value=duration)
                client.increment(f"{metric_name}.status_codes.{status_code}")

            # track all status codes here.
            client.increment(f"request.status_codes.{status_code}")

        return response

    @cache
    def _build_metric_name(self, method: str, path: str) -> str:
        return "{}.{}".format(
            method, path.lower().lstrip("/").replace("/", ".")
        ).lower()
