"""Test StaticAddonsBackend."""
import pytest

from merino.providers.addons.addons_data import STATIC_DATA
from merino.providers.addons.backends.protocol import Addon
from merino.providers.addons.backends.static import (
    STATIC_RATING_AND_ICONS,
    StaticAddonsBackend,
)


@pytest.fixture(name="static_backend")
def fixture_static_backend() -> StaticAddonsBackend:
    """Create a RemoteSettingsBackend object for test."""
    return StaticAddonsBackend()


@pytest.mark.asyncio
async def test_get_addons_success(static_backend: StaticAddonsBackend):
    """Test that we can get Addon information statically."""
    addons = await static_backend.get_addons(["video-downloadhelper", "languagetool"])
    assert len(addons) == 2
    video_downloader = STATIC_DATA["video-downloadhelper"]
    languagetool = STATIC_DATA["languagetool"]
    vd_icon_rating = STATIC_RATING_AND_ICONS["video-downloadhelper"]
    lt_icon_rating = STATIC_RATING_AND_ICONS["languagetool"]
    assert [
        Addon(
            name=video_downloader["name"],
            description=video_downloader["description"],
            url=video_downloader["url"],
            icon=vd_icon_rating["icon"],
            rating=vd_icon_rating["rating"],
        ),
        Addon(
            name=languagetool["name"],
            description=languagetool["description"],
            url=languagetool["url"],
            icon=lt_icon_rating["icon"],
            rating=lt_icon_rating["rating"],
        ),
    ] == addons


@pytest.mark.asyncio
async def test_get_addons_bad_addon_key(static_backend: StaticAddonsBackend):
    """Test that an error is raised when passed a bad addon key."""
    with pytest.raises(KeyError) as ex:
        await static_backend.get_addons(["bad_key"])

    assert str(ex.value) == "'bad_key'"
