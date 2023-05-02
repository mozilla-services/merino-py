"""Static Mapping for the Addon data, along with the associated keywords
to do the query string matching.
"""
import enum


class SupportedAddon(enum.StrEnum):
    """Enum for the Supported Addons for the Addons Provider."""

    VIDEO_DOWNLOADER = "video-downloadhelper"
    LANGAUGE_TOOL = "languagetool"
    PRIVATE_RELAY = "private-relay"
    SEARCH_BY_IMAGE = "search_by_image"
    DARKREADER = "darkreader"
    PRIVACY_BADGER = "privacy-badger17"
    UBLOCK_ORIGIN = "ublock-origin"
    READ_ALOUD = "read-aloud"


# This object contains all the Product specified details to display to users.
# In particular, we want the name and description to be specified for Search and Suggest
# specific suggestions.
ADDON_DATA: dict[SupportedAddon, dict[str, str]] = {
    SupportedAddon.VIDEO_DOWNLOADER: {
        "name": "Video DownloadHelper",
        "description": (
            "Easily download videos from most popular video sites — "
            "YouTube, Facebook, Vimeo, Twitch, and more."
        ),
        "url": "https://addons.mozilla.org/en-US/firefox/addon/video-downloadhelper/",
    },
    SupportedAddon.LANGAUGE_TOOL: {
        "name": "LanguageTool",
        "description": (
            "Get grammar, spelling, and style help anywhere you write online — "
            "social media, email, docs, and more."
        ),
        "url": "https://addons.mozilla.org/en-US/firefox/addon/languagetool/",
    },
    SupportedAddon.PRIVATE_RELAY: {
        "name": "Firefox Relay",
        "description": (
            "Email masking to protect your inbox and identity "
            "from hackers and junk mail."
        ),
        "url": "https://addons.mozilla.org/en-US/firefox/addon/private-relay/",
    },
    SupportedAddon.SEARCH_BY_IMAGE: {
        "name": "Search by Image",
        "description": (
            "Search images easily with 30+ search engines. "
            "Find similar images, identify sources and more."
        ),
        "url": "https://addons.mozilla.org/en-US/firefox/addon/search_by_image/",
    },
    SupportedAddon.DARKREADER: {
        "name": "Dark Reader",
        "description": (
            "Get night mode for the entire internet. "
            "Adjust colors and reduce eye strain."
        ),
        "url": "https://addons.mozilla.org/en-US/firefox/addon/darkreader/",
    },
    SupportedAddon.PRIVACY_BADGER: {
        "name": "Privacy Badger",
        "description": (
            "Block invisible trackers and spying ads that follow you around the web. "
            "Protect your privacy online."
        ),
        "url": "https://addons.mozilla.org/en-US/firefox/addon/privacy-badger17/",
    },
    SupportedAddon.UBLOCK_ORIGIN: {
        "name": "uBlock Origin",
        "description": (
            "Block ads and enjoy a faster internet with "
            "this efficient content blocker."
        ),
        "url": "https://addons.mozilla.org/en-US/firefox/addon/ublock-origin/",
    },
    SupportedAddon.READ_ALOUD: {
        "name": "Read Aloud: A Text to Speech Reader",
        "description": (
            "Listen to web pages read aloud in 40+ languages "
            "with customizable reading speed. "
            "Supports PDF and EPUB."
        ),
        "url": "https://addons.mozilla.org/firefox/addon/read-aloud/",
    },
}

ADDON_KEYWORDS: dict[SupportedAddon, set[str]] = {
    SupportedAddon.VIDEO_DOWNLOADER: {
        "Video download",
        "Video DownloadHelper",
        "Download helper",
        "Downloader",
        "Video dl",
        "How to download",
        "Movie download",
        "Media download",
        "Clips",
        "Videos",
        "Entertainment",
        "Online movies",
        "Helper",
    },
    SupportedAddon.LANGAUGE_TOOL: {
        "Grammar",
        "Spell check",
        "Spelling",
        "Typo",
        "Edit",
        "Copy",
        "Syntax",
        "Autocorrect",
        "Language",
        "Misspelling",
        "LanguageTool",
        "Language Tool",
    },
    SupportedAddon.PRIVATE_RELAY: {
        "Temp mail",
        "Email Mask",
        "Masking",
        "Alias",
        "Spam",
        "Relay",
    },
    SupportedAddon.SEARCH_BY_IMAGE: {
        "Reverse image search",
        "Reverse search",
        "Pics search",
        "Image search",
        "Image history",
        "Visual search",
        "Alt search",
        "Image finder",
        "Image locator",
        "Image investigator",
        "Search by Image",
        "Tineye",
    },
    SupportedAddon.DARKREADER: {
        "Dark mode",
        "Dark theme",
        "Dark reader",
        "Night mode",
        "Shade mode",
        "Darker theme",
        "Purple mode",
        "Purple theme",
        "Eye strain",
    },
    SupportedAddon.PRIVACY_BADGER: {
        "Privacy",
        "Privacy Badger",
        "Anti Tracking",
        "Cybersecurity",
        "Tracking",
        "Trackers",
        "Spyware",
        "Malware",
        "Ad tracking",
        "Invisible trackers",
        "Security",
    },
    SupportedAddon.UBLOCK_ORIGIN: {
        "Adblock",
        "Ad block",
        "Ad blocker",
        "Ads",
        "Advertisement",
        "Content block",
        "How to block ads",
        "uBlock",
        "uBlock Origin",
    },
    SupportedAddon.READ_ALOUD: {
        "TTS",
        "Text to speech",
        "Reader",
        "Audio reader",
        "Speech reader",
        "Voice reader",
        "Accessibility reader",
        "Online reader",
        "Web reader",
        "Read aloud",
    },
}
