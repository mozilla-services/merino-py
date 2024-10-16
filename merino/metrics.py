"""Client class for recording and sending StatsD metrics."""

import logging
from functools import cache
from typing import Final, Mapping, ParamSpec, TypeVar

import aiodogstatsd

from merino.config import settings

logger = logging.getLogger(__name__)

# Type definition for tags in aiodogstatsd metrics
MetricTags = Mapping[str, float | int | str]

# Type definitions for the `calls` attribute on the `Client` class
MetricCall = dict[str, str | tuple | dict]
MetricCalls = list[MetricCall]

# TypeVar for the `Client` class
C = TypeVar("C", bound="Client")

# ParamSpec for the client_method
P = ParamSpec("P")

# TypeVar for the return type of the StatsD client method
R = TypeVar("R")

# The following methods are added to the `Client` class by the meta class
SUPPORTED_METHODS: Final[list[str]] = [
    "gauge",
    "increment",
    "decrement",
    "histogram",
    "distribution",
    "timing",
    "timeit_task",
]


class Client:
    """Proxy for a StatsD client"""

    statsd_client: aiodogstatsd.Client
    calls: MetricCalls

    def __init__(self, statsd_client: aiodogstatsd.Client) -> None:
        """Initialize the client instance."""
        self.statsd_client = statsd_client
        self.calls = []

    def __getattr__(self, attr_name: str):
        """Raise an exception when an unsupported attribute is requested."""
        logger.warning(f"{attr_name} is not a supported method: {SUPPORTED_METHODS}")
        raise AttributeError(f"attribute '{attr_name}' is not supported by metrics.Client class")


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
