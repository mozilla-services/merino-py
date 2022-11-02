"""Client class for recording and sending StatsD metrics."""

import logging
from functools import cache
from typing import Any, Callable, Final, Mapping, TypeVar, Union

from aiodogstatsd import Client as StatsDClient
from aiodogstatsd.client import DatagramProtocol
from wrapt import decorator

from merino.config import settings
from merino.featureflags import FeatureFlags

logger = logging.getLogger(__name__)

# Type definitions for tags in aiodogstatsd metrics
MTagKey = str
MTagValue = Union[float, int, str]
MTags = Mapping[MTagKey, MTagValue]

# TypeVar for the `ClientMeta` meta class
_M = TypeVar("_M", bound="ClientMeta")

# Type definitions for the `calls` attribute on the `Client` class
MetricCall = dict[str, str | tuple | dict]
MetricCalls = list[MetricCall]

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

# Prefix for the tags for feature flags
FLAGS_PREFIX: Final[str] = "feature_flag"


def feature_flags_as_tags(feature_flags: FeatureFlags) -> MTags:
    """Return a representation of feature flags decisions."""
    return {
        f"{FLAGS_PREFIX}.{name}": int(decision)
        for name, decision in feature_flags.decisions.items()
    }


@decorator
def add_feature_flags(
    wrapped_method: Callable, instance: "Client", args: tuple, kwargs: dict
):
    """Add feature flag decisions as tags when recording metrics."""
    # Tags added manually to the metrics client call
    tags = kwargs.pop("tags", {})

    # Generate tags based on the recorded feature flag decisions
    feature_flags_tags = feature_flags_as_tags(instance.feature_flags)

    # The order is important here. Feature flag tags added manually take
    # precedence over the auto-generated ones.
    kwargs["tags"] = {**feature_flags_tags, **tags}

    return wrapped_method(*args, **kwargs)


class ClientMeta(type):
    """Metaclass that decorates Client methods with add_feature_flags."""

    def __new__(
        cls: type[_M],
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> _M:
        """Create a new class with decorated methods."""

        def method_proxy(method_name: str) -> Callable:
            """Return a method that proxies to correct method of the StatsD client."""

            def client_method(instance: "Client", *args, **kwargs) -> Any:
                """Look up the correct method of the StatsD client call it."""
                # Keep track of all calls made to the metrics client
                call: MetricCall = {
                    "method_name": method_name,
                    "args": args,
                    "kwargs": kwargs,
                }
                instance.calls.append(call)

                # Look up the method on the StatsD client on the instance
                method: Callable = getattr(instance.statsd_client, method_name)

                return method(*args, **kwargs)

            return client_method

        # Add the following proxy methods and decorate them with `add_feature_flags`
        for method_name in SUPPORTED_METHODS:
            namespace[method_name] = add_feature_flags(method_proxy(method_name))

        return super().__new__(cls, name, bases, namespace, **kwargs)


class Client(metaclass=ClientMeta):
    """Proxy for a StatsD client that adds tags for feature flags."""

    statsd_client: StatsDClient
    feature_flags: FeatureFlags
    calls: MetricCalls

    def __init__(
        self, statsd_client: StatsDClient, feature_flags: FeatureFlags
    ) -> None:
        """Initialize the client instance."""
        self.statsd_client = statsd_client
        self.feature_flags = feature_flags
        self.calls = []

    def __getattr__(self, attr_name: str):
        """Raise an exception when an unsupported attribute is requested."""
        logger.warning(f"{attr_name} is not a supported method: {SUPPORTED_METHODS}")
        raise AttributeError(
            f"attribute '{attr_name}' is not supported by metrics.Client class"
        )


@cache
def get_metrics_client() -> StatsDClient:
    """Instantiate and memoize the StatsD client."""
    return StatsDClient(
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
