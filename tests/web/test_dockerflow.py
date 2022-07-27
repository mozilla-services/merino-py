import pytest
from fastapi.testclient import TestClient

from merino.main import app

client = TestClient(app)


def test_version():
    response = client.get("/__version__")
    assert response.status_code == 200

    result = response.json()
    assert "source" in result
    assert "version" in result
    assert "commit" in result
    assert "build" in result


def test_version_error(mocker):
    mocker.patch("os.path.exists", return_value=False)
    response = client.get("/__version__")
    assert response.status_code == 500


@pytest.mark.parametrize("endpoint", ["__heartbeat__", "__lbheartbeat__"])
def test_heartbeats(endpoint):
    response = client.get(f"/{endpoint}")
    assert response.status_code == 200
