"""AdM integration that uses the remote-settings provided data."""

import asyncio
import base64
import logging
import functools
import hashlib
import time
from enum import Enum, unique
from typing import Any, Final

import tldextract

from pydantic import HttpUrl
from tldextract.tldextract import ExtractResult

from merino.providers.suggest.adm.backends.remotesettings import FormFactor
from merino.utils import cron
from merino.jobs.utils.domain_category_mapping import DOMAIN_MAPPING
from merino.providers.suggest.adm.backends.protocol import AdmBackend, SuggestionContent
from merino.providers.suggest.base import BaseProvider, BaseSuggestion, Category, SuggestionRequest

logger = logging.getLogger(__name__)


@unique
class IABCategory(str, Enum):
    """Enum for IAB categories.

    Suggestions with the category `SHOPPING` will be labelled as
    sponsored suggestions. Otherwise, they're nonsponsored.
    """

    SHOPPING: Final = "22 - Shopping"
    EDUCATION: Final = "5 - Education"


# Used whenever the `icon` field is missing from the suggestion payload.
MISSING_ICON_ID: Final = "-1"
FORM_FACTORS_FALLBACK_MAPPING = {
    "other": FormFactor.DESKTOP.value,
    "tablet": FormFactor.PHONE.value,
    "desktop": FormFactor.DESKTOP.value,
    "phone": FormFactor.PHONE.value,
}


class SponsoredSuggestion(BaseSuggestion):
    """Model for sponsored suggestions."""

    block_id: int
    full_keyword: str
    advertiser: str
    impression_url: HttpUrl
    click_url: HttpUrl


class NonsponsoredSuggestion(BaseSuggestion):
    """Model for nonsponsored suggestions.

    Both `impression_url` and `click_url` are optional compared to
    sponsored suggestions.
    """

    block_id: int
    full_keyword: str
    advertiser: str
    impression_url: HttpUrl | None = None
    click_url: HttpUrl | None = None


class Provider(BaseProvider):
    """Suggestion provider for adMarketplace through Remote Settings."""

    suggestion_content: SuggestionContent
    # Store the value to avoid fetching it from settings every time as that'd
    # require a three-way dict lookup.
    score: float
    last_fetch_at: float
    cron_task: asyncio.Task
    backend: AdmBackend
    resync_interval_sec: float

    def __init__(
        self,
        backend: AdmBackend,
        score: float,
        name: str,
        resync_interval_sec: float,
        cron_interval_sec: float,
        enabled_by_default: bool = True,
        **kwargs: Any,
    ) -> None:
        """Store the given Remote Settings backend on the provider."""
        self.backend = backend
        self.score = score
        self.resync_interval_sec = resync_interval_sec
        self.cron_interval_sec = cron_interval_sec
        self.suggestion_content = SuggestionContent(
            suggestions={}, full_keywords=[], results=[], icons={}
        )
        self._name = name
        self._enabled_by_default = enabled_by_default
        super().__init__(**kwargs)

    async def initialize(self) -> None:
        """Initialize cron job."""
        try:
            await self._fetch()
        except Exception as e:
            logger.warning(
                "Failed to fetch data from Remote Settings, will retry it soon",
                extra={"error message": f"{e}"},
            )
            # Set the last fetch timestamp to 0 so that the cron job will retry
            # the fetch upon the next tick.
            self.last_fetch_at = 0

        # Run a cron job that resyncs data from Remote Settings in the background.
        cron_job = cron.Job(
            name="resync_rs_data",
            interval=self.cron_interval_sec,
            condition=self._should_fetch,
            task=self._fetch,
        )
        # Store the created task on the instance variable. Otherwise it will get
        # garbage collected because asyncio's runtime only holds a weak
        # reference to it.
        self.cron_task = asyncio.create_task(cron_job())

    def _should_fetch(self) -> bool:
        """Check if it should fetch data from Remote Settings."""
        return (time.time() - self.last_fetch_at) >= self.resync_interval_sec

    async def _fetch(self) -> None:
        """Fetch suggestions, keywords, and icons from Remote Settings."""
        self.suggestion_content = await self.backend.fetch()
        self.last_fetch_at = time.time()

    def hidden(self) -> bool:  # noqa: D102
        return False

    def normalize_query(self, query: str) -> str:
        """Convert a query string to lowercase and remove leading spaces."""
        return query.lstrip().lower()

    @staticmethod
    @functools.lru_cache(maxsize=100)
    def serp_categories(domain: str) -> list[Category]:
        """Query SERP categories for a given domain.

        Note that to leverage caching and be consistent with SERP Categories,
        passing in a domain instead of a URL. For example, for the URL
        "https://www.foo.com/bar", you should pass in "foo.com".

        This function is sped up via caching ("memoization"). The LRU cache
        size is determined by the fact that there are normally no more than
        100 unique domains for AMP suggestions.

        Params:
            `domain`: the domain of a URL.
        Returns a list of SERP categories if any or else an empty list.
        """
        hash = base64.b64encode(
            hashlib.md5(domain.encode(), usedforsecurity=False).digest()
        ).decode()
        return DOMAIN_MAPPING.get(hash, [])

    async def query(self, srequest: SuggestionRequest) -> list[BaseSuggestion]:
        """Provide suggestion for a given query."""
        q: str = srequest.query
        form_factor = srequest.user_agent.form_factor if srequest.user_agent else None
        country = srequest.geolocation.country
        if country and form_factor:
            segment = (FORM_FACTORS_FALLBACK_MAPPING.get(form_factor, FormFactor.DESKTOP.value),)
            if (
                suggest_look_ups := self.suggestion_content.suggestions.get(country, {})
                .get(q, {})
                .get(segment)
            ) is not None:
                results_id, fkw_id = suggest_look_ups
                res = self.suggestion_content.results[results_id]
                is_sponsored = res.get("iab_category") == IABCategory.SHOPPING

                url: str = res["url"]
                e: ExtractResult = tldextract.extract(url)
                categories: list[Category] = Provider.serp_categories(
                    domain=f"{e.domain}.{e.suffix}"
                )
                suggestion_dict: dict[str, Any] = {
                    "block_id": res.get("id"),
                    "full_keyword": self.suggestion_content.full_keywords[fkw_id],
                    "title": res.get("title"),
                    "url": url,
                    "categories": categories,
                    "impression_url": res.get("impression_url"),
                    "click_url": res.get("click_url"),
                    "provider": self.name,
                    "advertiser": res.get("advertiser"),
                    "is_sponsored": is_sponsored,
                    "icon": self.suggestion_content.icons.get(res.get("icon", MISSING_ICON_ID)),
                    "score": self.score,
                }
                return [
                    (
                        SponsoredSuggestion(**suggestion_dict)
                        if is_sponsored
                        else NonsponsoredSuggestion(**suggestion_dict)
                    )
                ]
        return []
