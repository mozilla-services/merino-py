"""Entrypoint for the command line interface."""
import click

from merino.config_logging import configure_logging
from merino.jobs.wikipedia_indexer import indexer_cmd

commands = {
    "wikipedia-indexer": indexer_cmd,
}


@click.group(commands=commands)
def cli():
    """CLI Entrypoint"""
    configure_logging()


if __name__ == "__main__":
    cli()
