"""Custom favicon URLs for domains that block scrapers or have unreliable favicon detection"""

# Mapping domain names without any suffix to their direct favicon URLs
CUSTOM_FAVICONS: dict[str, str] = {
    "axios": "https://static.axios.com/icons/favicon.svg",
    "ign": "https://kraken.ignimgs.com/favicon.ico",
    "infobae": "https://www.infobae.com/pf/resources/favicon/favicon-32x32.png?d=3209",
    "reuters": "https://www.reuters.com/pf/resources/images/reuters/favicon/tr_kinesis_v2.svg?d=287",
    "si": "https://images2.minutemediacdn.com/image/upload/v1713365891/shape/cover/sport/SI-f87ae31620c381274a85426b5c4f1341.ico",
    "yahoo": "https://s.yimg.com/rz/l/favicon.ico",
    "espn": "https://a.espncdn.com/favicon.ico",
    "telegraph": "https://www.telegraph.co.uk/etc.clientlibs/settings/wcm/designs/telegraph/core/clientlibs/core/resources/icons/favicon-196x196.png",
    "ndtv": "https://www.ndtv.com/images/icons/ndtv.ico",
}


def get_custom_favicon_url(domain: str) -> str:
    """Get the custom favicon URL for a given domain without a suffix.

    Args:
        domain: The second-level domain name to look up (no suffix)

    Returns:
        The custom favicon URL if found, empty string otherwise
    """
    return CUSTOM_FAVICONS.get(domain, "")
