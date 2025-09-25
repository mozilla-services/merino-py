"""CLI commands for the flight schedules job"""

import asyncio
import logging

import httpx
import typer
from merino.configs import settings

from merino.jobs.flightaware import fetch_schedules

logger = logging.getLogger(__name__)

cli = typer.Typer(
    name="fetch_flights",
    help="Commands to fetch flight schedules and store flight numbers",
)


@cli.command()
def fetch_and_store():
    """Fetch and store flight numbers"""
    logger.info("Starting flight schedules pipeline...")

    base_url = settings.flightaware.base_url

    try:
        with httpx.Client(base_url=base_url) as client:
            flight_number_set, api_call_count = fetch_schedules.fetch_schedules(client)

            asyncio.run(fetch_schedules.store_flight_numbers(flight_number_set))
            logger.info(
                f"Successfully fetched {len(flight_number_set)} flights with {api_call_count} API calls"
            )

    except Exception as ex:
        logger.error(f"Failed to fetch schedules: {ex.__class__.__name__}", exc_info=True)
