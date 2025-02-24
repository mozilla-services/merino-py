"""Integration tests for merino/curated_recommendations/corpus_backends/corpus_api_backend.py"""

from datetime import datetime

import pytest
from httpx import Response
from pydantic import HttpUrl

from merino.curated_recommendations.corpus_backends.corpus_api_backend import (
    CorpusApiBackend,
)
from merino.curated_recommendations.corpus_backends.protocol import (
    ScheduledSurfaceId,
    CorpusItem,
    Topic,
)


@pytest.mark.asyncio
async def test_fetch(corpus_backend: CorpusApiBackend, fixture_response_data):
    """Test if the fetch method returns data from cache if available."""
    surface_id = ScheduledSurfaceId.NEW_TAB_EN_US

    # Populate the cache by calling the fetch method
    results = await corpus_backend.fetch(surface_id)

    assert len(results) == 80
    assert results[0] == CorpusItem(
        url=HttpUrl(
            "https://getpocket.com/explore/item/milk-powder-is-the-key-to-better-cookies-"
            "brownies-and-cakes?utm_source=firefox-newtab-en-us"
        ),
        title="Milk Powder Is the Key to Better Cookies, Brownies, and Cakes",
        excerpt="Consider this pantry staple your secret ingredient for making more flavorful "
        "desserts.",
        topic=Topic.FOOD,
        publisher="Epicurious",
        isTimeSensitive=False,
        imageUrl=HttpUrl(
            "https://s3.us-east-1.amazonaws.com/pocket-curatedcorpusapi-prod-images/"
            "40e30ce2-a298-4b34-ab58-8f0f3910ee39.jpeg"
        ),
        scheduledCorpusItemId="de614b6b-6df6-470a-97f2-30344c56c1b3",
        corpusItemId="4095b364-02ff-402c-b58a-792a067fccf2",
        iconUrl=HttpUrl("https://example.com/icon.png"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_input,expected_title",
    [
        ({}, "Scheduled items from day 0"),  # Default value is 0
        ({"days_offset": 0}, "Scheduled items from day 0"),
        ({"days_offset": -1}, "Scheduled items from day -1"),
        ({"days_offset": -2}, "Scheduled items from day -2"),
        ({"days_offset": 1}, "Scheduled items from day 1"),
    ],
)
async def test_fetch_days_since_today(
    corpus_backend: CorpusApiBackend,
    fixture_request_data,
    corpus_http_client,
    test_input,
    expected_title,
):
    """Test fetch method with days_offset parameter."""
    surface_id = ScheduledSurfaceId.NEW_TAB_EN_US

    def mock_post_by_date(*args, **kwargs):
        """Mock scheduledSurface response containing a single item with the schedule date."""
        variables = kwargs["json"]["variables"]
        surface_timezone = corpus_backend.get_surface_timezone(variables["scheduledSurfaceId"])
        date_today = corpus_backend.get_scheduled_surface_date(surface_timezone).date()
        days_ago = (datetime.strptime(variables.get("date"), "%Y-%m-%d").date() - date_today).days
        return Response(
            status_code=200,
            json={
                "data": {
                    "scheduledSurface": {
                        "items": [
                            {
                                "id": "de614b6b-6df6-470a-97f2-30344c56c1b3",
                                "corpusItem": {
                                    "id": "f00ba411-6df6-470a-97f2-30344c56c1b3",
                                    "url": "https://example.com",
                                    "title": f"Scheduled items from day {days_ago}",
                                    "excerpt": "",
                                    "topic": "FOOD",
                                    "publisher": "Mozilla",
                                    "isTimeSensitive": True,
                                    "imageUrl": "https://example.com/image.jpg",
                                    "iconUrl": None
                                },
                            },
                        ]
                    }
                },
            },
            request=fixture_request_data,
        )

    corpus_http_client.post.side_effect = mock_post_by_date

    results = await corpus_backend.fetch(surface_id, **test_input)
    assert len(results) == 1
    assert results[0].title == expected_title
