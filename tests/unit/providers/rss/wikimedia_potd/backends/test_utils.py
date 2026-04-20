# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for Wikimedia POTD backend utility functions."""

import pytest
from feedparser import FeedParserDict

from merino.providers.rss.wikimedia_potd.backends.utils import extract_potd

VALID_FIELDS: dict[str, str] = {
    "title": "Test Title",
    "description": (
        "<img src='https://upload.wikimedia.org/thumb/a/b/file/100px-file.jpg' />"
        "<div class='description'>A photo</div>"
    ),
    "published": "Mon, 13 Apr 2026 00:00:00 GMT",
}


def _make_entry(**fields: str) -> FeedParserDict:
    entry = FeedParserDict()
    for k, v in fields.items():
        entry[k] = v
    return entry


def _make_feed(entries: list[FeedParserDict]) -> FeedParserDict:
    feed = FeedParserDict()
    feed["entries"] = entries
    return feed


@pytest.fixture(name="valid_entry")
def fixture_valid_entry() -> FeedParserDict:
    """Return a FeedParserDict entry with all required fields."""
    return _make_entry(**VALID_FIELDS)


def test_extract_potd_returns_none_for_empty_entries() -> None:
    """Returns None when the feed has no entries."""
    assert extract_potd(_make_feed([])) is None


def test_extract_potd_returns_entry_for_single_valid_entry(
    valid_entry: FeedParserDict,
) -> None:
    """Returns the entry when feed has one valid entry."""
    result = extract_potd(_make_feed([valid_entry]))
    assert result is valid_entry


def test_extract_potd_returns_last_entry_from_multiple(
    valid_entry: FeedParserDict,
) -> None:
    """Returns the last entry when feed has multiple valid entries."""
    older_entry = _make_entry(**VALID_FIELDS)
    feed = _make_feed([older_entry, valid_entry])
    assert extract_potd(feed) is valid_entry


def test_extract_potd_returns_none_when_a_required_field_missing() -> None:
    """Returns None when a required field is absent from the entry."""
    fields = VALID_FIELDS
    # remove the "published" key.
    fields.pop("published")
    feed = _make_feed([_make_entry(**fields)])
    assert extract_potd(feed) is None
