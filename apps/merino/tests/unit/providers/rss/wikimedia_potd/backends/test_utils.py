# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for Wikimedia POTD backend utility functions."""

import pytest
import freezegun
from pydantic import HttpUrl

from merino.providers.rss.wikimedia_potd.backends.protocol import (
    PictureOfTheDay,
    PictureOfTheDayBase,
    WikimediaPotdError,
)
from merino.providers.rss.wikimedia_potd.backends.utils import (
    as_previous_entry,
    is_valid_potd_image_url,
    parse_potd,
    extract_image_description_with_lang_code,
    parse_discovered_languages,
    build_potd_bucket_directory_path,
    previous_day,
)

THUMBNAIL_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Test.jpg/320px-Test.jpg"
HIGH_RES_URL = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Test.jpg"
FILE_PAGE_URL = "https://commons.wikimedia.org/wiki/File:Test.jpg"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0"


def _make_featured(**image_overrides: object) -> dict:
    """Build a minimal Wikimedia Featured API response dict with an image object."""
    image: dict = {
        "title": "File:Test.jpg",
        "thumbnail": {"source": THUMBNAIL_URL},
        "image": {"source": HIGH_RES_URL},
        "description": {"text": "Test description.", "html": "<p>Test description.</p>"},
        "artist": {
            "text": "Test Artist Really long name which is more than fifty characters",
            "html": "<bdi>Test Artist</bdi>",
        },
        "license": {"type": "CC BY-SA 4.0", "url": LICENSE_URL},
        "file_page": FILE_PAGE_URL,
    }
    image.update(image_overrides)
    return {"image": image}


@pytest.fixture(name="featured")
def fixture_featured() -> dict:
    """Return a Featured API response dict with all fields required by parse_potd."""
    return _make_featured()


@freezegun.freeze_time("2026-04-13")
def test_parse_potd_returns_picture_of_the_day(featured: dict) -> None:
    """Returns a PictureOfTheDay with correct fields when all data is present."""
    result = parse_potd(featured)

    assert isinstance(result, PictureOfTheDay)
    assert result.title == "Wikimedia Commons Picture of the Day for April 13"
    assert result.published_date == "2026-04-13"
    assert result.description == "Test description."
    assert str(result.thumbnail_image_url) == THUMBNAIL_URL
    assert str(result.high_res_image_url) == HIGH_RES_URL
    assert result.author == result.author[0:50] + "..."
    assert str(result.file_page) == FILE_PAGE_URL
    assert result.license_label == "CC BY-SA 4.0"
    assert str(result.license_link) == LICENSE_URL


@freezegun.freeze_time("2026-04-13")
def test_parse_potd_returns_empty_description_when_no_description(featured: dict) -> None:
    """Returns a PictureOfTheDay with empty description when no description is present."""
    featured["image"].pop("description")

    result = parse_potd(featured)

    assert result is not None
    assert result.description == ""
    assert isinstance(result.thumbnail_image_url, HttpUrl)


@freezegun.freeze_time("2026-04-13")
def test_parse_potd_defaults_missing_metadata(featured: dict) -> None:
    """Falls back to empty/None defaults when the optional metadata fields are absent."""
    image = featured["image"]
    for key in ("description", "artist", "license", "file_page"):
        image.pop(key, None)

    result = parse_potd(featured)

    assert result.description == ""
    assert result.author == ""
    assert result.file_page is None
    assert result.license_label == ""
    assert result.license_link is None


@freezegun.freeze_time("2026-04-13")
def test_parse_potd_raises_when_image_missing() -> None:
    """Raises WikimediaPotdError when the response has no image object."""
    with pytest.raises(WikimediaPotdError):
        parse_potd({"news": []})


@freezegun.freeze_time("2026-04-13")
def test_parse_potd_raises_when_source_url_missing(featured: dict) -> None:
    """Raises WikimediaPotdError when a thumbnail or full-res source url is absent."""
    featured["image"]["thumbnail"] = {}

    with pytest.raises(WikimediaPotdError):
        parse_potd(featured)


@freezegun.freeze_time("2026-04-13")
def test_parse_potd_uses_full_res_image_source_directly(featured: dict) -> None:
    """Reads high_res_image_url straight from image.source without deriving it."""
    featured["image"]["image"]["source"] = (
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/Photo.jpg"
    )

    result = parse_potd(featured)

    assert result is not None
    assert str(result.thumbnail_image_url) == THUMBNAIL_URL
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
        (HttpUrl("http://www.test-image.com/image.JPG"), True),
        (HttpUrl("http://www.test-image.com/image.text"), False),
        (HttpUrl("http://www.test-image.com/image"), False),
        (HttpUrl("http://www.test-image.com/"), False),
        (HttpUrl("http://www.test-image.com/image.jpg?width=960"), True),
        (HttpUrl("http://www.test-image.com/image.text?foo=image.jpg"), False),
        (HttpUrl("http://www.test-image.com/image.png#fragment"), True),
        (
            HttpUrl(
                "https://upload.wikimedia.org/wikipedia/commons/thumb/2/27/"
                "Rom_%28IT%29%2C_Br%C3%BCcke_%E2%80%9EPonte_Vittorio_Emanuele_II%E2%80%9C"
                "_--_2024_--_0732.jpg/960px-Rom_%28IT%29%2C_Br%C3%BCcke_"
                "%E2%80%9EPonte_Vittorio_Emanuele_II%E2%80%9C_--_2024_--_0732.jpg"
                "?utm_source=commons.wikimedia.org&utm_campaign=imageinfo"
                "&utm_content=thumbnail"
            ),
            True,
        ),
    ],
    ids=[
        "jpeg",
        "jpg",
        "png",
        "webp",
        "uppercase_extension",
        "text",
        "no_extension",
        "no_path",
        "query_string",
        "non_image_with_image_in_query",
        "fragment",
        "wikimedia_thumbnail_with_utm_params",
    ],
)
def test_is_valid_potd_image_url(url: HttpUrl, expected: bool) -> None:
    """Test is_valid_potd_image_url for each supported image extension."""
    assert is_valid_potd_image_url(url) == expected


@freezegun.freeze_time("2026-06-07")
def test_build_potd_bucket_directory_path() -> None:
    """Test build_potd_bucket_directory_path returns the dated gcs bucket directory path."""
    assert build_potd_bucket_directory_path() == "wikimedia_potd/2026-06-07/"


@freezegun.freeze_time("2026-06-07")
def test_build_potd_bucket_directory_path_uses_the_given_date() -> None:
    """Test that an explicit date is used instead of today, so past days can be addressed."""
    assert build_potd_bucket_directory_path("2026-06-06") == "wikimedia_potd/2026-06-06/"


@pytest.mark.parametrize(
    ["date_str", "expected"],
    [
        ("2026-06-07", "2026-06-06"),
        ("2026-06-01", "2026-05-31"),
        ("2026-01-01", "2025-12-31"),
        ("2028-03-01", "2028-02-29"),
    ],
    ids=["mid_month", "month_boundary", "year_boundary", "leap_day"],
)
def test_previous_day(date_str: str, expected: str) -> None:
    """Test previous_day returns the calendar day before the given date."""
    assert previous_day(date_str) == expected


def test_as_previous_entry_returns_none_when_there_is_no_manifest() -> None:
    """Returns None when yesterday has no manifest, so `previous` serializes as null."""
    assert as_previous_entry(None) is None

def test_as_previous_entry_drops_the_days_own_previous() -> None:
    """Drops the fetched day's `previous` so a published manifest is only one day deep."""
    two_days_ago = PictureOfTheDayBase(
        title="Wikimedia Commons Picture of the Day for June 5",
        published_date="2026-06-05",
        thumbnail_image_url=HttpUrl(THUMBNAIL_URL),
        high_res_image_url=HttpUrl(HIGH_RES_URL),
        description="Two days ago.",
    )
    yesterday = PictureOfTheDay(
        title="Wikimedia Commons Picture of the Day for June 6",
        published_date="2026-06-06",
        thumbnail_image_url=HttpUrl(THUMBNAIL_URL),
        high_res_image_url=HttpUrl(HIGH_RES_URL),
        description="Yesterday's description.",
        previous=two_days_ago,
    )

    entry = as_previous_entry(yesterday)

    assert entry is not None
    assert entry.published_date == "2026-06-06"
    # the chain stops here: the entry has no `previous` field at all
    assert "previous" not in entry.model_dump()


def test_extract_image_description_with_lang_code_returns_lang_and_text(featured: dict) -> None:
    """Returns the description language and text from a Featured API response."""
    featured["image"]["description"] = {"lang": "de", "text": "Deutscher Text"}

    assert extract_image_description_with_lang_code(featured) == ("de", "Deutscher Text")


@pytest.mark.parametrize(
    ["data"],
    [
        ({"image": {"description": {}}},),
        ({"image": {}},),
        ({},),
    ],
    ids=["empty-description", "no-description", "no-image"],
)
def test_extract_image_description_with_lang_code_defaults_to_empty(data: dict) -> None:
    """Returns empty strings when the description or image is absent."""
    assert extract_image_description_with_lang_code(data) == ("", "")


def test_parse_discovered_languages_extracts_codes() -> None:
    """Extracts language codes and skips the bare file-selector subpage."""
    commons_data = {
        "query": {
            "allpages": [
                {"title": "Template:Potd/2026-07-14"},
                {"title": "Template:Potd/2026-07-14 (de)"},
                {"title": "Template:Potd/2026-07-14 (es)"},
                {"title": "Template:Potd/2026-07-14 (zh-hans)"},
            ]
        }
    }

    assert parse_discovered_languages(commons_data) == {"de", "es", "zh-hans"}


def test_parse_discovered_languages_returns_empty_when_no_pages() -> None:
    """Returns an empty set when the Commons response has no allpages."""
    assert parse_discovered_languages({}) == set()
