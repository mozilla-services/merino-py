# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for Wikimedia POTD backend utility functions."""

import pytest
import freezegun
from pydantic import HttpUrl

from merino.providers.rss.wikimedia_potd.backends.protocol import (
    PictureOfTheDay,
    WikimediaPotdError,
)
from merino.providers.rss.wikimedia_potd.backends.utils import (
    is_valid_potd_image_url,
    parse_potd,
    extract_image_description_with_lang_code,
    parse_discovered_languages,
    build_potd_bucket_directory_path,
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
        (HttpUrl("http://www.test-image.com/image.text"), False),
    ],
    ids=["jpeg", "jpg", "png", "webp", "text"],
)
def test_is_valid_potd_image_url(url: HttpUrl, expected: bool) -> None:
    """Test is_valid_potd_image_url for each supported image extension."""
    assert is_valid_potd_image_url(url) == expected


@freezegun.freeze_time("2026-06-07")
def test_build_potd_bucket_directory_path() -> None:
    """Test build_potd_bucket_directory_path returns the dated gcs bucket directory path."""
    assert build_potd_bucket_directory_path() == "wikimedia_potd/2026-06-07/"


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

    assert parse_discovered_languages(commons_data) == ["de", "es", "zh-hans"]


def test_parse_discovered_languages_returns_empty_when_no_pages() -> None:
    """Returns an empty list when the Commons response has no allpages."""
    assert parse_discovered_languages({}) == []
