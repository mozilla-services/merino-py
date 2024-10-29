"""Util module containing blocklists for Dynamic Wikipedia and Top Picks providers."""

WIKIPEDIA_TITLE_BLOCKLIST: set[str] = set()
TOP_PICKS_BLOCKLIST: set[str] = {
    "4channel",
    "draftkings",
    "furaffinity",
    "internalfb",
    "megapersonals",
    "myvidster",
    "rt",
    "sniffies",
    "thegatewaypundit",
    "urbandictionary",
    "winloot",
    "worldstarhiphop",
}

FAKESPOT_CSV_UPLOADER_BLOCKLIST: set[str] = set()
