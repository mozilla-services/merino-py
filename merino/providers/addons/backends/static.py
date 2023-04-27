"""Static Addon Endpoint"""
from merino.providers.addons.addons_data import ADDON_DATA, SupportedAddons
from merino.providers.addons.backends.protocol import Addon

STATIC_RATING_AND_ICONS = {
    SupportedAddons.VIDEO_DOWNLOADER: {
        "rating": "4.284",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/3/3006-64.png",
    },
    SupportedAddons.LANGAUGE_TOOL: {
        "rating": "4.7452",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/708/708770-64.png",
    },
    SupportedAddons.PRIVATE_RELAY: {
        "rating": "4.117",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/2633/2633704-64.png",
    },
    SupportedAddons.SEARCH_BY_IMAGE: {
        "rating": "4.6515",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/824/824288-64.png",
    },
    SupportedAddons.DARKREADER: {
        "rating": "4.5586",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/855/855413-64.png",
    },
    SupportedAddons.PRIVACY_BADGER: {
        "rating": "4.8009",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/506/506646-64.png",
    },
    SupportedAddons.UBLOCK_ORIGIN: {
        "rating": "4.781",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/607/607454-64.png",
    },
    SupportedAddons.READ_ALOUD: {
        "rating": "3.9603",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/952/952959-64.png",
    },
}


class StaticAddonsBackend:
    """Static Addons Backend. This backend is mainly useful for
    tests and potentially a fallback if the API is broken.
    """

    async def initialize_addons(self) -> None:
        """Initialize Addons. Pass for static Addons."""
        pass

    async def get_addon(self, addon_key: SupportedAddons) -> Addon:
        """Get an Addon based on the addon_key"""
        static_info: dict[str, str] = ADDON_DATA[addon_key]
        icon_and_rating: dict[str, str] = STATIC_RATING_AND_ICONS[addon_key]

        return Addon(
            name=static_info["name"],
            description=static_info["description"],
            url=static_info["url"],
            icon=icon_and_rating["icon"],
            rating=icon_and_rating["rating"],
        )
