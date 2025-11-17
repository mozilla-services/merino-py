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
def fetch_and_store():  # pragma: no cover
    """Fetch and store flight numbers"""
    logger.info("Starting flight schedules pipeline...")

    base_url = settings.flightaware.base_url
    flight_number_set = set()
    api_call_count = 0

    try:
        with httpx.Client(base_url=base_url) as client:
            flight_number_set, api_call_count = fetch_schedules.fetch_schedules(client)

    except Exception as ex:
        logger.error(f"Failed to fetch schedules: {ex.__class__.__name__}", exc_info=True)

    finally:
        # Always try to persist whatever we have
        if flight_number_set:
            logger.info(f"Persisting {len(flight_number_set)} flight numbers (even if partial)")
            asyncio.run(fetch_schedules.store_flight_numbers(flight_number_set))

    logger.info(
        f"Fetch finished with {len(flight_number_set)} flights after {api_call_count} API calls"
    )
