import logging
from functools import cache

from aiodogstatsd import Client
from aiodogstatsd.client import DatagramProtocol

from merino.config import settings

logger = logging.getLogger(__name__)


@cache
def get_metrics_client() -> Client:
    return Client(
        host=settings.metrics.host,
        port=settings.metrics.port,
        constant_tags={"application": "merino-py"},
    )


async def configure_metrics() -> None:
    client = get_metrics_client()
    if settings.metrics.dev_logger:
        client._protocol = LocalDatagramLogger()
    await client.connect()


class LocalDatagramLogger(DatagramProtocol):
    def send(self, data: bytes):
        logger.debug("sending metrics", extra={"data": data.decode("utf8")})

    def error_received(self, exc):
        logger.exception(exc)
