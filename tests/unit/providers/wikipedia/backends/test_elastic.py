"""Unit tests for the Merino v1 suggest API endpoint for the Elastic Backend."""
from typing import Any
from unittest.mock import AsyncMock

import pytest
from elasticsearch import AsyncElasticsearch
from pytest_mock import MockerFixture

from merino.exceptions import BackendError
from merino.providers.wikipedia.backends.elastic import (
    SUGGEST_ID,
    ElasticBackend,
    ElasticBackendError,
)


@pytest.fixture(name="fake_elastic_cloud_id")
def fixture_fake_elastic_cloud_id() -> str:
    """Return a fake but valid elastic cloud id"""
    return (
        "cluster:dXMtZWFzdC0xLmF3cy5mb3VuZC5pbyQ0ZmE4ODIxZTc1NjM0MDMyYmVk"
        "MWNmMjIxMTBlMmY5NyQ0ZmE4ODIxZTc1NjM0MDMyYmVkMWNmMjIxMTBlMmY5Ng=="
    )


@pytest.fixture(name="es_backend")
def fixture_es_backend() -> ElasticBackend:
    """Return an ES backend instance."""
    return ElasticBackend(
        url="http://localhost:9200",
        cloud_id=None,
    )


def test_initialize_es_backend_cloud_id_success(
    mocker: MockerFixture, fake_elastic_cloud_id: str
):
    """Test that the ElasticBackend initializes successfully with a cloud_id."""
    es_client_spy: Any = mocker.spy(AsyncElasticsearch, "__init__")

    ElasticBackend(cloud_id=fake_elastic_cloud_id)

    es_client_spy.assert_called_once()

    assert es_client_spy.call_args.kwargs["cloud_id"] == fake_elastic_cloud_id


def test_initialize_es_backend_url_success(
    mocker: MockerFixture,
):
    """Test that the ElasticBackend initializes successfully with a URL."""
    fake_url: str = "http://localhost:9200"
    es_client_spy: Any = mocker.spy(AsyncElasticsearch, "__init__")

    ElasticBackend(url=fake_url)

    es_client_spy.assert_called_once()

    assert fake_url in es_client_spy.call_args[0]


def test_initialize_es_backend_error_without_url_and_cloud_id():
    """Test that the ElasticBackend returns an error for invalid initialization inputs."""
    with pytest.raises(ElasticBackendError):
        ElasticBackend()


def test_initialize_es_backend_error_with_url_and_cloud_id(
    fake_elastic_cloud_id: str,
):
    """Test that the ElasticBackend returns an error for invalid initialization inputs."""
    fake_url: str = "http://localhost:9200"
    with pytest.raises(ElasticBackendError):
        ElasticBackend(url=fake_url, cloud_id=fake_elastic_cloud_id)


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
