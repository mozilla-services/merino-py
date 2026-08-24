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
    "twitch": "https://www.twitch.tv/apple-touch-icon.png",  # 180x180
    # --- New Tab publishers flagged by editorial across markets (HNT-2760) ---
    # Publisher-hosted assets only. Domains whose second-level name is shared with a
    # separately branded publisher are deliberately omitted; see the PR for the list.
    # EN
    "aeon": "https://aeon.co/icon-512.png",  # 512x512
    "cbc": "https://site-cbc.radio-canada.ca/media/4616/imagesgem-menu-guide-line.png",  # 301x301
    "cntraveler": "https://www.cntraveler.com/apple-touch-icon.png",  # 180x180
    "cp24": "https://www.bellmedia.ca/lede/wp-content/uploads/2014/06/tv_cp24.png",  # 500x500
    "discovermagazine": "https://cdn.discovermagazine.com/immutable-assets/favicon/android-chrome-512x512.png",  # 512x512
    "epicurious": "https://www.epicurious.com/apple-touch-icon.png",  # 180x180
    "food52": "https://food52.com/food52/favicon.png",  # 180x180
    "gamespot": "https://www.gamespot.com/wp-content/uploads/2026/04/cropped-gamespot-favicon.png",  # 512x512
    "hollywoodreporter": "https://www.hollywoodreporter.com/wp-content/uploads/2026/05/thr-site-icon.png",  # 512x512
    "ipolitics": "https://www.ipolitics.ca/wp-content/uploads/2026/03/cropped-Screen-Shot-2026-03-03-at-4.54.56-PM-270x270.png",  # 270x270
    "macleans": "https://macleans.ca/android-chrome-512x512.png",  # 512x512
    "mit": "https://web.mit.edu/themes/mit/assets/favicon/favicon-512x512.png",  # 512x512
    "mother": "https://mother.ly/wp-content/themes/motherly/assets/img/favicon/apple-touch-icon.png",  # 180x180
    "nautil": "https://lede-admin.nautil.us/wp-content/uploads/sites/70/sites/3/nautilus/cropped-thicker_smaller_logo.png",  # 512x512
    "politico": "https://www.politico.com/android-chrome-512x512.png?v=2",  # 512x512
    "profootballnetwork": "https://statico.profootballnetwork.com/wp-content/uploads/2025/07/11135952/Favicon.png",  # 560x560
    "psyche": "https://psyche.co/icon-512.png",  # 512x512
    "rte": "https://www.rte.ie/img/logo-192.png",  # 192x192
    "simplyrecipes": "https://www.simplyrecipes.com/apple-touch-icon-180x180.png",  # 180x180
    "thecanadianpressnews": "https://www.thecanadianpress.com/app/themes/canadianpress/assets/favicon/android-icon-192x192.png",  # 192x192
    "todaysparent": "https://www.todaysparent.com/android-chrome-512x512.png",  # 512x512
    # FR
    "admagazine": "https://admagazine.fr/apple-touch-icon.png",  # 180x180
    "cotemaison": "https://cotemaison.fr/front/site/static/ctm/icon-512.png",  # 512x512
    "elle": "https://cdn-elle.ladmedia.fr/design/elle2/images/apple/favicon-192x192.png",  # 192x192
    "gqmagazine": "https://gqmagazine.fr/apple-touch-icon.png",  # 180x180
    "jeuxactu": "https://i.jeuxactus.com/images/site/ja_appletouch.png",  # 129x129
    "sciencesetavenir": "https://www.sciencesetavenir.fr/icons/apple-touch-icon-180x180.png",  # 180x180
    "sudouest": "https://sudouest.fr/so/android-icon-512x512.png",  # 512x512
    # DE
    "ad-magazin": "https://ad-magazin.de/apple-touch-icon.png",  # 180x180
    "futurezone": "https://futurezone.at/assets/favicon/apple-touch-icon-1024x1024.cef1c336bdc1a58c3763.png",  # 1024x1024
    "kicker": "https://kicker.de/content/img/favicon/appicon1000x1000.png",  # 1000x1000
    # IT
    "agi": "https://agi.it/favicons/android-icon-192x192.png",  # 192x192
    "fanpage": "https://d2kujwgapv5t1y.cloudfront.net/static/1531231231/images/fp-icon-192x192.png",  # 192x192
    "gqitalia": "https://gqitalia.it/apple-touch-icon.png",  # 180x180
    "ilmattino": "https://statics.cedscdn.it/utils/img/favicon/ilmattino/android-icon-192x192.png",  # 192x192
    "spaziogames": "https://cdn.spaziogames.it/assets/favicons/apple-touch-icon.png",  # 180x180
    "vanityfair": "https://vanityfair.it/apple-touch-icon.png",  # 180x180
    # ES
    "bonviveur": "https://bonviveur.com/apple-touch-icon.png",  # 302x302
    "clara": "https://clara.es/favicon.ico",  # 48x48
    "eleconomista": "https://eleconomista.es/favicon.ico",  # 256x256
    "gamereactor": "https://www.gamereactor.es/media/icons/touch_icon_ipad_retina.png",  # 144x144
    "generacionxbox": "https://generacionxbox.com/wp-content/uploads/2020/05/cropped-favicon-gx-2.png",  # 512x512
    "guiainfantil": "https://guiainfantil.com/android-chrome-512x512.png",  # 512x512
    "libertaddigital": "https://s.libertaddigital.com/images/icono-ld.png",  # 1024x1024
    "muyinteresante": "https://muyinteresante.okdiario.com/wp-content/uploads/sites/5/2024/09/cropped-muy-favicon.png?w=512",  # 512x512
    "traveler": "https://traveler.es/apple-touch-icon.png",  # 180x180
    "vogue": "https://vogue.es/apple-touch-icon.png",  # 180x180
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
