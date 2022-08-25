import logging
from typing import Optional

from fastapi import HTTPException
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    DispatchFunction,
    RequestResponseEndpoint,
)
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from merino.metrics import get_client

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):

    _metric_names: dict[str, str]

    def __init__(
        self, app: ASGIApp, dispatch: Optional[DispatchFunction] = None
    ) -> None:
        super().__init__(app, dispatch)
        self._metric_names = {
            route.path: route.path.lstrip("/").replace("/", ".") for route in app.routes
        }

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        client = get_client()
        metric_name = self._metric_names[request.url.path]
        status_code = 0

        try:
            with client.timeit(f"{metric_name}.timing"):
                response = await call_next(request)
            client.increment(f"{metric_name}.status_codes.{response.status_code}")
            status_code = response.status_code
        except HTTPException as e:
            status_code = e.status_code
            raise e
        finally:
            client.increment(f"{metric_name}.status_codes.{status_code}")
        return response
