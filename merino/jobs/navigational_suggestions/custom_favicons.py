"""Custom favicon URLs for domains that block scrapers or have unreliable favicon detection"""

# Mapping of domain names to their direct favicon URLs
CUSTOM_FAVICONS: dict[str, str] = {
    "axios.com": "https://static.axios.com/icons/favicon.svg",
    "ign.com": "https://kraken.ignimgs.com/favicon.ico",
    "infobae.com": "https://www.infobae.com/pf/resources/favicon/favicon-32x32.png?d=3209",
    "reuters.com": "https://www.reuters.com/pf/resources/images/reuters/favicon/tr_kinesis_v2.svg?d=287",
    "si.com": "https://images2.minutemediacdn.com/image/upload/v1713365891/shape/cover/sport/SI-f87ae31620c381274a85426b5c4f1341.ico",
    "yahoo.com": "https://s.yimg.com/rz/l/favicon.ico",
    "espn.com": "https://a.espncdn.com/favicon.ico",
}


def get_custom_favicon_url(domain: str) -> str:
    """Get the custom favicon URL for a given domain.

    Args:
        domain: The domain name to look up

    Returns:
        The custom favicon URL if found, empty string otherwise
    """
    return CUSTOM_FAVICONS.get(domain, "")
