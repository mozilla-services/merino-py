# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for __init__.py module."""

from typing import Any

from merino.jobs.amo_rs_uploader import upload

# The number of mock addons to set up.
TEST_ADDON_COUNT = 3

# The number of key-value pairs of static and dynamic data to set up per addon
# not including name/title.
TEST_DATA_COUNT = 3

# The number of keywords to set up per addon.
TEST_KEYWORD_COUNT = 3


def mock_addons_data(
    mocker,
    mock_backend,
    addon_count: int = TEST_ADDON_COUNT,
    data_count: int = TEST_DATA_COUNT,
    keyword_count: int = TEST_KEYWORD_COUNT,
) -> None:
    """Set up mock dynamic and static addons data and keywords."""
    # dynamic data
    type(mock_backend).dynamic_data = mocker.PropertyMock(
        return_value={
            f"addon-{a}": {
                f"dynamic-key-{a}-{p}": f"dynamic-value-{a}-{p}" for p in range(data_count)
            }
            for a in range(addon_count)
        }
    )

    # static data
    mocker.patch(
        "merino.jobs.amo_rs_uploader.ADDON_DATA",
        new={
            f"addon-{a}": {
                f"static-key-{a}-{p}": f"static-value-{a}-{p}" for p in range(data_count)
            }
            | {"name": f"name-{a}"}
            for a in range(addon_count)
        },
    )

    # keywords
    mocker.patch(
        "merino.jobs.amo_rs_uploader.ADDON_KEYWORDS",
        new={
            f"addon-{a}": [f"kw-{a}-{k}" for k in range(keyword_count)] for a in range(addon_count)
        },
    )


def expected_add_suggestion_calls(
    mocker,
    addon_count: int = TEST_ADDON_COUNT,
    data_count: int = TEST_DATA_COUNT,
    keyword_count: int = TEST_KEYWORD_COUNT,
):
    """Return a list of expected `add_suggestion()` calls."""
    calls = []
    for a in range(addon_count):
        call: dict[str, Any] = {"title": f"name-{a}"}
        for p in range(data_count):
            call[f"static-key-{a}-{p}"] = f"static-value-{a}-{p}"
            call[f"dynamic-key-{a}-{p}"] = f"dynamic-value-{a}-{p}"
        call["keywords"] = [f"kw-{a}-{k}" for k in range(keyword_count)]
        calls.append(mocker.call(call))
    return calls


def do_upload_test(
    mocker,
    keep_existing_records: bool = True,
    score: float = 0.99,
) -> None:
    """Perform an upload test."""
    # Mock `DynamicAmoBackend`.
    mock_backend_ctor = mocker.patch("merino.jobs.amo_rs_uploader.DynamicAmoBackend")
    mock_backend = mock_backend_ctor.return_value
    type(mock_backend).fetch_and_cache_addons_info = mocker.AsyncMock()

    # Mock the addons data.
    mock_addons_data(mocker, mock_backend)

    # Mock the chunked uploader.
    mock_chunked_uploader_ctor = mocker.patch(
        "merino.jobs.amo_rs_uploader.ChunkedRemoteSettingsSuggestionUploader"
    )
    mock_chunked_uploader = mock_chunked_uploader_ctor.return_value.__enter__.return_value

    # Do the upload.
    common_kwargs: dict[str, Any] = {
        "auth": "auth",
        "bucket": "bucket",
        "chunk_size": 99,
        "collection": "collection",
        "dry_run": False,
        "record_type": "record_type",
        "server": "server",
    }
    upload(
        **common_kwargs,
        keep_existing_records=keep_existing_records,
        score=score,
    )

    # Check calls.
    mock_backend_ctor.assert_called_once()
    mock_backend.fetch_and_cache_addons_info.assert_called_once()

    mock_chunked_uploader_ctor.assert_called_once_with(
        **common_kwargs,
        suggestion_score_fallback=score,
        total_data_count=TEST_ADDON_COUNT,
    )

    if not keep_existing_records:
        mock_chunked_uploader.delete_records.assert_called_once()
    else:
        mock_chunked_uploader.delete_records.assert_not_called()

    mock_chunked_uploader.add_suggestion.assert_has_calls(expected_add_suggestion_calls(mocker))


def test_upload_without_deleting(mocker):
    """Tests `upload(keep_existing_records=True)`"""
    do_upload_test(mocker, keep_existing_records=True)


def test_delete_and_upload(mocker):
    """Tests `upload(keep_existing_records=True)`"""
    do_upload_test(mocker, keep_existing_records=False)


def test_upload_with_score(mocker):
    """Tests `upload(score=float)`"""
    do_upload_test(mocker, score=0.12)
