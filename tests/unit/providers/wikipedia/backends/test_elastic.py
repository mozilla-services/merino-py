"""Unit tests for the Elastic Backend."""
from unittest.mock import AsyncMock

import pytest
from elasticsearch import AsyncElasticsearch
from pytest_mock import MockerFixture

from merino.config import settings
from merino.exceptions import BackendError
from merino.providers.wikipedia.backends.elastic import (
    SUGGEST_ID,
    ElasticBackend,
    ElasticBackendError,
)


@pytest.fixture(name="es_backend")
def fixture_es_backend() -> ElasticBackend:
    """Return an ES backend instance."""
    return ElasticBackend(
        cloud_id=settings.providers.wikipedia.es_cloud_id,
        api_key=settings.providers.wikipedia.es_api_key,
    )


def test_es_backend_initialize_with_url():
    """Test that backend initializes when we pass a URL."""
    backend = ElasticBackend(
        url="https://localhost:9200",
        api_key=settings.providers.wikipedia.es_api_key,
    )
    assert backend


def test_es_backend_initialize_error():
    """Test that the backend errors out when we initialize it without URL or cloud id."""
    with pytest.raises(ElasticBackendError) as eb_error:
        ElasticBackend(api_key=settings.providers.wikipedia.es_api_key)
    assert (
        "Require one of {url, cloud_id} to initialize Elasticsearch client."
        == eb_error.value.args[0]
    )


@pytest.mark.asyncio
async def test_es_backend_search_success(
    mocker: MockerFixture, es_backend: ElasticBackend
) -> None:
    """Test the search method of the ES backend."""
    async_mock = AsyncMock(
        return_value={
            "suggest": {
                SUGGEST_ID: [
                    {
                        "options": [
                            {"_source": {"title": "foo"}},
                            {"_source": {"title": "foo bar"}},
                        ]
                    }
                ]
            }
        }
    )
    mocker.patch.object(AsyncElasticsearch, "search", side_effect=async_mock)

    suggestions = await es_backend.search("foo")

    assert suggestions == [
        {
            "full_keyword": "foo",
            "title": "foo",
            "url": "https://en.wikipedia.org/wiki/foo",
        },
        {
            "full_keyword": "foo bar",
            "title": "foo bar",
            "url": "https://en.wikipedia.org/wiki/foo_bar",
        },
    ]


@pytest.mark.asyncio
async def test_es_backend_search_without_suggest(
    mocker: MockerFixture, es_backend: ElasticBackend
) -> None:
    """Test it can handle malformed responses (i.e. without the `suggest` field) from ES."""
    async_mock = AsyncMock(return_value={})
    mocker.patch.object(AsyncElasticsearch, "search", side_effect=async_mock)

    suggestions = await es_backend.search("foo")

    assert suggestions == []


@pytest.mark.asyncio
async def test_es_backend_search_exception(
    mocker: MockerFixture,
    es_backend: ElasticBackend,
) -> None:
    """Test the exception handling in the search method of the ES backend."""
    mocker.patch.object(
        AsyncElasticsearch, "search", side_effect=Exception("404 error")
    )

    with pytest.raises(BackendError) as excinfo:
        await es_backend.search("foo")

    assert str(excinfo.value) == "Failed to search from Elasticsearch: 404 error"


@pytest.mark.asyncio
async def test_es_backend_shutdown(
    mocker: MockerFixture, es_backend: ElasticBackend
) -> None:
    """Test the shutdown method of the ES backend."""
    spy = mocker.spy(AsyncElasticsearch, "close")

    await es_backend.shutdown()
    spy.assert_called_once()
