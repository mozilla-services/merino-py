from typing import Any

from merino import remotesettings
from merino.providers.base import BaseProvider

# The IAB category for online shopping. Suggestions with this value will be labelled as sponsored
# suggestions. Otherwise, they're nonsponsored.
IAB_CAT_SHOPPING: str = "22 - Shopping"

# Used whenever the `icon` field is missing from the suggestion payload.
MISSING_ICON_ID = "-1"


class Provider(BaseProvider):
    """
    Suggestion provider for adMarketplace through Remote Settings.
    """

    suggestions: dict[str, int] = {}
    results: list[dict[str, Any]] = []
    icons: dict[int, str] = {}

    def __init__(self) -> None:
        rs = remotesettings.Client()
        suggest_settings = rs.get("main", "quicksuggest")
        data_items = [i for i in suggest_settings if i["type"] == "data"]
        for item in data_items:
            res = rs.fetch_attachment(item["attachment"]["location"])
            for suggestion in res.json():
                id = len(self.results)
                for kw in suggestion.get("keywords"):
                    self.suggestions[kw] = id
                self.results.append(
                    {k: suggestion[k] for k in suggestion if k != "keywords"}
                )
        icon_items = [i for i in suggest_settings if i["type"] == "icon"]
        for icon in icon_items:
            id = int(icon["id"].replace("icon-", ""))
            self.icons[id] = rs.get_icon_url(icon["attachment"]["location"])

    def enabled_by_default(self) -> bool:
        return True

    def hidden(self) -> bool:
        return False

    async def query(self, q: str) -> list[dict[str, Any]]:
        if (id := self.suggestions.get(q)) is not None:
            if (res := self.results[id]) is not None:
                return [
                    {
                        "block_id": res.get("id"),
                        "full_keyword": q,
                        "title": res.get("title"),
                        "url": res.get("url"),
                        "impression_url": res.get("impression_url"),
                        "click_url": res.get("click_url"),
                        "provider": "adm",
                        "advertiser": res.get("advertiser"),
                        "is_sponsored": res.get("iab_category") == IAB_CAT_SHOPPING,
                        "icon": self.icons.get(
                            int(res.get("icon", MISSING_ICON_ID)), ""
                        ),
                        "score": 0.5,
                    }
                ]
        return []
