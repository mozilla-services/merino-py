"""CLI commands for the polygon image ingestion job"""

import asyncio
import logging
from typing import Annotated

import typer

from merino.configs import settings as config
from merino.jobs.polygon.polygon_ingestion import PolygonIngestion

logger = logging.getLogger(__name__)

cli = typer.Typer(
    name="polygon-ingestion",
    help="Commands to download ticker logos, upload to GCS, and generate manifest",
)


@cli.command()
def ingest():
    """Download logos, upload to GCS, and generate manifest."""
    logger.info("Starting Polygon ingestion pipeline...")

    try:
        ingestion = PolygonIngestion()

        asyncio.run(ingestion.ingest())
    except Exception as ex:
        # Minimal, sanitized message; traceback but *no locals*.
        logger.error(f"Ingestion failed: {ex.__class__.__name__}", exc_info=True)
