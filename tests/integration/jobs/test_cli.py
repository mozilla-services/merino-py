"""Integration test for CLI command output"""
import pytest
from typer.testing import CliRunner

from merino.jobs.cli import cli

runner = CliRunner()


def test_cli_no_args():
    """Test that invoking the app with no arguments does not fail"""
    result = runner.invoke(cli)
    assert result.exit_code == 0


@pytest.mark.parametrize(
    argnames=[
        "command_name",
    ],
    argvalues=[
        ["wikipedia-indexer"],
        ["navigational-suggestions"],
        ["amo-rs-uploader"],
    ],
)
def test_cli_help_shows_commands(command_name):
    """Test that the commands we expect to see are listed in the help output"""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert command_name in result.stdout


@pytest.mark.parametrize(
    argnames=["command_name", "subcommand_names"],
    argvalues=[
        ["wikipedia-indexer", ["index", "copy-export"]],
        [
            "navigational-suggestions",
            [
                "prepare-domain-metadata",
            ],
        ],
    ],
)
def test_cli_help_shows_sub_commands(command_name, subcommand_names):
    """Test that the commands we expect to see are listed in the help output"""
    result = runner.invoke(cli, [command_name, "--help"])
    assert result.exit_code == 0
    for sub_commmand in subcommand_names:
        assert sub_commmand in result.stdout
