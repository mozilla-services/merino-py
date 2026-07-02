# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for Wikimedia POTD backend utility functions."""

import pytest
import freezegun
from feedparser import FeedParserDict
from pydantic import HttpUrl

from merino.providers.rss.wikimedia_potd.backends.protocol import (
    PictureOfTheDay,
    WikimediaPotdError,
)
from merino.providers.rss.wikimedia_potd.backends.utils import (
    extract_potd,
    is_valid_potd_image_url,
    parse_potd,
    build_potd_path_and_name,
)
from merino.utils.gcs.models import Image

VALID_FIELDS: dict[str, str] = {
    "title": "Test Title",
    "description": (
        "<img src='https://upload.wikimedia.org/thumb/a/b/file/100px-file.jpg' />"
        "<div class='description'>A photo</div>"
    ),
    "published": "Mon, 13 Apr 2026 00:00:00 GMT",
}

THUMBNAIL_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Test.jpg/320px-Test.jpg"
HIGH_RES_URL = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Test.jpg"

DESCRIPTION_HTML = f'<img src="{THUMBNAIL_URL}" /><div class="description">Test description.</div>'


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


def test_extract_potd_raises_for_empty_entries() -> None:
    """Raises WikimediaPotdError when the feed has no entries."""
    with pytest.raises(WikimediaPotdError):
        extract_potd(_make_feed([]))


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


def test_extract_potd_raises_when_a_required_field_missing() -> None:
    """Raises WikimediaPotdError when a required field is absent from the entry."""
    fields = dict(VALID_FIELDS)
    # remove the "published" key.
    fields.pop("published")
    feed = _make_feed([_make_entry(**fields)])
    with pytest.raises(WikimediaPotdError):
        extract_potd(feed)


@pytest.fixture(name="potd_entry")
def fixture_potd_entry() -> FeedParserDict:
    """Return a FeedParserDict entry with all fields required by parse_potd."""
    return _make_entry(
        title="Test POTD",
        published="Mon, 13 Apr 2026 00:00:00 GMT",
        description=DESCRIPTION_HTML,
    )


@freezegun.freeze_time("2026-04-13")
def test_parse_potd_returns_picture_of_the_day(potd_entry: FeedParserDict) -> None:
    """Returns a PictureOfTheDay with correct fields when all data is present."""
    result = parse_potd(potd_entry)

    assert isinstance(result, PictureOfTheDay)
    assert result.title == "Test POTD"
    assert result.published_date == "2026-04-13"
    assert result.description == "Test description."
    assert str(result.thumbnail_image_url) == THUMBNAIL_URL
    assert str(result.high_res_image_url) == HIGH_RES_URL


@freezegun.freeze_time("2026-04-13")
def test_parse_potd_returns_empty_description_when_no_description_div(
    potd_entry: FeedParserDict,
) -> None:
    """Returns a PictureOfTheDay with empty description when no description div is present."""
    potd_entry["description"] = f'<img src="{THUMBNAIL_URL}" />'

    result = parse_potd(potd_entry)

    assert result is not None
    assert result.description == ""
    assert isinstance(result.thumbnail_image_url, HttpUrl)


def test_parse_potd_raises_when_the_published_date_is_not_today(
    potd_entry: FeedParserDict,
) -> None:
    """Raises WikimediaPotdError when the published date is not today."""
    # the potd_entry fixture object has the date set to 2026-04-13.
    with pytest.raises(WikimediaPotdError):
        parse_potd(potd_entry)


@freezegun.freeze_time("2026-04-13")
def test_parse_potd_raises_when_no_img_tag(potd_entry: FeedParserDict) -> None:
    """Raises WikimediaPotdError when the description HTML contains no img element."""
    potd_entry["description"] = '<div class="description">No image here.</div>'

    with pytest.raises(WikimediaPotdError):
        parse_potd(potd_entry)


@freezegun.freeze_time("2026-04-13")
def test_parse_potd_raises_when_img_has_no_src(potd_entry: FeedParserDict) -> None:
    """Raises WikimediaPotdError when the img element is missing a src attribute."""
    potd_entry["description"] = '<img alt="missing src" />'

    with pytest.raises(WikimediaPotdError):
        parse_potd(potd_entry)


@freezegun.freeze_time("2026-04-13")
def test_parse_potd_derives_high_res_url_from_thumbnail(potd_entry: FeedParserDict) -> None:
    """Derives high_res_image_url by stripping /thumb and the trailing size segment from the thumbnail URL."""
    thumbnail = (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Photo.jpg/640px-Photo.jpg"
    )
    potd_entry["description"] = f'<img src="{thumbnail}" />'

    result = parse_potd(potd_entry)

    assert result is not None
    assert str(result.thumbnail_image_url) == thumbnail
    assert (
        str(result.high_res_image_url)
        == "https://upload.wikimedia.org/wikipedia/commons/a/ab/Photo.jpg"
    )


@pytest.mark.parametrize(
    ["url", "expected"],
    [
        (HttpUrl("http://www.test-image.com/image.jpeg"), True),
        (HttpUrl("http://www.test-image.com/image.jpg"), True),
        (HttpUrl("http://www.test-image.com/image.png"), True),
        (HttpUrl("http://www.test-image.com/image.webp"), True),
        (HttpUrl("http://www.test-image.com/image.text"), False),
    ],
    ids=["jpeg", "jpg", "png", "webp", "text"],
)
def test_is_valid_potd_image_url(url: HttpUrl, expected: bool) -> None:
    """Test is_valid_potd_image_url for each supported image extension."""
    assert is_valid_potd_image_url(url) == expected


@freezegun.freeze_time("2026-06-07")
def test_build_potd_path_and_name() -> None:
    """Test build_potd_path_and_name returns correct path for thumbnail and hi-res urls."""
    image = Image(content=b"255", content_type="Image/jpeg")

    expected_thumbnail_path = "rss/wikimedia_potd/POTD_2026-06-07_thumbnail.jpeg"
    expected_hires_path = "rss/wikimedia_potd/POTD_2026-06-07_hi_res.jpeg"

    actual_thumbnail_path = build_potd_path_and_name(image=image, is_thumbnail=True)
    actual_hires_path = build_potd_path_and_name(image=image, is_thumbnail=False)

    assert actual_thumbnail_path == expected_thumbnail_path
    assert actual_hires_path == expected_hires_path
