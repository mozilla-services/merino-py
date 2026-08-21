"""Initialize all RSS providers."""

import logging

from merino.providers.rss.base import BaseRssProvider
from merino.providers.rss.wikimedia_potd.provider import WikimediaPictureOfTheDayProvider
from merino.providers.rss.manager import load_providers

logger = logging.getLogger(__name__)

providers: dict[str, BaseRssProvider] = {}


async def init_providers() -> None:
    """Initialize all RSS providers.

    This should only be called once at the startup of the application.
    """
    # load_providers() pulls all the rss providers from the config file.
    providers.update(load_providers())
    for name, provider in providers.items():
        await provider.initialize()
        logger.info("RSS provider initialized", extra={"provider": name})


async def shutdown_providers() -> None:
    """Shut down all RSS providers.

    This should only be called once at the shutdown of the application.
    """
    for name, provider in providers.items():
        await provider.shutdown()
        logger.info("RSS provider shut down", extra={"provider": name})
    # remove all providers from the module level providers dict.
    providers.clear()


def get_wikimedia_potd_provider() -> WikimediaPictureOfTheDayProvider:
    """Return the Wikimedia Picture of the Day provider."""
    provider = providers["wikimedia_potd"]
    assert isinstance(provider, WikimediaPictureOfTheDayProvider)
    return provider
