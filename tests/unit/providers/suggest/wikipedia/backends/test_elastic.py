"""Unit tests for the Elastic Backend."""

import string
from unittest.mock import AsyncMock

import pytest
from elasticsearch import AsyncElasticsearch
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.suggest.wikipedia.backends.elastic import (
    SUGGEST_ID,
    ElasticBackend,
    get_best_keyword,
)


@pytest.fixture(name="es_backend")
def fixture_es_backend() -> ElasticBackend:
    """Return an ES backend instance."""
    return ElasticBackend(
        url="https://localhost:9200",
        api_key=settings.providers.wikipedia.es_api_key,
    )


def test_es_backend_initialize_with_url():
    """Test that backend initializes when we pass a URL."""
    backend = ElasticBackend(
        url="https://localhost:9200",
        api_key=settings.providers.wikipedia.es_api_key,
    )
    assert backend


@pytest.mark.asyncio
async def test_es_backend_search_success_en(
    mocker: MockerFixture, es_backend: ElasticBackend
) -> None:
    """Test the search method of the ES backend for english."""
    async_mock = AsyncMock(
        return_value={
            "suggest": {
                SUGGEST_ID: [
                    {
                        "options": [
                            {"_source": {"title": "Food"}},
                            {"_source": {"title": "Dog food"}},
                            {"_source": {"title": "Food for Thought"}},
                            {"_source": {"title": "Returned by ES but missing value"}},
                        ]
                    }
                ]
            }
        }
    )
    mocker.patch.object(AsyncElasticsearch, "search", side_effect=async_mock)

    suggestions = await es_backend.search("foO", "en")

    assert suggestions == [
        {
            "full_keyword": "food",
            "title": "Wikipedia - Food",
            "url": "https://en.wikipedia.org/wiki/Food",
        },
        {
            "full_keyword": "food",
            "title": "Wikipedia - Dog food",
            "url": "https://en.wikipedia.org/wiki/Dog_food",
        },
        {
            "full_keyword": "food",
            "title": "Wikipedia - Food for Thought",
            "url": "https://en.wikipedia.org/wiki/Food_for_Thought",
        },
        {
            "full_keyword": "returned by es but missing value",
            "title": "Wikipedia - Returned by ES but missing value",
            "url": "https://en.wikipedia.org/wiki/Returned_by_ES_but_missing_value",
        },
    ]


@pytest.mark.asyncio
async def test_es_backend_search_success_fr(mocker, es_backend: ElasticBackend) -> None:
    """Test the search method of the ES backend for French."""
    async_mock = AsyncMock(
        return_value={
            "suggest": {
                SUGGEST_ID: [
                    {
                        "options": [
                            {"_source": {"title": "Nourriture"}},
                            {"_source": {"title": "Nourriture pour chien"}},
                            {"_source": {"title": "Matière à réflexion"}},
                        ]
                    }
                ]
            }
        }
    )
    mocker.patch.object(AsyncElasticsearch, "search", side_effect=async_mock)

    suggestions = await es_backend.search("nou", "fr")

    assert suggestions == [
        {
            "full_keyword": "nourriture",
            "title": "Wikipédia - Nourriture",
            "url": "https://fr.wikipedia.org/wiki/Nourriture",
        },
        {
            "full_keyword": "nourriture",
            "title": "Wikipédia - Nourriture pour chien",
            "url": "https://fr.wikipedia.org/wiki/Nourriture_pour_chien",
        },
        {
            "full_keyword": "matière à réflexion",
            "title": "Wikipédia - Matière à réflexion",
            "url": "https://fr.wikipedia.org/wiki/Mati%C3%A8re_%C3%A0_r%C3%A9flexion",
        },
    ]


@pytest.mark.asyncio
async def test_es_backend_search_multiword_query_en(
    mocker: MockerFixture, es_backend: ElasticBackend
) -> None:
    """Test the search method of the ES backend with multiword query for english."""
    async_mock = AsyncMock(
        return_value={
            "suggest": {
                SUGGEST_ID: [
                    {
                        "options": [
                            {"_source": {"title": "Food for Thought"}},
                            {"_source": {"title": "Food Fortune"}},
                            {"_source": {"title": "No Food Forgiveness"}},
                        ]
                    }
                ]
            }
        }
    )
    mocker.patch.object(AsyncElasticsearch, "search", side_effect=async_mock)

    suggestions = await es_backend.search("food f", "en")

    assert suggestions == [
        {
            "full_keyword": "food for",
            "title": "Wikipedia - Food for Thought",
            "url": "https://en.wikipedia.org/wiki/Food_for_Thought",
        },
        {
            "full_keyword": "food fortune",
            "title": "Wikipedia - Food Fortune",
            "url": "https://en.wikipedia.org/wiki/Food_Fortune",
        },
        {
            "full_keyword": "food forgiveness",
            "title": "Wikipedia - No Food Forgiveness",
            "url": "https://en.wikipedia.org/wiki/No_Food_Forgiveness",
        },
    ]


@pytest.mark.asyncio
async def test_es_backend_search_multiword_query_de(
    mocker: MockerFixture, es_backend: ElasticBackend
) -> None:
    """Test the search method of the ES backend with multiword query for german."""
    async_mock = AsyncMock(
        return_value={
            "suggest": {
                SUGGEST_ID: [
                    {
                        "options": [
                            {"_source": {"title": "Berliner Flughafen"}},
                            {"_source": {"title": "Berliner Freiheit"}},
                            {"_source": {"title": "Nicht Berliner Fernsehen"}},
                        ]
                    }
                ]
            }
        }
    )
    mocker.patch.object(AsyncElasticsearch, "search", side_effect=async_mock)

    suggestions = await es_backend.search("berliner f", "de")

    assert suggestions == [
        {
            "full_keyword": "berliner flughafen",
            "title": "Wikipedia - Berliner Flughafen",
            "url": "https://de.wikipedia.org/wiki/Berliner_Flughafen",
        },
        {
            "full_keyword": "berliner freiheit",
            "title": "Wikipedia - Berliner Freiheit",
            "url": "https://de.wikipedia.org/wiki/Berliner_Freiheit",
        },
        {
            "full_keyword": "berliner fernsehen",
            "title": "Wikipedia - Nicht Berliner Fernsehen",
            "url": "https://de.wikipedia.org/wiki/Nicht_Berliner_Fernsehen",
        },
    ]


@pytest.mark.asyncio
async def test_es_backend_search_without_suggest(
    mocker: MockerFixture, es_backend: ElasticBackend
) -> None:
    """Test it can handle malformed responses (i.e. without the `suggest` field) from ES."""
    async_mock = AsyncMock(return_value={})
    mocker.patch.object(AsyncElasticsearch, "search", side_effect=async_mock)

    suggestions = await es_backend.search("foo", "en")

    assert suggestions == []


@pytest.mark.asyncio
async def test_es_backend_search_exception_en(
    mocker: MockerFixture,
    es_backend: ElasticBackend,
) -> None:
    """Test the exception handling in the search method of the ES backend for english."""
    mocker.patch.object(AsyncElasticsearch, "search", side_effect=Exception("404 error"))

    with pytest.raises(BackendError) as excinfo:
        await es_backend.search("foo", "en")

    assert str(excinfo.value) == "Failed to search from Elasticsearch for en: 404 error"


@pytest.mark.asyncio
async def test_es_backend_search_exception_it(
    mocker: MockerFixture,
    es_backend: ElasticBackend,
) -> None:
    """Test the exception handling in the search method of the ES backend for italian."""
    mocker.patch.object(AsyncElasticsearch, "search", side_effect=Exception("404 error"))

    with pytest.raises(BackendError) as excinfo:
        await es_backend.search("bis", "it")

    assert str(excinfo.value) == "Failed to search from Elasticsearch for it: 404 error"


@pytest.mark.asyncio
async def test_es_backend_shutdown(mocker: MockerFixture, es_backend: ElasticBackend) -> None:
    """Test the shutdown method of the ES backend."""
    spy = mocker.spy(AsyncElasticsearch, "close")

    await es_backend.shutdown()
    spy.assert_called_once()


def test_get_best_keyword_removes_trailing_punctuation() -> None:
    """Test that the get_best_keyword method removes any trailing punctuation for
    keywords.
    """
    keyword = get_best_keyword(q="mozi", title="Mozilla, Corporation")
    assert string.punctuation not in keyword


@pytest.mark.asyncio
async def test_es_backend_search_keyword_strip(
    mocker: MockerFixture, es_backend: ElasticBackend
) -> None:
    """Test that ensures the search keyword does not return dangling punctuation
    and that ascii encoding for punctuation remains in url with replaced underscores.
    """
    async_mock = AsyncMock(
        return_value={
            "suggest": {
                SUGGEST_ID: [
                    {
                        "options": [
                            {"_source": {"title": "Mozilla, Corporation"}},
                        ]
                    }
                ]
            }
        }
    )
    mocker.patch.object(AsyncElasticsearch, "search", side_effect=async_mock)

    suggestions = await es_backend.search("mozi", "en")

    assert suggestions == [
        {
            "full_keyword": "mozilla",
            "title": "Wikipedia - Mozilla, Corporation",
            "url": "https://en.wikipedia.org/wiki/Mozilla%2C_Corporation",
        },
    ]
