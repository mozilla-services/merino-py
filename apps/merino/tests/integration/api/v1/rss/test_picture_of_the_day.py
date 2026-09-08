# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the /api/v1/rss/picture-of-the-day endpoint."""

import freezegun
from fastapi.testclient import TestClient

from merino.providers.rss.wikimedia_potd.backends.protocol import PictureOfTheDay
from merino.providers.rss.wikimedia_potd.provider import WikimediaPictureOfTheDayProvider

POTD_URL = "/api/v1/rss/picture-of-the-day"


@freezegun.freeze_time("2026-06-07")
def test_picture_of_the_day_returns_the_previous_day_alongside_today(
    client: TestClient,
    potd_provider: WikimediaPictureOfTheDayProvider,
    potd: PictureOfTheDay,
) -> None:
    """Serves today's picture with the previous day's picture nested under `previous`."""
    potd_provider.potd = potd

    response = client.get(POTD_URL)

    assert response.status_code == 200
    assert response.json() == {
        "title": "Wikimedia Commons Picture of the Day for June 7",
        "published_date": "2026-06-07",
        "thumbnail_image_url": "https://test-cdn/wikimedia_potd/2026-06-07/thumbnail.png",
        "high_res_image_url": "https://test-cdn/wikimedia_potd/2026-06-07/hi_res.webp",
        "description": "Today's description.",
        "author": "Test Artist",
        "file_page": "https://commons.wikimedia.org/wiki/File:Today.jpg",
        "license_label": "CC BY-SA 4.0",
        "license_link": "https://creativecommons.org/licenses/by-sa/4.0",
        "previous": {
            "title": "Wikimedia Commons Picture of the Day for June 6",
            "published_date": "2026-06-06",
            "thumbnail_image_url": "https://test-cdn/wikimedia_potd/2026-06-06/thumbnail.png",
            "high_res_image_url": "https://test-cdn/wikimedia_potd/2026-06-06/hi_res.webp",
            "description": "Yesterday's description.",
            "author": "Previous Artist",
            "file_page": "https://commons.wikimedia.org/wiki/File:Yesterday.jpg",
            "license_label": "CC BY-SA 4.0",
            "license_link": "https://creativecommons.org/licenses/by-sa/4.0",
        },
    }


@freezegun.freeze_time("2026-06-07")
def test_picture_of_the_day_omits_the_localization_map_at_both_levels(
    client: TestClient,
    potd_provider: WikimediaPictureOfTheDayProvider,
    potd: PictureOfTheDay,
) -> None:
    """Keeps the server-side localization map out of the response, nested one included."""
    potd_provider.potd = potd

    body = client.get(POTD_URL).json()

    assert "localized_descriptions" not in body
    assert "localized_descriptions" not in body["previous"]


@freezegun.freeze_time("2026-06-07")
def test_picture_of_the_day_localizes_both_descriptions_for_accept_language(
    client: TestClient,
    potd_provider: WikimediaPictureOfTheDayProvider,
    potd: PictureOfTheDay,
) -> None:
    """Swaps in the client's language for today's description and the previous day's."""
    potd_provider.potd = potd

    body = client.get(POTD_URL, headers={"Accept-Language": "de-DE,de;q=0.9"}).json()

    assert body["description"] == "Heutiger deutscher Text"
    assert body["previous"]["description"] == "Gestriger deutscher Text"


@freezegun.freeze_time("2026-06-07")
def test_picture_of_the_day_keeps_default_descriptions_for_an_unmatched_language(
    client: TestClient,
    potd_provider: WikimediaPictureOfTheDayProvider,
    potd: PictureOfTheDay,
) -> None:
    """Serves the default descriptions when the client's language has no localization."""
    potd_provider.potd = potd

    body = client.get(POTD_URL, headers={"Accept-Language": "fr-FR"}).json()

    assert body["description"] == "Today's description."
    assert body["previous"]["description"] == "Yesterday's description."


@freezegun.freeze_time("2026-06-07")
def test_picture_of_the_day_returns_previous_as_null_when_there_is_no_previous_day(
    client: TestClient,
    potd_provider: WikimediaPictureOfTheDayProvider,
    potd: PictureOfTheDay,
) -> None:
    """Always sends the `previous` key, as null, so clients see one response shape."""
    potd_provider.potd = potd.model_copy(update={"previous": None})

    body = client.get(POTD_URL).json()

    assert body["previous"] is None


def test_picture_of_the_day_returns_null_when_nothing_is_cached(
    client: TestClient,
    potd_provider: WikimediaPictureOfTheDayProvider,
    backend_mock,
) -> None:
    """Serves a null body when no picture has ever been cached, exclusions notwithstanding."""
    backend_mock.fetch_potd_from_gcs_bucket.return_value = None

    response = client.get(POTD_URL)

    assert response.status_code == 200
    assert response.json() is None
