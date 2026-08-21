"""CLI commands for the Particle updater job."""

import asyncio
import logging
import typer

from merino.providers import games

logger = logging.getLogger(__name__)

cli = typer.Typer(
    name="games_tasks",
    help="Commands to process data related to New Tab games.",
)


@cli.command("update-particle")
def update_particle():  # pragma: no cover
    """Initialize the Particle provider and execute the process to attempt to update the Particle game."""
    games.init_particle()

    provider = games.get_particle_provider()

    logger.info("Beginning Particle update process...")

    updated = asyncio.run(provider.run_update_process())

    logger.info(f"Finished Particle update process. Files updated? {updated}")
