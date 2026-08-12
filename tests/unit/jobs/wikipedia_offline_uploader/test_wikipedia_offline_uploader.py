# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for __init__.py module."""

from typing import Any
from unittest.mock import call

from merino.jobs.wikipedia_offline_uploader import upload

SCORE = 0.99


def mock_get_wiki_suggestions_return_value() -> dict[str, list]:
    """Mock return value for get_wiki_suggestions."""
    return {
        "en": [
            {"title": "en-wiki-1", "score": SCORE},
            {"title": "en-wiki-2", "score": SCORE},
        ],
        "fr": [
            {"title": "fr-wiki-1", "score": SCORE},
            {"title": "fr-wiki-2", "score": SCORE},
        ],
    }


def do_upload_test(
    mocker,
    keep_existing_records: bool = True,
    score: float = SCORE,
) -> None:
    """Perform an upload test."""
    mock_rs_client_ctor = mocker.patch(
        "merino.jobs.wikipedia_offline_uploader.RemoteSettingsClient"
    )
    mock_rs_client = mock_rs_client_ctor.return_value
    mock_rs_client.dry_run = False
    mock_rs_client.get_records.return_value = []

    mock_return_value = mock_get_wiki_suggestions_return_value()
    mock_get_wiki_suggestions = mocker.patch(
        "merino.jobs.wikipedia_offline_uploader.get_wiki_suggestions",
        new_callable=mocker.AsyncMock,
        return_value=mock_return_value,
    )

    common_kwargs: dict[str, Any] = {
        "auth": "auth",
        "bucket": "bucket",
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

    mock_get_wiki_suggestions.assert_called_once()
    mock_rs_client_ctor.assert_called_once_with(
        auth="auth",
        bucket="bucket",
        collection="collection",
        server="server",
        dry_run=False,
    )

    if not keep_existing_records:
        # Twice for EN and FR
        assert mock_rs_client.get_records.call_count == 2
    else:
        mock_rs_client.get_records.assert_not_called()

    en_attachment = [
        {"title": "en-wiki-1", "score": score},
        {"title": "en-wiki-2", "score": score},
    ]
    fr_attachment = [
        {"title": "fr-wiki-1", "score": score},
        {"title": "fr-wiki-2", "score": score},
    ]
    mock_rs_client.upload.assert_has_calls(
        [
            call(
                record={
                    "id": "data-wikipedia-en",
                    "type": "wikipedia",
                    "filter_expression": "env.locale in ['en-CA', 'en-GB', 'en-US']",
                },
                attachment=en_attachment,
            ),
            call(
                record={
                    "id": "data-wikipedia-fr",
                    "type": "wikipedia",
                    "filter_expression": "env.locale in ['fr', 'fr-FR']",
                },
                attachment=fr_attachment,
            ),
        ]
    )
    assert mock_rs_client.upload.call_count == 2


def test_upload_without_deleting(mocker):
    """Tests `upload(keep_existing_records=True)`"""
    do_upload_test(mocker, keep_existing_records=True)


def test_delete_and_upload(mocker):
    """Tests `upload(keep_existing_records=False)`"""
    do_upload_test(mocker, keep_existing_records=False)


def test_delete_records_removes_matching_language(mocker):
    """Deletion should target existing wikipedia records for the language."""
    mock_rs_client_ctor = mocker.patch(
        "merino.jobs.wikipedia_offline_uploader.RemoteSettingsClient"
    )
    mock_rs_client = mock_rs_client_ctor.return_value
    mock_rs_client.dry_run = False
    mock_rs_client.get_records.return_value = [
        {"id": "data-wikipedia-en", "type": "wikipedia"},
        {"id": "data-wikipedia-en-0-999", "type": "wikipedia"},
        {"id": "data-wikipedia-fr", "type": "wikipedia"},
        {"id": "data-other-en", "type": "other"},
    ]

    mocker.patch(
        "merino.jobs.wikipedia_offline_uploader.get_wiki_suggestions",
        new_callable=mocker.AsyncMock,
        return_value={"en": [{"title": "en-wiki-1"}]},
    )

    upload(
        auth="auth",
        bucket="bucket",
        collection="collection",
        dry_run=False,
        server="server",
        languages="en",
        relevance_type="frequency",
        keep_existing_records=False,
        score=SCORE,
    )

    mock_rs_client.delete_record.assert_has_calls(
        [call("data-wikipedia-en"), call("data-wikipedia-en-0-999")]
    )
    assert mock_rs_client.delete_record.call_count == 2
