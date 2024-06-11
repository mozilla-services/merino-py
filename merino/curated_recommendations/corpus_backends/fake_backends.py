"""Test backends"""
from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusBackend,
    CorpusItem,
    Topic,
)


class FakeCuratedCorpusBackend(CorpusBackend):
    """A fake backend that returns static content."""

    async def fetch(self) -> list[CorpusItem]:
        """Echoing the query as the single suggestion."""
        return [
            CorpusItem(
                scheduledCorpusItemId="50f86ebe-3f25-41d8-bd84-53ead7bdc76e",
                url="https://www.themarginalian.org/2024/05/28/passenger-pigeon/?utm_source=pocket-newtab-en-us",
                title="Thunder, Bells, and Silence: the Eclipse That Went Extinct",
                excerpt="What was it like for Martha, the endling of her species, to die alone at the Cincinnati Zoo that late-summer day in 1914, all the other passenger pigeons gone from the face of the Earth, having onc…",
                topic=Topic.EDUCATION,
                publisher="The Marginalian",
                imageUrl="https://www.themarginalian.org/wp-content/uploads/2024/05/PassengerPigeon_Audubon_TheMarginalian.jpg?fit=1200%2C630&ssl=1",
            )
        ]
