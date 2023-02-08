"""Entrypoint for the command line interface."""
import typer

from merino.config_logging import configure_logging
from merino.jobs.wikipedia_indexer import indexer_cmd

cli = typer.Typer(no_args_is_help=True, add_completion=False)
# Add the wikipedia-indexer subcommands
cli.add_typer(indexer_cmd, no_args_is_help=True)


@cli.callback("setup")
def setup():
    """CLI Entrypoint"""
    configure_logging()


if __name__ == "__main__":
    cli()
