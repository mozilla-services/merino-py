"""Test StaticAddonsBackend."""
import pytest

from merino.providers.addons.addons_data import ADDON_DATA, SupportedAddons
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
    addons = await static_backend.get_addon(SupportedAddons.VIDEO_DOWNLOADER)
    video_downloader = ADDON_DATA[SupportedAddons.VIDEO_DOWNLOADER]
    vd_icon_rating = STATIC_RATING_AND_ICONS[SupportedAddons.VIDEO_DOWNLOADER]
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
