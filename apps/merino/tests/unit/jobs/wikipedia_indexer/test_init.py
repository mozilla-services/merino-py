# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the wikipedia indexer CLI commands."""

import logging

import pytest

from merino.jobs.wikipedia_indexer import RunMode, copy_export, index

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
        "load_article_blocklist": mocker.patch(
            f"{MODULE}.load_article_blocklist", return_value={"Q1"}
        ),
        "upload_blocked_titles": mocker.patch(
            f"{MODULE}.upload_blocked_titles", return_value="blocked_titles/en/1.csv"
        ),
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
        "follower_sync_timeout": 3600,
        "follower_sync_poll_interval": 15,
        "follower_discovery_period": 60,
        "article_blocklist_bucket": "blocklist-bucket",
        "article_blocklist_prefix": "article_blocklist",
        "article_blocklist_project": "blocklist-project",
        "blocked_titles_destination": "",
        "index_version": "v1",
        "total_docs": 100,
        "gcs_path": "bucket/prefix",
        "gcp_project": "a-project",
        "mode": RunMode.BOTH,
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

    collaborators["load_article_blocklist"].assert_called_once_with(
        "blocklist-bucket", "article_blocklist", "blocklist-project"
    )
    collaborators["file_manager"].assert_called_once_with("bucket/prefix", "a-project", "", "en")

    collaborators["indexer"].assert_called_once()
    version, articles, _titles, file_manager, elasticsearch = collaborators[
        "indexer"
    ].call_args.args
    assert version == "v1"
    assert articles == {"Q1"}
    assert file_manager is collaborators["file_manager"].return_value
    assert elasticsearch is collaborators["adapter"].return_value

    # The alias is looked up per language, e.g. `en_es_alias`.
    collaborators["indexer"].return_value.index_from_export.assert_called_once_with(
        100, "enwiki-{version}"
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"article_blocklist_bucket": ""},
        {"article_blocklist_prefix": ""},
        {"article_blocklist_project": ""},
    ],
    ids=["missing-bucket", "missing-prefix", "missing-project"],
)
def test_index_raises_without_article_blocklist_settings(collaborators, overrides):
    """Verify the command refuses to index without an article blocklist to filter with."""
    with pytest.raises(ValueError, match="Article blocklist GCS values must be set"):
        _index(**overrides)

    collaborators["load_article_blocklist"].assert_not_called()
    collaborators["indexer"].assert_not_called()


def test_index_uploads_the_blocked_titles_after_indexing(collaborators, mocker):
    """Verify the titles the run blocked are uploaded next to the article blocklist."""
    order = mocker.Mock()
    order.attach_mock(collaborators["indexer"].return_value.index_from_export, "index")
    order.attach_mock(collaborators["upload_blocked_titles"], "upload")

    _index(language="fr")

    blocked_titles = collaborators["indexer"].return_value.blocked_titles
    assert [c[0] for c in order.mock_calls] == ["index", "upload"]
    collaborators["upload_blocked_titles"].assert_called_once_with(
        blocked_titles,
        "blocklist-bucket",
        "article_blocklist/blocked_titles",
        "blocklist-project",
        "fr",
    )


def test_index_uploads_the_blocked_titles_to_the_requested_destination(collaborators):
    """Verify a destination option overrides the default folder for the blocked titles."""
    _index(blocked_titles_destination="offline_uploader/blocklists")

    collaborators["upload_blocked_titles"].assert_called_once_with(
        collaborators["indexer"].return_value.blocked_titles,
        "blocklist-bucket",
        "offline_uploader/blocklists",
        "blocklist-project",
        "en",
    )


def test_index_does_not_fail_when_the_blocked_titles_upload_fails(
    collaborators, caplog, filter_caplog
):
    """Verify a failed upload is logged rather than failing a run whose index is already live."""
    collaborators["upload_blocked_titles"].side_effect = Exception("forbidden")
    caplog.set_level(logging.INFO)

    _index()

    collaborators["indexer"].return_value.index_from_export.assert_called_once()
    records = filter_caplog(caplog.records, MODULE)
    failures = [r for r in records if r.message == "Failed to upload blocked titles"]
    assert len(failures) == 1
    assert failures[0].levelno == logging.ERROR
    assert failures[0].destination == "article_blocklist/blocked_titles"
    assert not [r for r in records if r.message == "Uploaded blocked titles"]


@pytest.mark.parametrize(
    "prefix",
    ["article_blocklist", "article_blocklist/", "/article_blocklist/"],
    ids=["no-slashes", "trailing-slash", "leading-and-trailing-slashes"],
)
def test_index_default_blocked_titles_destination_ignores_prefix_slashes(collaborators, prefix):
    """Verify the default destination has no empty path segments however the prefix is slashed."""
    _index(article_blocklist_prefix=prefix)

    destination = collaborators["upload_blocked_titles"].call_args.args[2]
    assert destination == "article_blocklist/blocked_titles"


def test_index_blocklist_only_uploads_titles_without_indexing(collaborators):
    """Verify `blocklist-only` scans the export for blocked titles and never indexes."""
    indexer = collaborators["indexer"].return_value

    _index(mode=RunMode.BLOCKLIST_ONLY)

    indexer.collect_blocked_titles.assert_called_once_with(100)
    indexer.index_from_export.assert_not_called()
    collaborators["upload_blocked_titles"].assert_called_once_with(
        indexer.blocked_titles,
        "blocklist-bucket",
        "article_blocklist/blocked_titles",
        "blocklist-project",
        "en",
    )


def test_index_index_only_indexes_without_uploading_titles(collaborators):
    """Verify `index-only` builds the index and skips the blocked titles upload."""
    indexer = collaborators["indexer"].return_value

    _index(mode=RunMode.INDEX_ONLY)

    indexer.index_from_export.assert_called_once_with(100, "enwiki-{version}")
    indexer.collect_blocked_titles.assert_not_called()
    collaborators["upload_blocked_titles"].assert_not_called()


def test_index_both_indexes_and_uploads_titles(collaborators):
    """Verify `both` builds the index from the same scan it uploads the titles of."""
    indexer = collaborators["indexer"].return_value

    _index(mode=RunMode.BOTH)

    indexer.index_from_export.assert_called_once_with(100, "enwiki-{version}")
    indexer.collect_blocked_titles.assert_not_called()
    collaborators["upload_blocked_titles"].assert_called_once()


def test_index_blocklist_only_fails_when_the_upload_fails(collaborators):
    """Verify `blocklist-only` fails on an upload error, since uploading is all it does."""
    collaborators["upload_blocked_titles"].side_effect = Exception("forbidden")

    with pytest.raises(Exception, match="forbidden"):
        _index(mode=RunMode.BLOCKLIST_ONLY)


def test_index_skips_the_upload_when_indexing_fails(collaborators):
    """Verify a failed run doesn't publish a partial list of blocked titles."""
    collaborators["indexer"].return_value.index_from_export.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        _index()

    collaborators["upload_blocked_titles"].assert_not_called()


def test_index_passes_the_follower_sync_settings_to_the_indexer(collaborators):
    """Verify the CCR follower wait settings reach the Indexer."""
    _index(follower_sync_timeout=600, follower_sync_poll_interval=5, follower_discovery_period=30)

    kwargs = collaborators["indexer"].call_args.kwargs
    assert kwargs == {
        "follower_sync_timeout": 600,
        "follower_sync_poll_interval": 5,
        "follower_discovery_period": 30,
    }


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
