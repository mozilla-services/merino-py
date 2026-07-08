"""CLI commands for the Wikimedia Picture of the Day updater job."""

import asyncio
import logging
import typer
from merino.providers.rss import get_wikimedia_potd_provider, init_providers

logger = logging.getLogger(__name__)

cli = typer.Typer(
    name="wikimedia_potd_updater",
    help="Commands to process and update data related to Picture of the Day widget on New Tab.",
)


async def _potd_update_job() -> bool:
    """Get the provider and call the method to upload potd."""
    await init_providers()
    provider = get_wikimedia_potd_provider()
    return await provider.upload_picture_of_the_day()


@cli.command("update-wikimedia-potd")
def update_wikimedia_potd():  # pragma: no cover
    """Execute the process to attempt to update the Wikimedia Picture of the Day."""
    logger.info("Beginning wikimedia potd update process...")

    success = asyncio.run(_potd_update_job())

    logger.info("Wikimedia potd update job finished", extra={"success": success})
