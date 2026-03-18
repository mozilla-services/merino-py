"""Custom favicon URLs for domains that block scrapers or have unreliable favicon detection"""

from typing import Any

# Mapping domain names without any suffix to their direct favicon URLs.
# Used for domains that block scrapers, have unreliable favicon detection,
# or only serve small favicon.ico files despite having larger icons available.
# All URLs below have been manually verified to return images >= 48px.
CUSTOM_FAVICONS: dict[str, str] = {
    # --- Original entries ---
    "axios": "https://static.axios.com/icons/favicon.svg",
    "espn": "https://a.espncdn.com/favicon.ico",
    "ign": "https://kraken.ignimgs.com/favicon.ico",
    "infobae": "https://www.infobae.com/pf/resources/favicon/favicon-32x32.png?d=3209",
    "mozilla": "https://www.mozilla.org/media/img/favicons/mozilla/favicon-196x196.e143075360ea.png",
    "ndtv": "https://www.ndtv.com/images/icons/ndtv.ico",
    "reuters": "https://www.reuters.com/pf/resources/images/reuters/favicon/tr_kinesis_v2.svg?d=287",
    "si": "https://images2.minutemediacdn.com/image/upload/v1713365891/shape/cover/sport/SI-f87ae31620c381274a85426b5c4f1341.ico",
    "telegraph": "https://www.telegraph.co.uk/etc.clientlibs/settings/wcm/designs/telegraph/core/clientlibs/core/resources/icons/favicon-196x196.png",
    "theverge": "https://www.theverge.com/static-assets/icons/android-chrome-512x512.png",
    "yahoo": "https://s.yimg.com/rz/l/favicon.ico",
    # --- Bot-protected domains (verified apple-touch-icon.png paths) ---
    "bloomberg": "https://www.bloomberg.com/apple-touch-icon.png",  # 180x180
    "britannica": "https://cdn.britannica.com/mendel-resources/3-124/images/shared/default3.png",  # 100x100
    "carvana": "https://www.carvana.com/apple-touch-icon.png",  # 57x57
    "dell": "https://www.dell.com/apple-touch-icon.png",  # 180x180
    "lego": "https://www.lego.com/apple-touch-icon.png",  # 180x180
    "patreon": "https://www.patreon.com/apple-touch-icon.png",  # 192x192
    "pixabay": "https://www.pixabay.com/apple-touch-icon.png",  # 180x180
    "rumble": "https://www.rumble.com/apple-touch-icon.png",  # 180x180
    # --- Domains where only small favicon.ico is found (verified larger icons) ---
    "bing": "https://www.bing.com/apple-touch-icon.png",  # 57x57
    "booking": "https://www.booking.com/apple-touch-icon.png",  # 180x180
    "ebay": "https://www.ebay.com/apple-touch-icon.png",  # 60x60
    "etsy": "https://www.etsy.com/apple-touch-icon.png",  # 57x57
    "google": "https://www.gstatic.com/images/branding/googleg/1x/googleg_standard_color_128dp.png",  # 128x128
    "imdb": "https://www.imdb.com/apple-touch-icon.png",  # 60x60
    "reddit": "https://www.reddit.com/apple-touch-icon.png",  # 57x57
    "twitch": "https://www.twitch.tv/apple-touch-icon.png",  # 180x180
}


def get_custom_favicon_url(domain: Any) -> str:
    """Get the custom favicon URL for a given domain without a suffix.

    Args:
        domain: The second-level domain name to look up (no suffix)

    Returns:
        The custom favicon URL if found, empty string otherwise
    """
    # Ensure domain is a string and handle edge cases
    if not isinstance(domain, str):
        return ""
    return CUSTOM_FAVICONS.get(domain, "")
