"""Entrypoint for the command line interface."""
import typer

from merino.config_logging import configure_logging
from merino.jobs.amo_rs_uploader import amo_rs_uploader_cmd
from merino.jobs.csv_rs_uploader import csv_rs_uploader_cmd
from merino.jobs.navigational_suggestions import navigational_suggestions_cmd
from merino.jobs.wikipedia_indexer import indexer_cmd

cli = typer.Typer(no_args_is_help=True, add_completion=False)
# Add the wikipedia-indexer subcommands
cli.add_typer(indexer_cmd, no_args_is_help=True)

# Add the navigational suggestions subcommands
cli.add_typer(navigational_suggestions_cmd, no_args_is_help=True)

# Add the AMO suggestions subcommands
cli.add_typer(amo_rs_uploader_cmd, no_args_is_help=True)

# Add the CSV remote settings uploader subcommands
cli.add_typer(csv_rs_uploader_cmd, no_args_is_help=True)


@cli.callback("setup")
def setup():
    """CLI Entrypoint"""
    configure_logging()


if __name__ == "__main__":
    cli()
