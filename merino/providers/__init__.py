"""Initialize all Providers."""
import asyncio
import logging
from enum import Enum, unique
from timeit import default_timer as timer

from merino import metrics
from merino.config import settings
from merino.exceptions import InvalidProviderError
from merino.providers.adm import Provider as AdmProvider
from merino.providers.adm import TestBackend
from merino.providers.base import BaseProvider
from merino.providers.wiki_fruit import WikiFruitProvider
from merino.remotesettings import LiveBackend

providers: dict[str, BaseProvider] = {}
default_providers: list[BaseProvider] = []

logger = logging.getLogger(__name__)


@unique
class ProviderType(str, Enum):
    """Enum for provider type."""

    ADM = "adm"
    WIKI_FRUIT = "wiki_fruit"


async def init_providers() -> None:
    """
    Initialize all suggestion providers.

    This should only be called once at the startup of application.
    """
    start = timer()

    # register providers
    for provider_type, setting in settings.providers.items():
        match provider_type:
            case ProviderType.ADM:
                providers["adm"] = AdmProvider(
                    backend=(
                        LiveBackend()
                        if setting.backend == "remote-settings"
                        else TestBackend()
                    ),
                    enabled_by_default=setting.enabled_by_default,
                )
            case ProviderType.WIKI_FRUIT:
                providers["wiki_fruit"] = WikiFruitProvider(
                    enabled_by_default=setting.enabled_by_default
                )
            case _:
                raise InvalidProviderError(f"Unknown provider type: {provider_type}")

    # initialize providers and record time
    init_metric = f"{__name__}.initialize"
    client = metrics.get_metrics_client()
    with client.timeit(init_metric):
        wrapped_tasks = [
            client.timeit_task(p.initialize(), f"{init_metric}.{provider_name}")
            for provider_name, p in providers.items()
        ]
        await asyncio.gather(*wrapped_tasks)
        default_providers.extend(
            [p for p in providers.values() if p.enabled_by_default]
        )
        logger.info(
            "Provider initialization complete",
            extra={"providers": [*providers.keys()], "elapsed": timer() - start},
        )


def get_providers() -> tuple[dict[str, BaseProvider], list[BaseProvider]]:
    """Return a tuple of all the providers and default providers."""
    return providers, default_providers
