# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the shared dockerflow router."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from merino_common.routers import dockerflow
from merino_common.utils.version import Version


@pytest.fixture
def client() -> TestClient:
    """Build a TestClient over a minimal FastAPI app with only the dockerflow router."""
    app = FastAPI()
    app.include_router(dockerflow.router)
    test_client = TestClient(app)
    test_client.follow_redirects = False
    return test_client


def test_root_redirects_to_docs(client: TestClient) -> None:
    """GET / issues a redirect to the interactive docs."""
    resp = client.get("/")
    assert resp.status_code == 307
    assert resp.headers["location"] == "/docs"


def test_version_returns_payload(client: TestClient, mocker: MockerFixture) -> None:
    """GET /__version__ returns the parsed version.json payload."""
    version = Version(
        source="https://github.com/mozilla-services/merino-py",
        version="v1.2.3",
        commit="abcdef1234567890",
        build="42",
    )
    mocker.patch(
        "merino_common.routers.dockerflow.fetch_app_version_from_file",
        return_value=version,
    )

    resp = client.get("/__version__")

    assert resp.status_code == 200
    assert resp.json() == {
        "source": "https://github.com/mozilla-services/merino-py",
        "version": "v1.2.3",
        "commit": "abcdef1234567890",
        "build": "42",
    }


def test_version_missing_file_returns_500(client: TestClient, mocker: MockerFixture) -> None:
    """GET /__version__ surfaces a 500 when version.json is missing."""
    mocker.patch(
        "merino_common.routers.dockerflow.fetch_app_version_from_file",
        side_effect=FileNotFoundError,
    )

    resp = client.get("/__version__")

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Version file does not exist"}


@pytest.mark.parametrize(
    "path",
    ["/__heartbeat__", "/__lbheartbeat__"],
    ids=["heartbeat", "lbheartbeat"],
)
def test_heartbeat_endpoints_return_empty_200(client: TestClient, path: str) -> None:
    """Both heartbeat endpoints respond 200 with an empty body."""
    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.content == b""


def test_error_endpoint_returns_500_and_logs(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """GET /__error__ raises a 500 and logs the invocation."""
    with caplog.at_level(logging.ERROR, logger="merino_common.routers.dockerflow"):
        resp = client.get("/__error__")

    assert resp.status_code == 500
    records = [r for r in caplog.records if r.name == "merino_common.routers.dockerflow"]
    assert len(records) == 1
    assert records[0].message == "The __error__ endpoint was called"
    assert records[0].levelno == logging.ERROR
