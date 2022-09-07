import unittest.mock as mock

import aiodogstatsd
import pytest
from fastapi.testclient import TestClient

from merino.main import app
from merino.providers import get_providers
from tests.web.util import CorruptProvider, get_provider_factory

client = TestClient(app)


@pytest.fixture()
def corrupt_provider():
    app.dependency_overrides[get_providers] = get_provider_factory(
        {
            "corrupt": CorruptProvider(),
        }
    )
    yield
    del app.dependency_overrides[get_providers]


@pytest.mark.parametrize(
    "url,metric_keys",
    [
        (
            "/api/v1/suggest?q=none",
            ["get.api.v1.suggest.timing", "get.api.v1.suggest.status_codes.200"],
        ),
        (
            "/api/v1/nonono",
            ["response.status_codes.404"],
        ),
        (
            "/api/v1/suggest",
            ["get.api.v1.suggest.timing", "get.api.v1.suggest.status_codes.400"],
        ),
        (
            "/__error__",
            ["get.__error__.timing", "get.__error__.status_codes.500"],
        ),
    ],
)
def test_metrics(url, metric_keys):

    with mock.patch.object(aiodogstatsd.Client, "_report") as reporter:
        client.get(url)
        for metric in metric_keys:
            reporter.assert_any_call(metric, mock.ANY, mock.ANY, mock.ANY, mock.ANY)


@pytest.mark.usefixtures("corrupt_provider")
def test_metrics_500(mocker):
    error_msg = "test"
    metric_keys = [
        "get.api.v1.suggest.timing",
        "get.api.v1.suggest.status_codes.500",
    ]

    reporter = mocker.patch.object(aiodogstatsd.Client, "_report")

    with pytest.raises(RuntimeError) as excinfo:
        client.get(f"/api/v1/suggest?q={error_msg}")

    for metric in metric_keys:
        reporter.assert_any_call(metric, mock.ANY, mock.ANY, mock.ANY, mock.ANY)

    assert str(excinfo.value) == error_msg
