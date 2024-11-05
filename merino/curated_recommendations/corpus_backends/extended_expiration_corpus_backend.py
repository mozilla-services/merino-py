"""Module to fetch corpus items from a range of days."""

import asyncio
from copy import copy

from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusBackend,
    CorpusItem,
    ScheduledSurfaceId,
)
from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend


class ExtendedExpirationCorpusBackend:
    """ExpiringCorpusBackend class that wraps around an existing CorpusBackend instance.
    It fetches items scheduled for today and highly engaging items from the last days.
    """

    def __init__(self, backend: CorpusBackend, engagement_backend: EngagementBackend):
        self.backend = backend
        self.engagement_backend = engagement_backend

    async def fetch(
        self,
        surface_id: ScheduledSurfaceId,
        window_start: int = -3,
    ) -> list[CorpusItem]:
        """Fetch corpus items for the specified `surface_id` from today and in the past.

        Args:
            surface_id: Identifies the scheduled surface, for example NEW_TAB_EN_US.
            window_start: Specifies how far back in days from today to fetch scheduled items.
                A negative value indicates days in the past. The default value of -3 means that
                items scheduled up to 3 days ago, from today up to now, will be included.

        Returns:
            list[CorpusItem]: A list of fetched corpus items from the backend, eligible to be shown.
        """
        tasks = [
            self.backend.fetch(surface_id, days_offset=offset)
            # Note: if window_start is -3, then range(window_start, 1) is [-3, -2, -1, 0].
            for offset in range(window_start, 1)
        ]
        results = await asyncio.gather(*tasks)

        # Separate today's items from past items
        eligible_items = copy(results[-1])  # Today's items are eligible. They're the last result.
        # Items from past days have eligibility requirements.
        for sublist in results[:-1]:
            for item in sublist:
                if self.is_past_item_eligible(item):
                    eligible_items.append(item)

        return eligible_items

    def is_past_item_eligible(self, item: CorpusItem) -> bool:
        """Check if an item scheduled for a past date is eligible to be shown.

        Args:
            item: The CorpusItem to check eligibility for.

        Returns:
            bool: True if the item is eligible, otherwise False.
        """
        if item.isTimeSensitive:
            # Past time-sensitive items are never eligible to be shown a second day.
            return False

        engagement = self.engagement_backend.get(item.scheduledCorpusItemId)
        if not engagement:
            # If a past item has no engagement then it's not eligible.
            return False

        impressions = engagement.impression_count
        clicks = engagement.click_count
        ctr = clicks / impressions
        treatment_population_size = (
            0.05  # TODO: Set to treatment population % once sizing is done.
        )
        # Past items are eligible if they meet an impression and CTR threshold over the last 24h.
        # Methodology and details for how the following values were derived is documented in
        # https://mozilla-hub.atlassian.net/browse/GENAI-244
        return impressions >= 360_000 * treatment_population_size and ctr > 0.0045
