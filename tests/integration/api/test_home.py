# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Integration tests for the Merino home API endpoint."""

from fastapi.testclient import TestClient

def test_home__redirects_to_docs(client: TestClient) -> None:
    """Test that the home endpoint redirects to the interactive documentation"""
    home_response = client.get("/")
    docs_response = client.get("/docs")

    assert home_response.status_code == 200
    assert home_response.content == docs_response.content
