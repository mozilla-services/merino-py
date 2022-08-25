import logging

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from merino.metrics import get_client

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):

    _metric_names: dict[str, str] = {}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        client = get_client()
        metric_name = self.build_metric_name(request.url.path)
        status_code = 0

        try:
            with client.timeit(f"{metric_name}.timing"):
                response = await call_next(request)
            status_code = response.status_code
        except HTTPException as e:
            status_code = e.status_code
            raise e
        finally:
            client.increment(f"{metric_name}.status_codes.{status_code}")
        return response

    def build_metric_name(self, path: str) -> str:
        if path not in self._metric_names:
            self._metric_names[path] = path.lower().lstrip("/").replace("/", ".")
        return self._metric_names[path]
