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
    build_potd_image_path,
)
from merino.utils.gcs.models import Image

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
        "artist": {"text": "Test Artist", "html": "<bdi>Test Artist</bdi>"},
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


@freezegun.freeze_time("2026-04-13")
def test_parse_potd_returns_empty_description_when_no_description(featured: dict) -> None:
    """Returns a PictureOfTheDay with empty description when no description is present."""
    featured["image"].pop("description")

    result = parse_potd(featured)

    assert result is not None
    assert result.description == ""
    assert isinstance(result.thumbnail_image_url, HttpUrl)


@freezegun.freeze_time("2026-04-13")
def test_parse_potd_maps_metadata_fields(featured: dict) -> None:
    """Maps the Featured API metadata: description html, artist, attribution, and license."""
    result = parse_potd(featured)

    assert result.description_html == "<p>Test description.</p>"
    assert result.artist_name == "Test Artist"
    assert str(result.attribution_url) == FILE_PAGE_URL
    assert result.license_name == "CC BY-SA 4.0"
    assert str(result.license_url) == LICENSE_URL


@freezegun.freeze_time("2026-04-13")
def test_parse_potd_defaults_missing_metadata(featured: dict) -> None:
    """Falls back to empty/None defaults when the optional metadata fields are absent."""
    image = featured["image"]
    for key in ("description", "artist", "license", "file_page"):
        image.pop(key, None)

    result = parse_potd(featured)

    assert result.description == ""
    assert result.description_html == ""
    assert result.artist_name == ""
    assert result.attribution_url is None
    assert result.license_name == ""
    assert result.license_url is None


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
def test_build_potd_path() -> None:
    """Test build_potd_path returns correct path for thumbnail and hi-res urls."""
    image = Image(content=b"255", content_type="Image/jpeg")

    expected_thumbnail_path = "rss/wikimedia_potd/POTD_2026-06-07_thumbnail.jpeg"
    expected_hires_path = "rss/wikimedia_potd/POTD_2026-06-07_hi_res.jpeg"

    actual_thumbnail_path = build_potd_image_path(image=image, is_thumbnail=True)
    actual_hires_path = build_potd_image_path(image=image, is_thumbnail=False)

    assert actual_thumbnail_path == expected_thumbnail_path
    assert actual_hires_path == expected_hires_path
