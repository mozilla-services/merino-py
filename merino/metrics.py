"""Client class for recording and sending StatsD metrics."""

import logging
from functools import cache
from typing import Mapping

import aiodogstatsd

from merino.config import settings

logger = logging.getLogger(__name__)

# Type definition for tags in aiodogstatsd metrics
MetricTags = Mapping[str, float | int | str]


@cache
def get_metrics_client() -> aiodogstatsd.Client:
    """Instantiate and memoize the StatsD client."""
    constant_tags: MetricTags = {
        "application": "merino-py",
        "deployment.canary": int(settings.deployment.canary),
    }

    return aiodogstatsd.Client(
        host=settings.metrics.host,
        port=settings.metrics.port,
        namespace="merino",
        constant_tags=constant_tags,
    )


async def configure_metrics() -> None:
    """Configure metrics client. Used in application startup."""
    client = get_metrics_client()
    if settings.metrics.dev_logger:
        client._protocol = _LocalDatagramLogger()
    await client.connect()


class _LocalDatagramLogger(aiodogstatsd.client.DatagramProtocol):
    """This class can be used to override the default DatagramProtocol.
    Instead of writing bytes to a socket, it logs them.
    The purpose is to make it easy to see the metrics in development environments.
    """

    def send(self, data: bytes) -> None:
        logger.debug("sending metrics", extra={"data": data.decode("utf8")})

    def error_received(self, exc) -> None:
        logger.exception(exc)
