"""Test StaticAddonsBackend."""
import pytest

from merino.providers.addons.addons_data import ADDON_DATA
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
async def test_get_addon_success(static_backend: StaticAddonsBackend):
    """Test that we can get Addon information statically."""
    addons = await static_backend.get_addon("video-downloadhelper")
    video_downloader = ADDON_DATA["video-downloadhelper"]
    vd_icon_rating = STATIC_RATING_AND_ICONS["video-downloadhelper"]
    assert (
        Addon(
            name=video_downloader["name"],
            description=video_downloader["description"],
            url=video_downloader["url"],
            icon=vd_icon_rating["icon"],
            rating=vd_icon_rating["rating"],
        )
        == addons
    )


@pytest.mark.asyncio
async def test_get_addon_bad_addon_key(static_backend: StaticAddonsBackend):
    """Test that an error is raised when passed a bad addon key."""
    with pytest.raises(KeyError) as ex:
        await static_backend.get_addon("bad_key")

    assert str(ex.value) == "'bad_key'"
