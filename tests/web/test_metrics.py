import unittest.mock as mock

import aiodogstatsd
import pytest
from fastapi.testclient import TestClient

from merino.main import app
from merino.metrics import get_metrics_client
from merino.providers import get_providers
from merino.web import api_v1
from tests.web.util import get_providers as override_dependency

app.dependency_overrides[get_providers] = override_dependency
client = TestClient(app)
metrics_client = get_metrics_client()


@pytest.mark.parametrize(
    "url,metric_keys",
    [
        (
            "/api/v1/suggest?q=none",
            ["get.api.v1.suggest.timing", "get.api.v1.suggest.status_codes.200"],
        ),
        (
            "/api/v1/nonono",
            ["get.api.v1.nonono.timing", "get.api.v1.nonono.status_codes.404"],
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
def test_metrics_spy(url, metric_keys):

    with mock.patch.object(aiodogstatsd.Client, "_report") as reporter:
        client.get(url)
        for metric in metric_keys:
            reporter.assert_any_call(metric, mock.ANY, mock.ANY, mock.ANY, mock.ANY)


def test_metrics_side_effect(mocker):
    error_msg = "Error creating ProviderResponse model instance"
    metric_keys = [
        "get.api.v1.providers.timing",
        "get.api.v1.providers.status_codes.500",
    ]

    mocker.patch.object(
        api_v1, "ProviderResponse", side_effect=RuntimeError(error_msg), autospec=True
    )
    reporter = mocker.patch.object(aiodogstatsd.Client, "_report")

    with pytest.raises(RuntimeError) as excinfo:
        client.get("/api/v1/providers")

    for metric in metric_keys:
        reporter.assert_any_call(metric, mock.ANY, mock.ANY, mock.ANY, mock.ANY)

    assert str(excinfo.value) == error_msg
