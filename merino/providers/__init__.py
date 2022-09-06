"""Initialize all Providers."""
import asyncio
import logging
from timeit import default_timer as timer

from merino import remotesettings
from merino.config import settings
from merino import metrics
from merino.config import settings
from merino.providers.adm import Provider as AdmProvider
from merino.providers.base import BaseProvider
from merino.providers.wiki_fruit import WikiFruitProvider

providers: dict[str, BaseProvider] = {}
default_providers: list[BaseProvider] = []

logger = logging.getLogger(__name__)


async def init_providers() -> None:
    """
    Initialize all suggestion providers.

    This should only be called once at the startup of application.
    """
    start = timer()

    # register providers
    providers["adm"] = AdmProvider(backend=remotesettings.LiveBackend())
    if settings.providers.wiki_fruit.enabled:
        providers["wiki_fruit"] = WikiFruitProvider()

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
            [p for p in providers.values() if p.enabled_by_default()]
        )
        logger.info(
            "Provider initialization complete",
            extra={"providers": [*providers.keys()], "elapsed": timer() - start},
        )


def get_providers() -> tuple[dict[str, BaseProvider], list[BaseProvider]]:
    """Return a tuple of all the providers and default providers."""
    return providers, default_providers
