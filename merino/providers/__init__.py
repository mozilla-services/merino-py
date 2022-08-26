import asyncio
import logging
from timeit import default_timer as timer

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
    providers["adm"] = AdmProvider()
    if settings.providers.wiki_fruit.enabled:
        providers["wiki_fruit"] = WikiFruitProvider()
    await asyncio.gather(*[p.initialize() for p in providers.values()])
    default_providers.extend([p for p in providers.values() if p.enabled_by_default()])
    logger.info(
        "Provider initialization complete",
        extra={"providers": [*providers.keys()], "elapsed": timer() - start},
    )


def get_providers() -> tuple[dict[str, BaseProvider], list[BaseProvider]]:
    """
    Return a tuple of all the providers and default providers.
    """
    return providers, default_providers
