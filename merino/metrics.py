"""Client class for recording and sending StatsD metrics."""

import logging
from functools import cache
from typing import Any, Callable, Concatenate, Final, Mapping, ParamSpec, TypeVar, Union

import aiodogstatsd
from wrapt import decorator

from merino.config import settings
from merino.featureflags import FeatureFlags

logger = logging.getLogger(__name__)

# Type definitions for tags in aiodogstatsd metrics
MetricTagKey = str
MetricTagValue = Union[float, int, str]
MetricTags = Mapping[MetricTagKey, MetricTagValue]

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


def feature_flags_as_tags(feature_flags: FeatureFlags) -> MetricTags:
    """Return a representation of feature flags decisions."""
    return {
        f"{FLAGS_PREFIX}.{name}": int(decision)
        for name, decision in feature_flags.decisions.items()
    }


@decorator
def add_feature_flags(
    wrapped_method: Callable, instance: "Client", args: tuple, kwargs: dict
) -> Any:
    """Add feature flag decisions as tags when recording metrics."""
    # Tags added manually to the metrics client call
    tags = kwargs.pop("tags", {})

    # Generate tags based on the recorded feature flag decisions
    feature_flags_tags = feature_flags_as_tags(instance.feature_flags)

    # The order is important here. Feature flag tags added manually take
    # precedence over the auto-generated ones.
    kwargs["tags"] = {**feature_flags_tags, **tags}

    return wrapped_method(*args, **kwargs)


# TypeVar for the `ClientMeta` meta class
M = TypeVar("M", bound="ClientMeta")

# TypeVar for the `Client` class
C = TypeVar("C", bound="Client")

# ParamSpec for the client_method
P = ParamSpec("P")

# TypeVar for the return type of the StatsD client method
R = TypeVar("R")


class ClientMeta(type):
    """Metaclass that decorates Client methods with add_feature_flags."""

    def __new__(
        mcls: type[M],
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: dict[str, Any],
    ) -> M:
        """Create a new class with decorated methods."""

        def method_proxy(
            method_name: str,
        ) -> Callable[Concatenate[C, P], R]:
            """Return a method that proxies to correct method of the StatsD client."""

            def client_method(
                instance: C, *method_args: P.args, **method_kwargs: P.kwargs
            ) -> R:
                """Look up the correct method of the StatsD client call it."""
                # Keep track of all calls made to the metrics client
                call: MetricCall = {
                    "method_name": method_name,
                    "args": method_args,
                    "kwargs": method_kwargs,
                }
                instance.calls.append(call)

                # Look up the method on the StatsD client on the instance
                method: Callable[..., R] = getattr(instance.statsd_client, method_name)

                return method(*method_args, **method_kwargs)

            return client_method

        # Add the following proxy methods and decorate them with `add_feature_flags`
        for method_name in SUPPORTED_METHODS:
            namespace[method_name] = add_feature_flags(method_proxy(method_name))

        return super().__new__(mcls, name, bases, namespace, **kwargs)


class Client(metaclass=ClientMeta):
    """Proxy for a StatsD client that adds tags for feature flags."""

    statsd_client: aiodogstatsd.Client
    feature_flags: FeatureFlags
    calls: MetricCalls

    def __init__(
        self, statsd_client: aiodogstatsd.Client, feature_flags: FeatureFlags
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
def get_metrics_client() -> aiodogstatsd.Client:
    """Instantiate and memoize the StatsD client."""
    return aiodogstatsd.Client(
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


class _LocalDatagramLogger(aiodogstatsd.client.DatagramProtocol):
    """
    This class can be used to override the default DatagramProtocol.
    Instead of writing bytes to a socket, it logs them.
    The purpose is to make it easy to see the metrics in development environments.
    """

    def send(self, data: bytes) -> None:
        logger.debug("sending metrics", extra={"data": data.decode("utf8")})

    def error_received(self, exc) -> None:
        logger.exception(exc)
