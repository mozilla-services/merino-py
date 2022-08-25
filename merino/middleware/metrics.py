from fastapi import HTTPException
import logging
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from merino.metrics import get_client

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            async with get_client() as client:
                metric_name = build_metric_name(request)
                with client.timeit(f"{metric_name}.timing"):
                    response = await call_next(request)
                client.increment(f"{metric_name}.status_codes.{response.status_code}")
                return response
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail=e)


def build_metric_name(req: Request) -> str:
    return req.url.path.lstrip("/").replace("/", ".")
