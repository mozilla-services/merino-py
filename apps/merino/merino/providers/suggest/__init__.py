"""Initialize all Providers."""

from __future__ import annotations

import asyncio
import logging
from timeit import default_timer as timer

from opentelemetry import metrics as otel_metrics

from merino.providers.suggest.base import BaseProvider
from merino.providers.suggest.manager import load_providers
from merino.utils import task_runner

providers: dict[str, BaseProvider] = {}
default_providers: list[BaseProvider] = []

logger = logging.getLogger(__name__)

_meter = otel_metrics.get_meter("merino.providers.suggest")
_provider_initialize_duration = _meter.create_histogram(
    "merino_providers_initialize_duration",
    unit="ms",
    description="Duration of suggest provider initialization",
)


async def _initialize_provider(provider_name: str, provider: BaseProvider) -> None:
    """Initialize a provider and record its initialization duration."""
    start = timer()
    try:
        await provider.initialize()
    finally:
        _provider_initialize_duration.record(
            (timer() - start) * 1000,
            {"provider": provider_name},
        )


async def init_providers() -> None:
    """Initialize all providers

    This should only be called once at the startup of application.
    """
    from merino.configs import settings
    from merino.utils.query_processing.normalization import init_pipeline

    start = timer()
    # register providers
    providers.update(load_providers(disabled_providers_list=settings.runtime.disabled_providers))

    # initialize providers and record time
    initialization_start = timer()
    try:
        wrapped_tasks = [
            asyncio.create_task(
                _initialize_provider(provider_name, provider),
                name=provider_name,
            )
            for provider_name, provider in providers.items()
        ]
        await task_runner.gather(wrapped_tasks)

        exceptions = [
            exception for task in wrapped_tasks if (exception := task.exception()) is not None
        ]
        if exceptions:
            raise exceptions[0]

        default_providers.extend([p for p in providers.values() if p.enabled_by_default])
        logger.info(
            "Provider initialization completed",
            extra={"providers": [*providers.keys()], "elapsed": timer() - start},
        )
    finally:
        _provider_initialize_duration.record(
            (timer() - initialization_start) * 1000,
            {"provider": "__ALL__"},
        )

    # init query normalization pipeline
    await init_pipeline()


async def shutdown_providers() -> None:
    """Shut down all providers

    This should only be called once at the shutdown of application.
    """
    start = timer()

    for provider in providers.values():
        await provider.shutdown()
    logger.info(
        "Provider shutdown completed",
        extra={"providers": [*providers.keys()], "elapsed": timer() - start},
    )


def get_providers() -> tuple[dict[str, BaseProvider], list[BaseProvider]]:
    """Return a tuple of all providers and default providers"""
    return providers, default_providers


def get_weather_provider() -> BaseProvider:
    """Return the weather provider"""
    return providers["accuweather"]
