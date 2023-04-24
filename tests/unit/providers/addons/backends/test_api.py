"""Unit tests for the Addon API provider backend"""
import pytest

from merino.providers.addons.addons_data import STATIC_DATA
from merino.providers.addons.backends.api import (
    AddonAPIBackend,
    AddonAPIBackendException,
)
from merino.providers.addons.backends.protocol import Addon


@pytest.fixture(name="api_backend")
def fixture_api_backend() -> AddonAPIBackend:
    """Create a AddonAPIBackend object for test."""
    return AddonAPIBackend(api_url="https://addons.mozilla.org/api/v5/addons/addon")


@pytest.mark.asyncio
async def test_get_addons_request_succeed(requests_mock, api_backend: AddonAPIBackend):
    """Test that we can get the Addons details via the Addon API."""
    resp_video = {
        "icon_url": "https://this.is.image",
        "ratings": {
            "average": 4.123,
        },
    }
    resp_language = {
        "icon_url": "https://this.is.image",
        "ratings": {
            "average": 4.123,
        },
    }
    requests_mock.get(
        "https://addons.mozilla.org/api/v5/addons/addon/video-downloadhelper",
        json=resp_video,
    )
    requests_mock.get(
        "https://addons.mozilla.org/api/v5/addons/addon/languagetool",
        json=resp_language,
    )

    addons = await api_backend.get_addons(["video-downloadhelper", "languagetool"])

    assert len(addons) == 2
    video_downloader = STATIC_DATA["video-downloadhelper"]
    languagetool = STATIC_DATA["languagetool"]
    assert [
        Addon(
            name=video_downloader["name"],
            description=video_downloader["description"],
            url=video_downloader["url"],
            icon="https://this.is.image",
            rating=4.123,
        ),
        Addon(
            name=languagetool["name"],
            description=languagetool["description"],
            url=languagetool["url"],
            icon="https://this.is.image",
            rating=4.123,
        ),
    ] == addons


@pytest.mark.asyncio
async def test_get_addons_request_failed(requests_mock, api_backend: AddonAPIBackend):
    """Test that an error is raised if request to Addons API fails."""
    resp_video = {
        "icon_url": "https://this.is.image",
        "ratings": {
            "average": 4.123,
        },
    }
    requests_mock.get(
        "https://addons.mozilla.org/api/v5/addons/addon/video-downloadhelper",
        json=resp_video,
    )
    requests_mock.get(
        "https://addons.mozilla.org/api/v5/addons/addon/languagetool",
        text="Not Found",
        status_code=404,
    )
    with pytest.raises(AddonAPIBackendException) as ex:
        await api_backend.get_addons(["video-downloadhelper", "languagetool"])

    assert str(ex.value) == "Addons API could not find key: languagetool"


@pytest.mark.asyncio
async def test_get_addons_bad_addon_key(api_backend: AddonAPIBackend):
    """Test that a bad key raises and error."""
    with pytest.raises(KeyError) as ex:
        await api_backend.get_addons(["bad_key"])

    assert str(ex.value) == "'bad_key'"
