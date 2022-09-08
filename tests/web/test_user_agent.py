from fastapi.testclient import TestClient

from merino.main import app
from merino.providers import get_providers
from tests.web.util import filter_caplog
from tests.web.util import get_providers as override_dependency

client = TestClient(app)
app.dependency_overrides[get_providers] = override_dependency


def test_user_agent_middleware(mocker, caplog):
    import logging

    caplog.set_level(logging.INFO)

    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "127.0.0.1"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 11.2;"
            " rv:85.0) Gecko/20100101 Firefox/103.0"
        )
    }
    client.get("/api/v1/suggest?q=nope", headers=headers)

    records = filter_caplog(caplog.records, "web.suggest.request")

    assert len(records) == 1

    record = records[0]
    assert record.browser == "Firefox(103.0)"
    assert record.os_family == "macos"
    assert record.form_factor == "desktop"


def test_user_agent_middleware_with_missing_ua_str(mocker, caplog):
    import logging

    caplog.set_level(logging.INFO)

    mock_client = mocker.patch("fastapi.Request.client")
    mock_client.host = "127.0.0.1"

    headers = {}
    client.get("/api/v1/suggest?q=nope", headers=headers)

    records = filter_caplog(caplog.records, "web.suggest.request")

    assert len(records) == 1

    record = records[0]
    assert record.browser == "Other"
    assert record.os_family == "other"
    assert record.form_factor == "other"
