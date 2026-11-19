"""Integration test for CLI command output"""

import pytest
from typer.testing import CliRunner

from merino.jobs.cli import cli
from merino.jobs.wikipedia_indexer import RunMode

runner = CliRunner()

WIKIPEDIA_INDEXER_MODULE = "merino.jobs.wikipedia_indexer"

# The article blocklist location the `index` command requires.
ARTICLE_BLOCKLIST_ARGS = [
    "--article-blocklist-bucket",
    "blocklist-bucket",
    "--article-blocklist-prefix",
    "article_blocklist",
    "--article-blocklist-project",
    "blocklist-project",
]


@pytest.fixture(name="indexer_collaborators")
def fixture_indexer_collaborators(mocker):
    """Replace everything the wikipedia indexer `index` command constructs or calls out to."""
    mocker.patch(f"{WIKIPEDIA_INDEXER_MODULE}.ElasticSearchAdapter")
    mocker.patch(f"{WIKIPEDIA_INDEXER_MODULE}.FileManager")
    mocker.patch(f"{WIKIPEDIA_INDEXER_MODULE}.load_article_blocklist", return_value={"Q1"})
    return {
        "indexer": mocker.patch(f"{WIKIPEDIA_INDEXER_MODULE}.Indexer"),
        "upload_blocked_titles": mocker.patch(
            f"{WIKIPEDIA_INDEXER_MODULE}.upload_blocked_titles", return_value="en-1.csv"
        ),
    }


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


@pytest.mark.parametrize(
    ["value", "expected"],
    [
        ("blocklist-only", RunMode.BLOCKLIST_ONLY),
        ("index-only", RunMode.INDEX_ONLY),
        ("both", RunMode.BOTH),
        (None, RunMode.BOTH),
    ],
    ids=["blocklist-only", "index-only", "both", "default"],
)
def test_wikipedia_indexer_index_mode_option_values(indexer_collaborators, value, expected):
    """Test that the wikipedia indexer accepts each `--mode` value, defaulting to `both`"""
    args = [*ARTICLE_BLOCKLIST_ARGS]
    if value is not None:
        args += ["--mode", value]
    indexer = indexer_collaborators["indexer"].return_value

    result = runner.invoke(cli, ["wikipedia-indexer", "index", *args])

    assert result.exit_code == 0, result.output
    assert indexer.collect_blocked_titles.called is (expected is RunMode.BLOCKLIST_ONLY)
    assert indexer.index_from_export.called is (expected is not RunMode.BLOCKLIST_ONLY)
    upload = indexer_collaborators["upload_blocked_titles"]
    assert upload.called is (expected is not RunMode.INDEX_ONLY)
