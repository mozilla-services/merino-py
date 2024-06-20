"""Tests the curated recommendation endpoint /api/v1/curated-recommendations"""

import freezegun
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.provider import CuratedRecommendation


@freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
def test_curated_recommendations_locale(client: TestClient) -> None:
    """Test if curated-recommendations endpoint returns result."""
    expected_recommendation = CuratedRecommendation(
        scheduledCorpusItemId="50f86ebe-3f25-41d8-bd84-53ead7bdc76e",
        url=HttpUrl("https://www.themarginalian.org/2024/05/28/passenger-pigeon/"),
        title="Thunder, Bells, and Silence: the Eclipse That Went Extinct",
        excerpt="What was it like for Martha, the endling of her species, to die alone at "
                "the Cincinnati Zoo that late-summer day in 1914, all the other "
                "passenger pigeons gone from the face of the Earth, having onc…",
        topic=Topic.EDUCATION,
        publisher="The Marginalian",
        imageUrl=HttpUrl(
            "https://www.themarginalian.org/wp-content/uploads/2024/05"
            "/PassengerPigeon_Audubon_TheMarginalian.jpg?fit=1200%2C630&ssl=1"
        ),
        receivedRank=0,
    )

    response = client.post("/api/v1/curated-recommendations", json={"locale": "en-US"})
    assert response.status_code == 200

    result = response.json()
    assert result["recommendedAt"] == 1326511294000  # 2012-01-14 03:21:34 UTC

    actual_recommendation: CuratedRecommendation = CuratedRecommendation(
        **result["data"][0]
    )

    assert actual_recommendation == expected_recommendation


def test_curated_recommendations_missing_locale(client: TestClient) -> None:
    """Test if curated-recommendations endpoint returns an error if locale is missing."""
    response = client.post("/api/v1/curated-recommendations", json={})
    assert response.status_code == 400
