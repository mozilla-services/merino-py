"""CLI commands for the Wikimedia Picture of the Day updater job."""

import logging
import typer
from merino.providers.rss import get_wikimedia_potd_provider

logger = logging.getLogger(__name__)


provider = get_wikimedia_potd_provider()

cli = typer.Typer(
    name="wikimedia_potd_updater",
    help="Commands to process and update data related to Picture of the Day widget on New Tab.",
)


@cli.command("update-wikimedia-potd")
async def update_wikimedia_potd():  # pragma: no cover
    """Execute the process to attempt to update the Wikimedia Picture of the Day."""
    logger.info("Beginning wikimedia potd update process...")

    await provider.upload_picture_of_the_day()

    logger.info("Finished wikimedia potd update.")
