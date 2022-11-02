# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture


def test_version(client: TestClient) -> None:
    """Test that the version endpoint is supported to conform to dockerflow"""
    response = client.get("/__version__")

    assert response.status_code == 200
    result = response.json()
    assert "source" in result
    assert "version" in result
    assert "commit" in result
    assert "build" in result


def test_version_error(mocker: MockerFixture, client: TestClient) -> None:
    mocker.patch("os.path.exists", return_value=False)

    response = client.get("/__version__")

    assert response.status_code == 500
