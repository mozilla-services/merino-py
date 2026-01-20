"""CLI commands for the massive image ingestion job"""

import asyncio
import logging

import typer

from merino.jobs.massive.massive_ingestion import MassiveIngestion

logger = logging.getLogger(__name__)

cli = typer.Typer(
    name="massive-ingestion",
    help="Commands to download ticker logos, upload to GCS, and generate manifest",
)


@cli.command()
def ingest():  # pragma: no cover
    """Download logos, upload to GCS, and generate manifest."""
    logger.info("Starting Massive ingestion pipeline...")

    try:
        ingestion = MassiveIngestion()

        asyncio.run(ingestion.ingest())
    except Exception as ex:
        # Minimal, sanitized message; traceback but *no locals*.
        logger.error(f"Ingestion failed: {ex.__class__.__name__}", exc_info=True)
