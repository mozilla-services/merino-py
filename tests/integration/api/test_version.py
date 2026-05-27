# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino __version__ API endpoint."""

import pathlib

from fastapi.testclient import TestClient
from pytest_mock import MockerFixture


def test_version(client: TestClient) -> None:
    """Test that the version endpoint conforms to dockerflow specifications."""
    response = client.get("/__version__")

    assert response.status_code == 200
    result = response.json()
    assert "source" in result
    assert "version" in result
    assert "commit" in result
    assert "build" in result


def test_version_error(mocker: MockerFixture, client: TestClient) -> None:
    """Test that the version endpoint returns a 500 status if an error occurs while
    evaluating the response.
    """
    mocker.patch.object(pathlib.Path, "read_text", side_effect=FileNotFoundError)

    response = client.get("/__version__")

    assert response.status_code == 500
    assert response.json() == {"detail": "Version file does not exist"}
