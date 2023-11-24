"""Initialization functions for the New Tab code."""
import logging

from merino.config import settings
from merino.newtab.upday_provider import UpdayProvider
from merino.utils.http_client import create_http_client

upday_provider: UpdayProvider | None = None

logger = logging.getLogger(__name__)


async def init_providers() -> None:
    """Initialize New Tab Providers.
    Currently only returning the Upday Provider as it's the only one that we are using.

    This should only be called once at the startup of the application.
    """
    if settings.newtab.upday.password:
        global upday_provider
        upday_provider = UpdayProvider(
            username=settings.newtab.upday.username,
            password=settings.newtab.upday.password,
            http_client=create_http_client(settings.newtab.upday.url),
        )
        logger.info("Initialized Upday Provider")
    else:
        logger.info("Skip initializing Upday Provider")


async def shutdown_providers() -> None:
    """Ensure that the providers shut down safely."""
    if upday_provider is not None:
        await upday_provider.shutdown()


def get_upday_provider() -> UpdayProvider | None:
    """Access function for the Upday provider."""
    return upday_provider
