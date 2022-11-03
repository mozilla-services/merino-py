# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from pytest_mock import MockerFixture
from starlette.testclient import TestClient

from merino.config import settings
from merino.exceptions import InvalidProviderError
from merino.main import app


def test_unknown_providers_should_shutdown_app(mocker: MockerFixture) -> None:
    """Test Merino should shut down upon an unknown provider."""

    mocker.patch.dict(settings.providers, values={"unknown-provider": {}})

    with pytest.raises(InvalidProviderError) as excinfo:
        # This will run all the FastAPI startup event handlers.
        with TestClient(app):
            # should never make to here
            assert False

    assert str(excinfo.value) == "Unknown provider type: unknown-provider"
