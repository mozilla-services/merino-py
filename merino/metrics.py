"""Configuration for aiodogstatsd Client"""
import logging
from functools import cache

from aiodogstatsd import Client
from aiodogstatsd.client import DatagramProtocol

from merino.config import settings

logger = logging.getLogger(__name__)


@cache
def get_metrics_client() -> Client:
    """Instantiate and memoize the metrics client."""
    return Client(
        host=settings.metrics.host,
        port=settings.metrics.port,
        namespace="merino",
        constant_tags={"application": "merino-py"},
    )


async def configure_metrics() -> None:
    """Configure metrics client. Used in application startup."""
    client = get_metrics_client()
    if settings.metrics.dev_logger:
        client._protocol = _LocalDatagramLogger()
    await client.connect()


class _LocalDatagramLogger(DatagramProtocol):
    """
    This class can be used to override the default DatagramProtocol.
    Instead of writing bytes to a socket, it logs them.
    The purpose is to make it easy to see the metrics in development environments.
    """

    def send(self, data: bytes) -> None:
        logger.debug("sending metrics", extra={"data": data.decode("utf8")})

    def error_received(self, exc) -> None:
        logger.exception(exc)
