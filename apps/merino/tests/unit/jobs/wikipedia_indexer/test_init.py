# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the wikipedia indexer CLI commands."""

import pytest

from merino.jobs.wikipedia_indexer import copy_export, index

MODULE = "merino.jobs.wikipedia_indexer"


@pytest.fixture(name="collaborators")
def fixture_collaborators(mocker):
    """Replace everything the CLI commands construct or call out to."""
    file_manager = mocker.patch(f"{MODULE}.FileManager")
    file_manager.return_value.stream_latest_dump_to_gcs = mocker.AsyncMock()

    return {
        "adapter": mocker.patch(f"{MODULE}.ElasticSearchAdapter"),
        "file_manager": file_manager,
        "indexer": mocker.patch(f"{MODULE}.Indexer"),
        "create_blocklist": mocker.patch(f"{MODULE}.create_blocklist", return_value={"meme"}),
    }


def _index(**overrides):
    """Invoke the index command with every option supplied explicitly.

    Typer's defaults are `OptionInfo` objects, so calling the function directly
    requires passing real values.
    """
    kwargs = {
        "language": "en",
        "elasticsearch_url": "http://es:9200",
        "elasticsearch_api_key": "key",
        "elasticsearch_request_timeout": 60,
        "elasticsearch_create_index_timeout": 120,
        "blocklist_file_url": "http://blocklist/cats.csv",
        "index_version": "v1",
        "total_docs": 100,
        "gcs_path": "bucket/prefix",
        "gcp_project": "a-project",
    }
    kwargs.update(overrides)
    return index(**kwargs)


def test_index_passes_the_configured_timeouts_to_the_adapter(collaborators):
    """Verify both timeout settings reach the Elasticsearch adapter."""
    _index(elasticsearch_request_timeout=45, elasticsearch_create_index_timeout=90)

    collaborators["adapter"].assert_called_once_with(
        url="http://es:9200",
        api_key="key",
        request_timeout=45,
        create_index_timeout=90,
    )


def test_index_builds_the_indexer_and_runs_it(collaborators):
    """Verify the command wires its collaborators together and starts indexing."""
    _index()

    collaborators["create_blocklist"].assert_called_once_with("http://blocklist/cats.csv")
    collaborators["file_manager"].assert_called_once_with("bucket/prefix", "a-project", "", "en")

    collaborators["indexer"].assert_called_once()
    version, categories, _titles, file_manager, elasticsearch = collaborators[
        "indexer"
    ].call_args.args
    assert version == "v1"
    assert categories == {"meme"}
    assert file_manager is collaborators["file_manager"].return_value
    assert elasticsearch is collaborators["adapter"].return_value

    # The alias is looked up per language, e.g. `en_es_alias`.
    collaborators["indexer"].return_value.index_from_export.assert_called_once_with(
        100, "enwiki-{version}"
    )


def test_index_resolves_the_alias_for_the_requested_language(collaborators):
    """Verify a non-default language reads its own alias setting."""
    _index(language="fr")

    collaborators["indexer"].return_value.index_from_export.assert_called_once_with(
        100, "frwiki-{version}"
    )


def test_copy_export_copies_the_latest_dump(collaborators):
    """Verify the command builds a FileManager pointed at the export URL and copies."""
    copy_export(
        language="en",
        export_base_url="http://dumps/",
        gcs_path="bucket/prefix",
        gcp_project="a-project",
    )

    collaborators["file_manager"].assert_called_once_with(
        "bucket/prefix", "a-project", "http://dumps/", "en"
    )
    collaborators["file_manager"].return_value.stream_latest_dump_to_gcs.assert_called_once_with()


def test_copy_export_raises_when_no_export_is_found(collaborators):
    """Verify the command fails loudly rather than exiting zero having copied nothing."""
    collaborators["file_manager"].return_value.stream_latest_dump_to_gcs.return_value = None

    with pytest.raises(RuntimeError, match="No complete en CirrusSearch export"):
        copy_export(
            language="en",
            export_base_url="http://dumps/",
            gcs_path="bucket/prefix",
            gcp_project="a-project",
        )
