import logging
from functools import cache

from aiodogstatsd import Client
from aiodogstatsd.client import DatagramProtocol

from merino.config import settings

logger = logging.getLogger(__name__)


@cache
def get_client() -> Client:
    return Client(
        host=settings.metrics.host,
        port=settings.metrics.port,
        constant_tags={"application": "merino"},
    )


async def configure_metrics() -> Client:
    client = get_client()
    try:
        if settings.metrics.dev_logger:
            client._protocol = LocalDatagramLogger()
        await client.connect()
    except Exception as e:
        logger.exception(e)
    finally:
        return client


class LocalDatagramLogger(DatagramProtocol):
    def send(self, data):
        logger.debug("sending metrics", extra={"data": data.decode("utf8")})

    def error_received(self, exc):
        logger.exception(exc)
