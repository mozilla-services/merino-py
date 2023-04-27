"""Static Addon Endpoint"""
from merino.providers.addons.addons_data import ADDON_DATA
from merino.providers.addons.backends.protocol import Addon

STATIC_RATING_AND_ICONS = {
    "video-downloadhelper": {
        "rating": "4.284",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/3/3006-64.png",
    },
    "languagetool": {
        "rating": "4.7452",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/708/708770-64.png",
    },
    "private-relay": {
        "rating": "4.117",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/2633/2633704-64.png",
    },
    "search_by_image": {
        "rating": "4.6515",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/824/824288-64.png",
    },
    "darkreader": {
        "rating": "4.5586",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/855/855413-64.png",
    },
    "privacy-badger17": {
        "rating": "4.8009",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/506/506646-64.png",
    },
    "ublock-origin": {
        "rating": "4.781",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/607/607454-64.png",
    },
    "read-aloud": {
        "rating": "3.9603",
        "icon": "https://addons.mozilla.org/user-media/addon_icons/952/952959-64.png",
    },
}


class StaticAddonsBackend:
    """Static Addons Backend. This backend is mainly useful for
    tests and potentially a fallback if the API is broken.
    """

    async def initialize_addons(self):
        """Initialize Addons. Pass for static Addons because we don't need to load it from anywhere."""
        pass

    async def get_addon(self, addon_key: str) -> Addon:
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
