from logging import LogRecord

import pytest
from fastapi.testclient import TestClient

from merino.main import app
from merino.metrics import configure_metrics, get_client
from merino.providers import get_providers
from tests.web.util import get_providers as override_dependency

app.dependency_overrides[get_providers] = override_dependency
client = TestClient(app)
metrics_client = get_client()


@pytest.mark.parametrize(
    "url,metric,expected_count",
    [
        ("/api/v1/suggest?q=none", "get.api.v1.suggest.timing", 1),
        ("/api/v1/suggest?q=none", "get.api.v1.suggest.status_codes.200", 1),
        ("/api/v1/no", "get.api.v1.no.timing", 1),
        ("/api/v1/no", "get.api.v1.no.status_codes.404", 1),
        ("/api/v1/suggest", "get.api.v1.suggest.timing", 1),
        ("/api/v1/suggest", "get.api.v1.suggest.status_codes.400", 1),
        ("/api/v1/providers", "get.api.v1.providers.timing", 1),
        # ("/api/v1/providers", "get.api.v1.providers.status_codes.500", 1),
    ],
)
@pytest.mark.asyncio
async def test_metrics(mocker, caplog, url, metric, expected_count):
    import logging

    caplog.set_level(logging.DEBUG)

    if "providers" in url:
        mock_endpoint = mocker.patch("merino.web.api_v1.providers")
        mock_endpoint.side_effect = KeyError("nope")

    await configure_metrics()
    client.get(url)
    await metrics_client.close()

    # assertions
    metrics = _parse_metrics(caplog.records)
    assert metric in metrics
    assert len(metrics[metric]) == expected_count


def _parse_metrics(records: list[LogRecord]) -> dict[str, list]:
    metrics = {}
    for rec in filter(lambda r: r.name == "merino.metrics", records):
        parts = rec.__dict__.get("data", "").split("|")
        key, value = parts[0].split(":")
        details = {"value": value, "type": parts[1], "tags": parts[2]}
        if key in metrics:
            metrics[key].append(details)
        else:
            metrics[key] = [details]
    return metrics
