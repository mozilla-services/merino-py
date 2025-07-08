# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for __init__.py module."""

from typing import Any
from unittest.mock import call

from merino.jobs.wikipedia_offline_uploader import upload

DATA_COUNT = 2


def mock_get_wiki_suggestions_return_value() -> dict[str, list]:
    """Mock return value for get_wiki_suggestions."""
    return {
        "en": [{"title": "en-wiki-1"}, {"title": "en-wiki-2"}],
        "fr": [{"title": "fr-wiki-1"}, {"title": "fr-wiki-2"}],
    }


def do_upload_test(
    mocker,
    keep_existing_records: bool = True,
    score: float = 0.99,
) -> None:
    """Perform an upload test."""
    # Mock the chunked uploader.
    mock_chunked_uploader_ctor = mocker.patch(
        "merino.jobs.wikipedia_offline_uploader.WikipediaSuggestionChunkRemoteSettingsUploader"
    )
    mock_chunked_uploader = mock_chunked_uploader_ctor.return_value.__enter__.return_value

    mock_return_value = mock_get_wiki_suggestions_return_value()
    mock_get_wiki_suggestions = mocker.patch(
        "merino.jobs.wikipedia_offline_uploader.get_wiki_suggestions",
        new_callable=mocker.AsyncMock,
        return_value=mock_return_value,
    )

    # Do the upload.
    common_kwargs: dict[str, Any] = {
        "auth": "auth",
        "bucket": "bucket",
        "chunk_size": 99,
        "collection": "collection",
        "dry_run": False,
        "server": "server",
        "languages": "en,fr",
        "relevance_type": "frequency",
    }
    upload(
        **common_kwargs,
        keep_existing_records=keep_existing_records,
        score=score,
    )

    # Check calls.
    mock_get_wiki_suggestions.assert_called_once()
    mock_chunked_uploader_ctor.assert_called()

    if not keep_existing_records:
        # Twice for EN and FR
        assert mock_chunked_uploader.delete_records.call_count == 2
    else:
        mock_chunked_uploader.delete_records.assert_not_called()

    mock_chunked_uploader.add_suggestion.assert_has_calls(
        [
            call({"title": "en-wiki-1"}),
            call({"title": "en-wiki-2"}),
            call({"title": "fr-wiki-1"}),
            call({"title": "fr-wiki-2"}),
        ]
    )


def test_upload_without_deleting(mocker):
    """Tests `upload(keep_existing_records=True)`"""
    do_upload_test(mocker, keep_existing_records=True)


def test_delete_and_upload(mocker):
    """Tests `upload(keep_existing_records=True)`"""
    do_upload_test(mocker, keep_existing_records=False)
